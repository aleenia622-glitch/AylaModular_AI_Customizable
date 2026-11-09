"""Escolhe o provedor pelo modelo, mantendo as interfaces internas da Ayla."""
from gemini_catalog import gemini_key, is_gemini
from groq_catalog import groq_key, is_groq, output_limit
from deepseek_catalog import deepseek_key, is_deepseek
from zai_provider import ZaiClient, _payload_to_messages
from ayla_emoji_context import normalizar_mensagens_contexto
from threading import RLock
from ayla_performance import emit


class AylaClient:
    def __init__(self, api_key='', *, settings=None, timeout=45.0, resolved_gemini_key=None, resolved_groq_key=None, resolved_deepseek_key=None):
        self._zai_key = api_key
        self._gemini_key = gemini_key(settings) if resolved_gemini_key is None else resolved_gemini_key
        self._groq_key = groq_key(settings) if resolved_groq_key is None else resolved_groq_key
        self._groq_output_limit = output_limit(settings)
        self._deepseek_key = deepseek_key(settings) if resolved_deepseek_key is None else resolved_deepseek_key
        self._timeout = timeout
        self._clients = {}
        self._lock = RLock()
        self._closed = False

    def _client(self, model):
        provider = 'deepseek' if is_deepseek(model) else 'groq' if is_groq(model) else 'gemini' if is_gemini(model) else 'zai'
        with self._lock:
            if self._closed:
                raise RuntimeError('Cliente de API encerrado.')
            if provider not in self._clients:
                if provider == 'deepseek':
                    from deepseek_provider import DeepSeekClient
                    self._clients[provider] = DeepSeekClient(self._deepseek_key, timeout=self._timeout)
                elif provider == 'gemini':
                    from gemini_provider import GeminiClient
                    self._clients[provider] = GeminiClient(self._gemini_key, timeout=self._timeout)
                elif provider == 'groq':
                    from groq_provider import GroqClient
                    self._clients[provider] = GroqClient(self._groq_key, timeout=self._timeout, max_output_tokens=self._groq_output_limit)
                else:
                    self._clients[provider] = ZaiClient(self._zai_key, timeout=self._timeout)
                emit('provider_client_created')
            else:
                emit('provider_client_reused')
            return self._clients[provider]

    def create_session(self, model, config=None, history=None):
        # Adia a validação da chave até a chamada para permitir fallback entre provedores.
        return RoutedSession(self, model, config, history)

    def complete(self, model, messages, config=None):
        return self._client(model).complete(model=model, messages=normalizar_mensagens_contexto(messages), config=config)

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            for client in self._clients.values():
                try:
                    client.close()
                    emit('provider_client_closed')
                except Exception:
                    # Um provedor não pode impedir o fechamento dos demais.
                    pass


class RoutedSession:
    def __init__(self, client, model, config, history):
        self.client, self.model, self.config = client, model, config
        self._history = normalizar_mensagens_contexto(history or [])

    def get_history(self):
        return list(self._history)

    def _session(self):
        return self.client._client(self.model).create_session(
            model=self.model, config=self.config, history=self._history)

    def send(self, payload):
        session = self._session()
        result = session.send(normalizar_mensagens_contexto(_payload_to_messages(payload)))
        self._history = normalizar_mensagens_contexto(session.get_history())
        return result

    def stream(self, payload):
        session = self._session()
        yield from session.stream(normalizar_mensagens_contexto(_payload_to_messages(payload)))
        self._history = normalizar_mensagens_contexto(session.get_history())
