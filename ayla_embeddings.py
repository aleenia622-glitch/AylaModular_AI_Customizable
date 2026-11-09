"""Embeddings Gemini para o RAG, com cache persistente e prazo total de 5 s.

O chamador filtra escopo/status antes de entregar documentos a este módulo.
Falhas nunca interrompem a busca léxica. Apenas um worker pode estar em voo;
o prazo do chamador também cobre DNS, conexão, indexação e leitura do cache.
"""
from __future__ import annotations

import atexit
import hashlib
import json
import logging
import math
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path

import httpx

from gemini_catalog import gemini_key
from ayla_memory_search import MIN_SEMANTIC as MIN_SIMILARITY

MODEL = "gemini-embedding-001"
DIMENSIONS = 768
TIMEOUT = 5.0
CACHE_PATH = Path(__file__).resolve().parent / "ayla_embeddings.sqlite3"
_status_lock = threading.Lock()
_status_carregamento = "Aguardando consulta"


def obter_status_carregamento():
    with _status_lock:
        return _status_carregamento


def _registrar_carregamento(valor):
    global _status_carregamento
    with _status_lock:
        _status_carregamento = valor


_busy = threading.Lock()
_client = None
_client_lock = threading.RLock()
_closed = False
_logger = logging.getLogger(__name__)


def _normalize(values):
    if len(values) != DIMENSIONS:
        raise ValueError("Dimensão de embedding inválida")
    values = [float(v) for v in values]
    if not all(math.isfinite(v) for v in values):
        raise ValueError("Embedding não finito")
    norm = math.sqrt(sum(v * v for v in values))
    if not norm or not math.isfinite(norm):
        raise ValueError("Embedding inválido")
    return [v / norm for v in values]


def _chunks(text):
    # Limite conservador em bytes: inclusive Unicode cabe nos 2048 tokens.
    # Sobreposição mantém relações entre frases nas bordas, sem perder o final.
    chunks, current, size = [], [], 0
    for char in str(text):
        char_size = len(char.encode("utf-8"))
        if size + char_size > 1600:
            chunks.append("".join(current))
            current = current[-100:]
            size = len("".join(current).encode("utf-8"))
        current.append(char)
        size += char_size
    if current:
        chunks.append("".join(current))
    return chunks


def _cache_key(text, task):
    return hashlib.sha256(f"v1|{MODEL}|{DIMENSIONS}|{task}|{text}".encode()).hexdigest()


class IndexadorMemorias:
    """Indexa snapshots do JSON; o worker nunca escreve na memória principal."""

    RETRY_DELAYS = (5.0, 30.0)

    def __init__(self, cache_path=CACHE_PATH):
        self.cache_path = Path(cache_path)
        self.condition = threading.Condition()
        self.documentos = {}
        self.settings = {}
        self.revisao = 0
        self.falhas = {}
        self.contagens = {"indexadas": 0, "pendentes": 0, "falhas": 0}
        self.thread = None
        self.encerrado = False

    def atualizar(self, documentos, settings):
        documentos = dict(documentos)
        with self.condition:
            if documentos != self.documentos or gemini_key(settings) != gemini_key(self.settings):
                self.revisao += 1
                self.documentos = documentos
                self.settings = dict(settings)
                self.falhas.clear()
                # Contagem definitiva será calculada pelo worker sem bloquear a GUI.
                self.contagens = {"indexadas": 0, "pendentes": len(documentos), "falhas": 0}
                self.condition.notify_all()

    def status(self):
        with self.condition:
            return dict(self.contagens)

    def iniciar(self):
        with self.condition:
            if self.thread is None or not self.thread.is_alive():
                self.encerrado = False
                self.thread = threading.Thread(target=self._loop, daemon=True,
                                               name="ayla-indexacao-memorias")
                self.thread.start()

    def parar(self):
        with self.condition:
            self.encerrado = True
            self.condition.notify_all()

    def _loop(self):
        revisao_processada = -1
        while True:
            with self.condition:
                if self.encerrado:
                    return
                pendente = self.contagens["pendentes"] > 0
                if revisao_processada == self.revisao and not pendente:
                    # Uma busca pode preencher o cache após uma falha da fila.
                    # Recontar periodicamente não repete chamadas de API esgotadas.
                    self.condition.wait(timeout=30.0)
                    if self.encerrado:
                        return
                revisao = self.revisao
            try:
                processado = self.executar_ciclo()
                if processado:
                    revisao_processada = revisao
            except Exception as exc:
                _logger.warning("RAG: indexação em background falhou (%s).", type(exc).__name__)
            with self.condition:
                if not self.encerrado and revisao == self.revisao:
                    self.condition.wait(timeout=1.0)

    def executar_ciclo(self):
        # Compartilha o limite de concorrência com a busca; nenhuma chamada
        # de rede nem acesso SQLite acontece na thread que salvou o JSON.
        if _closed or not _busy.acquire(blocking=False):
            return False
        try:
            return self._indexar_snapshot()
        finally:
            _busy.release()

    def _indexar_snapshot(self):
        with self.condition:
            documentos, settings, revisao = dict(self.documentos), dict(self.settings), self.revisao
        entries, doc_ids = {}, {}
        for nome, texto in documentos.items():
            identifiers = []
            for chunk in _chunks(texto):
                identifier = _cache_key(chunk, "RETRIEVAL_DOCUMENT")
                entries[identifier] = (chunk, "RETRIEVAL_DOCUMENT")
                identifiers.append(identifier)
            doc_ids[nome] = identifiers

        with closing(sqlite3.connect(str(self.cache_path), timeout=0.1)) as db:
            db.execute("CREATE TABLE IF NOT EXISTS vectors (id TEXT PRIMARY KEY, vector TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS memory_vectors (memory_key TEXT NOT NULL, "
                       "vector_id TEXT NOT NULL, PRIMARY KEY (memory_key, vector_id))")
            cached = set()
            for identifier in entries:
                row = db.execute("SELECT vector FROM vectors WHERE id=?", (identifier,)).fetchone()
                if row:
                    try:
                        _normalize(json.loads(row[0]))
                        cached.add(identifier)
                    except (TypeError, ValueError):
                        db.execute("DELETE FROM vectors WHERE id=?", (identifier,))
            db.commit()

        now = time.monotonic()
        with self.condition:
            if revisao != self.revisao or self.encerrado:
                return False
            missing = [i for i in entries if i not in cached]
            elegiveis = [i for i in missing if self.falhas.get(i, (0, 0))[0] < 3
                        and self.falhas.get(i, (0, 0))[1] <= now]
        batch = elegiveis[:32]
        generated = {}
        if batch:
            try:
                key = gemini_key(settings)
                if not key:
                    raise RuntimeError("Chave Gemini ausente")
                values = _embed_batch(key, [entries[i] for i in batch], TIMEOUT)
                if len(values) != len(batch):
                    raise ValueError("Lote de embeddings incompleto")
                generated = {i: _normalize(vector) for i, vector in zip(batch, values)}
            except Exception as exc:
                with self.condition:
                    if revisao == self.revisao:
                        for identifier in batch:
                            attempts = self.falhas.get(identifier, (0, 0))[0] + 1
                            delay = self.RETRY_DELAYS[min(attempts - 1, len(self.RETRY_DELAYS) - 1)]
                            # Sem chave não insistimos até a configuração mudar.
                            self.falhas[identifier] = (attempts if gemini_key(settings) else 3,
                                                       time.monotonic() + delay)
                _logger.warning("RAG: lote pendente de indexação (%s).", type(exc).__name__)

        with self.condition:
            # Uma edição/exclusão durante a chamada não pode publicar vetores antigos.
            if revisao != self.revisao or self.encerrado:
                return False
            with closing(sqlite3.connect(str(self.cache_path), timeout=0.1)) as db:
                anteriores = {}
                for nome, identifier in db.execute("SELECT memory_key, vector_id FROM memory_vectors"):
                    anteriores.setdefault(nome, set()).add(identifier)
                antigos = set().union(*anteriores.values()) if anteriores else set()
                for identifier, vector in generated.items():
                    db.execute("INSERT OR REPLACE INTO vectors VALUES (?, ?)",
                               (identifier, json.dumps(vector)))
                disponiveis = cached | generated.keys()
                publicados = {}
                for nome, ids in doc_ids.items():
                    publicados[nome] = set(ids)
                    if not all(i in disponiveis for i in ids):
                        # Migração progressiva: conserva cache anterior até o
                        # documento novo estar completo. A busca só reutiliza
                        # chaves do conteúdo atual, nunca conteúdo de uma edição.
                        publicados[nome].update(anteriores.get(nome, ()))
                db.execute("DELETE FROM memory_vectors")
                db.executemany("INSERT INTO memory_vectors VALUES (?, ?)",
                               [(nome, i) for nome, ids in publicados.items() for i in ids])
                # Só remove vetores de documentos rastreados; conserva cache de consultas.
                mantidos = set().union(*publicados.values()) if publicados else set()
                db.executemany("DELETE FROM vectors WHERE id=?", [(i,) for i in antigos - mantidos])
                db.commit()
            cached.update(generated)
            contagens = {"indexadas": 0, "pendentes": 0, "falhas": 0}
            for ids in doc_ids.values():
                missing = [i for i in ids if i not in cached]
                if not missing:
                    contagens["indexadas"] += 1
                elif any(self.falhas.get(i, (0, 0))[0] >= 3 for i in missing):
                    contagens["falhas"] += 1
                else:
                    contagens["pendentes"] += 1
            self.contagens = contagens
        return True


_indexador = IndexadorMemorias()


def enfileirar_indexacao(documentos, settings):
    _indexador.atualizar(documentos, settings)
    _indexador.iniciar()


def obter_status_indexacao():
    return _indexador.status()


def iniciar_sessao():
    """Transporte independente do modelo de conversa, mantido até o shutdown."""
    global _client, _closed
    with _client_lock:
        _closed = False
        if _client is None:
            _client = httpx.Client(
                timeout=TIMEOUT,
                limits=httpx.Limits(max_connections=1, max_keepalive_connections=1,
                                    keepalive_expiry=None),
            )
        return _client


def fechar_sessao():
    global _client, _closed
    _indexador.parar()
    with _client_lock:
        _closed = True
        client, _client = _client, None
        if client is not None:
            client.close()


atexit.register(fechar_sessao)


def _embed_batch(key, items, timeout):
    global _client
    requests = [{"model": f"models/{MODEL}",
                 "content": {"parts": [{"text": text}]},
                 "taskType": task, "outputDimensionality": DIMENSIONS}
                for text, task in items]
    deadline = time.monotonic() + timeout
    with _client_lock:
        if _closed:
            raise RuntimeError("Transporte de embeddings encerrado")
        for attempt in range(2):
            client = iniciar_sessao()
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                response = client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:batchEmbedContents",
                    headers={"x-goog-api-key": key}, json={"requests": requests},
                    timeout=remaining)
                response.raise_for_status()
                embeddings = response.json()["embeddings"]
                if len(embeddings) != len(items):
                    raise ValueError("Lote de embeddings incompleto")
                return [_normalize(item["values"]) for item in embeddings]
            except Exception as exc:
                _logger.warning(
                    "RAG: falha no embedding (%s); fechando e reabrindo a sessão.",
                    type(exc).__name__)
                _client = None
                try:
                    client.close()
                except Exception:
                    _logger.warning("RAG: falha ao fechar transporte antigo do embedding.")
                iniciar_sessao()
                # Erros de credencial/cota não melhoram repetindo o mesmo pedido.
                permanent = (isinstance(exc, httpx.HTTPStatusError)
                             and 400 <= exc.response.status_code < 500)
                if attempt or permanent or time.monotonic() >= deadline:
                    raise


def _score(consulta, documentos, key, deadline, cache_path, *, sqlite_only=False,
           diagnostico=None, documentos_anteriores=None):
    info = diagnostico if diagnostico is not None else {}
    info.update(chamadas_api=0, erro_embedding=None, consulta_com_vetor=False)
    entries, doc_ids = {}, {}

    def add(text, task):
        identifier = _cache_key(text, task)
        entries[identifier] = (text, task)
        return identifier

    query_ids = [add(chunk, "RETRIEVAL_QUERY") for chunk in _chunks(consulta)]
    for name, text in documentos.items():
        doc_ids[name] = [add(chunk, "RETRIEVAL_DOCUMENT") for chunk in _chunks(text)]
    legacy_ids = {
        name: [_cache_key(chunk, "RETRIEVAL_DOCUMENT") for chunk in _chunks(text)]
        for name, text in (documentos_anteriores or {}).items() if name in documentos
    }
    vectors = {}
    # Offline é realmente somente leitura, inclusive para entradas corrompidas.
    connection = (sqlite3.connect(Path(cache_path).resolve().as_uri() + "?mode=ro", uri=True, timeout=0.1)
                  if sqlite_only else sqlite3.connect(str(cache_path), timeout=0.1))
    with closing(connection) as db:
        if not sqlite_only:
            db.execute("CREATE TABLE IF NOT EXISTS vectors (id TEXT PRIMARY KEY, vector TEXT NOT NULL)")
        identifiers = dict.fromkeys([*entries, *(i for ids in legacy_ids.values() for i in ids)])
        for identifier in identifiers:
            if time.monotonic() >= deadline:
                break
            row = db.execute("SELECT vector FROM vectors WHERE id=?", (identifier,)).fetchone()
            if row:
                try:
                    vectors[identifier] = _normalize(json.loads(row[0]))
                except (ValueError, TypeError):
                    if not sqlite_only:
                        db.execute("DELETE FROM vectors WHERE id=?", (identifier,))
        if not sqlite_only:
            db.commit()
            # Consulta primeiro: um índice incompleto não pode consumir todo o
            # prazo sem gerar o único vetor necessário para consultar o cache.
            missing_queries = [i for i in query_ids if i not in vectors]
            missing_docs = [i for i in entries if i not in vectors and i not in query_ids]
            groups = [missing_queries, missing_docs]
            stop = False
            for missing in groups:
                if stop:
                    break
                for offset in range(0, len(missing), 32):
                    remaining = deadline - time.monotonic()
                    if remaining < 0.25:
                        info["erro_embedding"] = "TimeoutError"
                        stop = True
                        break
                    batch = missing[offset:offset + 32]
                    try:
                        info["chamadas_api"] += 1
                        embedded = _embed_batch(key, [entries[i] for i in batch], remaining)
                        if len(embedded) != len(batch):
                            raise ValueError("Lote de embeddings incompleto")
                        validated = [_normalize(v) for v in embedded]
                        for identifier, vector in zip(batch, validated):
                            vectors[identifier] = vector
                            db.execute("INSERT OR REPLACE INTO vectors VALUES (?, ?)",
                                       (identifier, json.dumps(vector)))
                        db.commit()
                    except Exception as exc:
                        # Aproveita o cache já lido e os lotes válidos; não repete
                        # uma leitura completa com o mesmo prazo já esgotado.
                        info["erro_embedding"] = type(exc).__name__
                        _logger.warning("RAG: geração parcial (%s); preservando vetores válidos.", type(exc).__name__)
                        stop = True
                        break
    queries = [vectors[i] for i in query_ids if i in vectors]
    info["consulta_com_vetor"] = bool(queries)
    if not queries:
        return {}
    scores = {}
    legados = 0
    for name, identifiers in doc_ids.items():
        if not any(i in vectors for i in identifiers):
            identifiers = legacy_ids.get(name, [])
            if any(i in vectors for i in identifiers):
                legados += 1
        similarities = [sum(a * b for a, b in zip(query, vectors[i]))
                        for i in identifiers if i in vectors for query in queries]
        if similarities:
            scores[name] = max(-1.0, min(1.0, max(similarities)))
    info["vetores_anteriores"] = legados
    return scores


def buscar_similaridades(consulta, documentos, settings, *, cache_path=None,
                         sqlite_only=False, diagnostico=None, documentos_anteriores=None):
    """Retorna cossenos somente dos documentos autorizados, ou {} no fallback."""
    info = diagnostico if diagnostico is not None else {}
    info.update(origem="Busca textual local", vetores=0, chamadas_api=0, erro_embedding=None)
    if not consulta.strip() or not documentos:
        return {}
    _registrar_carregamento("Busca local (JSON) · fallback")
    key = gemini_key(settings)
    sqlite_only = sqlite_only or not key
    if _closed:
        return {}
    deadline = time.monotonic() + TIMEOUT
    if not _busy.acquire(timeout=TIMEOUT):
        _logger.warning("RAG: embedding ocupado por 5 s; usando busca local nesta consulta.")
        return {}
    done, result = threading.Event(), {}
    worker_info = {}

    def work():
        try:
            path = cache_path or CACHE_PATH
            if sqlite_only and not Path(path).exists():
                return
            result.update(_score(consulta, documentos, key, deadline, path,
                                 sqlite_only=sqlite_only, diagnostico=worker_info,
                                 documentos_anteriores=documentos_anteriores))
            if sqlite_only or not worker_info.get("chamadas_api"):
                origem = "SQLite (vetores salvos)"
            elif worker_info.get("erro_embedding"):
                origem = "SQLite / busca textual (fallback após falha Gemini)"
            else:
                origem = "Gemini / cache SQLite"
            worker_info.update(origem=origem, vetores=len(result))
            if not result:
                worker_info["origem"] = "Busca textual local (cache sem vetores suficientes)"
        except Exception as exc:
            worker_info["erro_embedding"] = type(exc).__name__
            # Não logar a exceção completa: pode conter texto da memória/chave.
            _logger.warning("RAG: embeddings indisponíveis (%s); usando busca local.", type(exc).__name__)
        finally:
            _busy.release()
            done.set()

    worker = threading.Thread(target=work, name="ayla-rag-embeddings", daemon=True)
    try:
        worker.start()
    except Exception:
        _busy.release()
        return {}
    if not done.wait(max(0.0, deadline - time.monotonic())):
        _logger.warning("RAG: embeddings excederam 5 segundos; usando busca local nesta consulta.")
        info["erro_embedding"] = "TimeoutError"
        return {}
    info.update(worker_info)
    if result:
        _registrar_carregamento(info["origem"])
    return dict(result)
