"""Curadoria assistida: analisar nunca altera memórias; excluir exige a lista revisada."""
from __future__ import annotations

import copy
import json
import os
import queue
import re
import threading
from datetime import datetime
from urllib.request import Request, urlopen

MODELOS = (
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemma-4-31b-it",
    "gemma-4-26b-a4b-it",
)
MODELO_GROQ = 'openai/gpt-oss-120b'
TIMEOUT = 30
TIMEOUT_INATIVIDADE = 240
TIMEOUT_TOTAL = 600
MAX_RESPOSTA = 4 * 1024 * 1024


class PrazoExcedido(TimeoutError):
    pass


class ModelosEsgotados(RuntimeError):
    pass


def _com_timeout(func, *args, **kwargs):
    # O prazo cobre conexão, cabeçalhos e eventos vazios até conteúdo real.
    resultado = queue.Queue()
    cancelado = threading.Event()
    iniciou = False
    def primeiro_token():
        nonlocal iniciou
        if cancelado.is_set():
            raise TimeoutError('Tentativa descartada')
        if not iniciou:
            iniciou = True
            resultado.put(('token', None))
    def executar():
        try:
            valor = func(*args, primeiro_token=primeiro_token, **kwargs)
            resultado.put(('ok', valor))
        except Exception as exc:
            resultado.put(('erro', exc))
    threading.Thread(target=executar, daemon=True, name='EsquecimentoTentativa').start()
    try:
        tipo, valor = resultado.get(timeout=TIMEOUT)
    except queue.Empty:
        cancelado.set()
        raise PrazoExcedido('30 segundos sem primeiro token') from None
    if tipo == 'token':
        try:
            tipo, valor = resultado.get(timeout=TIMEOUT_TOTAL)
        except queue.Empty:
            cancelado.set()
            raise PrazoExcedido('Prazo máximo da análise excedido') from None
    if tipo == 'erro':
        raise valor
    return valor


def _eventos_sse(response):
    linhas = []
    for raw in response:
        linha = raw.decode('utf-8').rstrip('\r\n')
        if linha.startswith('data:'):
            linhas.append(linha[5:].lstrip())
        elif not linha and linhas:
            if '\n'.join(linhas) == '[DONE]':
                return
            yield json.loads('\n'.join(linhas))
            linhas = []
    if linhas:
        if '\n'.join(linhas) == '[DONE]':
            return
        yield json.loads('\n'.join(linhas))


def _gerar(chave, modelo, prompt, nivel='high', primeiro_token=None, texto_delta=None):
    payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
               "generationConfig": {
                   "temperature": 0.1, "maxOutputTokens": 32768,
                   "thinkingConfig": {"thinkingLevel": nivel},
               }}
    if modelo.startswith('gemini-'):
        payload['generationConfig'].pop('temperature', None)
    request = Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:streamGenerateContent?alt=sse",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": chave}, method="POST")
    textos, finish = [], None
    with urlopen(request, timeout=TIMEOUT_INATIVIDADE) as response:
        for data in _eventos_sse(response):
            if data.get('promptFeedback', {}).get('blockReason'):
                raise ValueError('Resposta bloqueada')
            candidates = data.get('candidates') or []
            if not candidates:
                continue
            candidate = candidates[0]
            reason = candidate.get('finishReason')
            if reason:
                finish = reason
                if reason != 'STOP':
                    raise ValueError('Resposta incompleta ou bloqueada')
            for part in candidate.get('content', {}).get('parts', []):
                if part.get('text'):
                    if primeiro_token:
                        primeiro_token()
                    if not part.get('thought'):
                        textos.append(part['text'])
                        if texto_delta:
                            texto_delta(part['text'])
    if finish != 'STOP':
        raise ValueError('Resposta incompleta')
    return ''.join(textos)


def _gerar_groq(chave, modelo, prompt, nivel='high', primeiro_token=None, texto_delta=None):
    payload = {
        'model': modelo, 'messages': [{'role': 'user', 'content': prompt}],
        'stream': True, 'reasoning_effort': nivel,
        'max_completion_tokens': 32768, 'response_format': {'type': 'json_object'},
    }
    request = Request(
        'https://api.groq.com/openai/v1/chat/completions',
        data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {chave}'},
        method='POST')
    textos, finish = [], None
    with urlopen(request, timeout=TIMEOUT_INATIVIDADE) as response:
        for data in _eventos_sse(response):
            if data.get('error'):
                raise ValueError('Erro na resposta Groq')
            choices = data.get('choices') or []
            if not choices:
                continue
            delta = choices[0].get('delta') or {}
            texto = delta.get('content') or ''
            if (texto or delta.get('reasoning') or delta.get('reasoning_content')) and primeiro_token:
                primeiro_token()
            if texto:
                textos.append(texto)
                if texto_delta:
                    texto_delta(texto)
            reason = choices[0].get('finish_reason')
            if reason:
                finish = reason
                if reason != 'stop':
                    raise ValueError('Resposta incompleta')
    if finish != 'stop':
        raise ValueError('Resposta incompleta')
    return ''.join(textos)


def _gerar_glm(chave, modelo, prompt, nivel='high', primeiro_token=None, texto_delta=None):
    from zai_provider import ZaiClient, ZaiChatConfig, ZaiMessage, _attr, log_zai_usage
    client = ZaiClient(chave, timeout=TIMEOUT_INATIVIDADE)
    stream = None
    try:
        stream = client._stream(model=modelo, messages=[ZaiMessage.user(prompt)],
            config=ZaiChatConfig(thinking_level=nivel, request_timeout=TIMEOUT_INATIVIDADE,
                                 max_tokens=32768, response_format={'type': 'json_object'}))
        textos, finish, usage = [], None, None
        for chunk in stream:
            usage = _attr(chunk, 'usage', None) or usage
            choices = _attr(chunk, 'choices', []) or []
            if not choices:
                continue
            delta = _attr(choices[0], 'delta', None)
            texto = _attr(delta, 'content', '') or ''
            raciocinio = _attr(delta, 'reasoning_content', '') or ''
            if (texto or raciocinio) and primeiro_token:
                primeiro_token()
            if texto:
                textos.append(texto)
                if texto_delta:
                    texto_delta(texto)
            reason = _attr(choices[0], 'finish_reason', None)
            if reason:
                finish = reason
                if reason != 'stop':
                    raise ValueError('Resposta incompleta')
        if finish != 'stop':
            raise ValueError('Resposta incompleta')
        log_zai_usage(usage, modelo)
        return ''.join(textos)
    finally:
        try:
            if stream is not None:
                stream.close()
        finally:
            client.close()


def _validar(texto, memorias):
    texto = texto.strip()
    if texto.startswith("```") and texto.endswith("```"):
        texto = texto.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    dados = json.loads(texto)
    if not isinstance(dados, dict) or not isinstance(dados.get("avaliacoes"), list):
        raise ValueError("Formato inválido")
    itens, vistos = [], set()
    for item in dados["avaliacoes"]:
        if not isinstance(item, dict):
            raise ValueError("Sugestão inválida")
        chave, motivo = item.get("chave"), item.get("motivo")
        if not isinstance(chave, str) or chave not in memorias or chave in vistos:
            raise ValueError("Chave inválida ou repetida")
        if not isinstance(motivo, str) or not motivo.strip():
            raise ValueError("Motivo ausente")
        if item.get("decisao") not in ("manter", "esquecer"):
            raise ValueError("Decisão inválida")
        vistos.add(chave)
        if item["decisao"] == "esquecer":
            itens.append({"chave": chave, "motivo": motivo.strip(),
                          "registro": copy.deepcopy(memorias[chave])})
    if vistos != set(memorias):
        raise ValueError("Análise incompleta: faltam decisões para algumas memórias")
    return itens


class AvaliacoesStream:
    """Publica apenas objetos JSON completos e válidos da lista de avaliações."""
    def __init__(self, memorias, callback):
        self.memorias, self.callback = memorias, callback
        self.buffer = ''
        self.pos = None
        self.itens = []
        self.vistos = set()

    def feed(self, texto):
        if len(self.buffer) + len(texto) > MAX_RESPOSTA:
            raise ValueError('Resposta excedeu o limite de tamanho')
        self.buffer += texto
        if self.pos is None:
            match = re.match(r'\s*(?:```(?:json)?\s*)?\{\s*"avaliacoes"\s*:\s*\[', self.buffer)
            if not match:
                return
            self.pos = match.end()
        while True:
            while self.pos < len(self.buffer) and self.buffer[self.pos] in ' \r\n\t,':
                self.pos += 1
            if self.pos >= len(self.buffer) or self.buffer[self.pos] == ']':
                return
            try:
                item, end = json.JSONDecoder().raw_decode(self.buffer, self.pos)
            except json.JSONDecodeError:
                return
            chave = item.get('chave') if isinstance(item, dict) else None
            if not isinstance(chave, str) or chave not in self.memorias or chave in self.vistos:
                raise ValueError('Avaliação inválida ou duplicada')
            _validar(json.dumps({'avaliacoes': [item]}), {chave: self.memorias[chave]})
            self.vistos.add(chave)
            completo = dict(chave=chave, motivo=item['motivo'].strip(), decisao=item['decisao'],
                            registro=copy.deepcopy(self.memorias[chave]))
            self.itens.append(completo)
            self.pos = end
            if self.callback:
                self.callback('item', completo)


def analisar(api_key=None, progresso=None, gerar=None, banco=None, modelo_glm=None, avaliacao=None,
             raciocinio='auto'):
    if raciocinio not in ('auto', 'low'):
        raise ValueError('Escolha raciocínio automático ou baixo.')
    if banco is None:
        import ayla_cerebro as banco
    memorias = copy.deepcopy(banco.carregar_memoria())
    if not memorias:
        return {"itens": [], "analisadas": 0, "modelo": "—"}
    if modelo_glm and (not modelo_glm.startswith('glm-') or modelo_glm == 'glm-ocr'):
        raise ValueError('Escolha um modelo GLM de conversa.')
    if modelo_glm and not api_key:
        api_key = os.getenv('ZAI_API_KEY') or os.getenv('ZAI_API_KEY_1')
    if not api_key and not modelo_glm:
        try:
            settings = json.loads(banco.ARQUIVO_CONFIG_AYLA.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            settings = {}
        api_key = settings.get("gemini_api_key") or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    api_key = (api_key or '').strip()
    chave_groq = os.getenv('GROQ_API_KEY', '').strip() if not modelo_glm else ''
    if not api_key and not chave_groq:
        raise ValueError('Configure a chave Z.ai.' if modelo_glm else "Configure a chave Gemini ou GROQ_API_KEY no .env.")
    prompt = ""
    prompt += "\nAgora: " + datetime.now().astimezone().isoformat()
    prompt += "\nMemórias completas: " + json.dumps(memorias, ensure_ascii=False)
    erros = []
    if modelo_glm:
        tentativas = [(modelo_glm, 'low' if raciocinio == 'low' else 'high', api_key, _gerar_glm)]
    else:
        tentativas = []
        for nivel in (('low',) if raciocinio == 'low' else ('high', 'low')):
            if api_key:
                tentativas.extend((modelo, nivel, api_key, _gerar) for modelo in MODELOS)
            if chave_groq:
                tentativas.append((MODELO_GROQ, nivel, chave_groq, _gerar_groq))
    for modelo, nivel, chave, gerador in tentativas:
        parcial = AvaliacoesStream(memorias, avaliacao)
        if avaliacao:
            avaliacao('inicio', None)
        if progresso:
            progresso(f"Analisando {len(memorias)} memórias com {modelo} · raciocínio {'alto' if nivel == 'high' else 'fraco'} · até {TIMEOUT}s para o primeiro token…")
        try:
            texto = _com_timeout(gerar or gerador,
                                 chave, modelo, prompt, nivel=nivel,
                                 **({'texto_delta': parcial.feed} if avaliacao else {}))
            itens = _validar(texto, memorias)
            completas = AvaliacoesStream(memorias, None)
            completas.feed(texto)
            return {"itens": itens, "analisadas": len(memorias), "modelo": modelo, 'nivel': nivel, 'avaliacoes': completas.itens}
        except Exception as exc:
            # Não iniciar outra conexão enquanto a thread anterior ainda pode estar viva.
            if isinstance(exc, PrazoExcedido):
                raise ModelosEsgotados('Análise interrompida por tempo excedido.') from None
            # Nunca exibir exceções do transporte que possam conter credenciais ou dados.
            erros.append(f"{modelo} ({nivel}): {type(exc).__name__}")
    if avaliacao:
        avaliacao('inicio', None)
    erro = RuntimeError if modelo_glm else ModelosEsgotados
    raise erro("Nenhum modelo concluiu a análise. " + "; ".join(erros))


def apagar(itens, banco=None):
    if banco is None:
        import ayla_cerebro as banco
    removidas, ignoradas, falhas = [], [], []
    with banco._MEMORIA_LOCK:
        atuais = banco.carregar_memoria()
        for item in itens:
            chave = item["chave"]
            if chave not in atuais or atuais[chave] != item["registro"]:
                ignoradas.append(chave)
                continue
            try:
                resultado = banco.enviar_memoria_para_lixeira(chave, "Esquecimento natural: " + item["motivo"])
                if resultado.get("ok"):
                    removidas.append(chave)
                    atuais.pop(chave, None)
                else:
                    falhas.append(chave)
            except Exception:
                falhas.append(chave)
        try:
            banco._limpar_chaves_do_log_automatico(set(removidas))
        except Exception:
            falhas.append("limpeza do log automático")
    return {"removidas": removidas, "ignoradas": ignoradas, "falhas": falhas}
