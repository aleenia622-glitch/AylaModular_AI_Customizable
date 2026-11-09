"""Transporte compartilhado; leases não contêm histórico nem configuração de chat."""
from dataclasses import dataclass
from threading import RLock

from ayla_provider import AylaClient
from gemini_catalog import gemini_key
from groq_catalog import groq_key, output_limit
from deepseek_catalog import deepseek_key
from ayla_performance import emit


@dataclass(eq=False)
class _Entry:
    client: object
    users: int = 0
    retired: bool = False


class ClientLease:
    def __init__(self, pool, entry):
        self._pool, self._entry = pool, entry
        self.client = entry.client
        self._released = False

    def close(self):
        self._pool.release(self)


class ApiClientPool:
    def __init__(self, factory=AylaClient):
        self._factory = factory
        self._lock = RLock()
        self._entries = {}
        self._closed = False
        self._counts = dict(created=0, reused=0, closed=0, close_errors=0)

    def _close(self, entry):
        try:
            entry.client.close()
        except Exception:
            self._counts['close_errors'] += 1
        finally:
            self._counts['closed'] += 1
            emit('client_closed')

    def acquire(self, api_key='', *, settings=None, timeout=45.0, replace=None):
        # Apenas parâmetros que definem transporte/autenticação. Nunca logar key.
        key = (api_key, gemini_key(settings), float(timeout), groq_key(settings), output_limit(settings), deepseek_key(settings))
        with self._lock:
            if self._closed:
                raise RuntimeError('Pool de API encerrado.')
            entry = self._entries.get(key)
            # Compare-and-swap: dois workers que falharam no mesmo cliente
            # reaproveitam uma única substituição, sem fechar streams em curso.
            if entry is None or (replace is not None and entry.client is replace):
                client = self._factory(api_key=api_key, settings=settings, timeout=timeout,
                                       resolved_gemini_key=key[1], resolved_groq_key=key[3],
                                       resolved_deepseek_key=key[5])
                previous = entry
                entry = _Entry(client)
                self._entries[key] = entry
                self._counts['created'] += 1
                emit('client_created')
                if previous is not None:
                    previous.retired = True
                    if not previous.users:
                        self._close(previous)
            else:
                self._counts['reused'] += 1
                emit('client_reused')
            entry.users += 1
            return ClientLease(self, entry)

    def release(self, lease):
        with self._lock:
            if lease._released:
                return
            lease._released = True
            entry = lease._entry
            entry.users -= 1
            if entry.retired and not entry.users:
                self._close(entry)

    def retire(self):
        """Troca de credenciais: novos pedidos não recebem clientes antigos."""
        with self._lock:
            entries = list(self._entries.values())
            self._entries.clear()
            for entry in entries:
                entry.retired = True
                if not entry.users:
                    self._close(entry)

    def close(self):
        with self._lock:
            self._closed = True
            self.retire()

    def stats(self):
        with self._lock:
            return dict(self._counts)
