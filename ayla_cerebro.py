"""
ayla_cerebro.py — Sistema Completo de RAG Híbrido, Armazenamento Persistente e Extração Assíncrona da Ayla 🧠🐾

Módulo unificado e desacoplado que centraliza:
1. Sistema de Armazenamento Atômico e Persistente de Memória (com locks e backups .bak)
2. Motor RAG Híbrido (Palavras/IDF, Embeddings Gemini e Filtro Adaptativo de Relevância)
3. Curadoria e Manutenção Estruturada de Memórias (CRUD, Lixeira, Histórico, Expiração e Revisão Automática)
4. Extrator Assíncrono em Segundo Plano (Cérebro em Background com Gemini e fallback Groq - Estilo MemGPT)
"""

from __future__ import annotations

import os
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

import html
import json
import time
import math
import queue
import re
import shutil
import copy
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from difflib import SequenceMatcher

def _log_cerebro(msg: str):
    """Exibe mensagens no console de forma segura para evitar erros de charset no Windows."""
    try:
        print(msg)
    except Exception:
        try:
            seguro = msg.encode("ascii", errors="backslashreplace").decode("ascii")
            print(seguro)
        except Exception:
            pass


# ══════════════════════════════════════════════════════════
#  CONFIGURAÇÃO DE AMBIENTE E CAMINHOS DE ARQUIVO
# ══════════════════════════════════════════════════════════
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
try:
    from dotenv import load_dotenv
    load_dotenv(ENV_PATH, override=True)
except ImportError:
    pass

ARQUIVO_MEMORIA = BASE_DIR / "Ayla_Memoria.json"
ARQUIVO_MEMORIA_LIXEIRA = BASE_DIR / "Ayla_Memoria_lixeira.json"
ARQUIVO_MEMORIA_HISTORICO = BASE_DIR / "Ayla_Memoria_historico.jsonl"
ARQUIVO_STOPWORDS_MEMORIA = BASE_DIR / "ayla_stopwords.json"
ARQUIVO_CONFIG_AYLA = BASE_DIR / "ayla_settings.json"
ARQUIVO_MEMORIAS_LOG = BASE_DIR / "ayla_memorias_automaticas.jsonl"

DISCORD_OWNER_ID = int(os.getenv("DISCORD_OWNER_ID", "CONFIGURE_LOCALMENTE") or "CONFIGURE_LOCALMENTE")

# Locks e Controles de Cache
_MEMORIA_LOCK = threading.RLock()
_MEMORIA_SEGURA_PARA_GRAVAR = True
_MEMORIA_CACHE = None
_MEMORIA_CACHE_TIME = 0.0
_MEMORIA_CACHE_STAMP = None
_MEMORIA_CACHE_TTL = 30.0  # segundos
_MEMORIA_ACESSOS_PENDENTES: dict[str, int] = {}
_MEMORIA_ULTIMO_FLUSH_ACESSOS = 0.0
_MEMORIA_SCHEMA_VERSION = 2
_MEMORIA_TIPOS_VALIDOS = {
    "preferencia", "pessoa", "projeto", "regra", "momento", "contexto", "lore", "outro"
}

_CONFIG_LOCK = threading.RLock()


# ══════════════════════════════════════════════════════════
#  I/O ATÔMICO E SEGURO COM BACKUP AUTOMÁTICO
# ══════════════════════════════════════════════════════════

def _backup_path(path: Path) -> Path:
    return path.with_name(path.name + ".bak")


def _json_valido(path: Path) -> bool:
    try:
        json.loads(path.read_text(encoding="utf-8"))
        return True
    except Exception:
        return False


def _escrever_texto_atomico(path: Path, texto: str, criar_backup: bool = True):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporario = path.with_name(path.name + ".tmp")
    with open(temporario, "w", encoding="utf-8", newline="") as f:
        f.write(texto)
        f.flush()
        try:
            os.fsync(f.fileno())
        except Exception:
            pass

    if criar_backup and path.exists() and _json_valido(path):
        try:
            shutil.copy2(path, _backup_path(path))
        except Exception:
            pass
    os.replace(temporario, path)


def _escrever_json_atomico(path: Path, dados, criar_backup: bool = True):
    texto = json.dumps(dados, indent=4, ensure_ascii=False)
    _escrever_texto_atomico(path, texto, criar_backup=criar_backup)


def _carregar_json_com_backup(path: Path, padrao):
    erros = []
    for candidato in (path, _backup_path(path)):
        if not candidato.exists():
            continue
        try:
            return json.loads(candidato.read_text(encoding="utf-8")), candidato, erros
        except Exception as e:
            erros.append(f"{candidato.name}: {e}")
    return padrao, None, erros


# ══════════════════════════════════════════════════════════
#  NORMALIZAÇÃO, DATAS E CARACTERES
# ══════════════════════════════════════════════════════════

def _agora_memoria_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


_MAPA_ACENTOS = str.maketrans({
    "à": "a", "á": "a", "â": "a", "ã": "a", "ä": "a", "å": "a",
    "è": "e", "é": "e", "ê": "e", "ë": "e",
    "ì": "i", "í": "i", "î": "i", "ï": "i",
    "ò": "o", "ó": "o", "ô": "o", "õ": "o", "ö": "o",
    "ù": "u", "ú": "u", "û": "u", "ü": "u",
    "ý": "y", "ÿ": "y", "ñ": "n", "ç": "c",
    "À": "A", "Á": "A", "Â": "A", "Ã": "A", "Ä": "A", "Å": "A",
    "È": "E", "É": "E", "Ê": "E", "Ë": "E",
    "Ì": "I", "Í": "I", "Î": "I", "Ï": "I",
    "Ò": "O", "Ó": "O", "Ô": "O", "Õ": "O", "Ö": "O",
    "Ù": "U", "Ú": "U", "Û": "U", "Ü": "U",
    "Ý": "Y", "Ÿ": "Y", "Ñ": "N", "Ç": "C",
})


def _texto_memoria_normalizado(valor) -> str:
    """Normaliza texto para busca: lowercase, remove acentos com mapeamento controlado, colapsa espaços."""
    texto = str(valor or "").lower().translate(_MAPA_ACENTOS)
    return re.sub(r"\s+", " ", texto).strip()


def normalizar_chave_memoria(chave: str) -> str:
    chave = _texto_memoria_normalizado(chave)
    return re.sub(r"[^a-z0-9]+", "_", chave).strip("_")[:90]


def _parse_data_memoria(valor):
    if not valor:
        return None
    if isinstance(valor, datetime):
        return valor
    texto = str(valor).strip()
    for formato in (None, "%d/%m/%Y %H:%M:%S", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            if formato is None:
                return datetime.fromisoformat(texto.replace("Z", "+00:00"))
            return datetime.strptime(texto.split(" (")[0], formato)
        except (TypeError, ValueError):
            continue
    return None


def _formatar_data_memoria(valor: str | None = None) -> str:
    data = _parse_data_memoria(valor) if valor else datetime.now()
    return data.strftime("%d/%m/%Y %H:%M:%S") if data else str(valor or "")


def _tipo_memoria_inferido(chave: str, valor: str, tag: str) -> str:
    texto = _texto_memoria_normalizado(f"{chave} {tag} {valor}")
    if any(p in texto for p in ("gosta", "prefere", "favorit", "nao gosta", "odeia")):
        return "preferencia"
    if any(p in texto for p in ("aniversario", "privacidade", "so devo", "regra", "nunca", "sempre")):
        return "regra"
    if any(p in texto for p in ("projeto", "historia", "codigo", "github", "vtuber")):
        return "projeto"
    if any(p in texto for p in ("conversa", "momento", "aconteceu", "dia")):
        return "momento"
    return "outro"


def _normalizar_escopo_memoria(escopo) -> str:
    escopo = _texto_memoria_normalizado(escopo)
    if escopo in {"publica", "publico", "public", "compartilhavel"}:
        return "publica"
    return "privada"


def _normalizar_importancia_memoria(valor, padrao: int = 3) -> int:
    try:
        return max(1, min(5, int(valor)))
    except (TypeError, ValueError):
        return padrao


def normalizar_registro_memoria(chave: str, valor) -> dict:
    """Converte memórias antigas para o formato atual sem descartar campos legados."""
    bruto = dict(valor) if isinstance(valor, dict) else {"Valor": valor}
    texto = str(bruto.get("Valor", bruto.get("valor", ""))).strip()
    data_legada = bruto.get("Data e hora", bruto.get("data_hora", ""))
    data_criacao = _parse_data_memoria(data_legada)
    criada_em = bruto.get("criada_em") or (
        data_criacao.astimezone().isoformat(timespec="seconds")
        if data_criacao and data_criacao.tzinfo else (data_criacao.replace(tzinfo=datetime.now().astimezone().tzinfo).isoformat(timespec="seconds") if data_criacao else _agora_memoria_iso())
    )
    tags_brutas = bruto.get("tags", [])
    if isinstance(tags_brutas, str):
        tags_brutas = [tags_brutas]
    if not isinstance(tags_brutas, list):
        tags_brutas = []
    tag_legada = str(bruto.get("tag", bruto.get("Tag", "Gerais"))).strip() or "Gerais"
    tags = []
    for tag in [tag_legada, *tags_brutas]:
        tag_limpa = str(tag).strip()
        if tag_limpa and tag_limpa.lower() not in {t.lower() for t in tags}:
            tags.append(tag_limpa[:50])

    tipo = _texto_memoria_normalizado(bruto.get("tipo", ""))
    if tipo not in _MEMORIA_TIPOS_VALIDOS:
        tipo = _tipo_memoria_inferido(chave, texto, tag_legada)
    try:
        acessos = max(0, int(bruto.get("acessos", 0)))
    except (TypeError, ValueError):
        acessos = 0
    importancia_padrao = 4 if tipo in {"preferencia", "pessoa", "regra"} else 3
    if acessos >= 15:
        importancia_padrao = min(5, importancia_padrao + 1)

    registro = {
        "versao": _MEMORIA_SCHEMA_VERSION,
        "Data e hora": data_legada or _formatar_data_memoria(criada_em),
        "Valor": texto,
        "tag": tag_legada,
        "tags": tags or ["Gerais"],
        "tipo": tipo,
        "importancia": _normalizar_importancia_memoria(bruto.get("importancia"), importancia_padrao),
        "escopo": _normalizar_escopo_memoria(bruto.get("escopo", "privada")),
        "confianca": _texto_memoria_normalizado(bruto.get("confianca", "confirmada")) or "confirmada",
        "status": "arquivada" if _texto_memoria_normalizado(bruto.get("status")) == "arquivada" else "ativa",
        "criada_em": criada_em,
        "atualizada_em": bruto.get("atualizada_em") or criada_em,
        "ultimo_acesso_em": bruto.get("ultimo_acesso_em"),
        "expira_em": bruto.get("expira_em") or None,
        "acessos": acessos,
        "origem": str(bruto.get("origem", "legada"))[:80],
    }
    for campo in ("arquivada_em", "motivo_arquivo"):
        if bruto.get(campo):
            registro[campo] = bruto[campo]
    return registro


def _normalizar_banco_memoria(dados: dict) -> dict:
    return {
        str(chave): normalizar_registro_memoria(str(chave), valor)
        for chave, valor in dados.items()
        if str(chave).strip()
    }


def memoria_expirada(registro: dict, agora: datetime | None = None) -> bool:
    expira_em = _parse_data_memoria(registro.get("expira_em"))
    if not expira_em:
        return False
    if expira_em.tzinfo is None:
        return expira_em <= datetime.now()
    agora = agora or datetime.now(expira_em.tzinfo)
    return expira_em <= agora.astimezone(expira_em.tzinfo)


# ══════════════════════════════════════════════════════════
#  CARREGAMENTO, PERSISTÊNCIA E ACESSOS
# ══════════════════════════════════════════════════════════

def carregar_memoria() -> dict:
    global _MEMORIA_SEGURA_PARA_GRAVAR, _MEMORIA_CACHE, _MEMORIA_CACHE_TIME, _MEMORIA_CACHE_STAMP
    with _MEMORIA_LOCK:
        now = time.time()
        stamp = tuple((p.stat().st_mtime_ns,p.stat().st_size) if p.exists() else None
                      for p in (ARQUIVO_MEMORIA,_backup_path(ARQUIVO_MEMORIA)))
        if _MEMORIA_CACHE is not None and stamp == _MEMORIA_CACHE_STAMP and (now - _MEMORIA_CACHE_TIME) < _MEMORIA_CACHE_TTL:
            return copy.deepcopy(_MEMORIA_CACHE)
        dados, origem, erros = _carregar_json_com_backup(ARQUIVO_MEMORIA, {})
        if isinstance(dados, dict) and origem is not None:
            _MEMORIA_SEGURA_PARA_GRAVAR = True
            if origem != ARQUIVO_MEMORIA:
                _log_cerebro(f"⚠️ Memória principal inválida; recuperando de {origem.name}.")
            dados = _normalizar_banco_memoria(dados)
            _MEMORIA_CACHE = dados
            _MEMORIA_CACHE_STAMP = stamp
            _MEMORIA_CACHE_TIME = now
            return copy.deepcopy(dados)
        if not ARQUIVO_MEMORIA.exists() and not _backup_path(ARQUIVO_MEMORIA).exists():
            _MEMORIA_SEGURA_PARA_GRAVAR = True
            _MEMORIA_CACHE = {}
            _MEMORIA_CACHE_TIME = now
            return {}

        _MEMORIA_SEGURA_PARA_GRAVAR = False
        detalhe = " | ".join(erros) if erros else "conteúdo não é um objeto JSON"
        _log_cerebro(f"❌ Memória não carregada para evitar perda de dados: {detalhe}")
        return {}


def salvar_memoria(dados: dict):
    global _MEMORIA_SEGURA_PARA_GRAVAR, _MEMORIA_CACHE, _MEMORIA_CACHE_TIME
    if not isinstance(dados, dict):
        raise TypeError("A memória precisa ser um objeto/dicionário.")
    with _MEMORIA_LOCK:
        if not _MEMORIA_SEGURA_PARA_GRAVAR:
            raise RuntimeError(
                "A memória principal e o backup estão inválidos. "
                "A gravação foi bloqueada para não apagar os dados existentes."
            )
        dados_normalizados = _normalizar_banco_memoria(dados)
        _aplicar_acessos_pendentes_memoria(dados_normalizados)
        dados.clear()
        dados.update(dados_normalizados)
        _escrever_json_atomico(ARQUIVO_MEMORIA, dados_normalizados)
        _MEMORIA_SEGURA_PARA_GRAVAR = True
        _MEMORIA_CACHE = None
        _MEMORIA_CACHE_TIME = 0.0
        _enfileirar_embeddings_memorias(dados_normalizados)


def _enfileirar_embeddings_memorias(mem):
    """JSON já persistido; enviar apenas um snapshot à indexação assíncrona."""
    try:
        from ayla_embeddings import enfileirar_indexacao
        from ayla_memory_search import texto_embedding_memoria
        documentos = {
            chave: texto_embedding_memoria(chave, reg)
            for chave, reg in mem.items()
            if reg.get("status") == "ativa" and not memoria_expirada(reg)
        }
        enfileirar_indexacao(documentos, carregar_configuracoes_ayla())
    except Exception as exc:
        _log_cerebro(f"⚠️ Indexação não enfileirada ({type(exc).__name__}); memória preservada no JSON.")


def _aplicar_acessos_pendentes_memoria(dados: dict):
    global _MEMORIA_ACESSOS_PENDENTES, _MEMORIA_ULTIMO_FLUSH_ACESSOS
    if not _MEMORIA_ACESSOS_PENDENTES:
        return
    pendentes = _MEMORIA_ACESSOS_PENDENTES
    _MEMORIA_ACESSOS_PENDENTES = {}
    agora = _agora_memoria_iso()
    for chave, quantidade in pendentes.items():
        if chave not in dados:
            continue
        registro = normalizar_registro_memoria(chave, dados[chave])
        registro["acessos"] += quantidade
        registro["ultimo_acesso_em"] = agora
        dados[chave] = registro
    _MEMORIA_ULTIMO_FLUSH_ACESSOS = time.time()


def registrar_acessos_memoria(chaves) -> dict:
    """Atualiza métricas de uso em lote, evitando uma escrita no disco por leitura."""
    global _MEMORIA_ACESSOS_PENDENTES, _MEMORIA_ULTIMO_FLUSH_ACESSOS
    chaves = [str(chave) for chave in chaves if str(chave).strip()]
    if not chaves:
        return {}
    with _MEMORIA_LOCK:
        mem = carregar_memoria()
        retornos = {}
        agora = _agora_memoria_iso()
        for chave in chaves:
            if chave not in mem:
                continue
            registro = normalizar_registro_memoria(chave, mem[chave])
            registro["acessos"] += 1
            registro["ultimo_acesso_em"] = agora
            mem[chave] = registro
            _MEMORIA_ACESSOS_PENDENTES[chave] = _MEMORIA_ACESSOS_PENDENTES.get(chave, 0) + 1
            retornos[chave] = registro["acessos"]
        deve_flush = sum(_MEMORIA_ACESSOS_PENDENTES.values()) >= 5 or time.time() - _MEMORIA_ULTIMO_FLUSH_ACESSOS >= 60
        if deve_flush:
            _MEMORIA_ACESSOS_PENDENTES = {}
            _MEMORIA_ULTIMO_FLUSH_ACESSOS = time.time()
            salvar_memoria(mem)
        return retornos


def _registrar_historico_memoria(acao: str, chave: str, antes=None, depois=None, detalhes: dict | None = None):
    registro = {
        "timestamp": _agora_memoria_iso(), "acao": acao, "chave": chave,
        "antes": antes, "depois": depois, "detalhes": detalhes or {},
    }
    try:
        with open(ARQUIVO_MEMORIA_HISTORICO, "a", encoding="utf-8", newline="") as arquivo:
            arquivo.write(json.dumps(registro, ensure_ascii=False) + "\n")
            arquivo.flush()
            try:
                os.fsync(arquivo.fileno())
            except Exception:
                pass
    except Exception as erro:
        _log_cerebro(f"⚠️ Não consegui registrar o histórico da memória: {erro}")


def _carregar_lixeira_memoria() -> dict:
    dados, _, _ = _carregar_json_com_backup(ARQUIVO_MEMORIA_LIXEIRA, {})
    return dados if isinstance(dados, dict) else {}


def _salvar_lixeira_memoria(dados: dict):
    _escrever_json_atomico(ARQUIVO_MEMORIA_LIXEIRA, dados)


# ══════════════════════════════════════════════════════════
#  STOPWORDS, EMBEDDINGS LEVES E SIMILARIDADE VETORIAL
# ══════════════════════════════════════════════════════════

def carregar_palavras_ignoradas_memoria() -> set[str]:
    """Carrega as palavras de exceção/stopwords da memória a partir do ayla_stopwords.json."""
    if ARQUIVO_STOPWORDS_MEMORIA.exists():
        try:
            with open(ARQUIVO_STOPWORDS_MEMORIA, "r", encoding="utf-8") as f:
                dados = json.load(f)
                if isinstance(dados, list):
                    return {str(p).strip().lower() for p in dados if str(p).strip()}
                elif isinstance(dados, dict) and "palavras" in dados:
                    return {str(p).strip().lower() for p in dados["palavras"] if str(p).strip()}
        except Exception as e:
            _log_cerebro(f"⚠️ Erro ao carregar '{ARQUIVO_STOPWORDS_MEMORIA.name}': {e}")
    # Fallback seguro caso o arquivo seja deletado
    return {
        "a", "ao", "aos", "as", "um", "uma", "uns", "umas", "ele", "ela", "eles", "elas", "eu", "tu",
        "voce", "voces", "nos", "vos", "me", "te", "se", "lhe", "lhes", "meu", "minha", "seu", "sua",
        "de", "da", "do", "das", "dos", "em", "na", "no", "nas", "nos", "com", "para", "pra", "pro",
        "por", "e", "ou", "mas", "que", "como", "se", "mais", "muito", "ja", "nao", "sim", "ser", "estar",
        "ter", "fazer", "ir", "ne", "ta", "vc", "pq", "ayla", "usuario"
    }


def salvar_palavras_ignoradas_memoria(palavras: set[str] | list[str]):
    """Salva a lista de palavras ignoradas/stopwords no arquivo ayla_stopwords.json."""
    lista_ordenada = sorted(list({str(p).strip().lower() for p in palavras if str(p).strip()}))
    payload = {
        "descricao": "Lista de palavras ignoradas / stopwords na indexação e busca vetorial e léxica da memória da Ayla",
        "palavras": lista_ordenada
    }
    _escrever_json_atomico(ARQUIVO_STOPWORDS_MEMORIA, payload)


_PALAVRAS_IGNORADAS_MEMORIA = carregar_palavras_ignoradas_memoria()


def _tokens_memoria(texto: str) -> set[str]:
    return {
        palavra for palavra in re.findall(r"[a-z0-9]{2,}", _texto_memoria_normalizado(texto))
        if palavra not in _PALAVRAS_IGNORADAS_MEMORIA
    }


def _extrair_features_vetoriais(texto: str) -> dict[str, float]:
    """Extrai features vetoriais (palavras TF + trigramas de caracteres) com normalização L2."""
    texto_norm = _texto_memoria_normalizado(texto)
    if not texto_norm:
        return {}
    features: dict[str, float] = {}

    # 1. Unigramas de palavras (se não tiver palavras relevantes, não gera vetor de ruído)
    palavras = [p for p in re.findall(r"[a-z0-9]{2,}", texto_norm) if p not in _PALAVRAS_IGNORADAS_MEMORIA]
    if not palavras:
        return {}
    for p in palavras:
        features[f"w:{p}"] = features.get(f"w:{p}", 0.0) + 1.8

    # 2. Trigramas de caracteres (capturam raízes, plurais, erros leves e correspondência semântica morfológica)
    if len(texto_norm) >= 3:
        for i in range(len(texto_norm) - 2):
            tri = texto_norm[i:i+3]
            features[f"c:{tri}"] = features.get(f"c:{tri}", 0.0) + 0.35

    # 3. Normalização Euclidiana (L2)
    soma_quad = sum(v * v for v in features.values())
    if soma_quad > 0:
        norm = math.sqrt(soma_quad)
        for k in features:
            features[k] /= norm

    return features


def _similaridade_cosseno_vetores(v1: dict[str, float], v2: dict[str, float]) -> float:
    """Calcula similaridade de cosseno ultrarrápida entre dois vetores esparsos."""
    if not v1 or not v2:
        return 0.0
    if len(v1) > len(v2):
        v1, v2 = v2, v1
    return sum(peso * v2[feat] for feat, peso in v1.items() if feat in v2)


def _similaridade_multi_chunk(consulta_norm: str, texto_norm: str) -> float:
    """Calcula similaridade entre consulta e texto, usando multi-chunk para textos longos."""
    tam = len(texto_norm)
    if tam <= 800:
        return SequenceMatcher(None, consulta_norm, texto_norm).ratio()
    sim_inicio = SequenceMatcher(None, consulta_norm, texto_norm[:600]).ratio()
    sim_fim = SequenceMatcher(None, consulta_norm, texto_norm[-400:]).ratio()
    return max(sim_inicio, sim_fim)


# ══════════════════════════════════════════════════════════
#  MOTOR RAG HÍBRIDO AVANÇADO (10 MEMÓRIAS POR PADRÃO)
# ══════════════════════════════════════════════════════════

def buscar_memorias_estruturadas(
    consulta: str = "",
    limite: int = 10,
    escopos_permitidos=None,
    incluir_arquivadas: bool = False,
    tipos=None,
    tags=None,
    *, sqlite_only: bool = False, diagnostico=None,
) -> list[dict]:
    """Recupera apenas memórias relevantes, após validar escopo e status.

    Texto por palavras/IDF e embeddings são sinais independentes de relevância.
    Importância/recência desempatarão resultados aceitos, sem criar relevância.
    """
    from ayla_memory_search import BuscaMemorias, texto_embedding_memoria
    from ayla_embeddings import buscar_similaridades

    mem = carregar_memoria()
    escopos = set(escopos_permitidos if escopos_permitidos is not None else {"privada", "publica"})
    tipos_filtro = {_texto_memoria_normalizado(t) for t in (tipos or [])}
    tags_norm = {_texto_memoria_normalizado(t) for t in (tags or [])}
    agora = datetime.now().astimezone()
    candidatas = {}
    for chave, registro in mem.items():
        if registro["escopo"] not in escopos:
            continue
        if registro["status"] != "ativa" and not incluir_arquivadas:
            continue
        if memoria_expirada(registro, agora):
            continue
        if tipos_filtro and registro["tipo"] not in tipos_filtro:
            continue
        tags_registro = {_texto_memoria_normalizado(t) for t in registro.get("tags", [])}
        if tags_norm and not tags_norm.intersection(tags_registro):
            continue
        candidatas[chave] = registro

    info = diagnostico if diagnostico is not None else {}
    info.update(origem="Busca textual local", vetores=0)
    busca = BuscaMemorias(consulta, candidatas, _PALAVRAS_IGNORADAS_MEMORIA)
    has_consulta = bool(str(consulta or "").strip())
    semanticas = buscar_similaridades(consulta, {
        chave: texto_embedding_memoria(chave, reg) for chave, reg in candidatas.items()
    }, carregar_configuracoes_ayla(), sqlite_only=sqlite_only,
       diagnostico=info, documentos_anteriores={
           chave: f"{chave} {' '.join(reg.get('tags', []))} {reg['Valor']}"
           for chave, reg in candidatas.items()
       }) if busca.tokens and candidatas else {}
    sinais = busca.combinar(semanticas, info) if has_consulta else {
        chave: {"pontuacao": 0.0, "evidencias": {"motivos": ["listagem sem consulta"]}}
        for chave in candidatas
    }
    if not has_consulta:
        info.update(candidatas=len(candidatas), relevantes=len(sinais), descartadas=0)
    resultados = []
    for chave, sinal in sinais.items():
        registro = candidatas[chave]
        bonus = registro["importancia"] * 0.08
        atualizada = _parse_data_memoria(registro.get("atualizada_em"))
        if atualizada:
            if atualizada.tzinfo:
                dias = max(0, (agora - atualizada.astimezone(agora.tzinfo)).days)
            else:
                dias = max(0, (agora.replace(tzinfo=None) - atualizada).days)
            bonus += max(0, 0.25 - dias / 3650)
        # Na busca, esse pequeno bônus só desempata relevâncias próximas.
        if has_consulta:
            bonus *= 0.05
        evidencias = dict(sinal["evidencias"], bonus_contexto=round(bonus, 4))
        resultados.append({"chave": chave, "registro": registro,
                           "pontuacao": round(sinal["pontuacao"] + bonus, 4),
                           "evidencias": evidencias})
    resultados.sort(key=lambda item: (item["pontuacao"], item["registro"]["importancia"],
                                      item["registro"].get("atualizada_em", ""), item["chave"]),
                    reverse=True)
    selecionadas = resultados[:max(1, min(int(limite or 10), 50))]
    info["retornadas"] = len(selecionadas)
    return selecionadas


_RE_EMOJI_DISCORD = re.compile(r"<a?:[^:]+:\d+>")


def formatar_memorias_encontradas(resultados: list[dict], incluir_metadados: bool = True, limite_caracteres: int = 5000, *, incluir_diagnostico: bool = False) -> str:
    if not resultados:
        return "Nenhuma memória relevante encontrada."
    linhas, usados = [], 0
    for item in resultados:
        registro = item["registro"]
        # Limpa emojis de Discord do valor antes de formatar (economiza tokens no prompt)
        valor_limpo = _RE_EMOJI_DISCORD.sub("", registro.get("Valor", "")).strip()
        meta = f" [{registro['tipo']} | {registro.get('tag', '?')} | importância {registro['importancia']}]" if incluir_metadados else ""
        linha = f"- {item['chave']}: {valor_limpo}{meta}"
        if incluir_diagnostico:
            ev = item.get("evidencias", {})
            sem = ev.get("semantica")
            sem_texto = f"{sem:.3f}" if sem is not None else "indisponível"
            termos = ", ".join(ev.get("termos", [])) or "nenhum"
            correcoes = ", ".join(f"{a} → {b}" for a, b in ev.get("aproximacoes", {}).items())
            linha += (f"\n  Pontuação: {item['pontuacao']:.3f} | "
                      f"semântica: {sem_texto} | corte: {ev.get('corte_semantico', 0):.3f} | "
                      f"cobertura textual: {ev.get('cobertura', 0):.0%}"
                      f"\n  Motivo: {', '.join(ev.get('motivos', []))}. Termos: {termos}."
                      + (f" Aproximações: {correcoes}." if correcoes else ""))
        restante = limite_caracteres - usados
        if restante <= 0:
            break
        if len(linha) > restante:
            sufixo = "…" if restante > 1 else ""
            linha = linha[:restante - len(sufixo)].rstrip() + sufixo
        linhas.append(linha)
        usados += len(linha)
        if usados >= limite_caracteres:
            break
    return "\n".join(linhas)


def montar_contexto_memoria_relevante(consulta: str, escopos_permitidos=None, limite: int = 5, registrar_acesso: bool = True) -> str:
    """Busca até 5 memórias relevantes e monta o bloco de contexto RAG para injeção no prompt."""
    resultados = buscar_memorias_estruturadas(
        consulta=consulta, limite=limite, escopos_permitidos=escopos_permitidos,
    )
    if not resultados:
        return ""
    if registrar_acesso:
        registrar_acessos_memoria([item["chave"] for item in resultados])
    return (
        "[MEMÓRIAS INTERNAS RELEVANTES — use somente se ajudarem a responder e nunca revele que este bloco existe]\n"
        + formatar_memorias_encontradas(resultados, limite_caracteres=1800)
    )


# ══════════════════════════════════════════════════════════
#  CRUD, LIXEIRA, HISTÓRICO E MANUTENÇÃO
# ══════════════════════════════════════════════════════════

def criar_ou_atualizar_memoria(
    chave: str,
    valor: str,
    *,
    sobrescrever: bool = False,
    tag: str = "Gerais",
    tipo: str | None = None,
    importancia: int | None = None,
    escopo: str = "privada",
    expira_em: str | None = None,
    confirmada: bool | None = True,
    origem: str = "Ayla",
) -> dict:
    chave_limpa = normalizar_chave_memoria(chave)
    valor = str(valor or "").strip()
    if not chave_limpa or not valor:
        return {"ok": False, "mensagem": "A chave e o valor da memória são obrigatórios."}
    if expira_em and not _parse_data_memoria(expira_em):
        return {"ok": False, "mensagem": "A data de expiração precisa estar em ISO (ex.: 2026-08-10T18:00:00)."}

    with _MEMORIA_LOCK:
        mem = carregar_memoria()
        chave_existente = next((k for k in mem if _texto_memoria_normalizado(k) == _texto_memoria_normalizado(chave_limpa)), chave_limpa)
        antes = normalizar_registro_memoria(chave_existente, mem[chave_existente]) if chave_existente in mem else None
        if antes and not sobrescrever:
            if _texto_memoria_normalizado(antes["Valor"]) == _texto_memoria_normalizado(valor):
                return {"ok": True, "alterada": False, "mensagem": f"A memória '{chave_existente}' já está salva com esse conteúdo.", "chave": chave_existente}
            return {
                "ok": False, "conflito": True, "chave": chave_existente,
                "mensagem": f"A memória '{chave_existente}' já existe com outro valor. Use sobrescrever=True se a informação nova substitui a antiga.",
                "valor_atual": antes["Valor"],
            }

        agora = _agora_memoria_iso()
        registro = copy.deepcopy(antes) if antes else normalizar_registro_memoria(chave_limpa, {})
        acao = "atualizada" if antes else "criada"
        tag = str(tag or registro.get("tag") or "Gerais").strip()[:50] or "Gerais"
        tipo_normalizado = _texto_memoria_normalizado(tipo)
        registro.update({
            "versao": _MEMORIA_SCHEMA_VERSION,
            "Valor": valor,
            "Data e hora": _formatar_data_memoria(agora),
            "tag": tag,
            "tags": list(dict.fromkeys([tag, *registro.get("tags", [])])),
            "tipo": tipo_normalizado if tipo_normalizado in _MEMORIA_TIPOS_VALIDOS else _tipo_memoria_inferido(chave_limpa, valor, tag),
            "importancia": _normalizar_importancia_memoria(importancia, registro.get("importancia", 3)),
            "escopo": _normalizar_escopo_memoria(escopo),
            "confianca": "confirmada" if confirmada is not False else "pendente",
            "status": "ativa",
            "criada_em": registro.get("criada_em") or agora,
            "atualizada_em": agora,
            "expira_em": expira_em or None,
            "origem": str(origem or "Ayla")[:80],
        })
        mem[chave_existente] = registro
        salvar_memoria(mem)
        _registrar_historico_memoria(acao, chave_existente, antes, registro)

    similares = [
        item["chave"] for item in buscar_memorias_estruturadas(
            f"{chave_limpa} {valor}", limite=4, escopos_permitidos={"privada", "publica"}, incluir_arquivadas=True, sqlite_only=True,
        ) if item["chave"] != chave_existente and item["pontuacao"] >= 1.2
    ]
    return {"ok": True, "alterada": True, "chave": chave_existente, "acao": acao, "similares": similares, "mensagem": f"Memória '{chave_existente}' {acao} com sucesso."}


def arquivar_memoria_estruturada(chave: str, motivo: str = "") -> dict:
    with _MEMORIA_LOCK:
        mem = carregar_memoria()
        if chave not in mem:
            return {"ok": False, "mensagem": f"A memória '{chave}' não existe."}
        antes = normalizar_registro_memoria(chave, mem[chave])
        depois = dict(antes)
        depois.update({"status": "arquivada", "arquivada_em": _agora_memoria_iso(), "motivo_arquivo": str(motivo or "")[:300]})
        mem[chave] = depois
        salvar_memoria(mem)
        _registrar_historico_memoria("arquivada", chave, antes, depois, {"motivo": motivo})
    return {"ok": True, "mensagem": f"Memória '{chave}' arquivada; ela não será mais usada automaticamente."}


def enviar_memoria_para_lixeira(chave: str, motivo: str = "") -> dict:
    with _MEMORIA_LOCK:
        mem = carregar_memoria()
        if chave not in mem:
            return {"ok": False, "mensagem": f"A memória '{chave}' não existe."}
        antes = normalizar_registro_memoria(chave, mem[chave])
        lixeira = _carregar_lixeira_memoria()
        identificador = f"{chave}__{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        lixeira[identificador] = {
            "chave_original": chave,
            "removida_em": _agora_memoria_iso(),
            "motivo": str(motivo or "")[:300],
            "registro": antes,
        }
        _salvar_lixeira_memoria(lixeira)
        del mem[chave]
        salvar_memoria(mem)
        _registrar_historico_memoria("movida_para_lixeira", chave, antes, None, {"identificador": identificador, "motivo": motivo})
    return {"ok": True, "identificador": identificador, "mensagem": f"Memória '{chave}' foi para a lixeira e pode ser restaurada."}


def listar_lixeira_memoria(limite: int = 30) -> list[dict]:
    itens = []
    for identificador, item in _carregar_lixeira_memoria().items():
        if not isinstance(item, dict):
            continue
        itens.append({
            "identificador": identificador,
            "chave": item.get("chave_original", ""),
            "removida_em": item.get("removida_em", ""),
            "motivo": item.get("motivo", ""),
        })
    return sorted(itens, key=lambda item: item["removida_em"], reverse=True)[:max(1, min(int(limite or 30), 100))]


def restaurar_memoria_estruturada(identificador_ou_chave: str, sobrescrever: bool = False) -> dict:
    with _MEMORIA_LOCK:
        lixeira = _carregar_lixeira_memoria()
        identificador = identificador_ou_chave if identificador_ou_chave in lixeira else next(
            (i for i, item in sorted(lixeira.items(), reverse=True) if isinstance(item, dict) and item.get("chave_original") == identificador_ou_chave),
            None,
        )
        if not identificador:
            return {"ok": False, "mensagem": "Memória não encontrada na lixeira."}
        item = lixeira[identificador]
        chave = str(item.get("chave_original", "")).strip()
        registro = normalizar_registro_memoria(chave, item.get("registro", {}))
        mem = carregar_memoria()
        if chave in mem and not sobrescrever:
            return {"ok": False, "conflito": True, "mensagem": f"Já existe uma memória ativa com a chave '{chave}'."}
        antes = normalizar_registro_memoria(chave, mem[chave]) if chave in mem else None
        registro.update({"status": "ativa", "atualizada_em": _agora_memoria_iso()})
        registro.pop("arquivada_em", None)
        registro.pop("motivo_arquivo", None)
        mem[chave] = registro
        # Publica primeiro o destino. Falha aqui conserva a origem na lixeira.
        salvar_memoria(mem)
        del lixeira[identificador]
        _salvar_lixeira_memoria(lixeira)
        _registrar_historico_memoria("restaurada", chave, antes, registro, {"identificador": identificador})
    return {"ok": True, "mensagem": f"Memória '{chave}' restaurada da lixeira."}


def revisar_memorias_estruturadas(arquivar_expiradas: bool = False, limite: int = 12) -> dict:
    mem = carregar_memoria()
    ativos = []
    expiradas, possiveis_duplicatas, possiveis_conflitos = [], [], []
    for chave, registro in mem.items():
        if registro["status"] != "ativa":
            continue
        if memoria_expirada(registro):
            expiradas.append(chave)
        else:
            ativos.append((chave, registro))

    for indice, (chave_a, reg_a) in enumerate(ativos):
        tokens_a = _tokens_memoria(f"{chave_a} {reg_a['Valor']}")
        for chave_b, reg_b in ativos[indice + 1:]:
            tokens_b = _tokens_memoria(f"{chave_b} {reg_b['Valor']}")
            uniao = tokens_a | tokens_b
            similaridade = len(tokens_a & tokens_b) / len(uniao) if uniao else 0
            if similaridade >= 0.72:
                possiveis_duplicatas.append((chave_a, chave_b, round(similaridade, 2)))
            elif (
                reg_a["tipo"] == reg_b["tipo"] == "preferencia"
                and _texto_memoria_normalizado(chave_a).split("_")[0] == _texto_memoria_normalizado(chave_b).split("_")[0]
            ):
                possiveis_conflitos.append((chave_a, chave_b))

    if arquivar_expiradas and expiradas:
        for chave in expiradas:
            arquivar_memoria_estruturada(chave, "Expirada durante revisão automática")
    return {
        "total_ativas": len(ativos),
        "expiradas": expiradas[:limite],
        "duplicatas": possiveis_duplicatas[:limite],
        "possiveis_conflitos": possiveis_conflitos[:limite],
        "lixeira": len(_carregar_lixeira_memoria()),
        "arquivadas_agora": bool(arquivar_expiradas and expiradas),
    }


# ══════════════════════════════════════════════════════════
#  CONFIGURAÇÕES GERAIS E REVISÃO AUTOMÁTICA
# ══════════════════════════════════════════════════════════

def configuracoes_padrao_ayla() -> dict:
    return {
        "name_trigger": True,
        "memoria_revisao_automatica_dias": 2,
        "rag_embeddings_enabled": True,
        "max_tokens": 65536,
        "top_p": 0.95,
        "thinking_level": "low",
    }


def carregar_configuracoes_ayla() -> dict:
    with _CONFIG_LOCK:
        defaults = configuracoes_padrao_ayla()
        if not ARQUIVO_CONFIG_AYLA.exists() and not _backup_path(ARQUIVO_CONFIG_AYLA).exists():
            return defaults
        try:
            data, origem, erros = _carregar_json_com_backup(ARQUIVO_CONFIG_AYLA, defaults)
            if not isinstance(data, dict):
                return defaults
            merged = data.copy()
            for key in defaults:
                if key not in merged:
                    merged[key] = defaults[key]
                elif isinstance(defaults[key], bool):
                    merged[key] = bool(data[key])

            if origem and origem != ARQUIVO_CONFIG_AYLA:
                _log_cerebro(f"⚠️ Configuração principal inválida; usando {origem.name}.")
            elif erros:
                _log_cerebro(f"⚠️ Problemas ao carregar configuração: {' | '.join(erros)}")
            return merged
        except Exception as e:
            _log_cerebro(f"⚠️ Erro ao carregar ayla_settings.json: {e}")
            return defaults


def salvar_configuracoes_ayla(dados: dict):
    with _CONFIG_LOCK:
        _escrever_json_atomico(ARQUIVO_CONFIG_AYLA, dados)


def executar_revisao_automatica_memoria_se_necessario() -> dict | None:
    """Arquiva apenas memórias vencidas, no máximo uma vez por intervalo configurado."""
    try:
        config = carregar_configuracoes_ayla()
        dias = max(1, min(90, int(config.get("memoria_revisao_automatica_dias", 7))))
        ultima = _parse_data_memoria(config.get("memoria_ultima_revisao_em"))
        agora = datetime.now().astimezone()
        if ultima:
            ultima = ultima.astimezone(agora.tzinfo) if ultima.tzinfo else ultima.replace(tzinfo=agora.tzinfo)
            if agora - ultima < timedelta(days=dias):
                return None
        relatorio = revisar_memorias_estruturadas(arquivar_expiradas=True)
        config["memoria_ultima_revisao_em"] = _agora_memoria_iso()
        salvar_configuracoes_ayla(config)
        if relatorio["expiradas"]:
            _log_cerebro(f"🧹 Revisão automática de memória arquivou {len(relatorio['expiradas'])} item(ns) vencido(s).")
        return relatorio
    except Exception as erro:
        _log_cerebro(f"⚠️ Revisão automática de memória ignorada: {erro}")
        return None


# ══════════════════════════════════════════════════════════
#  SUBSISTEMA DE EXTRAÇÃO ASSÍNCRONA (WORKER CÉREBRO)
# ══════════════════════════════════════════════════════════

MODELOS_GEMINI_CEREBRO = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite")
MODELOS_GROQ = ["openai/gpt-oss-120b"]


MODELO_CONFERIR_MEMORIAS = "openai/gpt-oss-120b"

PROMPT_SISTEMA_CONFERIR_MEMORIAS = ""

PROMPT_SISTEMA_CEREBRO = ""



_FILA_PROCESSAMENTO: queue.Queue[dict] = queue.Queue(maxsize=100)
_WORKER_THREAD: threading.Thread | None = None
_WORKER_ATIVO = False
_LOCK_CEREBRO = threading.RLock()
_LOCK_CONFERENCIA_MEMORIAS = threading.Lock()
_LOCK_MEMORIAS_LOG = threading.RLock()
_STATS = {
    "total_analisados": 0,
    "memorias_extraidas": 0,
    "descartados_sem_relevancia": 0,
    "descartados_por_similaridade": 0,
    "descartados_sem_grounding": 0,
    "consolidados_chave_existente": 0,
    "erros": 0,
    "ultimo_modelo_usado": "Nenhum",
    "modelo_em_uso": "Aguardando análise (Gemini 3.5 Flash Lite)",
    "ultima_analise_em": None,
}


def _obter_chave_groq() -> str:
    return os.getenv("GROQ_API_KEY", "").strip()


def _limpar_entrada_memoria(texto: str) -> str:
    """Remove instruções de transporte anexadas à fala, não fatos da usuária."""
    return re.sub(
        r'\[(?:Modo voz|Visão biônica):[^\]]*\]', '', texto or '',
        flags=re.IGNORECASE,
    ).strip()


def _candidata_tem_retencao(item: dict, user_input: str) -> bool:
    categorias = {'fato_estavel', 'preferencia_duradoura', 'regra_permanente',
                  'compromisso_futuro', 'pedido_explicito'}
    evidencia = item.get('evidencia')
    utilidade = item.get('utilidade_futura')
    categoria = item.get('categoria_retencao')
    if not isinstance(categoria, str) or categoria not in categorias:
        return False
    if not isinstance(evidencia, str) or not isinstance(utilidade, str):
        return False
    evidencia = ' '.join(evidencia.split())
    fonte = ' '.join(_limpar_entrada_memoria(user_input).split())
    sujeito = item.get('sujeito')
    if item.get('sujeito_inequivoco') is not True or not isinstance(sujeito, dict):
        return False
    tipo_sujeito, nome = sujeito.get('tipo'), sujeito.get('nome')
    if tipo_sujeito not in ('usuaria', 'ayla', 'terceiro') or not isinstance(nome, str) or not nome.strip():
        return False
    if tipo_sujeito == 'terceiro' and nome.strip().casefold() not in evidencia.casefold():
        return False
    return len(evidencia) >= 8 and evidencia in fonte and len(utilidade.strip()) >= 15


def _contexto_curadoria_memoria(texto: str) -> list[dict]:
    """Comparação local e limitada, sem chamadas de embedding ou registrar acessos."""
    tokens = _tokens_memoria(texto)
    candidatas = []
    for chave, registro in carregar_memoria().items():
        if registro.get('status', 'ativa') != 'ativa':
            continue
        valor = registro.get('Valor', '')
        comuns = tokens & _tokens_memoria(f'{chave} {valor}')
        if comuns:
            candidatas.append((len(comuns), chave, valor))
    candidatas.sort(key=lambda item: (-item[0], item[1]))
    resultado, tamanho = [], 0
    for _, chave, valor in candidatas[:8]:
        custo = len(chave) + len(valor)
        if tamanho + custo > 4000:
            continue
        resultado.append({'chave': chave, 'valor': valor})
        tamanho += custo
    return resultado


def _filtro_rapido_deve_analisar(user_input: str, origem: str, autor_id: int) -> tuple[bool, str]:
    """Verifica se a mensagem é genuína da usuario antes de gastar chamada de API."""
    texto = _limpar_entrada_memoria(user_input)
    if not texto or len(texto) < 4:
        return False, ""

    # 1. Somente mensagens da usuario Usuario devem ser analisadas
    eh_dona = (
        autor_id == DISCORD_OWNER_ID or
        origem in ("GUI", "Terminal", "Discord-Call", "DM-Dona")
    )
    if not eh_dona:
        return False, ""

    # 2. Limpa prefixos automáticos de Reply do Discord
    # Ex: [Em resposta à mensagem anterior da Ayla: "..."] texto real
    match_reply = re.match(r"^\[Em resposta à mensagem anterior[^\]]*?\]\s*(.*)$", texto, flags=re.DOTALL)
    if match_reply:
        texto = match_reply.group(1).strip()

    # 3. Rejeita dumps de histórico público com múltiplos usuários
    texto_lower = texto.lower()
    padroes_bloqueio = [
        "[atenção ayla:",
        "abaixo está o histórico",
        "histórico das últimas",
        "[histórico do discord",
    ]
    for pb in padroes_bloqueio:
        if pb in texto_lower:
            return False, ""

    # Se contiver marcações de mensagens de terceiros do tipo "[1] Nome (@user):"
    if re.search(r"\[\d+\]\s+.*?\(@\w+\):", texto):
        return False, ""

    if len(texto) < 4:
        return False, ""

    # Rejeita comandos de bot
    if texto.startswith(("!", "/", "$", ".")):
        return False, ""

    # Rejeita se a mensagem for exclusivamente stopwords/saudações/ruído
    tokens = _tokens_memoria(texto)
    if not tokens:
        return False, ""

    return True, texto



def _avaliar_similaridade_com_memoria_existente(chave: str, valor: str, tag: str = "", tipo: str = "") -> tuple[str, str, float]:
    """
    Avalia a similaridade entre uma nova memória e todas as memórias ativas já salvas.
    Aplica penalidade rígida de redundância para evitar memórias parecidas demais.
    
    Retorna: (decisao, chave_alvo, score_similaridade)
    - ('descartar', chave_existente, score): Conteúdo quase idêntico ou redundante.
    - ('consolidar', chave_existente, score): Mesmo assunto que atualiza a chave existente.
    - ('salvar_nova', chave, score): Memória inédita e suficientemente distinta.
    """
    mem = carregar_memoria()
    if not mem:
        return "salvar_nova", chave, 0.0

    chave_norm = normalizar_chave_memoria(chave)
    texto_novo = f"{chave_norm} {tag} {valor}"
    texto_novo_norm = _texto_memoria_normalizado(texto_novo)
    valor_novo_norm = _texto_memoria_normalizado(valor)
    tokens_novos = _tokens_memoria(texto_novo_norm)
    vetor_novo = _extrair_features_vetoriais(texto_novo_norm)

    maior_score = 0.0
    melhor_chave = ""
    melhor_sim_chave = 0.0

    for k_ex, reg_ex in mem.items():
        if not isinstance(reg_ex, dict) or reg_ex.get("status") != "ativa":
            continue

        val_ex = str(reg_ex.get("Valor", "")).strip()
        k_ex_norm = normalizar_chave_memoria(k_ex)
        texto_ex = f"{k_ex_norm} {' '.join(reg_ex.get('tags', []))} {val_ex}"
        texto_ex_norm = _texto_memoria_normalizado(texto_ex)
        valor_ex_norm = _texto_memoria_normalizado(val_ex)
        tokens_ex = _tokens_memoria(texto_ex_norm)
        vetor_ex = _extrair_features_vetoriais(texto_ex_norm)

        # 1. Similaridade vetorial cosseno (embeddings TF/trigramas)
        sim_cosseno = _similaridade_cosseno_vetores(vetor_novo, vetor_ex)

        # 2. Similaridade de sobreposição léxica (Jaccard de tokens)
        uniao_tokens = tokens_novos | tokens_ex
        inter_tokens = tokens_novos & tokens_ex
        jaccard = len(inter_tokens) / len(uniao_tokens) if uniao_tokens else 0.0

        # 3. Similaridade direta de texto
        sim_valor = SequenceMatcher(None, valor_novo_norm, valor_ex_norm).ratio()
        sim_k = SequenceMatcher(None, chave_norm, k_ex_norm).ratio()

        # Score ponderado de similaridade
        score = (sim_cosseno * 0.40) + (jaccard * 0.35) + (sim_valor * 0.25)
        if sim_k >= 0.70:
            score += 0.15

        if score > maior_score:
            maior_score = score
            melhor_chave = k_ex
            melhor_sim_chave = sim_k

    # 🛑 Penalidade de Redundância:
    # Se a similaridade for muito alta (>= 0.72) ou os textos forem quase idênticos (>= 0.75):
    if maior_score >= 0.72 or (melhor_chave and SequenceMatcher(None, valor_novo_norm, _texto_memoria_normalizado(mem[melhor_chave].get("Valor", ""))).ratio() >= 0.75):
        return "descartar", melhor_chave, round(maior_score, 3)

    # 🔄 Consolidação Inteligente:
    # Se for o mesmo assunto específico (similaridade >= 0.58 com chave afim):
    if maior_score >= 0.58 and melhor_chave:
        reg_alvo = mem[melhor_chave]
        if reg_alvo.get("tipo") == tipo or melhor_sim_chave >= 0.65:
            return "consolidar", melhor_chave, round(maior_score, 3)

    return "salvar_nova", chave, round(maior_score, 3)


def _resposta_extracao_valida(texto: str) -> bool:
    try:
        dados = json.loads(_remover_cercas_json(texto.strip()))
        return (isinstance(dados, dict) and isinstance(dados.get("memorias"), list)
                and all(isinstance(item, dict) for item in dados["memorias"]))
    except (ValueError, TypeError, AttributeError):
        return False


def _chamar_memorizacao_com_fallback(prompt_usuario: str) -> tuple[str | None, str | None]:
    """Gemini 3.5 → Gemini 3.1 → GPT-OSS 120B no Groq; nunca usa Z.ai."""

    import requests

    url = "https://api.groq.com/openai/v1/chat/completions"

    prompt_usuario_estruturado = (
        ""
    )

    from gemini_catalog import gemini_key
    chave_gemini = gemini_key(carregar_configuracoes_ayla())
    if chave_gemini:
        for modelo in MODELOS_GEMINI_CEREBRO:
            with _LOCK_CEREBRO:
                _STATS["modelo_em_uso"] = f"gemini:{modelo}"
            try:
                resp = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent",
                    headers={"x-goog-api-key": chave_gemini},
                    json={
                        "systemInstruction": {"parts": [{"text": PROMPT_SISTEMA_CEREBRO}]},
                        "contents": [{"role": "user", "parts": [{"text": prompt_usuario_estruturado}]}],
                        "generationConfig": {"responseMimeType": "application/json"},
                    }, timeout=14,
                )
                resp.raise_for_status()
                candidatos = resp.json().get("candidates", [])
                partes = candidatos[0].get("content", {}).get("parts", []) if candidatos else []
                conteudo = "".join(p.get("text", "") for p in partes if not p.get("thought"))
                if _resposta_extracao_valida(conteudo):
                    return conteudo, f"gemini:{modelo}"
                _log_cerebro(f"⚠️ [Ayla Cérebro] {modelo}: resposta vazia ou inválida; tentando fallback.")
            except Exception as exc:
                _log_cerebro(f"⚠️ [Ayla Cérebro] Falha em {modelo}: {type(exc).__name__}; tentando fallback.")

    api_key = _obter_chave_groq()
    if not api_key:
        with _LOCK_CEREBRO:
            _STATS["modelo_em_uso"] = "Indisponível: sem resposta dos modelos"
        return None, None
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    for modelo in MODELOS_GROQ:
        with _LOCK_CEREBRO:
            _STATS["modelo_em_uso"] = f"groq:{modelo}"
        # Tentativa 1: com response_format json_object
        try:
            payload = {
                "model": modelo,
                "messages": [
                    {"role": "system", "content": PROMPT_SISTEMA_CEREBRO},
                    {"role": "user", "content": prompt_usuario_estruturado},
                ],
                "temperature": 0.0,
                "response_format": {"type": "json_object"},
            }

            resp = requests.post(url, headers=headers, json=payload, timeout=14)
            if resp.status_code == 200:
                dados = resp.json()
                conteudo = dados.get("choices", [{}])[0].get("message", {}).get("content", "")
                if _resposta_extracao_valida(conteudo):
                    return conteudo, f"groq:{modelo}"

            # Tentativa 2: se o modelo reclamar de validação de schema JSON (código 400), tenta texto puro
            if resp.status_code == 400:
                payload_plano = {
                    "model": modelo,
                    "messages": [
                        {"role": "system", "content": PROMPT_SISTEMA_CEREBRO},
                        {"role": "user", "content": prompt_usuario_estruturado},
                    ],
                    "temperature": 0.0,
                }
                resp_plano = requests.post(url, headers=headers, json=payload_plano, timeout=14)
                if resp_plano.status_code == 200:
                    dados_p = resp_plano.json()
                    conteudo_p = dados_p.get("choices", [{}])[0].get("message", {}).get("content", "")
                    if _resposta_extracao_valida(conteudo_p):
                        return conteudo_p, f"groq:{modelo}"

            erro_txt = resp.text[:120]
            _log_cerebro(f"⚠️ [Ayla Cérebro] Groq ({modelo}) retornou status {resp.status_code}: {erro_txt}")
        except Exception as exc:
            _log_cerebro(f"⚠️ [Ayla Cérebro] Falha ao tentar Groq ({modelo}): {exc}")

    with _LOCK_CEREBRO:
        _STATS["modelo_em_uso"] = "Indisponível: todos os modelos falharam"
    return None, None


def _chamar_groq_conferencia_memorias(prompt_usuario: str) -> str | None:
    """Executa o modo de conferência exclusivamente no gpt-oss-120b."""
    api_key = _obter_chave_groq()
    if not api_key:
        return None

    import requests

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODELO_CONFERIR_MEMORIAS,
        "messages": [
            {"role": "system", "content": PROMPT_SISTEMA_CONFERIR_MEMORIAS},
            {"role": "user", "content": prompt_usuario},
        ],
        "temperature": 0.0,
        "response_format": {"type": "json_object"},
        "reasoning_effort": "low",
        # O plano on-demand desta conta limita prompt + resposta a 8.000 TPM.
        # A saída é compacta, mas o modelo também precisa de espaço para raciocinar.
        "max_completion_tokens": 1200,
    }

    try:
        resposta = requests.post(url, headers=headers, json=payload, timeout=120)
        if resposta.status_code == 400:
            payload.pop("response_format", None)
            resposta = requests.post(url, headers=headers, json=payload, timeout=120)
        if resposta.status_code != 200:
            _log_cerebro(
                f"⚠️ [Conferir memórias] Groq ({MODELO_CONFERIR_MEMORIAS}) "
                f"retornou status {resposta.status_code}: {resposta.text[:240]}"
            )
            return None
        dados = resposta.json()
        return dados.get("choices", [{}])[0].get("message", {}).get("content", "") or None
    except Exception as exc:
        _log_cerebro(f"⚠️ [Conferir memórias] Falha ao chamar o gptOSS_120b: {exc}")
        return None


def _remover_cercas_json(texto: str) -> str:
    """Remove uma cerca Markdown quando ela envolve toda a resposta."""
    limpo = texto.strip().lstrip("\ufeff").strip()
    cercado = re.fullmatch(
        r"```(?:json)?[ \t]*\r?\n?(.*?)\r?\n?```",
        limpo,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return cercado.group(1).strip() if cercado else limpo


def _extrair_json_balanceado(texto: str, inicio: int) -> str | None:
    """Extrai um objeto/lista balanceado a partir de uma posição conhecida."""
    pilha: list[str] = []
    em_string = False
    escapado = False
    pares = {"}": "{", "]": "["}

    for indice in range(inicio, len(texto)):
        char = texto[indice]
        if em_string:
            if escapado:
                escapado = False
            elif char == "\\":
                escapado = True
            elif char == '"':
                em_string = False
            continue

        if char == '"':
            em_string = True
        elif char in "[{":
            pilha.append(char)
        elif char in "}]":
            if not pilha or pilha[-1] != pares[char]:
                return None
            pilha.pop()
            if not pilha:
                return texto[inicio:indice + 1]

    return None


def _extrair_candidatos_json(texto: str) -> list[str]:
    """Encontra blocos JSON mesmo quando há colchetes ou chaves no texto anterior."""
    encontrados: list[str] = []
    for inicio, char in enumerate(texto):
        if char not in "[{":
            continue
        candidato = _extrair_json_balanceado(texto, inicio)
        if candidato and candidato not in encontrados:
            encontrados.append(candidato)
    return encontrados


def _reparar_json_de_modelo(texto: str) -> str:
    """Corrige apenas escapes inválidos, controles em strings e vírgulas finais."""
    saida: list[str] = []
    em_string = False
    indice = 0
    tamanho = len(texto)

    while indice < tamanho:
        char = texto[indice]
        if not em_string:
            if char == '"':
                em_string = True
            saida.append(char)
            indice += 1
            continue

        if char == '"':
            em_string = False
            saida.append(char)
            indice += 1
            continue

        if char == "\\":
            if indice + 1 >= tamanho:
                indice += 1
                continue
            proximo = texto[indice + 1]
            if proximo in '"\\/bfnrt':
                saida.extend((char, proximo))
                indice += 2
                continue
            if proximo == "u" and re.fullmatch(r"[0-9a-fA-F]{4}", texto[indice + 2:indice + 6]):
                saida.append(texto[indice:indice + 6])
                indice += 6
                continue
            # Modelos às vezes escapam pontuação como Markdown (ex.: nome\_curto).
            # Só esses caracteres inequívocos são reparados; uma sequência como
            # C:\Users permanece inválida em vez de virar silenciosamente C:Users.
            if proximo in "_*[]()#`~>+-.!{}|":
                indice += 1
            else:
                saida.append(char)
                indice += 1
            continue

        codigo = ord(char)
        if codigo < 0x20:
            escapes_controle = {"\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t"}
            saida.append(escapes_controle.get(char, f"\\u{codigo:04x}"))
        else:
            saida.append(char)
        indice += 1

    reparado = "".join(saida)

    # Vírgula antes de fechar objeto/lista é um defeito comum e inequívoco.
    # O segundo passe respeita strings para não alterar um valor como "texto,]}".
    saida_sem_virgula: list[str] = []
    em_string = False
    escapado = False
    for indice, char in enumerate(reparado):
        if em_string:
            saida_sem_virgula.append(char)
            if escapado:
                escapado = False
            elif char == "\\":
                escapado = True
            elif char == '"':
                em_string = False
            continue

        if char == '"':
            em_string = True
        elif char == ",":
            proximo = indice + 1
            while proximo < len(reparado) and reparado[proximo].isspace():
                proximo += 1
            if proximo < len(reparado) and reparado[proximo] in "}]":
                continue
        saida_sem_virgula.append(char)

    return "".join(saida_sem_virgula)


def _memorias_do_json(parsed: Any) -> list[dict] | None:
    memorias = None
    if isinstance(parsed, dict):
        if isinstance(parsed.get("memorias"), list):
            memorias = parsed["memorias"]
        elif isinstance(parsed.get("memories"), list):
            memorias = parsed["memories"]
        elif "chave" in parsed and "valor" in parsed:
            memorias = [parsed]
    elif isinstance(parsed, list):
        memorias = parsed
    if memorias is None:
        return None
    return [item for item in memorias if isinstance(item, dict)]


def _limpar_e_parsear_json(texto: str) -> list[dict]:
    """Converte JSON puro ou levemente deformado pelo modelo em memórias."""
    if not texto or not texto.strip():
        return []

    original = texto.strip()
    bases = [original]
    espacos_html = re.sub(
        r"(?i)&#(?:x0*20|0*32);|&nbsp;|&#(?:x0*a0|0*160);",
        " ",
        original,
    )
    if espacos_html != original:
        bases.append(espacos_html)
    decodificado_html = html.unescape(original)
    if decodificado_html not in bases:
        bases.append(decodificado_html)

    candidatos: list[str] = []
    for base in bases:
        limpo = _remover_cercas_json(base)
        for candidato in (limpo, *_extrair_candidatos_json(limpo)):
            if candidato and candidato not in candidatos:
                candidatos.append(candidato)

    melhor_erro: tuple[int, json.JSONDecodeError, str] | None = None
    for candidato in candidatos:
        variantes = [candidato]
        reparado = _reparar_json_de_modelo(candidato)
        if reparado != candidato:
            variantes.append(reparado)
        for variante in variantes:
            try:
                memorias = _memorias_do_json(json.loads(variante))
            except json.JSONDecodeError as exc:
                falha = (exc.pos, exc, variante)
                if melhor_erro is None or falha[0] > melhor_erro[0]:
                    melhor_erro = falha
                continue
            except TypeError:
                continue
            if memorias is not None:
                return memorias

    if melhor_erro is not None:
        posicao, erro, variante = melhor_erro
        inicio = max(0, posicao - 90)
        fim = min(len(variante), posicao + 90)
        amostra = repr(variante[inicio:fim])
        detalhe = str(erro)
    else:
        detalhe = "estrutura JSON sem lista de memórias"
        amostra = repr(original[:180])
    _log_cerebro(
        f"⚠️ [Ayla Cérebro] Falha ao parsear JSON retornado: {detalhe} "
        f"| Trecho próximo ao erro: {amostra}"
    )
    return []


def _salvar_memoria_extraida(item: dict, modelo_origem: str, user_input: str, resposta: str):
    """Grava a memória extraída com penalidade de similaridade, grounding estrito e anti-alucinação."""
    chave = str(item.get("chave") or "").strip()
    valor = str(item.get("valor") or "").strip()
    tag = str(item.get("tag") or "Gerais").strip()
    tipo = str(item.get("tipo") or "preferencia").strip()
    importancia = item.get("importancia", 3)
    escopo = str(item.get("escopo") or "privada").strip()

    if not chave or not valor:
        return

    user_input = _limpar_entrada_memoria(user_input)
    if not _candidata_tem_retencao(item, user_input):
        with _LOCK_CEREBRO:
            _STATS['descartados_sem_relevancia'] += 1
        _log_cerebro('🛡️ [Ayla Cérebro]: Candidata sem evidência e utilidade futura rejeitada.')
        return

    # 0. Filtro Anti-Alucinação e Sanidade
    chave_norm = normalizar_chave_memoria(chave)
    valor_norm = _texto_memoria_normalizado(valor)

    TERMOS_BLOQUEADOS = [
        "creator_of_ayla", "criadora_da_ayla", "criadora_de_ayla", "discord_handle", "Usuario",
        "bandeira_a_meio_mastro", "meio_mastro", "saldo_infinito", "hackear_o_nubank",
        "expressa_pesames", "expresses_condolences", "dar_pesames", "luto_oficial",
        "bumbum_do_shy", "mambo", "nome_usuario", "sistema_operacional_Usuario"
    ]
    if any(tb in chave_norm or tb in valor_norm for tb in TERMOS_BLOQUEADOS):
        with _LOCK_CEREBRO:
            _STATS["descartados_sem_grounding"] += 1
        _log_cerebro(f"🛑 [Ayla Cérebro]: Memória '{chave}' bloqueada (metadado ou alucinação conhecida detectada).")
        return

    # Verificação de Grounding e autoria: fatos sobre a usuario precisam estar
    # ancorados na fala dela. A resposta da Ayla é apenas contexto e não pode,
    # sozinha, originar uma memória sobre a usuária.
    tokens_dialogo = _tokens_memoria(user_input)
    tokens_memoria = _tokens_memoria(f"{chave} {valor}")
    if not (tokens_dialogo & tokens_memoria):
        with _LOCK_CEREBRO:
            _STATS["descartados_sem_grounding"] += 1
        _log_cerebro(f"🛑 [Ayla Cérebro]: Memória '{chave}' rejeitada por falta de ancoragem na fala da usuario.")
        return

    # 1. Avalia similaridade e aplica penalidade contra duplicatas/redundâncias
    decisao, chave_alvo, score_sim = _avaliar_similaridade_com_memoria_existente(chave, valor, tag, tipo)

    if decisao == "descartar":
        with _LOCK_CEREBRO:
            _STATS["descartados_por_similaridade"] += 1
        _log_cerebro(f"🛡️ [Ayla Cérebro]: Memória '{chave}' descartada por alta similaridade ({score_sim:.0%}) com a existente '{chave_alvo}'.")
        
        # Registra no log de auditoria
        registro_log = {
            "timestamp": _agora_memoria_iso(),
            "chave": chave,
            "valor": valor,
            "tag": tag,
            "tipo": tipo,
            "status": "descartado_similaridade",
            "motivo": f"Alta similaridade ({score_sim:.0%}) com a chave '{chave_alvo}'",
            "modelo_origem": modelo_origem,
        }
        try:
            with _LOCK_MEMORIAS_LOG:
                with open(ARQUIVO_MEMORIAS_LOG, "a", encoding="utf-8", newline="") as f:
                    f.write(json.dumps(registro_log, ensure_ascii=False) + "\n")
                    f.flush()
        except Exception:
            pass
        return

    chave_final = chave_alvo if (decisao == "consolidar" and chave_alvo) else chave
    if decisao == "consolidar":
        with _LOCK_CEREBRO:
            _STATS["consolidados_chave_existente"] += 1
        _log_cerebro(f"🔄 [Ayla Cérebro]: Atualizando/consolidando na chave existente '{chave_final}' (similaridade {score_sim:.0%}).")

    # 2. Salva na base de memória persistente
    resultado = criar_ou_atualizar_memoria(
        chave=chave_final,
        valor=valor,
        sobrescrever=True,
        tag=tag,
        tipo=tipo,
        importancia=importancia,
        escopo=escopo,
        origem="cerebro_automatico",
    )
    sucesso = bool(resultado.get("ok"))

    # Notifica bot caso esteja instanciado em memória
    try:
        global_bot = globals().get("bot")
        if not global_bot:
            import sys
            ayla_mod = sys.modules.get("Ayla")
            if ayla_mod:
                global_bot = getattr(ayla_mod, "bot", None)
        if global_bot and hasattr(global_bot, "atualizar_prompt_memoria"):
            global_bot.atualizar_prompt_memoria()
    except Exception:
        pass

    # 3. Registra no log de auditoria de memórias automáticas (JSONL)
    registro_log = {
        "timestamp": _agora_memoria_iso(),
        "chave": chave_final,
        "valor": valor,
        "tag": tag,
        "tipo": tipo,
        "importancia": importancia,
        "escopo": escopo,
        "status": "salvo",
        "decisao": decisao,
        "score_similaridade": score_sim,
        "modelo_origem": modelo_origem,
        "contexto_usuario": user_input[:300],
        "contexto_resposta": resposta[:300],
        "salvo_com_sucesso": sucesso,
    }

    try:
        with _LOCK_MEMORIAS_LOG:
            with open(ARQUIVO_MEMORIAS_LOG, "a", encoding="utf-8", newline="") as f:
                f.write(json.dumps(registro_log, ensure_ascii=False) + "\n")
                f.flush()
    except Exception as e_log:
        _log_cerebro(f"⚠️ [Ayla Cérebro] Erro ao salvar log de memória automática: {e_log}")

    _log_cerebro(f"\n🧠✨ [Ayla Cérebro]: Nova memória guardada automaticamente ({modelo_origem})!")
    _log_cerebro(f"   🔑 Chave: '{chave_final}' | Tag: {tag}")
    _log_cerebro(f"   📝 Valor: {valor}\n")
    return sucesso



def _processar_item_fila(item_fila: dict):
    """Executa a análise de um turno de diálogo em segundo plano com ancoragem estrita."""
    global _STATS
    user_input = _limpar_entrada_memoria(item_fila.get("user_input", ""))
    resposta = item_fila.get("resposta", "")
    origem = item_fila.get("origem", "Discord")
    autor_id = item_fila.get("autor_id", 0)

    # Estrutura inequívoca: cada texto viaja com nome e role próprios. JSON
    # também impede que quebras de linha no conteúdo confundam os rótulos.
    prompt_analise = json.dumps(
        {
            "memorias_relacionadas": _contexto_curadoria_memoria(user_input),
            "mensagem_da_usuaria": {
                "autora": "usuario Usuario",
                "role": "user",
                "conteudo": user_input,
            },
            "mensagem_da_ayla": {
                "autora": "Ayla",
                "role": "assistant",
                "conteudo": resposta,
            },
        },
        ensure_ascii=False,
        indent=2,
    )


    with _LOCK_CEREBRO:
        _STATS["total_analisados"] += 1
        _STATS["ultima_analise_em"] = _agora_memoria_iso()

    # Extração automática prioriza Gemini e usa GPT-OSS no Groq como último fallback.
    conteudo_json, modelo_usado = _chamar_memorizacao_com_fallback(prompt_analise)

    if not conteudo_json or not modelo_usado:
        with _LOCK_CEREBRO:
            _STATS["erros"] += 1
        return

    with _LOCK_CEREBRO:
        _STATS["ultimo_modelo_usado"] = modelo_usado

    # 3. Parse e Curadoria
    memorias = _limpar_e_parsear_json(conteudo_json)
    if not memorias:
        with _LOCK_CEREBRO:
            _STATS["descartados_sem_relevancia"] += 1
        return

    # 4. Salva cada memória válida
    for mem in memorias:
        if isinstance(mem, dict):
            if _salvar_memoria_extraida(mem, modelo_usado, user_input, resposta):
                with _LOCK_CEREBRO:
                    _STATS["memorias_extraidas"] += 1


def _worker_loop():
    """Loop principal do worker em background thread."""
    global _WORKER_ATIVO
    _log_cerebro("🧠 [Ayla Cérebro]: Worker assíncrono de memória ativado com sucesso!")
    while _WORKER_ATIVO:
        try:
            item = _FILA_PROCESSAMENTO.get(timeout=2.0)
            if item is None:
                break
            try:
                _processar_item_fila(item)
            except Exception as exc:
                _log_cerebro(f"⚠️ [Ayla Cérebro] Erro no processamento de memória em background: {exc}")
            finally:
                _FILA_PROCESSAMENTO.task_done()
        except queue.Empty:
            continue
        except Exception as e_loop:
            _log_cerebro(f"⚠️ [Ayla Cérebro] Erro no loop do worker: {e_loop}")
            time.sleep(1.0)


def iniciar_cerebro():
    """Garante que a background thread do cérebro esteja rodando."""
    global _WORKER_THREAD, _WORKER_ATIVO
    with _LOCK_CEREBRO:
        if _WORKER_THREAD is not None and _WORKER_THREAD.is_alive():
            return
        _WORKER_ATIVO = True
        _WORKER_THREAD = threading.Thread(target=_worker_loop, daemon=True, name="AylaCerebroWorker")
        _WORKER_THREAD.start()
    # Reconstrói pendências após reiniciar a Ayla usando o JSON como fonte.
    memorias = carregar_memoria()
    if _MEMORIA_SEGURA_PARA_GRAVAR:
        _enfileirar_embeddings_memorias(memorias)


def parar_cerebro():
    """Para o worker de background de forma limpa."""
    global _WORKER_ATIVO, _WORKER_THREAD
    with _LOCK_CEREBRO:
        _WORKER_ATIVO = False
        if _WORKER_THREAD and _WORKER_THREAD.is_alive():
            try:
                _FILA_PROCESSAMENTO.put_nowait(None)
            except Exception:
                pass


def enfileirar_interacao(user_input: str, resposta: str, origem: str = "Discord", autor_id: int = 0):
    """
    Enfileira a interação de forma ultrarrápida e não bloqueante.
    Retorna imediatamente para não atrasar a resposta da Ayla.
    """
    deve_analisar, user_input_limpo = _filtro_rapido_deve_analisar(user_input, origem, autor_id)
    if not deve_analisar:
        return

    iniciar_cerebro()

    try:
        _FILA_PROCESSAMENTO.put_nowait({
            "user_input": user_input_limpo,
            "resposta": resposta,
            "origem": origem,
            "autor_id": autor_id,
            "timestamp": _agora_memoria_iso(),
        })
    except queue.Full:
        _log_cerebro("⚠️ [Ayla Cérebro] Fila de análise cheia; descartando turno mais antigo.")
        try:
            _FILA_PROCESSAMENTO.get_nowait()
            _FILA_PROCESSAMENTO.put_nowait({
                "user_input": user_input_limpo,
                "resposta": resposta,
                "origem": origem,
                "autor_id": autor_id,
                "timestamp": _agora_memoria_iso(),
            })
        except Exception:
            pass


def obter_status_cerebro() -> dict:
    """Retorna estatísticas operacionais do Cérebro."""
    with _LOCK_CEREBRO:
        dados = dict(_STATS)
        dados["fila_pendente"] = _FILA_PROCESSAMENTO.qsize()
        dados["worker_ativo"] = bool(_WORKER_THREAD and _WORKER_THREAD.is_alive())
        return dados


def listar_memorias_automaticas_log(limite: int = 50) -> list[dict]:
    """Lê os últimos registros do log de memórias automáticas."""
    if not ARQUIVO_MEMORIAS_LOG.exists():
        return []
    registros = []
    try:
        with _LOCK_MEMORIAS_LOG:
            with open(ARQUIVO_MEMORIAS_LOG, "r", encoding="utf-8") as f:
                for linha in f:
                    linha_s = linha.strip()
                    if linha_s:
                        try:
                            registros.append(json.loads(linha_s))
                        except Exception:
                            pass
        return registros[-limite:][::-1]  # Mais recentes primeiro
    except Exception as e:
        _log_cerebro(f"⚠️ [Ayla Cérebro] Erro ao ler log de memórias automáticas: {e}")
        return []


def _registro_eh_memoria_automatica(registro: Any) -> bool:
    if not isinstance(registro, dict):
        return False
    origem = _texto_memoria_normalizado(registro.get("origem", ""))
    return "cerebro" in origem or "automatic" in origem




def _parsear_conferencia_memorias(texto: str) -> tuple[list[dict], int | None]:
    if not texto or not texto.strip():
        return [], None
    base = _remover_cercas_json(html.unescape(texto.strip()))
    candidatos = [base, *_extrair_candidatos_json(base)]
    for candidato in candidatos:
        for variante in (candidato, _reparar_json_de_modelo(candidato)):
            try:
                dados = json.loads(variante)
            except Exception:
                continue
            if isinstance(dados, dict) and isinstance(dados.get("apagar"), list):
                try:
                    total = int(dados.get("total_analisado"))
                except (TypeError, ValueError):
                    total = None
                itens = []
                for item in dados["apagar"]:
                    if isinstance(item, str):
                        itens.append({
                            "chave": item,
                            "confianca": 1.0,
                            "motivo": "Classificada como inútil pelo gptOSS_120b.",
                        })
                    elif isinstance(item, dict):
                        itens.append(item)
                return itens, total
    return [], None


def _montar_prompt_conferencia_memorias(candidatas: dict[str, dict]) -> str:
    """Monta uma entrada compacta que caiba no limite de 8.000 TPM da Groq."""
    cabecalho = (
        f"Revise as {len(candidatas)} memórias automáticas abaixo. Cada item é [chave, valor]. "
        "Compare a lista inteira para detectar redundâncias. Na saída, informe total_analisado e liste "
        "somente as chaves que devem ser apagadas; memórias mantidas não devem aparecer.\n"
    )
    prompt = ""
    # Reduz valores progressivamente apenas se a coleção crescer muito. As chaves nunca são cortadas.
    for limite_valor in (500, 360, 240, 160, 100, 60, 40):
        pares = [
            [chave, str(registro.get("Valor", registro.get("valor", "")))[:limite_valor]]
            for chave, registro in candidatas.items()
        ]
        prompt = cabecalho + json.dumps(pares, ensure_ascii=False, separators=(",", ":"))
        if len(PROMPT_SISTEMA_CONFERIR_MEMORIAS) + len(prompt) <= 9_000:
            break
    return prompt


def _limpar_chaves_do_log_automatico(chaves: set[str]) -> int:
    """Remove do JSONL todos os registros ligados às chaves descartadas."""
    if not chaves or not ARQUIVO_MEMORIAS_LOG.exists():
        return 0
    chaves_norm = {_texto_memoria_normalizado(chave) for chave in chaves}
    mantidas: list[str] = []
    removidas = 0
    with _LOCK_MEMORIAS_LOG:
        with open(ARQUIVO_MEMORIAS_LOG, "r", encoding="utf-8") as arquivo:
            for linha in arquivo:
                linha_limpa = linha.rstrip("\r\n")
                try:
                    item = json.loads(linha_limpa)
                    chave_norm = _texto_memoria_normalizado(item.get("chave", "")) if isinstance(item, dict) else ""
                except Exception:
                    chave_norm = ""
                if chave_norm and chave_norm in chaves_norm:
                    removidas += 1
                else:
                    mantidas.append(linha_limpa)

        try:
            shutil.copy2(ARQUIVO_MEMORIAS_LOG, _backup_path(ARQUIVO_MEMORIAS_LOG))
        except Exception:
            pass
        texto_final = "\n".join(mantidas)
        if mantidas:
            texto_final += "\n"
        _escrever_texto_atomico(ARQUIVO_MEMORIAS_LOG, texto_final, criar_backup=False)
    return removidas


def conferir_memorias_uteis() -> dict:
    """Pede ao gptOSS_120b que revise e remova somente memórias automáticas inúteis."""
    with _LOCK_CONFERENCIA_MEMORIAS:
        memoria = carregar_memoria()
        candidatas = {
            chave: registro for chave, registro in memoria.items()
            if _registro_eh_memoria_automatica(registro)
        }

        if not candidatas:
            return {
                "ok": True,
                "modelo": MODELO_CONFERIR_MEMORIAS,
                "analisadas": 0,
                "mantidas": 0,
                "apagadas": [],
                "registros_log_removidos": 0,
                "mensagem": "Não há memórias automáticas para conferir.",
            }
        if not _obter_chave_groq():
            return {
                "ok": False,
                "modelo": MODELO_CONFERIR_MEMORIAS,
                "mensagem": "A chave GROQ_API_KEY não está configurada.",
            }

        prompt = _montar_prompt_conferencia_memorias(candidatas)
        resposta = _chamar_groq_conferencia_memorias(prompt)
        analises_apagar, total_declarado = _parsear_conferencia_memorias(resposta or "")

        chaves_exatas = set(candidatas)
        if total_declarado != len(chaves_exatas):
            return {
                "ok": False,
                "modelo": MODELO_CONFERIR_MEMORIAS,
                "analisadas": total_declarado or 0,
                "total": len(chaves_exatas),
                "mensagem": (
                    "O gptOSS_120b não confirmou a análise da lista inteira; nenhuma memória foi apagada. "
                    "Tente novamente."
                ),
            }

        por_chave: dict[str, dict] = {}
        chaves_desconhecidas: list[str] = []
        for analise in analises_apagar:
            chave = str(analise.get("chave") or "").strip()
            if chave not in chaves_exatas:
                if chave:
                    chaves_desconhecidas.append(chave)
                continue
            if chave in por_chave:
                continue
            por_chave[chave] = analise

        if chaves_desconhecidas:
            return {
                "ok": False,
                "modelo": MODELO_CONFERIR_MEMORIAS,
                "analisadas": total_declarado,
                "total": len(chaves_exatas),
                "mensagem": (
                    "O gptOSS_120b devolveu chave(s) que não pertencem às memórias automáticas; "
                    "nenhuma memória foi apagada. Tente novamente."
                ),
            }

        apagar: dict[str, str] = {}
        protegidas_baixa_confianca = 0
        for chave, analise in por_chave.items():
            try:
                confianca = float(analise.get("confianca", 0.0))
            except (TypeError, ValueError):
                confianca = 0.0
            motivo = str(analise.get("motivo") or "Classificada como inútil pelo gptOSS_120b.").strip()
            if confianca >= 0.80:
                apagar[chave] = motivo[:300]
            else:
                protegidas_baixa_confianca += 1

        mantidas = len(chaves_exatas) - len(apagar)

        apagadas: list[dict] = []
        for chave, motivo in apagar.items():
            # Revalida a origem no momento da mutação para jamais atingir uma memória manual.
            atual = carregar_memoria().get(chave)
            if not _registro_eh_memoria_automatica(atual):
                mantidas += 1
                continue
            resultado = enviar_memoria_para_lixeira(
                chave,
                f"Conferir memórias / gptOSS_120b: {motivo}",
            )
            if resultado.get("ok"):
                apagadas.append({"chave": chave, "motivo": motivo})
            else:
                mantidas += 1

        chaves_apagadas = {item["chave"] for item in apagadas}
        removidas_log = _limpar_chaves_do_log_automatico(chaves_apagadas)

        try:
            global_bot = globals().get("bot")
            if not global_bot:
                ayla_mod = sys.modules.get("Ayla")
                global_bot = getattr(ayla_mod, "bot", None) if ayla_mod else None
            if global_bot and hasattr(global_bot, "atualizar_prompt_memoria"):
                global_bot.atualizar_prompt_memoria()
        except Exception:
            pass

        return {
            "ok": True,
            "modelo": MODELO_CONFERIR_MEMORIAS,
            "analisadas": len(chaves_exatas),
            "mantidas": mantidas,
            "apagadas": apagadas,
            "protegidas_baixa_confianca": protegidas_baixa_confianca,
            "registros_log_removidos": removidas_log,
            "mensagem": f"Conferência concluída: {len(apagadas)} memória(s) inútil(eis) removida(s).",
        }


# Inicia o worker automaticamente ao carregar o módulo
iniciar_cerebro()
