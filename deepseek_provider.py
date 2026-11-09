"""API oficial DeepSeek com sessões, ferramentas e streaming SSE da Ayla."""
from datetime import datetime, timezone
from typing import Any
from deepseek_catalog import (BASE_URL, MAX_OUTPUT_TOKENS, VISION_MODELS,
                              chat_model, model_id)
from zai_provider import (ZaiClient, ZaiChatConfig, _assistant_response,
                          _validate_finish_reason, log_zai_usage)
from ayla_performance import emit, first, trace_model


class DeepSeekModalityError(ValueError):
    status_code = 400


class DeepSeekAuthError(RuntimeError):
    status_code = 401


class DeepSeekBalanceError(RuntimeError):
    status_code = 402
    is_quota = True


class DeepSeekClient(ZaiClient):
    provider_name = 'DeepSeek'

    def __init__(self, api_key, *, timeout=45.0, http_client=None):
        if not str(api_key or '').strip():
            raise DeepSeekAuthError('DEEPSEEK_API_KEY não configurada; preencha a chave na aba ENV.')
        super().__init__(api_key, timeout=timeout, http_client=http_client, base_url=BASE_URL)

    def list_chat_models(self):
        return sorted({'deepseek:' + model_id(m.id)
                       for m in self._sdk_client.models.list().data
                       if chat_model(m.model_dump())})

    def get_balance(self):
        """Consulta de conta; não cria uma geração nem consome tokens de chat."""
        result = self._sdk_client.get('/user/balance', cast_to=dict[str, Any])
        if (not isinstance(result, dict) or not isinstance(result.get('is_available'), bool)
                or not isinstance(result.get('balance_infos'), list)):
            raise ValueError('A DeepSeek retornou um formato de saldo inesperado.')
        return result

    def _prepare_messages(self, messages):
        native = list(messages)
        for message in native:
            if any(not str(a.mime_type).startswith('image/') for a in message.attachments):
                raise DeepSeekModalityError(
                    'DeepSeek: modality not supported; envie texto ou imagens, ou use o reserva de mídia.')
            if message.attachments and message.role != 'user':
                raise DeepSeekModalityError(
                    'DeepSeek: modality not supported; imagens são aceitas apenas em mensagens de usuário.')
        return native

    @staticmethod
    def _request_kwargs(model, messages, config, stream):
        name = model_id(model)
        if not chat_model({'id': name}):
            raise ValueError(f'Modelo DeepSeek fora do catálogo de conversa: {name}')
        if name not in VISION_MODELS and any(isinstance(m.get('content'), list) for m in messages):
            raise DeepSeekModalityError(
                'DeepSeek: modality not supported por este modelo de texto; use Flash ou o reserva de mídia.')
        # Reutiliza o contrato interno, removendo as extensões exclusivas da Z.ai.
        kwargs = ZaiClient._request_kwargs(name, messages, config, stream)
        kwargs.pop('extra_body', None)
        effort = str(config.thinking_level or 'low').strip().lower()
        effort = {'minimal': 'low', 'medium': 'high', 'xhigh': 'high'}.get(effort, effort)
        kwargs['reasoning_effort'] = effort
        kwargs['extra_body'] = {'thinking': {'type': 'disabled' if effort == 'none' else 'enabled'}}
        if effort != 'none':
            # Temperatura não tem efeito em thinking; top_p segue as regras do modelo.
            kwargs.pop('temperature', None)
        if config.max_tokens is not None:
            kwargs['max_tokens'] = max(1, min(int(config.max_tokens), MAX_OUTPUT_TOKENS))
        if kwargs.get('tools') and effort != 'none':
            # Preserve todo raciocínio retornado, inclusive de turnos sem tool_calls.
            # Histórico vindo de outro provedor pode não conter este campo.
            kwargs['messages'] = [dict(m, reasoning_content=m.get('reasoning_content') or '')
                                  if m.get('role') == 'assistant' else m for m in messages]
        if stream:
            kwargs['stream_options'] = {'include_usage': True}
        return kwargs

    def _request(self, model, messages, config, stream):
        kwargs = self._request_kwargs(model, self._request_messages(
            self._prepare_messages(messages), config), config, stream)
        emit('provider_dispatch')
        # Sem repetição automática: uma falha nunca reenvia ferramentas ou texto emitido.
        try:
            return self._sdk_client.chat.completions.create(**kwargs)
        except Exception as exc:
            if getattr(exc, 'status_code', None) == 402:
                raise DeepSeekBalanceError(
                    'DeepSeek: saldo insuficiente (402); usando o reserva de cota configurado.') from None
            raise

    @trace_model
    def complete(self, model, messages, config=None):
        pricing_time = datetime.now(timezone.utc)
        result = self._request(model, messages, config or ZaiChatConfig(), False)
        first('first_provider_event')
        choice = result.choices[0] if result.choices else None
        response = _assistant_response(choice.message if choice else None, result.usage, model, result)
        response.model = 'deepseek:' + model_id(model)
        log_zai_usage(result.usage, response.model, pricing_time=pricing_time)
        _validate_finish_reason(response.finish_reason, self.provider_name)
        if response.text:
            first('first_content')
        return response

    def _stream(self, model, messages, config=None):
        pricing_time = datetime.now(timezone.utc)
        stream = self._request(model, messages, config or ZaiChatConfig(), True)
        try:
            for chunk in stream:
                data = chunk.model_dump()
                data['model'] = 'deepseek:' + model_id(model)
                data['_pricing_time'] = pricing_time
                yield data
        finally:
            stream.close()
