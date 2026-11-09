from ayla_paths import BASE_DIR, ENV_PATH
import socket
from pathlib import Path

# Força resolução IPv4 prioritária global para evitar falhas de handshake SSL em rotas IPv6 inativas/instáveis
_orig_getaddrinfo = socket.getaddrinfo
def _forcar_ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if family in (0, socket.AF_UNSPEC, socket.AF_INET6):
        try:
            return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
        except Exception:
            pass
    return _orig_getaddrinfo(host, port, family, type, proto, flags)
socket.getaddrinfo = _forcar_ipv4_getaddrinfo

import os
import sys

# O protocolo de transferência fica isolado em "ayla host" (ou "ayla_host" no Linux/Oracle)
# para ser instalado sem alterações. Importá-lo não faz conexão alguma.
_AYLA_HOST_DIR = BASE_DIR / "ayla_host" if (BASE_DIR / "ayla_host").is_dir() else BASE_DIR / "ayla host"
if _AYLA_HOST_DIR.is_dir() and str(_AYLA_HOST_DIR) not in sys.path:
    sys.path.insert(0, str(_AYLA_HOST_DIR))
try:
    from ayla_handoff import HandoffError, host_client_from_environment
except ImportError:
    HandoffError = RuntimeError
    host_client_from_environment = None

if "Ayla" not in sys.modules:
    sys.modules["Ayla"] = sys.modules[__name__]
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
import time
import shutil
import subprocess
import webbrowser
import json
import asyncio
import discord
from discord import app_commands
from pathlib import Path
from datetime import datetime
from urllib.parse import quote_plus, quote
import requests
import random    
# import winsound
import re
import threading
import unicodedata
import warnings
warnings.filterwarnings("ignore", message="data discontinuity in recording")
warnings.filterwarnings("ignore", category=UserWarning)


# ══════════════════════════════════════════════════════════
#  CONFIGURAÇÃO VIA .ENV
# ══════════════════════════════════════════════════════════
try:
    from dotenv import load_dotenv
    load_dotenv(ENV_PATH)
except ImportError:
    pass


def _confirmar_retomada_local_do_host():
    """Confirma a devolução antes de parar a Ayla que está no host."""
    texto = (
        "A Ayla será iniciada neste computador.\n\n"
        "Para evitar duas Aylas respondendo ao mesmo tempo, o host será parado, "
        "e as memórias, histórico, modelos e configurações serão trazidos para cá.\n\n"
        "Deseja continuar?"
    )
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance()
        # A retomada é verificada antes de abrir a GUI. Criar e encerrar um
        # QApplication aqui deixa uma instância Qt já finalizada, fazendo o
        # próximo app.exec() retornar imediatamente. Só usamos caixa visual se
        # uma aplicação Qt saudável já existir.
        if app is not None:
            resposta = QMessageBox.question(
                None, "Trazer Ayla do host", texto,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            return resposta == QMessageBox.StandardButton.Yes
    except Exception:
        pass
    # Em uma inicialização por terminal, a confirmação continua obrigatória e
    # não interfere com o ciclo de vida futuro da interface gráfica.
    if sys.stdin and sys.stdin.isatty():
        try:
            return input("Trazer a Ayla do host para este computador? [s/N] ").strip().lower() in {"s", "sim", "y", "yes"}
        except (EOFError, KeyboardInterrupt):
            return False
    print("⚠️ Não foi possível pedir a confirmação para trazer a Ayla do host.")
    return False


def _preparar_retomada_local_do_host():
    """Executa antes de ler modelos/chaves e antes de iniciar Discord localmente."""
    if os.getenv("AYLA_HOST_ROLE", "").strip().lower() == "host":
        return
    if host_client_from_environment is None:
        return
    try:
        client = host_client_from_environment(code_dir=_AYLA_HOST_DIR)
    except HandoffError as erro:
        print(f"⚠️ Transferência do host não configurada corretamente: {erro}")
        return
    if client is None:
        return
    try:
        client.ensure_tunnel()
        status_host = client._request("GET", "/v1/status")
        # Checa se o serviço no host está ativo OU se o host é o dono atual
        host_ativo = bool(status_host.get("service_active")) or (status_host.get("owner") == "host")
        if not host_ativo and not status_host.get("transition"):
            # O host está comprovadamente desligado e não há transição pendente
            return
    except HandoffError as erro:
        print(f"ℹ️ Status do host indisponível ({erro}). Prosseguindo localmente.")
        return
    except Exception as erro:
        print(f"ℹ️ Host offline ou inacessível ({erro}). Prosseguindo localmente.")
        return

    # O host está ativo! Avisa o host para parar e traz os dados atualizados
    print("🩵 Ayla detectada ativa no servidor host! Solicitando parada e sincronizando histórico/memórias...")
    try:
        client.claim_local(BASE_DIR)
        hist_path = BASE_DIR / "ayla_interaction_history.jsonl"
        sessao_path = BASE_DIR / "ayla_ultima_sessao.json"
        total_interacoes = 0
        ultima_interacao = "Nenhuma"
        if hist_path.exists():
            try:
                with open(hist_path, "r", encoding="utf-8") as f:
                    linhas = f.readlines()
                    total_interacoes = len(linhas)
                    if linhas:
                        ult = json.loads(linhas[-1])
                        ultima_interacao = ult.get("timestamp", "")
            except Exception:
                pass
        print(f"📜 Histórico de conversas recuperado: {total_interacoes} interações no histórico (última em {ultima_interacao}).")
        conversa_path = BASE_DIR / "ayla_conversa_ativa.json"
        if conversa_path.exists():
            try:
                conv_data = json.loads(conversa_path.read_text(encoding="utf-8"))
                turnos = sum(len(s.get("turns", {})) for s in conv_data.values())
                print(f"💬 Conversa ativa do host recuperada: {turnos} turnos recentes prontos no chat!")
            except Exception:
                pass
        if sessao_path.exists():
            try:
                sess_info = json.loads(sessao_path.read_text(encoding="utf-8"))
                print(f"🧠 Resumo da sessão do host carregado (encerrada em {sess_info.get('encerrada_em', '')}).")
            except Exception:
                pass
        print("🩵 Histórico e memórias recuperados do host com sucesso! Iniciando a Ayla local.")
    except HandoffError as erro:
        print(f"⚠️ A Ayla do host parece travada ou não encerrou a tempo: {erro}")
        print("🩵 Forçando encerramento da Ayla no servidor para liberar o início local...")
        try:
            client.force_stop_host()
            time.sleep(1.0)
            client.claim_local(BASE_DIR)
            print("🩵 Encerramento forçado concluído e dados recuperados com sucesso!")
        except Exception as falha_critica:
            print(f"⚠️ Não foi possível recuperar dados completos do host ({falha_critica}).")
            print("ℹ️ Prosseguindo com a inicialização local usando dados em disco para não travar o app.")


if __name__ == "__main__":
    _preparar_retomada_local_do_host()

ZAI_API_KEYS = [os.getenv(f"ZAI_API_KEY_{i}", "") for i in range(1, 7)]
ZAI_API_KEYS.append(os.getenv("ZAI_API_KEY", ""))
ZAI_API_KEYS = list(dict.fromkeys([k.strip() for k in ZAI_API_KEYS if k.strip()]))

DISCORD_TOKEN         = os.getenv("DISCORD_TOKEN", "")
DISCORD_OWNER_ID      = int(os.getenv("DISCORD_OWNER_ID", "0"))

from gemini_catalog import gemini_key
from groq_catalog import groq_key, is_groq
from deepseek_catalog import deepseek_key, is_deepseek
try:
    _provider_settings = json.loads((BASE_DIR / 'ayla_settings.json').read_text(encoding='utf-8'))
except (OSError, ValueError):
    _provider_settings = {}
if (not ZAI_API_KEYS and not gemini_key(_provider_settings) and not groq_key(_provider_settings) and not deepseek_key(_provider_settings)) or not DISCORD_TOKEN or DISCORD_OWNER_ID == 0:
    print("⚠️ ERRO FATAL: Configure ZAI_API_KEY, GEMINI_API_KEY, GROQ_API_KEY ou DEEPSEEK_API_KEY, DISCORD_TOKEN e DISCORD_OWNER_ID!")
    sys.exit(1)

# ══════════════════════════════════════════════════════════
#  SISTEMA DE MEMÓRIA PERSISTENTE
# ══════════════════════════════════════════════════════════
BASE_DIR = Path(__file__).resolve().parent
ARQUIVO_MEMORIA = BASE_DIR / "Ayla_Memoria.json"
ARQUIVO_MEMORIA_LIXEIRA = BASE_DIR / "Ayla_Memoria_lixeira.json"
ARQUIVO_MEMORIA_HISTORICO = BASE_DIR / "Ayla_Memoria_historico.jsonl"
ARQUIVO_STOPWORDS_MEMORIA = BASE_DIR / "ayla_stopwords.json"
ARQUIVO_MIDIAS_AYLA = BASE_DIR / "ayla_media.json"
ARQUIVO_CONFIG_AYLA = BASE_DIR / "ayla_settings.json"
ARQUIVO_HISTORICO_INTERACOES = BASE_DIR / "ayla_interaction_history.jsonl"


MAX_ANEXOS_POR_REQUISICAO = 10
MAX_BYTES_POR_ANEXO = 25 * 1024 * 1024
MAX_BYTES_ANEXOS_TOTAL = 50 * 1024 * 1024
MAX_TOKENS_HISTORICO_CHAT = 8_000
MAX_CARACTERES_HISTORICO_CHAT = MAX_TOKENS_HISTORICO_CHAT * 4  # 32.000 caracteres (~8.000 tokens)
MAX_RESULTADO_FERRAMENTA_CARACTERES = 8_000
TIMEOUT_API_ZAI_SECS = 45.0
_CONFIG_LOCK = threading.RLock()
_HISTORICO_LOCK = threading.RLock()

def classificar_erro_zai(erro: Exception) -> dict:
    erro_msg = str(erro)
    code = getattr(erro, "code", None) or getattr(erro, "status_code", None)
    if not isinstance(code, int):
        code = None

    has_code = lambda c: (code == c) or bool(re.search(rf"\b{c}\b", erro_msg))

    is_quota = bool(getattr(erro, "is_quota", False)) or has_code(429) or "rate limit" in erro_msg.lower() or "quota" in erro_msg.lower()
    is_interno = (code is not None and 500 <= code <= 599) or has_code(500) or "INTERNAL" in erro_msg
    is_indisponivel = has_code(502) or has_code(503) or has_code(504) or "UNAVAILABLE" in erro_msg
    is_403 = has_code(403) or "PERMISSION_DENIED" in erro_msg
    is_auth = has_code(401) or is_403 or "authentication" in erro_msg.lower() or "unauthorized" in erro_msg.lower()
    is_bad_request = has_code(400) or "bad request" in erro_msg.lower()
    is_modality = has_code(400) and ("modality" in erro_msg.lower() or "not supported" in erro_msg.lower())
    is_suspended = "suspended" in erro_msg.lower()

    is_handshake_or_connect = any(phrase in erro_msg.lower() for phrase in [
        "handshake",
        "connecttimeout",
        "connecterror",
        "10060",
        "10061",
        "10054",
        "10053",
        "socket",
        "reset by peer",
        "anulada pelo software",
    ])

    is_timeout = (not is_handshake_or_connect) and any(phrase in erro_msg.lower() for phrase in [
        "readtimeout",
        "pooltimeout",
        "timed out",
        "timeout",
    ]) and not (is_quota or is_interno or is_indisponivel or is_403 or is_suspended)

    is_conexao = (not (is_quota or is_interno or is_indisponivel or is_403 or is_suspended)) and (
        is_handshake_or_connect or isinstance(erro, (ConnectionError, OSError)) or any(phrase in erro_msg.lower() for phrase in [
            "readerror",
            "connection refused",
            "connection reset",
            "remotely closed",
            "broken pipe",
        ])
    )

    return {
        "is_quota": is_quota,
        "is_interno": is_interno,
        "is_indisponivel": is_indisponivel,
        "is_403": is_403,
        "is_auth": is_auth,
        "is_bad_request": is_bad_request,
        "is_modality": is_modality,
        "is_suspended": is_suspended,
        "is_conexao": is_conexao,
        "is_timeout": is_timeout,
    }


# ══════════════════════════════════════════════════════════
#  SISTEMA DE MEMÓRIA PERSISTENTE E RAG (CENTRALIZADO NO AYLA_CEREBRO)
# ══════════════════════════════════════════════════════════
try:
    import ayla_cerebro
    from ayla_cerebro import (
        ARQUIVO_MEMORIA,
        ARQUIVO_MEMORIA_LIXEIRA,
        ARQUIVO_MEMORIA_HISTORICO,
        ARQUIVO_STOPWORDS_MEMORIA,
        ARQUIVO_CONFIG_AYLA,
        ARQUIVO_MEMORIAS_LOG,
        _MEMORIA_LOCK,
        _MEMORIA_SCHEMA_VERSION,
        _MEMORIA_TIPOS_VALIDOS,
        _CONFIG_LOCK,
        _backup_path,
        _json_valido,
        _escrever_texto_atomico,
        _escrever_json_atomico,
        _carregar_json_com_backup,
        _agora_memoria_iso,
        _texto_memoria_normalizado,
        normalizar_chave_memoria,
        _parse_data_memoria,
        _formatar_data_memoria,
        _tipo_memoria_inferido,
        _normalizar_escopo_memoria,
        _normalizar_importancia_memoria,
        normalizar_registro_memoria,
        _normalizar_banco_memoria,
        memoria_expirada,
        carregar_memoria,
        salvar_memoria,
        registrar_acessos_memoria,
        _registrar_historico_memoria,
        _carregar_lixeira_memoria,
        _salvar_lixeira_memoria,
        carregar_palavras_ignoradas_memoria,
        salvar_palavras_ignoradas_memoria,
        _tokens_memoria,
        _extrair_features_vetoriais,
        _similaridade_cosseno_vetores,
        _similaridade_multi_chunk,
        buscar_memorias_estruturadas,
        formatar_memorias_encontradas,
        montar_contexto_memoria_relevante,
        criar_ou_atualizar_memoria,
        arquivar_memoria_estruturada,
        enviar_memoria_para_lixeira,
        listar_lixeira_memoria,
        restaurar_memoria_estruturada,
        revisar_memorias_estruturadas,
        configuracoes_padrao_ayla,
        carregar_configuracoes_ayla,
        salvar_configuracoes_ayla,
        executar_revisao_automatica_memoria_se_necessario,
    )
    print("🧠 [Ayla Cérebro]: Subsistema RAG Híbrido e Memória Persistente carregados com sucesso!")
except Exception as e_cerebro_imp:
    ayla_cerebro = None
    print(f"\n❌ [ERRO AYLA CÉREBRO]: Não foi possível carregar o módulo 'ayla_cerebro.py'!\n   ➡️ Detalhe do Erro: {e_cerebro_imp}\n   ⚠️ O bot funcionará normalmente, mas a memorização automática e RAG estarão indisponíveis.\n")


try:
    from zai_provider import (
        ZaiAttachment,
        ZaiChatConfig,
        ZaiClient,
        ZaiMessage,
        ZaiResponse,
        ZaiIncompleteResponseError,
        ZaiToolResult,
    )
except ImportError:
    print("ERRO: provedor Z.ai não disponível! Instale as dependências de requirements.txt")
    sys.exit(1)

# Configuração nativa de geração da Z.ai
generation_config = {
    'max_tokens': 65536,
    'top_p': 0.95,
    'thinking_level': 'low',
}

def sanear_historico(historico):
    """Mantém apenas mensagens válidas no formato nativo da Z.ai/OpenAI."""
    if not historico:
        return []
    resultado = []
    chamadas_pendentes = set()
    inicio_bloco_ferramentas = None
    descartadas = 0

    def descartar_bloco_incompleto():
        nonlocal descartadas, inicio_bloco_ferramentas
        if inicio_bloco_ferramentas is not None:
            descartadas += len(resultado) - inicio_bloco_ferramentas
            del resultado[inicio_bloco_ferramentas:]
        chamadas_pendentes.clear()
        inicio_bloco_ferramentas = None

    for message in historico:
        role = getattr(message, "role", None)
        if role not in ("system", "user", "assistant", "tool"):
            descartadas += 1
            continue

        if chamadas_pendentes:
            if role != "tool":
                descartar_bloco_incompleto()
            else:
                call_id = getattr(message, "tool_call_id", None)
                if not call_id or call_id not in chamadas_pendentes:
                    descartadas += 1
                    continue
                resultado.append(message)
                chamadas_pendentes.discard(call_id)
                if not chamadas_pendentes:
                    inicio_bloco_ferramentas = None
                continue

        if role == "tool":
            descartadas += 1
            continue

        if not (getattr(message, "text", "") or getattr(message, "attachments", None)
                or getattr(message, "tool_calls", None) or role == "tool"):
            descartadas += 1
            continue

        resultado.append(message)
        if role == "assistant":
            chamadas = getattr(message, "tool_calls", None) or []
            ids = [call.id for call in chamadas if getattr(call, "id", None)]
            if len(ids) != len(chamadas) or len(set(ids)) != len(ids):
                resultado.pop()
                descartadas += 1
                continue
            if ids:
                chamadas_pendentes.update(ids)
                inicio_bloco_ferramentas = len(resultado) - 1

    if chamadas_pendentes:
        descartar_bloco_incompleto()

    while resultado and resultado[0].role not in ("system", "user"):
        resultado.pop(0)
        descartadas += 1
    if descartadas:
        print(f"🧹 sanear_historico: {descartadas} mensagem(ns) inválida(s) descartada(s).")
    return resultado

_MIDIAS_LOCK = threading.RLock()
_MIDIAS_CACHE = None
_MIDIAS_CACHE_TIME = 0.0
_MIDIAS_CACHE_TTL = 30.0  # segundos

def carregar_midias_ayla() -> dict:
    global _MIDIAS_CACHE, _MIDIAS_CACHE_TIME
    with _MIDIAS_LOCK:
        now = time.time()
        if _MIDIAS_CACHE is not None and (now - _MIDIAS_CACHE_TIME) < _MIDIAS_CACHE_TTL:
            return _MIDIAS_CACHE
        padrao = {"emojis": {}, "gifs_e_fotos": {}}
        if not ARQUIVO_MIDIAS_AYLA.exists() and not _backup_path(ARQUIVO_MIDIAS_AYLA).exists():
            return padrao
        try:
            dados, origem, erros = _carregar_json_com_backup(ARQUIVO_MIDIAS_AYLA, padrao)
            if isinstance(dados, dict):
                if "emojis" not in dados or not isinstance(dados["emojis"], dict):
                    dados["emojis"] = {}
                if "gifs_e_fotos" not in dados or not isinstance(dados["gifs_e_fotos"], dict):
                    dados["gifs_e_fotos"] = {}
                _MIDIAS_CACHE = dados
                _MIDIAS_CACHE_TIME = now
                return dados
            return padrao
        except Exception as e:
            print(f"⚠️ Erro ao carregar ayla_media.json: {e}")
            return padrao

def salvar_midias_ayla(dados: dict):
    global _MIDIAS_CACHE, _MIDIAS_CACHE_TIME
    with _MIDIAS_LOCK:
        _escrever_json_atomico(ARQUIVO_MIDIAS_AYLA, dados)
        _MIDIAS_CACHE = None
        _MIDIAS_CACHE_TIME = 0.0

_TAGS_NORM_CACHE = None
_TAGS_NORM_SOURCE_ID = None  # id() do dict de mídias que gerou o cache

def processar_tags_midia_ayla(texto: str, converter_emojis: bool = True) -> str:
    global _TAGS_NORM_CACHE, _TAGS_NORM_SOURCE_ID
    if not texto or not isinstance(texto, str):
        return texto
    midias = carregar_midias_ayla()
    emojis = midias.get("emojis", {})
    gifs = midias.get("gifs_e_fotos", {})

    def _norm_midia(s: str) -> str:
        s_norm = unicodedata.normalize('NFD', s).encode('ascii', 'ignore').decode('utf-8').lower()
        return re.sub(r'[^a-z0-9]', '', s_norm)

    # Só reconstrói os dicts normalizados se a fonte de mídias mudou
    midias_id = id(midias)
    if _TAGS_NORM_CACHE is None or _TAGS_NORM_SOURCE_ID != midias_id:
        emojis_norm = {_norm_midia(k): (k, v) for k, v in emojis.items()}
        gifs_norm = {_norm_midia(k): (k, v) for k, v in gifs.items()}
        unificado_norm = {}
        for k_norm, (k_orig, val) in emojis_norm.items():
            unificado_norm[k_norm] = ("emoji", val)
        for k_norm, (k_orig, val) in gifs_norm.items():
            unificado_norm[k_norm] = ("gif", val)
        _TAGS_NORM_CACHE = (emojis_norm, gifs_norm, unificado_norm)
        _TAGS_NORM_SOURCE_ID = midias_id
    else:
        emojis_norm, gifs_norm, unificado_norm = _TAGS_NORM_CACHE

    def buscar_midia(nome_raw: str):
        nome_clean = _norm_midia(nome_raw)
        if not nome_clean:
            return None

        # 1. Busca no dicionário unificado de emojis, GIFs e fotos
        if nome_clean in unificado_norm:
            return unificado_norm[nome_clean]

        # 2. Variação com/sem 'ayla'
        if nome_clean.startswith("ayla") and nome_clean[4:] in unificado_norm:
            return unificado_norm[nome_clean[4:]]
        if f"ayla{nome_clean}" in unificado_norm:
            return unificado_norm[f"ayla{nome_clean}"]

        # 3. Busca por substring parcial
        for k_norm, (cat, val) in unificado_norm.items():
            if len(nome_clean) >= 3 and (k_norm in nome_clean or nome_clean in k_norm):
                return cat, val

        # 4. CORRETOR INTELIGENTE (Fuzzy Match / difflib): Encontra o nome mais parecido!
        if len(nome_raw) <= 50:
            import difflib
            todas_chaves = list(unificado_norm.keys())
            matches = difflib.get_close_matches(nome_clean, todas_chaves, n=1, cutoff=0.4)
            if matches:
                chave_mais_proxima = matches[0]
                cat, val = unificado_norm[chave_mais_proxima]
                print(f"🪄 [Corretor de Tags] Auto-corrigido '{nome_raw}' -> '{chave_mais_proxima}' ({val})")
                return cat, val

        return None

    def repl_midia(match):
        resultado = buscar_midia(match.group(1).strip())
        if resultado:
            categoria, midia = resultado
            if categoria == "emoji" and not converter_emojis:
                return match.group(0)
            return midia
        return match.group(0)

    # Suporta %Nome% (e fallback %Nome& / &Nome&). Ignora % precedido de números (ex: 100%, 50%)
    texto_proc = re.sub(r'(?<!\d)[%&]([^%&\n]+)[%&]', repl_midia, texto)
    return texto_proc


def preparar_rascunho_discord(texto: str) -> str:
    """Mantém emojis literais enquanto a resposta ainda está em streaming."""
    return processar_tags_midia_ayla(texto, converter_emojis=False)


def filtrar_emojis_ayla(texto: str) -> str:
    """Remove tags de emojis do Discord, emojis Unicode, tags %...% e formatações Markdown."""
    if not texto:
        return ""
    # 1. Remove Discord custom emojis (<:name:id> ou <a:name:id>)
    texto_filtrado = re.sub(r'<a?:[a-zA-Z0-9_]+:[0-9]+>', '', texto)
    # 2. Remove tags %...% ou &...&
    texto_filtrado = re.sub(r'[%&][^%&\n]+[%&]', '', texto_filtrado)
    # 3. Remove URLs/links
    texto_filtrado = re.sub(r'https?://\S+', '', texto_filtrado)
    # 4. Remove formatações Markdown (*, _, `, #, ~, >, |, etc.)
    texto_filtrado = re.sub(r'[*_`#~>|]', '', texto_filtrado)
    # 5. Remove todos os emojis Unicode (Astral plane emojis, dingbats, pictographs, symbols)
    texto_filtrado = re.sub(
        r'[\U00010000-\U0010ffff]|[\u2600-\u27bf]|[\u2300-\u23ff]|[\u2b50-\u2b55]|[\ufe00-\ufe0f]|[\u200d]',
        '',
        texto_filtrado
    )
    # 6. Limpa espaços excessivos
    texto_filtrado = re.sub(r'\s+', ' ', texto_filtrado).strip()
    return texto_filtrado

# ══════════════════════════════════════════════════════════
#  FERRAMENTAS DA AYLA
# ══════════════════════════════════════════════════════════

import ayla_state

# ══════════════════════════════════════════════════════════
#  SISTEMA DE MÓDULOS / PLUGINS (CARREGAMENTO DINÂMICO SOB DEMANDA)
# ══════════════════════════════════════════════════════════
from ayla_modules import ModuleManager, ACTIVE_REGISTRY
from ayla_runtime import CURRENT_WORKER, ConversationStore, conversation_key, new_task_id
from ayla_contexto import formatar_resumo, compactar_contexto
from ayla_sessao import MemoriaSessao
from ayla_verificacao import (
    EVIDENCIAS, ResultadoFerramenta, INSTRUCOES_VERIFICACAO,
    concluir_verificacao, retorno_falhou, verificar_memoria, proteger_confirmacao,
    identidade_acao,
)
import copy

MODOS_DIR = BASE_DIR / "MODOS"
_NOMES_COMPATIVEIS_MODOS = ('os', 'sys', 'time', 'shutil', 'subprocess', 'webbrowser', 'json', 'asyncio', 'discord', 'app_commands', 'Path', 'datetime', 'quote_plus', 'quote', 'requests', 'random', 'winsound', 're', 'threading', 'ZaiClient', 'ZaiChatConfig', 'ZaiAttachment', 'ZaiMessage', 'ZaiResponse', 'ZaiToolResult', 'ZAI_API_KEYS', 'DISCORD_TOKEN', 'DISCORD_OWNER_ID', 'ARQUIVO_MEMORIA', 'ARQUIVO_MEMORIA_LIXEIRA', 'ARQUIVO_MEMORIA_HISTORICO', 'ARQUIVO_STOPWORDS_MEMORIA', 'carregar_memoria', 'salvar_memoria', 'normalizar_registro_memoria', 'normalizar_chave_memoria', 'carregar_palavras_ignoradas_memoria', 'salvar_palavras_ignoradas_memoria', 'criar_ou_atualizar_memoria', 'buscar_memorias_estruturadas', 'formatar_memorias_encontradas', 'registrar_acessos_memoria', 'arquivar_memoria_estruturada', 'enviar_memoria_para_lixeira', 'listar_lixeira_memoria', 'restaurar_memoria_estruturada', 'revisar_memorias_estruturadas', 'ARQUIVO_MIDIAS_AYLA', 'carregar_midias_ayla', 'salvar_midias_ayla', 'processar_tags_midia_ayla', 'filtrar_emojis_ayla', 'AylaBot', 'bot', 'ayla_state', 'montar_prompt_com_memoria', 'dividir_mensagem_discord', 'executar_ferramenta', 'tocar_audio_na_call', 'desativar_modulo')

def _contexto_compatibilidade_modulo():
    contexto = {nome:globals()[nome] for nome in _NOMES_COMPATIVEIS_MODOS if nome in globals()}
    # Bot é a conexão Discord real; funções de ferramentas consultam ContextVars.
    contexto.update(ativar_modulo=ativar_modulo, ativar_ferramenta=ativar_ferramenta,
                    carregar_modulos=carregar_modulos)
    return contexto

def _atualizar_ferramentas_interacao():
    worker = CURRENT_WORKER.get()
    if worker is not None:
        worker.atualizar_ferramentas_zai()

_MODULE_MANAGER = ModuleManager(MODOS_DIR, _contexto_compatibilidade_modulo, _atualizar_ferramentas_interacao)
TOOL_MAP = _MODULE_MANAGER.tool_view
FUNCTION_DECLARATIONS = _MODULE_MANAGER.declaration_view
MODULOS_CARREGADOS = _MODULE_MANAGER.module_view
CATALOGO_MODULOS_ADICIONAIS = _MODULE_MANAGER.catalog
_NOMES_MODULOS_ESSENCIAIS = _MODULE_MANAGER.essential
_NOMES_MODULOS_CONTINUOS = _MODULE_MANAGER.continuous
_MODULOS_CONTINUOS_ATIVOS = _MODULE_MANAGER.continuous

def ativar_modulo(nome_modulo):
    return _MODULE_MANAGER.activate(nome_modulo)

def ativar_ferramenta(nome_modulo, nome_ferramenta):
    return _MODULE_MANAGER.activate_tool(nome_modulo,nome_ferramenta)

def desativar_modulo(nome_modulo):
    return _MODULE_MANAGER.deactivate(nome_modulo)

def carregar_modulos(pasta=MODOS_DIR):
    import runpy
    reload_namespace = runpy.run_path(str(BASE_DIR / 'ayla_module_reload.py'))
    reload_namespace['reload_active_manager'](_MODULE_MANAGER)
    worker = CURRENT_WORKER.get()
    if worker is not None:
        # O reload também substitui as funções selecionadas nesta interação.
        worker.atualizar_ferramentas_zai()


from ayla_prompt import montar_prompt_base

SYSTEM_PROMPT = montar_prompt_base()


def montar_prompt_com_memoria(incluir_diretrizes_privadas: bool = True) -> str:
    midias = carregar_midias_ayla()
    nomes_emojis = ", ".join(midias.get("emojis", {}).keys()) or "Nenhum emoji cadastrado"
    nomes_gifs = ", ".join(midias.get("gifs_e_fotos", {}).keys()) or "Nenhum gif cadastrado"

    try:
        sys_prompt_base = SYSTEM_PROMPT.format(
            lista_nomes_emojis=nomes_emojis,
            lista_nomes_gifs=nomes_gifs
        )
    except Exception as e:
        print(f"⚠️ Erro ao formatar SYSTEM_PROMPT com mídias: {e}")
        sys_prompt_base = SYSTEM_PROMPT

    return sys_prompt_base


def dividir_mensagem_discord(texto: str, limite: int = 1900) -> list[str]:
    restante = str(texto or "").strip()
    if not restante:
        return [""]

    pedacos = []
    while len(restante) > limite:
        corte = restante.rfind("\n", 0, limite)
        if corte <= 0:
            corte = restante.rfind(" ", 0, limite)
        if corte <= 0:
            corte = limite

        pedaco = restante[:corte].strip()
        restante = restante[corte:].strip()

        # Mantém blocos de código markdown fechados e reabertos caso cortados
        num_crases = pedaco.count("```")
        if num_crases % 2 != 0:
            match = list(re.finditer(r"```([a-zA-Z0-9_-]*)", pedaco))
            lang = match[-1].group(1) if match else ""
            pedaco = pedaco + "\n```"
            restante = f"```{lang}\n" + restante

        if pedaco:
            pedacos.append(pedaco)
    if restante or not pedacos:
        pedacos.append(restante)
    return pedacos


def limitar_historico(historico):
    # A compactação é transacional no ConversationStore; nunca corte o fallback.
    return sanear_historico(list(historico or []))


FERRAMENTAS_MEMORIA_TERMINAIS = {
    "memorizar_informacao",
    "editar_memoria",
    "apagar_memoria",
    "arquivar_memoria",
    "restaurar_memoria",
}


def build_tools():
    def build():
        tools = []
        for fd in FUNCTION_DECLARATIONS:
            nome = fd["name"]
            parametros = copy.deepcopy(
                fd.get("parameters", {"type": "object", "properties": {}})
            )
            if nome in FERRAMENTAS_MEMORIA_TERMINAIS:
                parametros.setdefault("type", "object")
                parametros.setdefault("properties", {})["resposta_final"] = {
                    "type": "string",
                    "description": (
                        "Resposta completa ao usuário depois que esta ação for concluída. "
                        "Preencha somente quando todas as chamadas desta rodada forem ações "
                        "finais de memória e nenhum resultado precisar ser analisado pelo modelo."
                    ),
                }
            tools.append({
                "type": "function",
                "function": {
                    "name": nome,
                    "description": fd["description"],
                    "parameters": parametros,
                },
            })
        return tools
    prepare = getattr(FUNCTION_DECLARATIONS, "prepare_tools", None)
    return prepare(build) if callable(prepare) else build()


FERRAMENTAS_MEMORIA = {
    "memorizar_informacao",
    "editar_memoria",
    "apagar_memoria",
    "ler_memoria",
    "consultar_memorias",
    "buscar_memorias",
    "arquivar_memoria",
    "restaurar_memoria",
    "consultar_lixeira_memoria",
    "revisar_memorias",
}


def executar_ferramenta(nome: str, args: dict) -> str:
    task_id = ayla_state.TAREFA_ATUAL.get()
    ayla_state.atualizar_tarefa(task_id, descricao=f"Executando {nome}", status="executando", ferramenta=nome)
    start = time.monotonic()
    token_evidencias = EVIDENCIAS.set([])
    worker = CURRENT_WORKER.get()
    action_key = identidade_acao(nome, args)
    try:
        if not isinstance(args, dict) or "_invalid_arguments" in args:
            raise ValueError("parâmetros de ferramenta inválidos.")
        fn = _MODULE_MANAGER.available_function(nome)
        if not fn:
            raise ValueError(f"ferramenta {nome} não está ativa. Use ativar_modulo e, nos modos complexos, ativar_ferramenta.")
        if nome in FERRAMENTAS_MEMORIA:
            with _MEMORIA_LOCK:
                before = None
                if nome == 'restaurar_memoria' and ayla_cerebro is not None:
                    before = json.loads(Path(ayla_cerebro.ARQUIVO_MEMORIA_LIXEIRA).read_text(encoding='utf-8-sig'))
                value = fn(**args)
                if nome in FERRAMENTAS_MEMORIA_TERMINAIS and not retorno_falhou(value):
                    if ayla_cerebro is None:
                        raise RuntimeError('Verificador de memória indisponível.')
                    verificar_memoria(nome, args, ayla_cerebro, before)
        else:
            value = fn(**args)
        resultado = concluir_verificacao(value, EVIDENCIAS.get())
    except Exception as exc:
        resultado = ResultadoFerramenta(f"Erro em {nome}: {exc}", 'falhou')
    finally:
        EVIDENCIAS.reset(token_evidencias)
        ayla_state.atualizar_tarefa(task_id, descricao="Preparando resposta", status="respondendo", ferramenta="")
    ok = resultado.estado != 'falhou'
    if worker is not None:
        if not hasattr(worker, '_tool_failures'):
            worker._tool_failures = {}
        if ok:
            worker._tool_failures.pop(action_key, None)
        else:
            worker._tool_failures[action_key] = (nome, str(resultado)[:350])
        worker._tool_errors = {name for name, _ in worker._tool_failures.values()}
    ayla_state.registrar_metrica(nome, (time.monotonic()-start)*1000, ok)
    return resultado

# ══════════════════════════════════════════════════════════
#  MENSAGENS PERSONALIZADAS DE STATUS E PENSAMENTO DA AYLA
# ══════════════════════════════════════════════════════════
GIF_GERAR_IMAGEM = "https://c.tenor.com/ukUeo6XcejEAAAAC/tenor.gif"

FRASES_PENSANDO_AYLA = [
    "<:ayla_concentrada:000000000000000000> *Fritando os neurônios de silício...* 🧠⚡",
    "<:ENA_PENSANDO:000000000000000000> *Consultando a sabedoria cósmica da usuario...* ✨💭",
    "<:Miku_bebendo_monster:000000000000000000> *Tomando um golinho de Monster e calculando tudo...* 🥤⚡",
    "<:ayla_fofa:000000000000000000> *Processando na velocidade da luz com muito carinho, nanodaze!* 💫💖",
    "<:EMOJI_NERD:000000000000000000> *Eu sabo... calma que a mestra tá compilando as ideias!* 🤓📚",
    "<:osaka_falando_yeppi:000000000000000000> *Conectando os fiozinhos do cérebro virtual da Ayla...* 🔌✨",
    "<:pato_de_bone:000000000000000000> *Farmando aura de inteligência pra responder à altura!* 🕶️📂",
    "<a:gatinho_bocejando:1511780012301226184> *Aquecendo a GPU pra soltar a melhor resposta...* ☕🩵",
    "<:ayla_orgulhosa:000000000000000000> *Sintonizando a frequência da sabedoria suprema...* 📡💎",
    "[kakegurui dasho](https://cdn.discordapp.com/attachments/1533105920098177260/1542364087101694033/content.png?ex=6a9e24fe&is=6a9cd37e&hm=c6edda26ce3dd48172f47e091eb9664d6c4c03175591d3add7e2352628daf381&) *Apostando todos os meus tokens nessa resposta...* 🎰💸",
    "*Dando soquinhos nos [bugs](https://klipy.com/gifs/smile-happy-573) até eles desistirem...*🐛🌸🌸",
    "<:ENA_APONTANDO:000000000000000000> *Apontando pro problema certo, confia na mestra!* 🎯💡",
    "<:gatinho_com_pistola:000000000000000000> *Ameaçando o código carinhosamente até ele funcionar...* :gun::light_blue_heart:",
    " *Hidratando os circuitos antes do esforço [mental](https://klipy.com/gifs/kanna-kamui-kanna-kobayashi-5)...* :droplet::sleeping:",
    "<:ENA_PENSANDO:000000000000000000> *Processando neurônios digitais... calma aí.*",
    "🤔 *Pensando... meus circuitos tão em modo turbo, não apressa.*",
    "<:ayla_concentrada:000000000000000000> *Deixa eu pensar direitinho... quase lá.*",
    "💭 *Hmm... calculando a resposta mais foda possível.*",
    "<:ENA_FOFA:000000000000000000> *Cérebro carregando...* 🧠✨",
    "<:gatinho_com_pistola:000000000000000000> *Pensando com pressão: o bug melhor não me fazer perder tempo.*",
    "https://klipy.com/gifs/-24690 *Pensando com força! HaruUrara tá dando soquinhos nos neurônios!*",
    "https://klipy.com/gifs/kanna-kamui-kanna-kobayashi-5 *Hidratando os circuitos antes de pensar... ok, pronto.*",
    "<:osaka_falando_yeppi:000000000000000000> *Pensando... yeppi... acho que achei a resposta!*",
    "<:Miku_bebendo_monster:000000000000000000> *Tomando um energéticozinho virtual pra pensar mais rápido* ⚡",
    "*Pensando... spoiler: a resposta vai ser brilhante.*",
    "💭 *Calculando... e olha que nem preciso de GPU pra isso.*",
    "*Pensando... se demorar mais é porque tô caprichando, viu?*",
    "<:pato_de_bone:000000000000000000> *Quack... digo, pensando...*",
    "<a:gatinho_bocejando:1511780012301226184> *Pensando sonolenta... mas pensando KKKKK*",
    "💭 Analisando todas as variáveis... sou basicamente um supercomputador fofo.",
    "🤖 Processando... se der erro eu culpo a reciclagem do Windows.",
    "<:ENA_APONTANDO:000000000000000000> Achei o problema! ...ops, ainda pensando, deixa eu terminar.",
]

def obter_status_pensando_formatado() -> str:
    frase = random.choice(FRASES_PENSANDO_AYLA)
    if re.search(r"https?://", frase):
        return frase
    return f"{frase}\n{GIF_GERAR_IMAGEM}"

def formatar_status_ferramenta(nome: str, args: dict) -> str:
    from ayla_discord_messages import formatar_andamento_modulo
    args_str = f" (`{args}`)" if args else ""
    nome_norm = nome.lower()
    if "memoria" in nome_norm:
        emoji = "<:pato_de_bone:000000000000000000> 🧠"
        acao = "consulta ao caderninho de memórias"
    elif "imagem" in nome_norm or "desenhar" in nome_norm:
        emoji = "<:ayla_orgulhosa:000000000000000000> 🎨"
        acao = "pintura de uma obra de arte exclusiva"
    elif "audio" in nome_norm or "voz" in nome_norm or "falar" in nome_norm or "tts" in nome_norm:
        emoji = "<:osaka_falando_yeppi:000000000000000000> 🎙️"
        acao = "preparo da voz e do microfone"
    elif "pesquisar" in nome_norm or "google" in nome_norm or "web" in nome_norm or "busca" in nome_norm:
        emoji = "<:FBI_de_olho:000000000000000000> 🔍"
        acao = "pesquisa na internet"
    elif "video" in nome_norm:
        emoji = "<:Miku_bebendo_monster:000000000000000000> 🎬"
        acao = "processamento do arquivo de vídeo"
    elif "comando" in nome_norm or "terminal" in nome_norm or "shell" in nome_norm or "executar" in nome_norm:
        emoji = "<:EMOJI_NERD:000000000000000000> 💻"
        acao = f"comando no sistema: `{nome}`"
    else:
        emoji = "<:ayla_concentrada:000000000000000000> ⚙️"
        acao = f"ferramenta **{nome}**"
    return f"{emoji} {formatar_andamento_modulo(acao)}{args_str}\n{GIF_GERAR_IMAGEM}"


# ══════════════════════════════════════════════════════════
#  LEITURA DE ANEXOS DISCORD (Mídia Multimodal + Notificação)
# ══════════════════════════════════════════════════════════

async def ler_anexos_discord(anexos, stickers=None) -> tuple[list[tuple[bytes, str]], str | None]:
    """Lê anexos e figurinhas (stickers) do Discord e retorna lista de (bytes, mime_type).
    Imagens, áudio, vídeo e figurinhas são processados como mídia multimodal nativa.
    Outros arquivos são registrados como anexos para leitura via ferramenta sob demanda."""
    anexos = list(anexos or [])
    stickers = list(stickers or [])

    if len(anexos) + len(stickers) > MAX_ANEXOS_POR_REQUISICAO:
        return [], f"⚠️ Envie no máximo {MAX_ANEXOS_POR_REQUISICAO} mídias/figurinhas por vez."

    arquivos = []
    total = 0

    for anexo in anexos:
        tipo = (getattr(anexo, "content_type", None) or "").split(";")[0].lower()
        nome = getattr(anexo, "filename", "anexo")

        tamanho_declarado = int(getattr(anexo, "size", 0) or 0)
        if tamanho_declarado > MAX_BYTES_POR_ANEXO:
            return [], f"⚠️ O anexo {nome} ultrapassa o limite de 25 MB."
        if total + tamanho_declarado > MAX_BYTES_ANEXOS_TOTAL:
            return [], "⚠️ Os anexos juntos ultrapassam o limite de 50 MB."

        try:
            arq_bytes = await anexo.read()
        except Exception as e:
            return [], f"⚠️ Falha ao baixar o arquivo {nome}: {e}"

        if len(arq_bytes) > MAX_BYTES_POR_ANEXO:
            return [], f"⚠️ O anexo {nome} ultrapassa o limite de 25 MB."
        total += len(arq_bytes)
        if total > MAX_BYTES_ANEXOS_TOTAL:
            return [], "⚠️ Os anexos juntos ultrapassam o limite de 50 MB."

        if tipo.startswith("image/") or tipo.startswith("audio/") or tipo.startswith("video/"):
            arquivos.append((arq_bytes, tipo))
        else:
            arquivos.append((arq_bytes, f"attachment:{nome}"))

    for sticker in stickers:
        nome = getattr(sticker, "name", "figurinha")
        url_lower = getattr(sticker, "url", "").lower()

        try:
            arq_bytes = await sticker.read()
        except Exception as e:
            print(f"⚠️ Falha ao baixar a figurinha '{nome}': {e}")
            continue

        if len(arq_bytes) > MAX_BYTES_POR_ANEXO:
            continue
        total += len(arq_bytes)
        if total > MAX_BYTES_ANEXOS_TOTAL:
            break

        # Determina o tipo MIME da figurinha
        tipo = "image/png"
        if arq_bytes.startswith(b"GIF8"):
            tipo = "image/gif"
        elif arq_bytes.startswith(b"\x89PNG"):
            tipo = "image/png"
        elif arq_bytes.startswith(b"RIFF") and b"WEBP" in arq_bytes[:16]:
            tipo = "image/webp"
        elif url_lower.endswith(".gif"):
            tipo = "image/gif"
        elif url_lower.endswith(".webp"):
            tipo = "image/webp"

        # Se for sticker em Lottie (JSON), ignora a conversão de imagem direta
        if arq_bytes.startswith(b"{") or url_lower.endswith(".json"):
            print(f"ℹ️ Figurinha Lottie (JSON) '{nome}' ignorada da conversão de imagem.")
            continue

        arquivos.append((arq_bytes, tipo))

    return arquivos, None


# ══════════════════════════════════════════════════════════
#  LÓGICA DO DISCORD COM FALLBACK DE MODELOS E APIs
# ══════════════════════════════════════════════════════════


class AylaBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True           # Permite carregar a lista de membros e buscar integrantes
        intents.message_content = True   # Necessário para ler conteúdo das mensagens
        intents.dm_messages = True       # Necessário para receber DMs
        intents.guilds = True            # Necessário para entrar em guildas
        intents.voice_states = True     # Acompanha entradas, trocas e saídas de call
        super().__init__(intents=intents)
        self.owner_id = DISCORD_OWNER_ID
        self.prefix = "!" # Prefixo para comandos de texto
        self.tree = app_commands.CommandTree(self)
        self.tools_config = []
        self.ayla_settings = carregar_configuracoes_ayla()
        from ayla_embeddings import iniciar_sessao
        iniciar_sessao()
        # Trava curta de metadados; inferências e tarefas usam workers independentes.
        self.lock = threading.RLock()
        self._conversation_store = ConversationStore(max_turns=16)
        ARQUIVO_CONVERSA_ATIVA = BASE_DIR / "ayla_conversa_ativa.json"
        turnos_carregados = 0
        if ARQUIVO_CONVERSA_ATIVA.is_file():
            if self._conversation_store.load_from_file(ARQUIVO_CONVERSA_ATIVA):
                turnos_carregados = sum(len(s.turns) for s in self._conversation_store.sessions.values())
                if turnos_carregados > 0:
                    print(f"💬 [Ayla Conversa]: Conversa da sessão restaurada com {turnos_carregados} turnos recentes na memória!")

        self._memoria_sessao = MemoriaSessao(BASE_DIR / "ayla_ultima_sessao.json")
        memoria_inicial = self._memoria_sessao.contexto()
        if memoria_inicial and turnos_carregados == 0:
            chave = conversation_key("Terminal", None, DISCORD_OWNER_ID)
            seq, _, _ = self._conversation_store.begin(chave)
            self._conversation_store.finish(chave, seq, [
                ZaiMessage(role="system", text=memoria_inicial),
            ])
            print("🧠 [Ayla Memória]: Contexto e histórico da sessão anterior carregados na memória global!")
        self.memoria_lock = _MEMORIA_LOCK
        self.last_active_channel_id = None
        self.last_message_time = 0.0
        self.discord_loop = None  # Fix #4: referência explícita ao event loop
        self._canal_debounce_timer = None  # Fix #8: debounce de salvar canal
        self._canal_debounce_lock = threading.Lock()

        self.prompt_com_memoria = montar_prompt_com_memoria()
        self.config = None
        self._api_key_cooldowns: dict[str, float] = {}  # Circuit Breaker: chave -> timestamp de expiração

        # Sistema de Voz do Discord (2.3) gerenciado no ayla_live.py
        try:
            from ayla_live import DiscordVoiceManager
            self.voice_manager = DiscordVoiceManager(self)
            self.voice_manager.registrar_comandos_discord(self.tree)
        except ImportError:
            self.voice_manager = None


    def _obter_proxima_chave_saudavel(self, excluir_atual: bool = False) -> tuple[int, str, bool]:
        """Circuit Breaker: seleciona a melhor chave de API fora de cooldown.
        Retorna: (idx_chave, api_key, todas_em_cooldown)
        """
        agora = time.time()
        for idx, k in enumerate(self.api_keys):
            if excluir_atual and idx == self.idx_api_atual and len(self.api_keys) > 1:
                continue
            cooldown = self._api_key_cooldowns.get(k, 0.0)
            if agora >= cooldown:
                return idx, k, False

        candidatos = []
        for idx, k in enumerate(self.api_keys):
            cooldown = self._api_key_cooldowns.get(k, 0.0)
            candidatos.append((cooldown, idx, k))
        if candidatos:
            candidatos.sort()
            _, best_idx, best_k = candidatos[0]
            return best_idx, best_k, True
        return 0, self.api_keys[0], True

    @property
    def _voice_clients(self) -> dict[int, object]:
        """Acesso retrocompatível ao mapa de conexões de voz gerenciadas."""
        if hasattr(self, "voice_manager") and self.voice_manager:
            return self.voice_manager._voice_clients
        return {}

    def get_voice_client(self, guild_id: int):
        """Retorna o VoiceClient da guilda de forma unificada."""
        if hasattr(self, "voice_manager") and self.voice_manager:
            return self.voice_manager.get_voice_client(guild_id)
        for client in getattr(self, "voice_clients", []):
            if getattr(getattr(client, "guild", None), "id", None) == guild_id:
                return client
        return None

    async def conectar_canal_voz(self, voice_channel: discord.VoiceChannel) -> tuple[bool, str]:
        """Conecta o bot ao canal de voz (delegado ao ayla_live.DiscordVoiceManager)."""
        if self.voice_manager:
            return await self.voice_manager.conectar_canal_voz(voice_channel)
        return False, "⚠️ Sistema de voz do Discord não disponível."

    async def desconectar_canal_voz(self, guild_id: int) -> tuple[bool, str]:
        """Desconecta o bot do canal de voz (delegado ao ayla_live.DiscordVoiceManager)."""
        if self.voice_manager:
            return await self.voice_manager.desconectar_canal_voz(guild_id)
        return False, "⚠️ Sistema de voz do Discord não disponível."

    def tocar_audio_na_call(self, guild_id: int, caminho_audio: str) -> bool:
        """Toca um arquivo de áudio de forma thread-safe na chamada ativa do servidor."""
        if self.voice_manager:
            return self.voice_manager.tocar_audio_na_call(guild_id, caminho_audio)
        return False

    def _construir_config_zai(self, system_prompt=None, tools=None):
        from ayla_discord_context import INSTRUCOES_AUTORIA
        from ayla_prompt import compose_system_prompt
        temp = float(self.ayla_settings.get("temperature", 0.7)) if isinstance(self.ayla_settings, dict) else 0.7
        max_tokens = int(self.ayla_settings.get("max_tokens", generation_config['max_tokens'])) if isinstance(self.ayla_settings, dict) else generation_config['max_tokens']
        top_p = float(self.ayla_settings.get("top_p", generation_config['top_p'])) if isinstance(self.ayla_settings, dict) else generation_config['top_p']
        thinking_level = self.ayla_settings.get("thinking_level", generation_config.get("thinking_level", "low")) if isinstance(self.ayla_settings, dict) else generation_config.get("thinking_level", "low")
        ferramentas = tools if tools is not None else getattr(self, "tools_config", None)
        self._system_prompt_base = system_prompt or self.prompt_com_memoria

        return ZaiChatConfig(
            system_prompt=compose_system_prompt(self._system_prompt_base, INSTRUCOES_VERIFICACAO, INSTRUCOES_AUTORIA),
            tools=ferramentas,
            temperature=temp,
            top_p=top_p,
            max_tokens=max_tokens,
            thinking_level=str(thinking_level or "low").strip().lower(),
        )

    def inicializar_configuracao_zai(self):
        self.generation_config = dict(generation_config)
        self.ayla_settings = carregar_configuracoes_ayla()
        self.tools_config = build_tools()
        self.config = self._construir_config_zai(
            system_prompt=self.prompt_com_memoria,
            tools=self.tools_config
        )

        modelos_json_path = Path(__file__).resolve().parent / "ayla_models.json"
        self.modelos_avancados = []
        modelos_padrao_fallback = ["glm-5.3-flash"]
        self.modelos_padrao = list(modelos_padrao_fallback)
        self.model_policy = {}

        if modelos_json_path.exists():
            try:
                data = json.loads(modelos_json_path.read_text(encoding="utf-8"))
                self.model_policy = data.get("roteamento", {})
                modelos_lidos = [
                    str(m.get("name", "")).strip()
                    for m in data.get("padrao", [])
                    if isinstance(m, dict) and str(m.get("name", "")).strip()
                ]
                if modelos_lidos:
                    self.modelos_padrao = list(dict.fromkeys(modelos_lidos))
            except Exception as e:
                print(f"⚠️ Erro ao ler ayla_models.json: {e}")

        from ayla_model_policy import normalize_policy, ordered_models
        self.model_policy = normalize_policy(self.model_policy, self.modelos_padrao)
        self.modelos_padrao = ordered_models(self.modelos_padrao, self.model_policy)
        self.modelos_disponiveis = self.modelos_padrao
        self.idx_modelo_atual = 0
        self.modelo_atual = self.modelos_disponiveis[self.idx_modelo_atual]
        self.model_status = {}

        self.api_keys = ZAI_API_KEYS or ['']  # Gemini também funciona sem uma chave Z.ai.
        self.idx_api_atual = 0

        # Pool persistente e preguiçoso: nenhuma conexão ou inferência de aquecimento.
        from ayla_client_pool import ApiClientPool
        if not hasattr(self, '_api_client_pool'):
            self._api_client_pool = ApiClientPool()
        for lease in getattr(self, '_client_leases', []):
            lease.close()
        self._client_leases = []
        self._pool_clientes = {}
        for key in self.api_keys:
            self._trocar_cliente_zai(key)
        self.zai_client = self._pool_clientes[self.api_keys[0]]
        self.chat_session = None

    def _criar_cliente_zai(self, api_key: str):
        from ayla_provider import AylaClient
        return AylaClient(
            api_key=api_key,
            settings=carregar_configuracoes_ayla(),
            timeout=TIMEOUT_API_ZAI_SECS,
        )

    def _trocar_cliente_zai(self, api_key: str, forcar_novo: bool = False):
        """Reserva transporte; uma substituição nunca fecha outro worker ativo."""
        if not forcar_novo and api_key in self._pool_clientes:
            self.zai_client = self._pool_clientes[api_key]
        else:
            lease = self._api_client_pool.acquire(
                api_key, settings=carregar_configuracoes_ayla(), timeout=TIMEOUT_API_ZAI_SECS,
                replace=self._pool_clientes.get(api_key) if forcar_novo else None,
            )
            self._client_leases.append(lease)
            self.zai_client = lease.client
            self._pool_clientes[api_key] = self.zai_client

    def _salvar_sessao_ativa(self):
        """Snapshot local para recuperação; publicação só ocorre ao completar."""
        self._historico_sessao = self.chat_session.get_history() if self.chat_session else []
        return self._historico_sessao


    def chave_sessao_contextual(self, origem="Discord", contexto_discord=None):
        return conversation_key(origem,contexto_discord,DISCORD_OWNER_ID)

    def obter_resumo_runtime(self):
        return self._conversation_store.summary()

    def atualizar_ferramentas_zai(self):
        self.ayla_settings = carregar_configuracoes_ayla()
        instrucao = getattr(self, '_system_prompt_base', self.prompt_com_memoria)
        self.tools_config = build_tools()
        self.config = self._construir_config_zai(system_prompt=instrucao, tools=self.tools_config)
        if self.chat_session:
            self.chat_session.config = self.config

    def aparar_historico_chat(self):
        if not getattr(self, "chat_session", None) or not hasattr(self.chat_session, "get_history"):
            return
        historico = self.chat_session.get_history()
        limitado = limitar_historico(historico)
        if len(limitado) == len(historico):
            return
        self.chat_session = self.zai_client.create_session(
            model=self.modelo_atual,
            config=self.config,
            history=limitado,
        )
        self._salvar_sessao_ativa()
        print(f"🧹 Histórico do chat reduzido de {len(historico)} para {len(limitado)} itens.")

    def _recriar_sessao_com_historico_limitado(self, modelo=None):
        """Recria a sessão preservando integralmente o turno em andamento."""
        with self.lock:
            modelo = modelo or self.modelo_atual
            # Durante um turno pode existir uma chamada de ferramenta aguardando
            # o resultado contido no próximo payload. Não a descarte no fallback.
            # O corte do histórico já ocorre antes de começar cada interação.
            historico = (self.chat_session.get_history()
                         if self.chat_session is not None else [])

            if not self.config:
                self.inicializar_configuracao_zai()

            self.chat_session = self.zai_client.create_session(
                model=modelo, config=self.config, history=historico
            )
            self.modelo_atual = modelo
            self._salvar_sessao_ativa()
            return self.chat_session

    def atualizar_prompt_memoria(self):
        self.prompt_com_memoria = montar_prompt_com_memoria()

    def _debounce_salvar_canal(self, channel_id):
        """Fix #8: Debounce — salva o canal ativo após 5s, cancelando saves anteriores."""
        with self._canal_debounce_lock:
            if self._canal_debounce_timer is not None:
                self._canal_debounce_timer.cancel()
            def _salvar():
                try:
                    s = carregar_configuracoes_ayla()
                    if s.get("last_active_channel_id") != channel_id:
                        s["last_active_channel_id"] = channel_id
                        salvar_configuracoes_ayla(s)
                except Exception as e:
                    print(f"⚠️ Erro ao salvar last_active_channel_id: {e}")
            self._canal_debounce_timer = threading.Timer(5.0, _salvar)
            self._canal_debounce_timer.daemon = True
            self._canal_debounce_timer.start()

    async def setup_hook(self):
        from ayla_discord_startup import sync_discord_commands
        self.discord_loop = asyncio.get_running_loop()
        # Command registration retries independently of login/the gateway.
        task = getattr(self, "_command_sync_task", None)
        if task is None or task.done():
            self._command_sync_task = asyncio.create_task(
                sync_discord_commands(self, stop_requested=_SHUTDOWN_REQUESTED.is_set),
                name="discord-command-sync",
            )

    async def on_ready(self):
        self.discord_loop = asyncio.get_running_loop()  # Fix #4: armazena event loop
        print(f"🩵 Ayla conectada como {self.user}! Dona Oficial: {DISCORD_OWNER_ID}")
        self.modelo_atual = self.modelos_disponiveis[self.idx_modelo_atual]
        self.chat_session = self.zai_client.create_session(model=self.modelo_atual, config=self.config)
        self.last_active_channel_id = self.ayla_settings.get("last_active_channel_id")
        if self.voice_manager:
            if not getattr(self, '_seguir_call', None):
                module, _, _ = _MODULE_MANAGER._load('seguir_dona_na_call')
                self._seguir_call = module.SeguirDonaNaCall(self, DISCORD_OWNER_ID)
            await self._seguir_call.sincronizar()

    async def on_voice_state_update(self, member, before, after):
        follower = getattr(self, '_seguir_call', None)
        if follower:
            await follower.on_voice_state_update(member, before, after)

    async def close(self):
        try:
            await super().close()
        finally:
            self.fechar_clientes_api()

    def fechar_clientes_api(self):
        from ayla_embeddings import fechar_sessao
        fechar_sessao()
        for lease in getattr(self, '_client_leases', []):
            lease.close()
        if hasattr(self, '_api_client_pool'):
            self._api_client_pool.close()

    async def _executar_fluxo_mensagem_discord(self, message: discord.Message, conteudo_texto: str, origem: str, historico_discord=None):
        if not DISCORD_OWNER_ID or message.author.id != DISCORD_OWNER_ID:
            return
        stickers = getattr(message, "stickers", []) or []
        has_stickers = bool(stickers)
        has_attachments = bool(getattr(message, "attachments", None))

        if not conteudo_texto and not has_attachments and not has_stickers:
            conteudo_texto = "Oi! O que você pode fazer?"
        elif has_stickers and not conteudo_texto:
            nomes_stickers = ", ".join([f"'{s.name}'" for s in stickers if hasattr(s, "name")])
            conteudo_texto = f"[Sem texto] [Figurinha: {nomes_stickers}]"
        elif has_stickers and conteudo_texto:
            nomes_stickers = ", ".join([f"'{s.name}'" for s in stickers if hasattr(s, "name")])
            conteudo_texto += f"\n[Figurinha enviada: {nomes_stickers}]"
        elif has_attachments and not conteudo_texto:
            conteudo_texto = "[Sem texto]"

        from ayla_discord_messages import MensagensTurnoDiscord, dividir_com_metadados
        primeira_mensagem = True

        async def enviar(texto, **kwargs):
            nonlocal primeira_mensagem
            if primeira_mensagem:
                msg = await message.reply(texto, **kwargs)
                primeira_mensagem = False
                return msg
            return await message.channel.send(texto, **kwargs)

        fluxo = MensagensTurnoDiscord(
            enviar,
            lambda texto: dividir_com_metadados(texto, dividir_mensagem_discord),
            preparar_rascunho_discord,
        )

        async def _run_task():
            try:
                arquivos, erro_anexo = await ler_anexos_discord(message.attachments, stickers)
            except Exception as exc:
                print(f"⚠️ Erro ao ler anexos do Discord: {exc}")
                arquivos = []
                erro_anexo = f"⚠️ Não consegui carregar os anexos enviados: {exc}"

            if erro_anexo:
                await fluxo.finalizar(erro_anexo)
                return

            try:
                resposta, img_gerada = await asyncio.to_thread(
                    self.processar_zai,
                    conteudo_texto or "[Sem texto]",
                    arquivos,
                    origem,
                    message,
                    fluxo.status_callback,
                    fluxo.stream_callback,
                    historico_discord=historico_discord,
                )
            except Exception as exc:
                import traceback
                print("❌ Erro em _run_task -> processar_zai:")
                traceback.print_exc()
                resposta = f"Eita, deu um probleminha aqui: {exc} 🥺"
                img_gerada = None

            arquivo_discord = None
            if img_gerada and Path(img_gerada).is_file():
                arquivo_discord = discord.File(img_gerada, filename=Path(img_gerada).name)

            try:
                await fluxo.finalizar(resposta, arquivo_discord)
            except discord.errors.Forbidden:
                print(f"⚠️ Sem permissão para enviar mensagem ({origem}).")
            except Exception as exc:
                print(f"⚠️ Erro ao enviar resposta ({origem}): {exc}")

        async def _manter_typing():
            try:
                while True:
                    await message.channel.typing()
                    await asyncio.sleep(8)
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        typing_task = asyncio.create_task(_manter_typing())
        try:
            await _run_task()
        finally:
            if typing_task and not typing_task.done():
                typing_task.cancel()

    async def _obter_contexto_historico_canal(self, message: discord.Message, limite: int = 5):
        from ayla_discord_context import obter_historico_canal
        return await obter_historico_canal(message, self.user.id, limite)

    async def on_message(self, message):
        # O chat do canal de voz participa do lote da call, como as vozes.
        voice_manager = getattr(self, "voice_manager", None)
        if voice_manager and voice_manager.route_call_chat(message):
            return

        if (message.author == self.user or message.author.bot
                or not DISCORD_OWNER_ID or message.author.id != DISCORD_OWNER_ID):
            return

        self.last_message_time = time.time()
        if message.channel is not None and not message.author.bot:
            self.last_active_channel_id = message.channel.id
            self._debounce_salvar_canal(message.channel.id)

        # Proteção: ignora mensagens se o bot ainda não terminou de inicializar
        if self.chat_session is None:
            print("⏳ Mensagem recebida antes da inicialização completa, ignorando...")
            return

        # ── 1. Verifica se é uma resposta (reply) a uma mensagem da Ayla ──
        is_reply_to_ayla = False
        historico_discord = []
        if message.reference:
            ref_msg = message.reference.resolved
            if ref_msg is None and message.reference.message_id and message.channel:
                try:
                    ref_msg = await message.channel.fetch_message(message.reference.message_id)
                except Exception:
                    pass
            if isinstance(ref_msg, discord.Message) and ref_msg.author == self.user:
                is_reply_to_ayla = True
                from ayla_discord_context import mensagem_historica
                historico_discord = [mensagem_historica(ref_msg, self.user.id, resposta_a=True)]

        # Em DM, preserve também a autoria da mensagem respondida.
        if message.guild is None:
            await self._executar_fluxo_mensagem_discord(
                message, message.content.strip(), "DM-Dona", historico_discord)
            return

        # ── 2. Verifica se o bot ou cargo do bot foi mencionado ──
        bot_roles = getattr(message.guild.me, "roles", []) if message.guild and hasattr(message.guild, "me") and message.guild.me else []
        mentioned_bot_role = any(role in message.role_mentions for role in bot_roles)
        bot_mencionado = (self.user in message.mentions) or mentioned_bot_role

        if is_reply_to_ayla or bot_mencionado:
            conteudo_limpo = message.content.replace(f"<@{self.user.id}>", "").replace(f"<@!{self.user.id}>", "").strip()
            for r in bot_roles:
                conteudo_limpo = conteudo_limpo.replace(f"<@&{r.id}>", "").strip()
            origem_tag = "Reply-Discord" if is_reply_to_ayla else "Discord"
            await self._executar_fluxo_mensagem_discord(message, conteudo_limpo, origem_tag, historico_discord)
            return

        # ── 3. NAME TRIGGER: responde se citarem "ayla" no texto (sem cooldown!) ──
        if self.ayla_settings.get("name_trigger", True):
            if "ayla" in message.content.lower():
                historico_discord = await self._obter_contexto_historico_canal(message, limite=5)
                await self._executar_fluxo_mensagem_discord(
                    message, message.content.strip(), "NomeCitado", historico_discord)
                return

    def enviar_com_fallback(self, payload, modelos_list=None, stream_callback=None):
        from dataclasses import replace
        from ayla_model_policy import normalize_policy, ordered_models, prioritize_fallback, record_success
        policy = normalize_policy(getattr(self, "model_policy", {}), self.modelos_disponiveis)
        if modelos_list is None:
            modelos_list = self.modelos_disponiveis
        modelos_list = ordered_models([str(modelo).strip() for modelo in modelos_list if str(modelo).strip()], policy)
        if not modelos_list:
            raise RuntimeError("Nenhum modelo Z.ai válido foi configurado.")

        if self.chat_session is None:
            self.modelo_atual = modelos_list[0]
            self.chat_session = self.zai_client.create_session(
                model=self.modelo_atual,
                config=self.config,
                history=[],
            )
            self._salvar_sessao_ativa()

        try:
            idx_modelo = modelos_list.index(self.modelo_atual)
        except ValueError:
            idx_modelo = 0
            self.modelo_atual = modelos_list[0]
            self._recriar_sessao_com_historico_limitado(modelos_list[0])

        if self.modelo_atual != policy["principal"]:
            modelos_list = [self.modelo_atual] + [m for m in modelos_list
                                                  if m not in (self.modelo_atual, policy["principal"])]
            idx_modelo = 0

        tentativas_conexao = 0
        max_tentativas_conexao = 3
        rodada_fallback = 1
        max_rodadas_fallback = policy["rodadas"]

        while True:
            text_parts = []
            try:
                self.chat_session.config = replace(self.config, request_timeout=policy["espera_segundos"])
                t0 = time.time()
                if stream_callback:
                    stream_iter = self.chat_session.stream(payload)
                    text_parts = []
                    tool_calls = []
                    reasoning_content = None
                    usage = None
                    response_model = self.modelo_atual
                    finish_reason = None
                    ultimo_stream_emitido = ""
                    horario_ultimo_stream = time.time()
                    is_live_stream = getattr(stream_callback, "is_live", False)
                    tamanho_chunk_stream = getattr(stream_callback, "chunk_size", 160 if not is_live_stream else 20)
                    intervalo_max_stream = getattr(stream_callback, "max_interval", 1.2 if not is_live_stream else 0.1)
                    for event in stream_iter:
                        if event.text_delta:
                            text_parts.append(event.text_delta)
                            if hasattr(stream_callback, "feed_delta"):
                                try:
                                    stream_callback.feed_delta(event.text_delta)
                                except Exception:
                                    pass
                            texto_acumulado_stream = "".join(text_parts)
                            agora_stream = time.time()
                            crescimento = len(texto_acumulado_stream) - len(ultimo_stream_emitido)
                            fim_seguro = is_live_stream or (texto_acumulado_stream[-1:].isspace() or texto_acumulado_stream[-1:] in ".,;:!?)]}\n")
                            deve_emitir = (
                                crescimento >= tamanho_chunk_stream
                                or (
                                    crescimento > 0
                                    and fim_seguro
                                    and (agora_stream - horario_ultimo_stream) >= intervalo_max_stream
                                )
                            )
                            if deve_emitir:
                                try:
                                    stream_callback(texto_acumulado_stream)
                                    ultimo_stream_emitido = texto_acumulado_stream
                                    horario_ultimo_stream = agora_stream
                                except Exception:
                                    pass
                        finish_reason = getattr(event, "finish_reason", None) or finish_reason
                        if event.tool_calls:
                            tool_calls.extend(event.tool_calls)
                        if event.usage is not None:
                            usage = event.usage
                        if event.model:
                            response_model = event.model
                        if event.reasoning_content is not None:
                            reasoning_content = event.reasoning_content

                    # Entrega qualquer bloco restante antes da edição final do Discord.
                    texto_completo_stream = "".join(text_parts)
                    if texto_completo_stream and texto_completo_stream != ultimo_stream_emitido:
                        try:
                            stream_callback(texto_completo_stream)
                        except Exception:
                            pass
                    resp = ZaiResponse(
                        text=texto_completo_stream,
                        finish_reason=finish_reason,
                        tool_calls=tool_calls,
                        usage=usage,
                        model=response_model,
                        reasoning_content=reasoning_content,
                    )
                else:
                    resp = self.chat_session.send(payload)
                if str(resp.finish_reason or "").lower() in {"length", "max_tokens"}:
                    raise ZaiIncompleteResponseError("A resposta atingiu o limite de saída e ficou incompleta.")
                dur = time.time() - t0
                self.model_status[self.modelo_atual] = {
                    "status": "slow" if dur > 5.0 else "ok",
                    "latency": f"{dur:.1f}s",
                    "latency_ms": int(dur * 1000),
                    "error": ""
                }
                record_success(self, policy)
                return resp
            except Exception as erro:
                erro_msg = str(erro)
                self.model_status[self.modelo_atual] = {
                    "status": "error",
                    "latency": "N/A",
                    "error": erro_msg[:80]
                }
                if isinstance(erro, ZaiIncompleteResponseError):
                    raise
                flags = classificar_erro_zai(erro)
                is_quota        = flags["is_quota"]
                is_interno      = flags["is_interno"]
                is_indisponivel = flags["is_indisponivel"]
                is_modality     = flags["is_modality"]
                is_403          = flags["is_403"]
                is_auth         = flags.get("is_auth", False)
                is_suspended    = flags["is_suspended"]
                is_conexao      = flags["is_conexao"]
                is_timeout      = flags.get("is_timeout", False)

                # Não misturar uma segunda resposta com texto já emitido (inclusive voz).
                if stream_callback and text_parts:
                    raise
                modelos_list = prioritize_fallback(modelos_list, idx_modelo, policy, flags)

                # Falhas de outros provedores não rotacionam nem bloqueiam chaves Z.ai.
                from gemini_catalog import is_gemini
                if (is_gemini(self.modelo_atual) or is_groq(self.modelo_atual) or is_deepseek(self.modelo_atual)) and (is_quota or is_suspended or is_auth):
                    from ayla_model_policy import fallback_error_label
                    motivo = fallback_error_label(erro)
                    modelo_falhou = self.modelo_atual
                    idx_modelo += 1
                    if idx_modelo >= len(modelos_list):
                        print(f"\n⚠️ {modelo_falhou}: {motivo}. Nenhum modelo reserva disponível.")
                        raise erro
                    print(f"\n⚠️ {modelo_falhou}: {motivo}. "
                          f"Alternando para o reserva {modelos_list[idx_modelo]}...")
                    self._recriar_sessao_com_historico_limitado(modelos_list[idx_modelo])
                    continue

                if is_conexao and not is_timeout and not policy.get("conexao") and tentativas_conexao < 2:
                    tentativas_conexao += 1
                    print(f"\n⚠️ Conexão de rede/socket interrompida ({erro_msg[:70]}). "
                          f"Reconectando cliente (tentativa {tentativas_conexao}/2)...")
                    time.sleep(min(2 ** tentativas_conexao + random.uniform(0, 1), 6.0))

                    try:
                        self._trocar_cliente_zai(self.api_keys[self.idx_api_atual], forcar_novo=True)
                        self._recriar_sessao_com_historico_limitado()
                    except Exception as reset_err:
                        print(f"⚠️ Erro ao recriar sessão de chat: {reset_err}")
                    continue

                if is_interno or is_indisponivel or is_modality or is_timeout:
                    motivo = (f"Timeout ({policy['espera_segundos']}s sem dados)" if is_timeout 
                              else ("Modelo não aceita mídia" if is_modality 
                              else ("API sobrecarregada (503)" if is_indisponivel 
                              else "Erro 500 interno")))
                    idx_modelo += 1
                    tentativas_conexao = 0

                    if idx_modelo >= len(modelos_list):
                        if rodada_fallback < max_rodadas_fallback and (is_indisponivel or is_interno or is_timeout):
                            tempo_espera = round(2.5 * rodada_fallback + random.uniform(0.5, 1.5), 1)
                            print(f"\n⚠️ {motivo}! Todos os modelos falharam na rodada {rodada_fallback}/{max_rodadas_fallback}. "
                                  f"Aguardando {tempo_espera}s antes da próxima rodada...")
                            time.sleep(tempo_espera)
                            rodada_fallback += 1
                            idx_modelo = 0
                            if len(self.api_keys) > 1:
                                self.idx_api_atual = (self.idx_api_atual + 1) % len(self.api_keys)
                                print(f"🔄 Rotacionando chave de API Z.ai para conta {self.idx_api_atual + 1}...")
                                self._trocar_cliente_zai(self.api_keys[self.idx_api_atual])
                            self._recriar_sessao_com_historico_limitado(modelos_list[0])
                            continue
                        else:
                            idx_modelo -= 1
                            raise Exception(f"Todos os modelos falharam após {rodada_fallback} rodada(s) devido a falhas na API Z.ai ({motivo}).")

                    tempo_pausa = round(1.0 + random.uniform(0.3, 0.8), 1)
                    print(f"\n⚠️ {motivo}! Aguardando {tempo_pausa}s e alternando para {modelos_list[idx_modelo]}...")
                    time.sleep(tempo_pausa)
                    self._recriar_sessao_com_historico_limitado(modelos_list[idx_modelo])
                    continue

                if is_quota or is_suspended or is_auth:
                    tentativas_conexao = 0
                    key_falha = self.api_keys[self.idx_api_atual]
                    cooldown_tempo = 90.0 if is_suspended else 60.0
                    self._api_key_cooldowns[key_falha] = time.time() + cooldown_tempo

                    novo_idx, nova_key, todas_em_cooldown = self._obter_proxima_chave_saudavel(excluir_atual=True)
                    if is_auth and todas_em_cooldown and idx_modelo + 1 >= len(modelos_list):
                        raise Exception(
                            "Autenticação Z.ai recusada (401/403). Verifique ZAI_API_KEY e o acesso ao modelo selecionado."
                        ) from erro
                    if todas_em_cooldown:
                        # Todas as contas de API esgotaram a quota neste modelo -> AVANÇA PARA O PRÓXIMO MODELO!
                        idx_modelo += 1
                        if idx_modelo >= len(modelos_list):
                            if rodada_fallback < max_rodadas_fallback:
                                tempo_espera = round(3.0 * rodada_fallback + random.uniform(1.0, 2.0), 1)
                                print(f"\n⚠️ Todas as contas e modelos esgotaram a quota na rodada {rodada_fallback}/{max_rodadas_fallback}. "
                                      f"Aguardando {tempo_espera}s para reset de quota...")
                                time.sleep(tempo_espera)
                                rodada_fallback += 1
                                idx_modelo = 0
                                self._api_key_cooldowns.clear()  # Limpa cooldowns para re-tentar na nova rodada
                            else:
                                idx_modelo -= 1
                                raise Exception(f"Todas as {len(self.api_keys)} contas e {len(modelos_list)} modelos esgotaram a quota no momento.")

                        self.modelo_atual = modelos_list[idx_modelo]
                        self.idx_api_atual = novo_idx
                        print(f"\n🔄 [Circuit Breaker] Todas as contas esgotaram a quota no modelo anterior! Avançando para modelo {self.modelo_atual} (chave {self.idx_api_atual + 1}/{len(self.api_keys)})...")
                    else:
                        self.idx_api_atual = novo_idx
                        motivo_chave = "Autenticação" if is_auth else "Quota/Suspensão"
                        print(f"\n⚡ [Circuit Breaker] {motivo_chave} na chave! Rotacionando imediatamente para chave {novo_idx + 1}/{len(self.api_keys)}...")

                    self._trocar_cliente_zai(self.api_keys[self.idx_api_atual])
                    self._recriar_sessao_com_historico_limitado(self.modelo_atual)
                    continue
                else:
                    erro_resumido = str(erro).strip().splitlines()[-1] if str(erro) else str(erro)
                    print(f"\n⚠️ Erro no modelo ({erro_resumido}): tentando próximo modelo...")
                    idx_modelo += 1
                    tentativas_conexao = 0
                    if idx_modelo >= len(modelos_list):
                        if is_conexao:
                            print("🔄 Tentando reconexão final do cliente antes de desistir...")
                            try:
                                self._trocar_cliente_zai(self.api_keys[self.idx_api_atual])
                                self._recriar_sessao_com_historico_limitado()
                            except Exception:
                                pass
                        idx_modelo -= 1
                        raise erro

                    self._recriar_sessao_com_historico_limitado(modelos_list[idx_modelo])
                    continue


    def _processar_zai_worker(self, user_input: str, arquivos: list[tuple[bytes, str]] = None, origem: str = "Discord", contexto_discord = None, status_callback = None, stream_callback = None) -> tuple[str, str | None]:
        from ayla_performance import measured, emit, stage
        task_id = self._task_id
        self.lock.acquire()
        try:
            ayla_state.ULTIMA_IMAGEM_GERADA.set(None)
            ayla_state.ULTIMO_ANEXO_IMAGEM.set(None)
            ayla_state.ULTIMO_ANEXO_AUDIO.set(None)
            ayla_state.ULTIMO_ARQUIVO_MIDIA.set(None)
            ayla_state.ULTIMO_ANEXO_VIDEO.set(None)
            ayla_state.CONTEXTO_ATIVO.set(contexto_discord)
            ayla_state.ULTIMAS_IMAGENS_MODULO.set([])

            def finalizar_interacao(resposta: str, img=None, status: str = "sucesso"):
                self._resultado_status = status
                resposta = proteger_confirmacao(resposta, getattr(self, '_tool_failures', {}))
                resposta_processada = processar_tags_midia_ayla(resposta)
                return resposta_processada, img

            contexto_privado = origem in ("GUI", "Terminal")
            if arquivos:
                for arq_bytes, tipo in arquivos:
                    if tipo.startswith("image/") and not ayla_state.ULTIMO_ANEXO_IMAGEM.get():
                        ayla_state.ULTIMO_ANEXO_IMAGEM.set((arq_bytes, tipo))
                    elif tipo.startswith("video/") and not ayla_state.ULTIMO_ANEXO_VIDEO.get():
                        pasta_video = BASE_DIR / "Buffer de video"
                        pasta_video.mkdir(parents=True, exist_ok=True)
                        import uuid
                        ext = ".mp4"
                        if "/" in tipo:
                            ext_sug = tipo.split("/")[-1]
                            if ext_sug in ("mp4", "webm", "mkv", "avi", "mov"):
                                ext = f".{ext_sug}"
                        caminho_video = pasta_video / f"video_{uuid.uuid4().hex[:8]}{ext}"
                        caminho_video.write_bytes(arq_bytes)
                        ayla_state.ULTIMO_ANEXO_VIDEO.set(str(caminho_video))

            try:
                # Identifica ID do autor
                autor_id = DISCORD_OWNER_ID if origem in ("GUI", "Terminal") else 0
                ctx = ayla_state.CONTEXTO_ATIVO.get()
                if origem not in ("GUI", "Terminal") and ctx is not None:
                    if hasattr(ctx, "author"):
                        autor_id = getattr(ctx.author, "id", 0)
                    elif hasattr(ctx, "user"):
                        autor_id = getattr(ctx.user, "id", 0)

                em_dm = bool(ctx is not None and getattr(ctx, "guild", None) is None)
                memoria_privada_permitida = origem in ("GUI", "Terminal") or (autor_id == DISCORD_OWNER_ID and em_dm)
                escopos_memoria = {"privada", "publica"} if memoria_privada_permitida else {"publica"}

                self.ayla_settings = carregar_configuracoes_ayla()
                measured('memory_maintenance', executar_revisao_automatica_memoria_se_necessario)

                # Ajusta dinamicamente a instrução do prompt em relação ao limite de fala/áudio
                sys_prompt_atual = montar_prompt_com_memoria(
                    incluir_diretrizes_privadas=memoria_privada_permitida,
                )
                if origem == "Discord-Call":
                    sys_prompt_atual += (
                        "\n[MODO CALL] Converse com todos os participantes humanos da chamada. "
                        "Não exija que a fala seja da dona para pensar ou responder. "
                        "Um lote pode conter várias pessoas: respeite a autoria indicada em cada "
                        "trecho e não atribua todas as falas à última pessoa ou à Usuario. "
                        "Pedidos de ação por voz usam as mesmas ferramentas do chat: emita "
                        "os function calls neste turno, ative o módulo necessário e execute "
                        "a ferramenta real antes de encerrar a resposta. Um aviso como 'vou "
                        "criar' não executa nada e não pode ser a resposta final ao pedido. "
                        "Não há execução automática depois que sua resposta termina. "
                        "O limite de 500 caracteres vale para a fala, não para as chamadas "
                        "de ferramentas nem para a execução da tarefa. Se faltar informação "
                        "essencial, pergunte; se a execução falhar, explique o erro real.\n"
                    )
                sys_prompt_atual = sys_prompt_atual.replace(
                    "- Como a sua fala de áudio é limitada a apenas 50 caracteres (letras), escreva textos bem curtinhos e diretos quando for usar a ferramenta de áudio!",
                    "- Como você está usando o Fish Audio, não há limite de caracteres para sua fala. Escreva livremente!"
                )
                self.config = self._construir_config_zai(
                    system_prompt=sys_prompt_atual,
                    tools=getattr(self, "tools_config", None) or build_tools()
                )
                if self.chat_session:
                    self.chat_session.config = self.config
                self.aparar_historico_chat()

                agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                if origem in ("GUI", "Terminal"):
                    usuario_nome = "Usuario"
                    local_info = origem
                    prefixo = f"[Data/Hora: {agora}] [local: {local_info}] [nome: {usuario_nome}] [id: {autor_id}]"
                elif origem == "Discord-Call":
                    autor = getattr(ctx, "author", None)
                    usuario_nome = str(getattr(autor, "display_name", "Participante da call"))
                    canal_nome = getattr(getattr(ctx, "channel", None), "name", "")
                    local_info = "Chamada de Voz do Discord" + (f" | Canal #{canal_nome}" if canal_nome else "")
                    prefixo = f"[Data/Hora: {agora}] [local: {local_info}] [nome: {usuario_nome}] [id: {autor_id}]"
                else:
                    usuario_nome = "Usuário"
                    local_info = "Discord"
                    ctx = ayla_state.CONTEXTO_ATIVO.get()
                    if ctx:
                        if hasattr(ctx, "author"):
                            usuario_nome = str(getattr(ctx.author, "display_name", ctx.author))
                        elif hasattr(ctx, "user"):
                            usuario_nome = str(getattr(ctx.user, "display_name", ctx.user))

                        guild_obj = getattr(ctx, "guild", None)
                        channel_obj = getattr(ctx, "channel", None)
                        canal_nome = getattr(channel_obj, "name", "") if channel_obj else ""

                        if guild_obj:
                            srv_nome = guild_obj.name
                            c_info = f" | Canal #{canal_nome}" if canal_nome else ""
                            if hasattr(ctx, "command") or type(ctx).__name__ == "Interaction":
                                local_info = f"Comando Slash no Servidor '{srv_nome}'{c_info}"
                            else:
                                local_info = f"Servidor '{srv_nome}'{c_info}"
                        else:
                            local_info = "Mensagem Direta (DM)"
                    prefixo = f"[Data/Hora: {agora}] [local: {local_info}] [nome: {usuario_nome}] [id: {autor_id}]"

                texto_formatado = f"{prefixo}: {user_input}" if user_input else f"{prefixo} enviou um arquivo"

                modelos_req = list(getattr(self, "modelos_padrao", []))
                if not modelos_req:
                    modelos_req = ["glm-5.3-flash"]

                from ayla_model_policy import select_start_model
                target_model = measured('model_selection', select_start_model, self, modelos_req)
                if getattr(self, "modelo_atual", None) != target_model:
                    print(f"🔄 Selecionando modelo para esta mensagem ({target_model})...")
                    self._recriar_sessao_com_historico_limitado(target_model)

                anexos_zai = []
                anexos_notificacao = []

                if arquivos:
                    for arq_bytes, arq_mime in arquivos:
                        if arq_mime.startswith("attachment:"):
                            nome_doc = arq_mime.split("attachment:", 1)[1]
                            anexos_notificacao.append(f"📎 [Arquivo anexado pelo usuário: '{nome_doc}']")
                        else:
                            mime_limpo = arq_mime.split(";")[0]
                            anexos_zai.append(ZaiAttachment(data=arq_bytes, mime_type=mime_limpo))

                # Monta o texto final
                tarefas = ayla_state.contexto_tarefas(self._conversation_key, incluir_todas=memoria_privada_permitida)
                texto_final = f"{tarefas}\n\n{texto_formatado}" if tarefas else texto_formatado
                contexto_memoria = measured('memory_retrieval', montar_contexto_memoria_relevante,
                    user_input,
                    escopos_permitidos=escopos_memoria,
                )
                if contexto_memoria:
                    texto_final = f"{contexto_memoria}\n\n{texto_final}"
                if anexos_notificacao:
                    info_anexos_str = "\n".join(anexos_notificacao)
                    texto_final = f"{info_anexos_str}\n\n{texto_final}"

                self._texto_usuario_enviado = texto_final
                texto_final = formatar_resumo(getattr(self, '_resumo_conversa', '')) + texto_final
                payload = ZaiMessage.user(text=texto_final, attachments=anexos_zai)
                # Preserve o texto original deste turno, inclusive horário e contexto.
                # O resumo não é duplicado no histórico persistido de cada turno.

                textos_acumulados = []

                def _stream_wrapper(texto_parcial_turno):
                    if not stream_callback:
                        return
                    # Uma resposta após falha só é publicada depois da conferência final.
                    if getattr(self, '_tool_failures', {}):
                        return
                    if texto_parcial_turno and texto_parcial_turno.strip():
                        try:
                            if (getattr(stream_callback, "live_mode", False)
                                    or getattr(stream_callback, "separate_turns", False)):
                                stream_callback(texto_parcial_turno.strip())
                            else:
                                prefixo_stream = "\n\n".join(
                                    texto.strip() for texto in textos_acumulados if texto and texto.strip()
                                )
                                texto_stream = texto_parcial_turno.strip()
                                if prefixo_stream and texto_stream != prefixo_stream:
                                    texto_stream = f"{prefixo_stream}\n\n{texto_stream}"
                                stream_callback(texto_stream)
                        except Exception:
                            pass

                if stream_callback:
                    for attr in ("is_live", "live_mode", "chunk_size", "max_interval"):
                        if hasattr(stream_callback, attr):
                            setattr(_stream_wrapper, attr, getattr(stream_callback, attr))
                    if hasattr(stream_callback, "feed_delta"):
                        def forward_delta(delta):
                            if not getattr(self, '_tool_failures', {}):
                                stream_callback.feed_delta(delta)
                        _stream_wrapper.feed_delta = forward_delta

                emit('context_ready')
                response = self.enviar_com_fallback(
                    [*getattr(self, '_historico_discord', []), payload],
                    modelos_list=modelos_req,
                    stream_callback=_stream_wrapper if stream_callback else None
                )

                loop_seguranca = 0


                while loop_seguranca < 50:
                    loop_seguranca += 1

                    if not response or (not response.text and not response.tool_calls):
                        break

                    fn_calls = list(response.tool_calls or [])
                    if response.text and response.text.strip():
                        t_strip = response.text.strip()
                        if t_strip not in textos_acumulados:
                            textos_acumulados.append(t_strip)

                    if not fn_calls: break

                    if hasattr(stream_callback, "on_tool_start"):
                        try:
                            stream_callback.on_tool_start(fn_calls[0].name if fn_calls else "")
                        except Exception as e_live:
                            print(f"⚠️ [Live TTS] Erro em on_tool_start: {e_live}")

                    # Formata a fala pré-ferramenta caso o modelo tenha falado antes de chamar a ferramenta
                    texto_pre_aviso = ""
                    if hasattr(status_callback, "on_notice"):
                        status_callback.on_notice(
                            processar_tags_midia_ayla((response.text or "").strip()),
                            fn_calls[0].name,
                        )
                    elif textos_acumulados:
                        texto_pre_bruto = "\n\n".join(t for t in textos_acumulados if t.strip())
                        if texto_pre_bruto.strip():
                            texto_pre_proc = preparar_rascunho_discord(texto_pre_bruto.strip())
                            texto_pre_aviso = f"{texto_pre_proc}\n\n"

                    fn_responses = []
                    somente_memoria_terminal = all(
                        fc.name in FERRAMENTAS_MEMORIA_TERMINAIS for fc in fn_calls
                    )
                    respostas_finais_terminais = []
                    acoes_terminais_ok = True
                    for tool_index, fc in enumerate(fn_calls):
                        nome = fc.name
                        args = dict(fc.arguments) if fc.arguments else {}
                        resposta_final_terminal = str(
                            args.pop("resposta_final", "") or ""
                        ).strip()

                        if status_callback:
                            if hasattr(status_callback, "on_tool_start"):
                                status_callback.on_tool_start(
                                    formatar_status_ferramenta(nome, args),
                                    nome=nome,
                                )
                            else:
                                status_callback(f"{texto_pre_aviso}{formatar_status_ferramenta(nome,args)}")
                        with stage('tool_execution', tool_index=tool_index):
                            resultado = executar_ferramenta(nome, args)
                        if hasattr(status_callback, "on_tool_result"):
                            status_callback.on_tool_result(resultado)

                        if somente_memoria_terminal:
                            acoes_terminais_ok = (
                                acoes_terminais_ok
                                and isinstance(resultado, ResultadoFerramenta)
                                and resultado.estado == 'verificado'
                            )
                            if resposta_final_terminal:
                                respostas_finais_terminais.append(resposta_final_terminal)

                        res_str = str(resultado)
                        if len(res_str) > 10000:
                            res_exibir = res_str[:10000] + "\n... [Resultado truncado no log do terminal por tamanho excessivo]"
                        else:
                            res_exibir = res_str

                        if "\n" in res_exibir:
                            print(f"   ➡️ Resultado:\n{res_exibir}")
                        else:
                            print(f"   ➡️ Resultado: {res_exibir}")

                        resultado_para_modelo = str(resultado)
                        if len(resultado_para_modelo) > MAX_RESULTADO_FERRAMENTA_CARACTERES:
                            resultado_para_modelo = (
                                resultado_para_modelo[:MAX_RESULTADO_FERRAMENTA_CARACTERES]
                                + "\n[Resultado truncado por segurança.]"
                            )

                        fn_responses.append(ZaiToolResult(
                            name=nome,
                            call_id=fc.id,
                            result=(resultado.para_modelo(MAX_RESULTADO_FERRAMENTA_CARACTERES)
                                    if isinstance(resultado, ResultadoFerramenta)
                                    else {"result": resultado_para_modelo}),
                        ))

                    if hasattr(stream_callback, "on_tool_end"):
                        try:
                            stream_callback.on_tool_end(fn_calls[0].name if fn_calls else "")
                        except Exception as e_live:
                            print(f"⚠️ [Live TTS] Erro em on_tool_end: {e_live}")

                    # Ações finais de memória não precisam reenviar prompt, histórico
                    # e resultado ao modelo. Em caso de falha ou ausência de resposta
                    # final, mantém o fluxo antigo para o modelo interpretar o resultado.
                    if (
                        somente_memoria_terminal
                        and acoes_terminais_ok
                        and respostas_finais_terminais
                    ):
                        resposta_terminal = respostas_finais_terminais[-1]
                        response = ZaiResponse(
                            text=resposta_terminal,
                            model=getattr(response, "model", None) or self.modelo_atual,
                        )
                        if stream_callback:
                            try:
                                if hasattr(stream_callback, "feed_delta"):
                                    stream_callback.feed_delta(resposta_terminal)
                                stream_callback(resposta_terminal)
                            except Exception:
                                pass
                        print("⚡ Ação de memória concluída sem nova chamada ao modelo.")
                        break

                    if status_callback:
                        try:
                            status_callback(f"{texto_pre_aviso}{obter_status_pensando_formatado()}")
                        except Exception as e_sc:
                            print(f"⚠️ Erro ao chamar status_callback: {e_sc}")

                    # Resultados e mídias seguem na mesma requisição, antes da resposta.
                    payload_ferramentas = [ZaiMessage.tool(result) for result in fn_responses]
                    ultimas_midias = ayla_state.ULTIMAS_IMAGENS_MODULO.get()
                    if ultimas_midias:
                        ayla_state.ULTIMAS_IMAGENS_MODULO.set([])
                        anexos_ferramenta = []
                        cont_midia = 0
                        has_video_or_audio = False

                        for item_dado, mime in ultimas_midias[:MAX_ANEXOS_POR_REQUISICAO]:
                            mime_limpo = str(mime).split(";")[0] if mime else "application/octet-stream"
                            is_video = mime_limpo.startswith("video/")
                            is_audio = mime_limpo.startswith("audio/")
                            if is_video or is_audio:
                                has_video_or_audio = True

                            # Se for caminho de arquivo (str ou Path)
                            if isinstance(item_dado, (str, Path)):
                                p_arq = Path(item_dado)
                                if p_arq.exists() and p_arq.is_file():
                                    if p_arq.stat().st_size <= MAX_BYTES_POR_ANEXO:
                                        b = p_arq.read_bytes()
                                        anexos_ferramenta.append(ZaiAttachment(data=b, mime_type=mime_limpo, filename=p_arq.name))
                                        cont_midia += 1
                                    else:
                                        print(
                                            f"   ⚠️ Mídia '{p_arq.name}' não enviada: a Z.ai não documenta "
                                            f"Files API equivalente e o arquivo excede 25 MB."
                                        )
                            elif isinstance(item_dado, bytes):
                                if len(item_dado) <= MAX_BYTES_POR_ANEXO:
                                    anexos_ferramenta.append(ZaiAttachment(data=item_dado, mime_type=mime_limpo))
                                    cont_midia += 1
                                    if mime_limpo.startswith("image/"):
                                        ayla_state.ULTIMO_ANEXO_IMAGEM.set((item_dado, mime_limpo))
                                else:
                                    print("   ⚠️ Mídia em memória não enviada à Z.ai porque excede 25 MB.")

                        if anexos_ferramenta:
                            if has_video_or_audio:
                                nota_midia = "[SISTEMA INTERNO]: Aqui está o vídeo/áudio copiado da área de transferência anexado na íntegra para sua análise visual e sonora completas:"
                                print(f"   ➡️ Enviando {cont_midia} mídia(s) (vídeo/áudio completo) junto com os resultados das ferramentas...")
                            else:
                                nota_midia = "[SISTEMA INTERNO]: Aqui está(ão) a(s) imagem(ns) capturada(s) pela ferramenta para sua análise visual:"
                                print(f"   ➡️ Enviando {cont_midia} imagem(ns) capturada(s) junto com os resultados das ferramentas...")
                            payload_ferramentas.append(
                                ZaiMessage.user(text=nota_midia, attachments=anexos_ferramenta))

                    response = self.enviar_com_fallback(
                        payload_ferramentas,
                        modelos_list=modelos_req,
                        stream_callback=_stream_wrapper if stream_callback else None
                    )


                # Extrai texto da resposta final (após todas as ferramentas)
                texto_resposta_final = (response.text or "").strip() if response else ""
                chamadas_pendentes = bool(response and response.tool_calls)

                status_final = "sucesso"
                if chamadas_pendentes and loop_seguranca >= 50:
                    texto_final = (
                        "Não consegui concluir a tarefa porque ela ultrapassou "
                        "o limite seguro de 50 rodadas de ferramentas."
                    )
                    status_final = "erro"
                else:
                    if texto_resposta_final and texto_resposta_final.strip():
                        texto_final = texto_resposta_final.strip()
                    elif textos_acumulados:
                        texto_final = "\n\n".join(t.strip() for t in textos_acumulados if t.strip())
                    else:
                        texto_final = "Não recebi uma resposta válida do modelo. Tente novamente."
                        status_final = "erro"

                if status_final == "erro":
                    try:
                        self._recriar_sessao_com_historico_limitado()
                    except Exception as e_reset:
                        print(f"⚠️ Auto-limpeza de sessão após erro: {e_reset}")

                img_gerada = ayla_state.ULTIMA_IMAGEM_GERADA.get()

                texto_final = proteger_confirmacao(texto_final, getattr(self, '_tool_failures', {}))

                # Deltas com falhas ficam retidos para não falar confirmações
                # indevidas. A resposta revisada ainda precisa ser pronunciada.
                if getattr(self, '_tool_failures', {}) and hasattr(stream_callback, 'feed_delta'):
                    stream_callback.feed_delta(texto_final)

                # U11: Registrar interação no histórico persistente
                _registrar_interacao(
                    channel_id=getattr(getattr(contexto_discord, 'channel', None), 'id', None),
                    user_id=autor_id,
                    user_input=user_input,
                    resposta=texto_final,
                    origem=origem,
                )

                # Processamento assíncrono de memória em background pelo Cérebro
                if ayla_cerebro is not None and status_final == "sucesso":
                    try:
                        ayla_cerebro.enfileirar_interacao(
                            user_input=user_input,
                            resposta=texto_final,
                            origem=origem,
                            autor_id=autor_id,
                        )
                    except Exception as e_cerebro:
                        print(f"⚠️ [Ayla] Erro ao enfileirar para o Cérebro: {e_cerebro}")

                return finalizar_interacao(texto_final, img_gerada, status_final)

            except Exception as e:
                from gemini_provider import GeminiContentBlockedError
                if isinstance(e, GeminiContentBlockedError):
                    print(f"⚠️ {e}")
                    return finalizar_interacao(e.user_message, None, "erro")
                import traceback
                traceback.print_exc()

                try:
                    self._recriar_sessao_com_historico_limitado()
                except Exception:
                    pass

                erro_final = (
                    f"Vish, capotei feio aqui: {e}"
                    if contexto_privado
                    else "Vish, ocorreu um erro interno enquanto eu processava a solicitação."
                )
                return finalizar_interacao(erro_final, None, "erro")

        finally:
            # Trava é exclusiva deste worker; registro não é compartilhado.
            self.lock.release()

            vid_temp = ayla_state.ULTIMO_ANEXO_VIDEO.get()
            if vid_temp and os.path.isfile(vid_temp):
                try:
                    pasta_buffer = (BASE_DIR / "Buffer de video").resolve()
                    p_vid = Path(vid_temp).resolve()
                    # Só remove se for um arquivo temporário gravado dentro do Buffer de video
                    if pasta_buffer in p_vid.parents:
                        os.remove(p_vid)
                        print(f"🧹 Vídeo temporário do buffer removido: {p_vid.name}")
                except Exception as e_rm:
                    print(f"⚠️ Erro ao apagar vídeo temporário: {e_rm}")
            _limpar_estado_ayla()

    def processar_zai(self, user_input: str, arquivos=None, origem="Discord", contexto_discord=None, status_callback=None, stream_callback=None, modo_modelo=None, historico_discord=None):
        if _DRAIN_REQUESTED.is_set():
            # Durante a troca de máquina, termina apenas o que já começou. Isso
            # evita iniciar outro turno que o host teria de interromper depois.
            return "Estou terminando o turno que já estava em andamento antes de trocar de máquina.", None
        # A restrição de autoria é exclusiva do chat. A recepção de voz já
        # exclui bots e entrega as falas de todos os participantes da call.
        if origem == "Discord-Call":
            pass
        elif contexto_discord is not None:
            autor = getattr(contexto_discord, "author", None) or getattr(contexto_discord, "user", None)
            if not DISCORD_OWNER_ID or getattr(autor, "id", None) != DISCORD_OWNER_ID:
                return "", None
        elif origem not in ("GUI", "Terminal"):
            return "", None
        from zai_provider import coletar_uso_zai
        from ayla_performance import begin, end, measured, perf_counter
        performance_started = perf_counter()

        # Copia apenas estado de inferência. A conexão Discord é usada pelos
        # módulos através do bot principal, nunca inicializada no worker.
        with self.lock:
            worker = copy.copy(self)
            from ayla_model_policy import policy_for_mode, ordered_models
            mode = "call" if origem == "Discord-Call" else modo_modelo
            worker.model_policy, recovery_mode = policy_for_mode(
                getattr(self, "model_policy", {}), getattr(self, "modelos_padrao", []), mode)
            worker.modelos_padrao = ordered_models(getattr(self, "modelos_padrao", []), worker.model_policy)
            worker.modelos_disponiveis = worker.modelos_padrao
            recovery = (getattr(self, "_mode_model_recovery", {}).get(recovery_mode)
                        if recovery_mode else getattr(self, "_model_recovery", None))
            worker._model_recovery = dict(recovery) if recovery else None
        worker.lock = threading.RLock()
        worker._conversation_key = self.chave_sessao_contextual(origem,contexto_discord)
        worker._task_id = new_task_id()
        worker._resultado_status = "erro"
        worker._tool_errors = set()
        worker._tool_failures = {}
        worker._resumo_conversa = ''
        worker._historico_discord = list(historico_discord or [])
        worker._texto_usuario_enviado = user_input or "[Anexo enviado]"
        seq, history, retained = self._conversation_store.begin(worker._conversation_key)
        self._memoria_sessao.iniciar_turno(worker._task_id, user_input or "[Anexo enviado]")
        worker.model_status = {}
        worker._api_key_cooldowns = {}
        worker._pool_clientes = {}
        worker._client_leases = []
        worker.api_keys = list(self.api_keys)
        worker.idx_api_atual = 0
        worker.chat_session = None
        worker_token = CURRENT_WORKER.set(worker)
        task_token = ayla_state.TAREFA_ATUAL.set(worker._task_id)
        registry_token = ACTIVE_REGISTRY.set(_MODULE_MANAGER.new_registry(retained))
        ayla_state.adicionar_tarefa(worker._task_id, user_input[:120] or "Analisando anexo", origem=origem,
                                   sessao=worker._conversation_key, status="respondendo")
        try:
            performance_token = begin(worker._task_id, performance_started)
            if not worker.api_keys:
                raise RuntimeError("Nenhuma chave Z.ai configurada.")
            worker._trocar_cliente_zai(worker.api_keys[0])
            worker.ayla_settings = carregar_configuracoes_ayla()
            worker.tools_config = build_tools()
            worker.config = worker._construir_config_zai(tools=worker.tools_config)
            with coletar_uso_zai() as uso_zai:
                worker._resumo_conversa, history = measured('context_compaction', self._conversation_store.compact_context,
                    worker._conversation_key,
                    lambda previous, turns: compactar_contexto(
                        worker.ayla_settings, worker.api_keys[0], previous, turns,
                        client_pool=worker._api_client_pool),
                    max_chars=MAX_CARACTERES_HISTORICO_CHAT,
                )
                worker.chat_session = worker.zai_client.create_session(
                    model=worker.modelo_atual, config=worker.config,
                    history=limitar_historico(history),
                )
                resposta, arquivo = worker._processar_zai_worker(user_input,arquivos,origem,contexto_discord,status_callback,stream_callback)
            # Guarda o mesmo texto enviado, sem reconstruir horário ou contexto.
            # Mídias são válidas apenas durante
            # a interação atual e não devem ser reenviadas nas próximas chamadas.
            self._conversation_store.finish(worker._conversation_key,seq,[
                ZaiMessage.user(text=worker._texto_usuario_enviado),
                ZaiMessage.assistant(text=resposta),
            ])
            try:
                self._conversation_store.save_to_file(BASE_DIR / "ayla_conversa_ativa.json")
            except Exception:
                pass
            self._memoria_sessao.finalizar_turno(worker._task_id)
            estado_final = "falhou" if worker._resultado_status!="sucesso" else ("parcial" if worker._tool_errors else "concluida")
            ayla_state.finalizar_tarefa(worker._task_id,estado_final)
            # Rodape apenas no texto enviado ao Discord, depois de salvar o historico.
            if origem in ("Discord", "Reply-Discord", "DM-Dona", "NomeCitado"):
                from gemini_catalog import is_gemini
                if not is_gemini(worker.modelo_atual) and uso_zai:
                    resposta += "\n\n-# " + " | ".join(uso_zai)
            return resposta,arquivo
        except Exception as exc:
            self._conversation_store.abandon(worker._conversation_key,seq)
            ayla_state.finalizar_tarefa(worker._task_id,"falhou")
            resposta = f"Não consegui concluir esta mensagem: {exc}"
            return resposta, None
        except BaseException:
            self._conversation_store.abandon(worker._conversation_key, seq)
            ayla_state.finalizar_tarefa(worker._task_id, "falhou")
            raise
        finally:
            with self.lock:
                self.model_status.update(worker.model_status)
                self.modelo_atual = worker.modelo_atual
                recovery = getattr(worker, "_model_recovery", None)
                if recovery_mode:
                    if not hasattr(self, "_mode_model_recovery"):
                        self._mode_model_recovery = {}
                    self._mode_model_recovery[recovery_mode] = dict(recovery) if recovery else None
                else:
                    self._model_recovery = dict(recovery) if recovery else None
            for lease in worker._client_leases:
                lease.close()
            end(performance_token)
            ACTIVE_REGISTRY.reset(registry_token)
            ayla_state.TAREFA_ATUAL.reset(task_token)
            CURRENT_WORKER.reset(worker_token)

def _limpar_estado_ayla(task_id: str = None):
    ayla_state.ULTIMA_IMAGEM_GERADA.set(None)
    ayla_state.CONTEXTO_ATIVO.set(None)
    ayla_state.ULTIMO_ANEXO_IMAGEM.set(None)
    ayla_state.ULTIMO_ANEXO_VIDEO.set(None)
    ayla_state.ULTIMO_ANEXO_AUDIO.set(None)
    ayla_state.ULTIMO_ARQUIVO_MIDIA.set(None)
    ayla_state.ULTIMAS_IMAGENS_MODULO.set([])
    if task_id:
        ayla_state.remover_tarefa(task_id)


def _registrar_interacao(channel_id, user_id, user_input, resposta, origem):
    """U11: Registra cada interação no histórico persistente (JSONL) sem cortar caracteres."""
    try:
        registro = {
            "timestamp": datetime.now().isoformat(),
            "channel_id": str(channel_id) if channel_id else None,
            "user_id": str(user_id) if user_id else None,
            "origem": origem,
            "input_resumo": (user_input or "").strip(),
            "output_resumo": (resposta or "").strip(),
        }
        with _HISTORICO_LOCK:
            with open(ARQUIVO_HISTORICO_INTERACOES, "a", encoding="utf-8") as f:
                f.write(json.dumps(registro, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"⚠️ Erro ao registrar interação: {e}")

bot = AylaBot()
carregar_modulos()
bot.inicializar_configuracao_zai()


# ══════════════════════════════════════════════════════════
#  HELPER DE ENVIO
# ══════════════════════════════════════════════════════════

async def _enviar_resposta(interaction: discord.Interaction, resposta: str, arquivo_discord=None, edit_original: bool = False, followup_msgs: list = None, textos_enviados: list = None):
    from ayla_discord_messages import dividir_com_metadados
    pedacos = dividir_com_metadados(resposta, dividir_mensagem_discord)
    followup_msgs = list(followup_msgs or [])
    textos_enviados = list(textos_enviados or [])

    if edit_original:
        if arquivo_discord:
            if followup_msgs:
                for fmsg in followup_msgs:
                    try:
                        await fmsg.delete()
                    except Exception:
                        pass
                followup_msgs.clear()
            try:
                await interaction.delete_original_response()
            except Exception as e:
                print(f"⚠️ Erro ao deletar original: {e}")
        else:
            try:
                await interaction.edit_original_response(content=pedacos[0])
                if len(textos_enviados) > 0:
                    textos_enviados[0] = pedacos[0]
                for i, pedaco in enumerate(pedacos[1:], start=1):
                    followup_idx = i - 1
                    if followup_idx < len(followup_msgs):
                        try:
                            await followup_msgs[followup_idx].edit(content=pedaco)
                            if len(textos_enviados) > i:
                                textos_enviados[i] = pedaco
                        except Exception as e_fedit:
                            print(f"⚠️ Erro ao editar followup ({followup_idx}): {e_fedit}")
                    else:
                        if pedaco.strip():
                            fmsg = await interaction.followup.send(pedaco, wait=True)
                            followup_msgs.append(fmsg)

                # Limpa followups excedentes caso o texto final seja menor que o stream
                if len(followup_msgs) > (len(pedacos) - 1):
                    for sobrou_fmsg in followup_msgs[len(pedacos) - 1:]:
                        try:
                            await sobrou_fmsg.delete()
                        except Exception:
                            pass
                    followup_msgs = followup_msgs[:len(pedacos) - 1]
                return
            except Exception as e:
                print(f"⚠️ Erro ao editar original, enviando followup: {e}")

    kwargs = {"file": arquivo_discord} if arquivo_discord else {}
    try:
        await interaction.followup.send(pedacos[0], **kwargs)
        for pedaco in pedacos[1:]:
            if pedaco.strip():
                await interaction.followup.send(pedaco)
    except discord.errors.Forbidden:
        print("⚠️ Sem permissão (403).")
    except Exception as e:
        print(f"Erro ao mandar resposta: {e}")


def tocar_audio_na_call(guild_id_or_obj, caminho_audio: str) -> bool:
    """Helper global para tocar áudio na chamada de voz do Discord ativa."""
    bot_inst = globals().get("bot")
    if not bot_inst:
        return False
    guild_id = getattr(guild_id_or_obj, "id", guild_id_or_obj)
    try:
        guild_id = int(guild_id)
        return bot_inst.tocar_audio_na_call(guild_id, caminho_audio)
    except Exception:
        return False


# ══════════════════════════════════════════════════════════
#  COMANDOS DISCORD
# ══════════════════════════════════════════════════════════

# ── Helper de Processamento e Resposta ──────────────────
async def processar_e_enviar_resposta(interaction: discord.Interaction, mensagem: str, anexos_list: list):
    if not DISCORD_OWNER_ID or interaction.user.id != DISCORD_OWNER_ID:
        return
    from ayla_discord_messages import MensagensTurnoDiscord, dividir_com_metadados
    await interaction.response.defer(ephemeral=False)
    primeira_mensagem = True

    async def enviar(texto, **kwargs):
        nonlocal primeira_mensagem
        if primeira_mensagem:
            anexo = kwargs.get("file")
            msg = await interaction.edit_original_response(
                content=texto,
                **({"attachments": [anexo]} if anexo is not None else {}),
            )
            primeira_mensagem = False
            return msg
        msg = await interaction.followup.send(texto, wait=True, **kwargs)
        return msg

    fluxo = MensagensTurnoDiscord(
        enviar,
        lambda texto: dividir_com_metadados(texto, dividir_mensagem_discord),
        preparar_rascunho_discord,
    )
    try:
        arquivos, erro_anexo = await ler_anexos_discord(anexos_list)
        if erro_anexo:
            await fluxo.finalizar(erro_anexo)
            return
        resposta, img_gerada = await asyncio.to_thread(
            bot.processar_zai,
            mensagem or "[Sem texto]",
            arquivos,
            "Discord",
            interaction,
            fluxo.status_callback,
            fluxo.stream_callback,
        )
    except Exception as exc:
        resposta = f"⚠️ Erro inesperado: {exc}"
        img_gerada = None

    arquivo_discord = None
    if img_gerada and Path(img_gerada).is_file():
        arquivo_discord = discord.File(img_gerada, filename=Path(img_gerada).name)
    try:
        await fluxo.finalizar(resposta, arquivo_discord)
    except discord.errors.Forbidden:
        print("⚠️ Sem permissão (403).")
    except Exception as exc:
        print(f"⚠️ Erro ao enviar resposta: {exc}")


# ── /ayla ────────────────────────────────────────────────
@bot.tree.command(name="ayla", description="Converse com a Ayla — controle total do PC")
@app_commands.describe(
    mensagem="O que quer que eu faça?",
    anexo="Anexo (imagem, áudio, vídeo, PDF, DOCX, TXT, CSV, XLSX...)"
)
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def cmd_ayla(
    interaction: discord.Interaction,
    mensagem: str = "",
    anexo: discord.Attachment = None
):
    if not DISCORD_OWNER_ID or interaction.user.id != DISCORD_OWNER_ID:
        await interaction.response.send_message("⚠️ Apenas a minha dona oficial (usuario Usuario) pode falar comigo!", ephemeral=True)
        return

    anexos_list = [anexo] if anexo is not None else []
    if not mensagem.strip() and not anexos_list:
        await interaction.response.send_message("⚠️ Fala alguma coisa comigo primeiro ou mande um anexo! https://media.tenor.com/DyqH3PQFYpsAAAAC/burn.gif ", ephemeral=True)
        return

    await processar_e_enviar_resposta(interaction, mensagem, anexos_list)


# ── /ayla_status ────────────────────────────────────────────
@bot.tree.command(name="ayla_status", description="Dashboard de status da Ayla")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def cmd_ayla_status(interaction: discord.Interaction):
    if not DISCORD_OWNER_ID or interaction.user.id != DISCORD_OWNER_ID:
        await interaction.response.send_message("⚠️ Apenas a minha dona pode ver o status!", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=False)
    try:
        import psutil
        ram_mb = psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
        ram_str = f"{ram_mb:.1f} MB"
    except Exception:
        ram_str = "N/A"

    api_key_mascarada = f"Key {bot.idx_api_atual + 1}/{len(bot.api_keys)}"
    modulos_carregados = len(MODULOS_CARREGADOS)
    modulos_adicionais = len(CATALOGO_MODULOS_ADICIONAIS) - len(_NOMES_MODULOS_ESSENCIAIS)
    modulos_continuos_cat = len(_NOMES_MODULOS_CONTINUOS)
    modulos_continuos_ativos = len(_MODULOS_CONTINUOS_ATIVOS)
    try:
        tarefas = ayla_state.listar_tarefas_detalhadas()
        tarefas_str = "\n".join(f"• {t['status']} • {t['descricao']}" for t in tarefas[:6]) if tarefas else "Nenhuma"
    except Exception:
        tarefas_str = "Nenhuma"

    # Latência do último modelo
    status_modelo = bot.model_status.get(bot.modelo_atual, {})
    latencia = status_modelo.get("latency", "N/A")
    status_str = status_modelo.get("status", "ok")

    # Métricas top 5 ferramentas
    metricas = ayla_state.obter_metricas()
    top_tools = sorted(metricas.items(), key=lambda x: x[1]["chamadas"], reverse=True)[:5]
    metricas_str = "\n".join(
        f"• `{nome}`: {m['chamadas']}x | {m['latencia_media_ms']}ms méd | {m['taxa_erro']}% erro"
        for nome, m in top_tools
    ) if top_tools else "Nenhuma métrica registrada ainda."

    # Extras espelhados da aba Status da GUI (tolerante a falhas)
    try:
        from ayla_cerebro import obter_status_cerebro
        cerebro = obter_status_cerebro()
        memoria_auto_str = (
            f"{cerebro.get('memorias_extraidas', 0)} extraídas · "
            f"{cerebro.get('total_analisados', 0)} analisados · fila: {cerebro.get('fila_pendente', 0)}"
        )
    except Exception:
        memoria_auto_str = "Indisponível"
    try:
        from ayla_embeddings import obter_status_carregamento, obter_status_indexacao
        idx_status = obter_status_indexacao()
        indexacao_str = f"{idx_status['indexadas']} indexadas · {idx_status['pendentes']} pendentes · {idx_status['falhas']} falhas"
        carregamento_str = obter_status_carregamento()
    except Exception:
        indexacao_str = "Indisponível"
        carregamento_str = "Indisponível"
    try:
        total_memorias = len(carregar_memoria())
    except Exception:
        total_memorias = 0
    try:
        from zai_provider import obter_gasto_total_sessao_zai, obter_gasto_total_acumulado_zai
        gasto_glm = f"US$ {obter_gasto_total_sessao_zai():.4f} (sessão) · US$ {obter_gasto_total_acumulado_zai():.4f} (total)"
    except Exception:
        gasto_glm = "Indisponível"
    try:
        from deepseek_consumo import obter_gasto_total_sessao_deepseek, obter_gasto_total_acumulado_deepseek
        gasto_dsk = f"US$ {obter_gasto_total_sessao_deepseek():.4f} (sessão) · US$ {obter_gasto_total_acumulado_deepseek():.4f} (total)"
    except Exception:
        gasto_dsk = "Indisponível"
    try:
        from deepseek_catalog import is_peak_time
        tarifa_str = "Pico (estimado)" if is_peak_time() else "Fora do pico · 50% do preço"
    except Exception:
        tarifa_str = "Indisponível"
    try:
        runtime = bot.obter_resumo_runtime() if hasattr(bot, "obter_resumo_runtime") else {}
        contexto_str = f"{runtime.get('tokens_estimados', 0):,} tokens · sessões: {runtime.get('sessoes', 0)}"
    except Exception:
        contexto_str = "Indisponível"
    papel = "🖥️ Host (servidor)" if os.getenv("AYLA_HOST_ROLE", "").strip().lower() == "host" else "💻 Local (PC)"

    embed = discord.Embed(
        title="📊 Dashboard da Ayla",
        color=discord.Color.from_rgb(56, 189, 248),
    )
    embed.add_field(name="📍 Onde estou", value=papel, inline=True)
    embed.add_field(name="🤖 Modelo Atual", value=f"`{bot.modelo_atual}`", inline=True)
    embed.add_field(name="⏱️ Latência", value=f"{latencia} ({status_str})", inline=True)
    embed.add_field(name="🔑 API Key", value=api_key_mascarada, inline=True)
    embed.add_field(name="💾 RAM", value=ram_str, inline=True)
    embed.add_field(name="📝 Ferramentas", value=f"{len(TOOL_MAP)} registradas", inline=True)
    embed.add_field(
        name="🧩 Módulos",
        value=f"{modulos_carregados} ativos ({modulos_continuos_ativos} contínuos) | {modulos_adicionais} catalogados ({modulos_continuos_cat} contínuos)",
        inline=False
    )
    embed.add_field(name="🧠 Memórias", value=f"{total_memorias} ativas · {carregamento_str}", inline=False)
    embed.add_field(name="🗂️ Indexação vetorial", value=indexacao_str, inline=True)
    embed.add_field(name="🪄 Memorização automática", value=memoria_auto_str, inline=True)
    embed.add_field(name="💬 Contexto", value=contexto_str, inline=True)
    embed.add_field(name="💰 Gasto GLM (Z.ai)", value=gasto_glm, inline=True)
    embed.add_field(name="💰 Gasto DeepSeek", value=f"{gasto_dsk}\nTarifa: {tarifa_str}", inline=True)
    embed.add_field(name="⚙️ Tarefas Ativas", value=tarefas_str, inline=False)
    embed.add_field(name="📊 Top Ferramentas", value=metricas_str, inline=False)
    embed.set_footer(text=f"🩵 Ayla v2.0 | {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")

    await interaction.followup.send(embed=embed)


# ── /aylaconfig ────────────────────────────────────────────
@bot.tree.command(name="aylaconfig", description="Configuração completa da Ayla (dona apenas)")
@app_commands.describe(
    acao="O que configurar ou consultar",
    chave="Chave (variável, memória, modelo, emoji ou GIF)",
    valor="Novo valor (para ações de salvar/editar)",
)
@app_commands.choices(acao=[
    app_commands.Choice(name="ENV: listar variáveis (valores ocultos)", value="env_listar"),
    app_commands.Choice(name="ENV: definir variável", value="env_set"),
    app_commands.Choice(name="ENV: remover variável", value="env_remover"),
    app_commands.Choice(name="Modelos: listar fila", value="modelos_listar"),
    app_commands.Choice(name="Modelos: adicionar à fila", value="modelo_add"),
    app_commands.Choice(name="Modelos: remover da fila", value="modelo_remover"),
    app_commands.Choice(name="Modelos: testar selecionados", value="modelos_testar"),
    app_commands.Choice(name="Voz: salvar chave TTS/STT", value="voz_chave"),
    app_commands.Choice(name="Mídias: listar emojis e GIFs", value="midias_listar"),
    app_commands.Choice(name="Mídias: adicionar emoji ou GIF", value="midia_add"),
    app_commands.Choice(name="Mídias: remover emoji ou GIF", value="midia_remover"),
    app_commands.Choice(name="Memória: buscar", value="memoria_buscar"),
    app_commands.Choice(name="Memória: criar ou editar", value="memoria_add"),
    app_commands.Choice(name="Memória: apagar (lixeira)", value="memoria_apagar"),
    app_commands.Choice(name="Memória: listar lixeira", value="memoria_lixeira"),
    app_commands.Choice(name="Memória: revisão estruturada", value="memoria_revisar"),
    app_commands.Choice(name="Cérebro: logs de memorização automática", value="cerebro_logs"),
    app_commands.Choice(name="Cérebro: conferir memórias úteis", value="cerebro_conferir"),
    app_commands.Choice(name="Tarefas: listar em andamento", value="tarefas_listar"),
])
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def cmd_aylaconfig(
    interaction: discord.Interaction,
    acao: app_commands.Choice[str],
    chave: str = "",
    valor: str = "",
):
    if not DISCORD_OWNER_ID or interaction.user.id != DISCORD_OWNER_ID:
        await interaction.response.send_message("⚠️ Apenas a minha dona pode mexer na minha configuração!", ephemeral=True)
        return

    LIMITE = 1900
    await interaction.response.defer(ephemeral=True)

    try:
        acao_valor = acao.value

        if acao_valor == "env_listar":
            variaveis = []
            if ENV_PATH.exists():
                for linha in ENV_PATH.read_text(encoding="utf-8").splitlines():
                    linha = linha.strip()
                    if linha and not linha.startswith("#") and "=" in linha:
                        nome_var = linha.split("=", 1)[0].strip()
                        oculta = "🔒" if any(s in nome_var.upper() for s in ("KEY", "TOKEN", "SECRET", "PASSWORD", "SENHA")) else "  "
                        variaveis.append(f"{oculta} {nome_var}")
            texto = f"🔐 Variáveis do .env ({len(variaveis)}):\n" + "\n".join(variaveis)

        elif acao_valor == "env_set":
            if not chave or not valor:
                texto = "⚠️ Informe a variável (chave) e o valor."
            else:
                linhas = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
                achou = False
                for i, linha in enumerate(linhas):
                    if linha.strip().startswith(f"{chave}="):
                        linhas[i] = f"{chave}={valor}"
                        achou = True
                        break
                if not achou:
                    linhas.append(f"{chave}={valor}")
                ENV_PATH.write_text("\n".join(linhas).rstrip() + "\n", encoding="utf-8")
                os.environ[chave] = valor
                texto = f"✅ {chave} gravada no .env e aplicada na sessão."

        elif acao_valor == "env_remover":
            if not chave:
                texto = "⚠️ Informe a variável (chave) a remover."
            else:
                linhas = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
                novas = [l for l in linhas if not l.strip().startswith(f"{chave}=")]
                if len(novas) == len(linhas):
                    texto = f"⚠️ {chave} não existe no .env."
                else:
                    ENV_PATH.write_text("\n".join(novas).rstrip() + "\n", encoding="utf-8")
                    os.environ.pop(chave, None)
                    texto = f"✅ {chave} removida do .env."

        elif acao_valor == "modelos_listar":
            fila = [m.get("name", "?") for m in bot.modelos_padrao]
            politica = getattr(bot, "model_policy", {})
            reserva_ativa = getattr(bot, "_model_recovery", None)
            texto = (
                "🔄 Ciclo padrão:\n• " + "\n• ".join(fila) +
                "\n\n🧭 Roteamento: " + json.dumps(politica, ensure_ascii=False) +
                (f"\n\n⚠️ Reserva em uso (reteste a cada {politica.get('testar_a_cada', '?')} msgs)" if reserva_ativa else "")
            )

        elif acao_valor == "modelo_add":
            from ayla_model_policy import ordered_models as _ordered_models
            if not chave:
                texto = "⚠️ Informe o nome do modelo (chave)."
            else:
                models_path = BASE_DIR / "ayla_models.json"
                try:
                    dados = json.loads(models_path.read_text(encoding="utf-8"))
                except Exception:
                    dados = {"padrao": []}
                fila = dados.setdefault("padrao", [])
                if any(m.get("name") == chave for m in fila):
                    texto = f"⚠️ `{chave}` já está na fila."
                else:
                    fila.append({"name": chave, "desc": valor or "Adicionado via /aylaconfig", "tags": []})
                    models_path.write_text(json.dumps(dados, indent=4, ensure_ascii=False), encoding="utf-8")
                    bot.modelos_padrao = _ordered_models([m.get("name", "") for m in fila], bot.model_policy)
                    bot.modelos_disponiveis = bot.modelos_padrao
                    texto = f"✅ `{chave}` adicionado à fila de reservas."

        elif acao_valor == "modelo_remover":
            from ayla_model_policy import ordered_models as _ordered_models
            if not chave:
                texto = "⚠️ Informe o nome do modelo a remover."
            else:
                models_path = BASE_DIR / "ayla_models.json"
                try:
                    dados = json.loads(models_path.read_text(encoding="utf-8"))
                except Exception:
                    dados = {"padrao": []}
                antes = len(dados.get("padrao", []))
                dados["padrao"] = [m for m in dados.get("padrao", []) if m.get("name") != chave]
                if len(dados["padrao"]) == antes:
                    texto = f"⚠️ `{chave}` não estava na fila."
                else:
                    models_path.write_text(json.dumps(dados, indent=4, ensure_ascii=False), encoding="utf-8")
                    bot.modelos_padrao = _ordered_models([m.get("name", "") for m in dados["padrao"]], bot.model_policy)
                    bot.modelos_disponiveis = bot.modelos_padrao
                    texto = f"✅ `{chave}` removido da fila."

        elif acao_valor == "modelos_testar":
            from zai_provider import ZaiChatConfig, ZaiMessage
            from ayla_provider import AylaClient
            resultados = []
            config = ZaiChatConfig(max_tokens=64, thinking_level="minimal")
            settings_teste = getattr(bot, "ayla_settings", {}) or {}
            for modelo in dict.fromkeys(bot.modelos_padrao):
                client = None
                try:
                    inicio = time.time()
                    client = AylaClient(api_key=bot.api_keys[bot.idx_api_atual] if bot.api_keys else "", settings=settings_teste)
                    res_teste = client.complete(model=modelo, messages=[ZaiMessage.user("Responda apenas OK")], config=config)
                    if not res_teste.text.strip():
                        raise RuntimeError("resposta vazia")
                    resultados.append(f"✅ {modelo} — {time.time() - inicio:.1f}s")
                except Exception as exc_teste:
                    resultados.append(f"❌ {modelo} — {str(exc_teste)[:80]}")
                finally:
                    if client is not None:
                        client.close()
            texto = "Teste de modelos:\n" + "\n".join(resultados)

        elif acao_valor == "voz_chave":
            mapa = {"FISH_AUDIO_API_KEY": "fish_audio_api_key", "FISH_AUDIO_VOICE_ID": "fish_audio_voice_id",
                    "GROQ_API_KEY": "groq_api_key", "GEMINI_API_KEY": "gemini_api_key"}
            if not chave or not valor:
                texto = "⚠️ Informe a chave (FISH_AUDIO_API_KEY, FISH_AUDIO_VOICE_ID, GROQ_API_KEY ou GEMINI_API_KEY) e o valor."
            elif chave.upper() not in mapa:
                texto = "⚠️ Use FISH_AUDIO_API_KEY, FISH_AUDIO_VOICE_ID, GROQ_API_KEY ou GEMINI_API_KEY."
            else:
                settings_path = BASE_DIR / "ayla_settings.json"
                try:
                    settings_voz = json.loads(settings_path.read_text(encoding="utf-8"))
                except Exception:
                    settings_voz = {}
                settings_voz[mapa[chave.upper()]] = valor
                settings_path.write_text(json.dumps(settings_voz, indent=4, ensure_ascii=False), encoding="utf-8")
                os.environ[chave.upper()] = valor
                try:
                    setattr(bot, "ayla_settings", settings_voz)
                except Exception:
                    pass
                texto = f"✅ {chave.upper()} salva nas configurações de voz."

        elif acao_valor == "midias_listar":
            midias = carregar_midias_ayla()
            emojis_str = "\n".join(f"• {k} → {v}" for k, v in midias.get("emojis", {}).items()) or "Nenhum"
            gifs_str = "\n".join(f"• {k} → {v}" for k, v in midias.get("gifs_e_fotos", {}).items()) or "Nenhum"
            texto = f"🌟 Emojis:\n{emojis_str}\n\n🎬 GIFs/Fotos:\n{gifs_str}"

        elif acao_valor == "midia_add":
            if not chave or not valor:
                texto = "⚠️ Informe o nome (chave) e a tag/URL (valor)."
            else:
                midias = carregar_midias_ayla()
                alvo = midias["emojis"] if valor.startswith("<") else midias["gifs_e_fotos"]
                tipo_midia = "emoji" if valor.startswith("<") else "GIF/foto"
                alvo[chave] = valor
                salvar_midias_ayla(midias)
                bot.prompt_com_memoria = montar_prompt_com_memoria()
                texto = f"✅ {tipo_midia.capitalize()} `{chave}` cadastrado."

        elif acao_valor == "midia_remover":
            if not chave:
                texto = "⚠️ Informe o nome do emoji/GIF a remover."
            else:
                midias = carregar_midias_ayla()
                removido = midias["emojis"].pop(chave, None) or midias["gifs_e_fotos"].pop(chave, None)
                if not removido:
                    texto = f"⚠️ `{chave}` não encontrado em emojis nem GIFs."
                else:
                    salvar_midias_ayla(midias)
                    bot.prompt_com_memoria = montar_prompt_com_memoria()
                    texto = f"✅ `{chave}` removido das mídias."

        elif acao_valor == "memoria_buscar":
            if not chave:
                texto = "⚠️ Informe o texto de busca."
            else:
                achadas = buscar_memorias_estruturadas(consulta=chave, limite=8)
                texto = formatar_memorias_encontradas(achadas, limite_caracteres=LIMITE) if achadas else "Nada encontrado."

        elif acao_valor == "memoria_add":
            if not chave or not valor:
                texto = "⚠️ Informe a chave da memória e o valor."
            else:
                resultado_mem = criar_ou_atualizar_memoria(chave, valor, sobrescrever=True, tag="Discord", origem="aylaconfig")
                texto = "✅ Memória salva!" if resultado_mem.get("ok") else f"⚠️ {resultado_mem.get('mensagem', 'Não foi possível salvar.')}"

        elif acao_valor == "memoria_apagar":
            if not chave:
                texto = "⚠️ Informe a chave da memória a apagar."
            else:
                resultado_mem = enviar_memoria_para_lixeira(chave, "Apagada via /aylaconfig")
                texto = "🗑️ Movida para a lixeira." if resultado_mem.get("ok") else f"⚠️ {resultado_mem.get('mensagem', 'Não foi possível apagar.')}"

        elif acao_valor == "memoria_lixeira":
            itens = listar_lixeira_memoria()
            texto = "\n".join(f"• {i['chave']} — {i['removida_em']}" for i in itens) or "A lixeira está vazia."

        elif acao_valor == "memoria_revisar":
            relatorio = revisar_memorias_estruturadas()
            texto = (
                f"Memórias ativas: {relatorio['total_ativas']}\n"
                f"Expiradas: {', '.join(relatorio['expiradas']) or 'nenhuma'}\n"
                f"Duplicatas: {', '.join(f'{a} ↔ {b}' for a, b, _ in relatorio['duplicatas']) or 'nenhuma'}\n"
                f"Conflitos: {', '.join(f'{a} ↔ {b}' for a, b in relatorio['possiveis_conflitos']) or 'nenhum'}\n"
                f"Lixeira: {relatorio['lixeira']}"
            )

        elif acao_valor == "cerebro_logs":
            if ayla_cerebro is None:
                texto = "⚠️ Cérebro indisponível nesta instância."
            else:
                logs_c = ayla_cerebro.listar_memorias_automaticas_log(limite=15)
                texto = "\n".join(
                    f"[{i.get('timestamp', '')[:16]}] {'🛡️' if i.get('status') == 'descartado_similaridade' else '🧠'} {i.get('chave', '')} → {i.get('valor', '')[:60]}"
                    for i in logs_c
                ) or "Nenhum log ainda."

        elif acao_valor == "cerebro_conferir":
            if ayla_cerebro is None:
                texto = "⚠️ Cérebro indisponível nesta instância."
            else:
                relatorio_c = ayla_cerebro.conferir_memorias_uteis()
                if relatorio_c.get("ok"):
                    apagadas_c = relatorio_c.get("apagadas", [])
                    texto = (
                        f"Analisadas: {relatorio_c.get('analisadas', 0)} · mantidas: {relatorio_c.get('mantidas', 0)} · removidas: {len(apagadas_c)}\n" +
                        "\n".join(f"• {m.get('chave', '')}: {m.get('motivo', '')}" for m in apagadas_c[:15])
                    )
                else:
                    texto = f"⚠️ {relatorio_c.get('mensagem', 'Conferência falhou.')}"

        elif acao_valor == "tarefas_listar":
            tarefas_cfg = ayla_state.listar_tarefas_detalhadas()
            texto = "\n".join(f"• {t['status']} • {t['origem']} • {t['descricao']}" for t in tarefas_cfg) or "Nenhuma tarefa."

        else:
            texto = f"⚠️ Ação desconhecida: {acao_valor}"

    except Exception as exc_cfg:
        texto = f"❌ Erro: {type(exc_cfg).__name__}: {str(exc_cfg)[:400]}"

    texto = str(texto or "").strip() or "(vazio)"
    pedacos_cfg = dividir_mensagem_discord(texto, LIMITE)
    await interaction.followup.send(pedacos_cfg[0], ephemeral=True)
    for pedaco_extra in pedacos_cfg[1:5]:
        await interaction.followup.send(pedaco_extra, ephemeral=True)


# ── /ayla_reload ────────────────────────────────────────────
@bot.tree.command(name="ayla_reload", description="Recarrega todos os módulos sem reiniciar")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def cmd_ayla_reload(interaction: discord.Interaction):
    if not DISCORD_OWNER_ID or interaction.user.id != DISCORD_OWNER_ID:
        await interaction.response.send_message("⚠️ Apenas a minha dona pode recarregar módulos!", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=False)
    try:
        qtd_antes = len(TOOL_MAP)

        carregar_modulos()
        bot.atualizar_prompt_memoria()
        bot.atualizar_ferramentas_zai()

        qtd_depois = len(TOOL_MAP)
        diff = qtd_depois - qtd_antes
        diff_str = f" ({'+' if diff > 0 else ''}{diff} ferramenta(s))" if diff != 0 else ""
        await interaction.followup.send(
            f"✨ Módulos recarregados com sucesso!\n"
            f"📦 {qtd_depois} ferramentas ativas{diff_str}\n"
            f"📚 {len(CATALOGO_MODULOS_ADICIONAIS) - len(_NOMES_MODULOS_ESSENCIAIS)} módulos adicionais catalogados ({len(_NOMES_MODULOS_CONTINUOS)} contínuos)"
        )
    except Exception as e:
        await interaction.followup.send(f"❌ Erro ao recarregar módulos: {e}")
# ── Bot Discord em thread separada ──
_DISCORD_THREAD_LOCK = threading.Lock()
_discord_thread = None


async def _iniciar_sessao_discord():
    from ayla_discord_startup import run_discord_client, describe_discord_error
    ayla_state.BOT_LAUNCH_ERROR.set(None)
    try:
        await run_discord_client(bot, DISCORD_TOKEN, stop_requested=_SHUTDOWN_REQUESTED.is_set)
    except Exception as error:
        message = describe_discord_error(error)
        ayla_state.BOT_LAUNCH_ERROR.set(message)
        print(f"\n⚠️ Não foi possível iniciar o bot Discord: {message}\n")


def run_discord_bot_thread():
    global _discord_thread
    def _run():
        asyncio.run(_iniciar_sessao_discord())

    with _DISCORD_THREAD_LOCK:
        if _discord_thread is not None and _discord_thread.is_alive():
            return _discord_thread
        _discord_thread = threading.Thread(target=_run, daemon=True, name="Ayla-Discord")
        _discord_thread.start()
        print("Bot Discord iniciando em background...")
        return _discord_thread


# ══════════════════════════════════════════════════════════
#  SHUTDOWN GRACEFUL
# ══════════════════════════════════════════════════════════
_SHUTDOWN_REQUESTED = threading.Event()
_DRAIN_REQUESTED = threading.Event()


def _solicitar_drenagem(signum=None, frame=None):
    """Fecha somente depois dos turnos em andamento; usado pelo host autenticado."""
    if _DRAIN_REQUESTED.is_set() or _SHUTDOWN_REQUESTED.is_set():
        return
    _DRAIN_REQUESTED.set()
    try:
        timeout = max(15, min(900, int(os.getenv("AYLA_HOST_DRAIN_TIMEOUT_SECONDS", "130"))))
    except ValueError:
        timeout = 130
    print("🩵 Transferência solicitada: terminando os turnos já iniciados antes de encerrar...")

    def aguardar_turnos():
        limite = time.monotonic() + timeout
        while time.monotonic() < limite:
            if not ayla_state.listar_tarefas_detalhadas():
                print("🩵 Turnos concluídos; liberando a Ayla para a transferência.")
                _solicitar_shutdown(pular_resumo_sessao=True)
                return
            time.sleep(0.4)
        print("⚠️ A drenagem atingiu o prazo; a Ayla continua aberta para não cortar um turno.")

    threading.Thread(target=aguardar_turnos, daemon=True, name="AylaDrain").start()

def _solicitar_shutdown(signum=None, frame=None, *, pular_resumo_sessao=False):
    """Solicita shutdown graceful em vez de matar o processo abruptamente."""
    if _SHUTDOWN_REQUESTED.is_set():
        if signum is None:
            return
        print("\n🩵 Forçando encerramento imediato...")
        os._exit(130)
    _SHUTDOWN_REQUESTED.set()
    print("\n🩵 Ayla encerrando graciosamente...")
    try:
        if 'bot' in globals() and bot and hasattr(bot, '_conversation_store'):
            bot._conversation_store.save_to_file(BASE_DIR / "ayla_conversa_ativa.json")
    except Exception:
        pass
    try:
        from zai_provider import salvar_consumo_zai
        salvar_consumo_zai()
    except Exception as erro:
        print(f"⚠️ Não foi possível salvar o consumo Z.ai ({type(erro).__name__}).")
    try:
        from deepseek_consumo import salvar_consumo_deepseek
        salvar_consumo_deepseek()
    except Exception as erro:
        print(f"⚠️ Não foi possível salvar o consumo DeepSeek ({type(erro).__name__}).")

    if not pular_resumo_sessao:
        try:
            from ayla_sessao import salvar_resumo_encerramento
            print(f"🧠 Gerando resumo da sessão com {bot.modelo_atual} (até 20s; máximo 1.000 caracteres)...")
            registro = salvar_resumo_encerramento(bot)
            tipo = 'Resumo por IA' if registro.get('resumo_status') == 'gerado' else 'Registro básico/contexto anterior'
            print(f"🧠 {tipo} salvo em ayla_ultima_sessao.json — {registro['encerrada_em']}")
        except Exception as erro:
            print(f"⚠️ Não foi possível salvar o resumo da sessão: {erro}")
    else:
        print("🧠 Resumo por IA não foi gerado: o estado completo foi entregue ao host.")

    # Inclui também eventual consumo do resumo de encerramento.
    try:
        from zai_provider import salvar_consumo_zai
        salvar_consumo_zai()
    except Exception as erro:
        print(f"⚠️ Não foi possível salvar o consumo Z.ai ({type(erro).__name__}).")
    try:
        from deepseek_consumo import salvar_consumo_deepseek
        salvar_consumo_deepseek()
    except Exception as erro:
        print(f"⚠️ Não foi possível salvar o consumo DeepSeek ({type(erro).__name__}).")

    # Também encerra o pool quando o gateway Discord já está fechado.
    try:
        bot.fechar_clientes_api()
    except Exception as erro:
        print(f"⚠️ Não foi possível fechar os clientes de API: {erro}")

    # U14: Salvar métricas no disco antes de sair
    try:
        metricas = ayla_state.obter_metricas()
        if metricas:
            metricas_path = BASE_DIR / "ayla_metrics.json"
            _escrever_json_atomico(metricas_path, metricas, criar_backup=False)
            print("📊 Métricas salvas em ayla_metrics.json")
    except Exception as erro:
        print(f"⚠️ Não foi possível salvar as métricas: {erro}")

    # Parar worker do cérebro de forma limpa
    try:
        import ayla_cerebro
        ayla_cerebro.parar_cerebro()
    except Exception:
        pass

    # Fix #4: Usa bot.discord_loop em vez de asyncio.get_event_loop()
    try:
        if 'bot' in globals() and bot and not bot.is_closed():
            try:
                loop = getattr(bot, 'discord_loop', None)
                if loop and loop.is_running():
                    asyncio.run_coroutine_threadsafe(bot.close(), loop)
                else:
                    asyncio.run(bot.close())
            except Exception as e_close:
                print(f"⚠️ Não foi possível fechar o bot graceful: {e_close}")
    except Exception:
        pass

    # Solicitar encerramento da interface gráfica Qt se estiver rodando
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QTimer
        app = QApplication.instance()
        if app is not None:
            QTimer.singleShot(0, app.quit)
    except Exception:
        pass

    # Dá um tempinho pra flush de arquivos e desconexão; se ainda não saiu, força a saída
    def _force_exit():
        time.sleep(2.5)
        os._exit(0)
    threading.Thread(target=_force_exit, daemon=True, name="AylaForceExit").start()


def _encerrar_pelo_gui_com_transferencia():
    """Entrega o estado ao host antes de fechar a única instância local."""
    if _transferir_estado_para_host():
        _solicitar_shutdown(pular_resumo_sessao=True)
        return True
    return False


def _transferir_estado_para_host(on_progress=None):
    """Executa somente a entrega; a GUI a chama fora da thread visual."""
    if host_client_from_environment is None:
        return True
    try:
        client = host_client_from_environment(code_dir=_AYLA_HOST_DIR)
    except HandoffError as erro:
        print(f"⚠️ Não foi possível preparar a transferência para o host: {erro}")
        return False
    if client is None:
        return True
    try:
        # Não deixa a curadoria/embeddings continuar escrevendo ou fazendo
        # chamadas enquanto os arquivos persistentes são fotografados para o
        # host. Turnos de conversa já ativos continuam protegidos pelo fluxo
        # normal de encerramento, mas novas tarefas do cérebro param aqui.
        try:
            import ayla_cerebro
            ayla_cerebro.parar_cerebro()
        except Exception:
            pass
        try:
            if 'bot' in globals() and bot and hasattr(bot, '_conversation_store'):
                bot._conversation_store.save_to_file(BASE_DIR / "ayla_conversa_ativa.json")
                from ayla_sessao import salvar_resumo_encerramento
                salvar_resumo_encerramento(bot)
                print("💬 [Ayla Conversa]: Turnos ativos e resumo salvos para envio ao host!")
        except Exception as erro:
            print(f"⚠️ Não foi possível salvar conversa ativa antes da transferência: {erro}")
        client.transfer_to_host(BASE_DIR, on_progress=on_progress)
        return True
    except HandoffError as erro:
        print(f"⚠️ A transferência para o host falhou inicialmente ({erro}). Forçando liberação do host e tentando novamente...")
        try:
            client.force_stop_host()
            time.sleep(1.0)
            client.transfer_to_host(BASE_DIR, on_progress=on_progress)
            return True
        except Exception as retry_err:
            print(f"⚠️ A transferência para o host falhou; a Ayla local continua aberta: {retry_err}")
            return False


def _finalizar_encerramento_apos_transferencia():
    print("🩵 O host confirmou que a Ayla foi iniciada. Encerrando esta instância local.")
    _solicitar_shutdown(pular_resumo_sessao=True)
    return True


_encerrar_pelo_gui_com_transferencia.requires_handoff_confirmation = bool(
    os.getenv("AYLA_HOST_URL", "").strip() or os.getenv("AYLA_HOST_TOKEN", "").strip()
) and os.getenv("AYLA_HOST_ROLE", "").strip().lower() != "host"
_encerrar_pelo_gui_com_transferencia.transfer_to_host_in_background = _transferir_estado_para_host
_encerrar_pelo_gui_com_transferencia.finish_handoff_shutdown = _finalizar_encerramento_apos_transferencia


if __name__ == "__main__":
    import signal
    signal.signal(signal.SIGINT, _solicitar_shutdown)
    try:
        signal.signal(signal.SIGTERM, _solicitar_shutdown)
    except (AttributeError, ValueError):
        pass  # SIGTERM pode não existir no Windows
    try:
        signal.signal(signal.SIGUSR1, _solicitar_drenagem)
    except (AttributeError, ValueError):
        pass  # SIGUSR1 não existe no Windows

    from colorama import Fore, Style
    print("\n" + "═" * 60)
    print(r"🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵")
    print(Fore.CYAN + r" .----------------. .----------------. .----------------. .----------------.")
    print(r"| .--------------. | .--------------. | .--------------. | .--------------. |")
    print(r"| |      __      | | |  ____  ____  | | |   _____      | | |      __      | |")
    print(r"| |     /  \     | | | |_  _||_  _| | | |  |_   _|     | | |     /  \     | |")
    print(r"| |    / /\ \    | | |   \ \  / /   | | |    | |       | | |    / /\ \    | |")
    print(r"| |   / ____ \   | | |    \ \/ /    | | |    | |   _   | | |   / ____ \   | |")
    print(r"| | _/ /    \ \_ | | |    _|  |_    | | |   _| |__/ |  | | | _/ /    \ \_ | |")
    print(r"| ||____|  |____|| | |   |______|   | | |  |________|  | | ||____|  |____|| |")
    print(r"| |              | | |              | | |              | | |              | |")
    print(r"| '--------------' | '--------------' | '--------------' | '--------------' |")
    print(r"'----------------' '----------------' '----------------' '------------------'")
    print(Style.RESET_ALL)
    print(r"🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵🩵")


    print("═" * 60 + "\n")

    abrir_gui_env = os.getenv("ABRIR_GUI", "true").lower() == "true"
    if abrir_gui_env:
        run_discord_bot_thread()
        try:
            from ayla_gui import abrir_gui
            print("🩵 Abrindo interface gráfica...")
            abrir_gui(bot, shutdown_callback=_encerrar_pelo_gui_com_transferencia)
            # Mantém a thread principal viva após fechar a GUI
            import time
            while not _SHUTDOWN_REQUESTED.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            _solicitar_shutdown()
        except Exception as e:
            print(f"⚠️ Erro ao abrir GUI: {e}")
            print("🩵 Mantendo o bot Discord em background...")
            try:
                discord_thread = run_discord_bot_thread()
                while discord_thread.is_alive() and not _SHUTDOWN_REQUESTED.is_set():
                    discord_thread.join(timeout=0.5)
            except KeyboardInterrupt:
                _solicitar_shutdown()
    else:
        print("🩵 Iniciando bot no thread principal...")
        try:
            asyncio.run(_iniciar_sessao_discord())
        except KeyboardInterrupt:
            _solicitar_shutdown()
