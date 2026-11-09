"""Chat e SSE Groq compatíveis com as sessões da Ayla, sem repetição de stream."""
import hashlib
import json
import math
import re
import time
from threading import RLock

from groq_catalog import chat_model, model_id
from zai_provider import (ZaiClient, ZaiChatConfig, _assistant_response,
                          _validate_finish_reason, log_zai_usage)
from ayla_performance import emit, first, trace_model

_LOCK = RLock()
# Compartilhado entre clientes da mesma chave neste processo, inclusive após reconexão.
_LIMIT_STATE = {}


class GroqQuotaError(RuntimeError):
    status_code = 429

    def __init__(self, seconds):
        self.retry_after = max(0.0, seconds)
        super().__init__(f'Groq: limite de uso (429). Tente em {math.ceil(self.retry_after)} s; '
                         'a Ayla pode usar o modelo reserva de cota configurado.')


class GroqInputLimitError(RuntimeError):
    status_code = 413
    is_quota = True

    def __init__(self, limit, requested):
        self.limit, self.requested = limit, requested
        super().__init__(f'Groq: cota de entrada (ITPM) {limit}; entrada {requested} tokens. '
                         'Instruções, ferramentas e turno atual não cabem com margem segura. '
                         'Reduzir a saída ou aguardar não resolve; usando a reserva de cota.')


def _input_size(kwargs):
    # Inclui schemas de ferramentas; não confundir com apenas o histórico de chat.
    return max(1, len(json.dumps({k: kwargs[k] for k in ('messages', 'tools', 'response_format')
                                 if k in kwargs}, ensure_ascii=False, separators=(',', ':'))))


def _input_limit_error(exc):
    if getattr(exc, 'status_code', None) not in (413, 429):
        return None
    body = getattr(exc, 'body', None)
    if not isinstance(body, dict):
        return None
    error = body.get('error', body)
    if not isinstance(error, dict) or error.get('code') != 'rate_limit_exceeded':
        return None
    message = str(error.get('message', ''))
    if 'request too large' not in message.lower() or not re.search(r'input tokens per minute|\bITPM\b', message, re.I):
        return None
    match = re.search(r'Limit\s+([\d,]+),\s*Requested\s+([\d,]+)', message, re.I)
    if match:
        limit, requested = (int(v.replace(',', '')) for v in match.groups())
        if requested > limit > 0:
            return limit, requested
    return None


class GroqModalityError(ValueError):
    status_code = 400


def _seconds(value):
    value = str(value or '').strip()
    try:
        result = float(value)
    except ValueError:
        parts = re.findall(r'(\d+(?:\.\d+)?)(ms|s|m|h|d)', value)
        if ''.join(n + unit for n, unit in parts) != value:
            return 0.0
        result = sum(float(n) * {'ms': .001, 's': 1, 'm': 60, 'h': 3600, 'd': 86400}[u]
                     for n, u in parts)
    return max(0.0, result) if math.isfinite(result) else 0.0


class GroqClient(ZaiClient):
    provider_name = "Groq"

    def __init__(self, api_key, *, timeout=45.0, http_client=None, max_output_tokens=2048):
        if not str(api_key or '').strip():
            raise RuntimeError('GROQ_API_KEY não configurada; informe a chave Groq nas configurações de voz ou no .env.')
        self._max_output_tokens = max(128, min(65536, int(max_output_tokens)))
        self._identity = hashlib.sha256(api_key.strip().encode()).hexdigest()
        super().__init__(api_key, timeout=timeout, http_client=http_client,
                         base_url='https://api.groq.com/openai/v1')

    def list_chat_models(self):
        models = self._sdk_client.models.list()
        return sorted({'groq:' + m.id for m in models.data
                       if chat_model(m.model_dump())})

    def rate_limits(self, model):
        """Últimos cabeçalhos observados; não representam consumo de outros processos."""
        with _LOCK:
            return dict(_LIMIT_STATE.get((self._identity, model_id(model)), {}))

    def _record_limits(self, model, headers, *, limited=False):
        headers = {str(k).lower(): v for k, v in headers.items()}
        now = time.monotonic()
        delay = _seconds(headers.get('retry-after')) if limited else 0.0
        for kind in ('requests', 'tokens'):
            try:
                exhausted = float(headers.get(f'x-ratelimit-remaining-{kind}', 'inf')) <= 0
            except (TypeError, ValueError):
                exhausted = False
            if exhausted:
                delay = max(delay, _seconds(headers.get(f'x-ratelimit-reset-{kind}')))
        if limited and not delay:
            delay = 60.0
        with _LOCK:
            key = (self._identity, model_id(model))
            old = _LIMIT_STATE.get(key, {})
            _LIMIT_STATE[key] = {
                **old,
                **{k: v for k, v in headers.items() if k.startswith('x-ratelimit-')},
                'blocked_until': max(old.get('blocked_until', 0), now + delay),
            }
        return delay

    def _learn_input_limit(self, model, kwargs, limit, requested):
        with _LOCK:
            state = _LIMIT_STATE.setdefault((self._identity, model_id(model)), {})
            state['input_token_limit'] = limit
            state['input_tokens_per_char'] = requested / _input_size(kwargs)
        print(f'⚠️ [Groq] {model_id(model)}: limite real de entrada informado pela API: {limit} tokens/min.')

    def _fit_input(self, model, kwargs):
        state = self.rate_limits(model)
        limit = state.get('input_token_limit')
        density = state.get('input_tokens_per_char')
        if not limit or not density:
            return kwargs
        # Estimativa calibrada pela rejeição real, com 10% de margem; não é tokenizer.
        budget = math.floor(limit * .9)
        result = dict(kwargs)
        result['messages'] = list(kwargs['messages'])
        removed = 0
        while math.ceil(_input_size(result) * density) > budget:
            users = [i for i, m in enumerate(result['messages']) if m.get('role') == 'user']
            if len(users) < 2:
                raise GroqInputLimitError(limit, math.ceil(_input_size(result) * density))
            start, end = users[0], users[1]
            # Retira um turno inteiro, nunca separa tool_calls de tool results.
            result['messages'][start:end] = [m for m in result['messages'][start:end]
                                            if m.get('role') in ('system', 'developer')]
            removed += 1
        if removed:
            print(f'⚠️ [Groq] Enviando contexto reduzido: {removed} turno(s) antigo(s) omitido(s) '
                  'desta chamada para caber na cota de entrada. Histórico salvo preservado.')
        return result

    def _prepare_messages(self, messages):
        messages = list(messages)
        if any(m.attachments for m in messages):
            raise GroqModalityError('Groq: modality not supported neste adaptador de texto; use o reserva de mídia.')
        return messages

    @staticmethod
    def _request_kwargs(model, messages, config, stream):
        name = model_id(model)
        # Reutiliza serialização de ferramentas, retirando extensões exclusivas da Z.ai.
        kwargs = ZaiClient._request_kwargs(name, messages, config, stream)
        kwargs.pop('extra_body', None)
        kwargs.pop('max_tokens', None)
        kwargs['max_completion_tokens'] = int(config.max_tokens) if config.max_tokens is not None else 2048
        for message in kwargs['messages']:
            message.pop('name', None)
            message.pop('reasoning_content', None)
        effort = str(config.thinking_level or 'low').lower()
        if name in {'openai/gpt-oss-20b', 'openai/gpt-oss-120b'}:
            kwargs['reasoning_effort'] = {'none': 'low', 'minimal': 'low', 'xhigh': 'high',
                                          'max': 'high'}.get(effort, effort)
        if name.startswith('openai/gpt-oss'):
            kwargs['extra_body'] = {'include_reasoning': False}
        if name in {'qwen/qwen3.8-27b', 'minimaxai/minimax-m2.7', 'meta-models/muse-spark-open'}:
            kwargs['extra_body'] = {'reasoning_format': 'hidden'}
        if name == 'qwen/qwen3.8-27b':
            kwargs['reasoning_effort'] = {'minimal': 'none', 'xhigh': 'high', 'max': 'high'}.get(effort, effort)
        elif name == 'meta-models/muse-spark-open':
            kwargs['reasoning_effort'] = {'none': 'low', 'minimal': 'low', 'max': 'xhigh'}.get(effort, effort)
        if 'safeguard' in name:
            kwargs.pop('tools', None)
            kwargs.pop('tool_choice', None)
        return kwargs

    def _request(self, model, messages, config, stream):
        kwargs = self._request_kwargs(model, self._request_messages(
            self._prepare_messages(messages), config), config, stream)
        model_max = 16384 if model_id(model) == 'qwen/qwen3.8-27b' else 32768 if model_id(model) == 'llama-3.3-70b-versatile' else 65536
        kwargs['max_completion_tokens'] = max(1, min(kwargs['max_completion_tokens'], self._max_output_tokens, model_max))
        with _LOCK:
            remaining = self.rate_limits(model).get('blocked_until', 0) - time.monotonic()
            if remaining > 0:
                raise GroqQuotaError(remaining)
        kwargs = self._fit_input(model, kwargs)
        # Uma única recuperação antes de abrir a resposta; nunca repete stream emitido.
        for attempt in range(2):
            emit('provider_dispatch')
            try:
                raw = self._sdk_client.chat.completions.with_raw_response.create(**kwargs)
                break
            except Exception as exc:
                input_limit = _input_limit_error(exc)
                if input_limit:
                    limit, requested = input_limit
                    self._learn_input_limit(model, kwargs, limit, requested)
                    if attempt:
                        raise GroqInputLimitError(limit, requested) from None
                    kwargs = self._fit_input(model, kwargs)
                    continue
                if getattr(exc, 'status_code', None) == 429:
                    delay = self._record_limits(model, exc.response.headers, limited=True)
                    raise GroqQuotaError(delay) from None
                raise
        self._record_limits(model, raw.headers)
        try:
            return raw.parse()
        except BaseException:
            raw.http_response.close()
            raise

    @trace_model
    def complete(self, model, messages, config=None):
        result = self._request(model, messages, config or ZaiChatConfig(), False)
        first('first_provider_event')
        result.model = 'groq:' + model_id(result.model or model)
        choice = result.choices[0] if result.choices else None
        response = _assistant_response(choice.message if choice else None, result.usage, result.model, result)
        log_zai_usage(result.usage, result.model)
        _validate_finish_reason(response.finish_reason, self.provider_name)
        if response.text:
            first('first_content')
        return response

    def _stream(self, model, messages, config=None):
        # O stream abre dentro do gerador; finally fecha mesmo em cancelamento/erro.
        stream = self._request(model, messages, config or ZaiChatConfig(), True)
        try:
            for chunk in stream:
                data = chunk.model_dump()
                data['model'] = 'groq:' + model_id(data.get('model') or model)
                data['usage'] = data.get('usage') or (data.get('x_groq') or {}).get('usage')
                for choice in data.get('choices') or []:
                    delta = choice.get('delta') or {}
                    if delta.get('reasoning') is not None:
                        delta['reasoning_content'] = delta.pop('reasoning')
                yield data
        finally:
            stream.close()
