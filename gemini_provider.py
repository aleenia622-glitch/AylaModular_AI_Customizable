"""Gemini Developer API nativa (AI Studio), com streaming e ferramentas da Ayla.

Usa REST via httpx, já instalado pela Ayla; não depende do SDK legado google.generativeai.
"""
from __future__ import annotations

import base64
import copy
import json
import re
import time
import uuid

import httpx
from ayla_performance import trace_model, stage, emit, first

from gemini_catalog import chat_model
from zai_provider import (ZaiChatConfig, ZaiChatSession, ZaiMessage, ZaiResponse,
                          ZaiStreamEvent, ZaiToolCall, _payload_to_messages, log_zai_usage,
                          notificar_primeiro_token)

BASE_URL = 'https://generativelanguage.googleapis.com/v1beta'
FLASH_LITE_MODELS = frozenset({'gemini-3.5-flash-lite', 'gemini-3.1-flash-lite'})
FLASH_LITE_ANTI_HALLUCINATION_PROMPT = ""


class GeminiAPIError(RuntimeError):
    def __init__(self, code, message):
        self.status_code = code
        super().__init__(f'Google Gemini HTTP {code}: {message}')


class GeminiContentBlockedError(RuntimeError):
    def __init__(self, reason):
        self.reason = reason
        self.user_message = (
            f'O Gemini bloqueou a solicitação ou a resposta por um filtro de conteúdo ({reason}). '
            'Não foi possível concluir esta resposta.'
        )
        super().__init__(self.user_message)


def request_body(model, messages, config):
    contents, system = [], [config.system_prompt] if config.system_prompt else []
    call_names, native_ids = {}, {}
    for message in messages:
        if message.role == 'system':
            system.append(message.text)
            continue
        role = 'model' if message.role == 'assistant' else 'user'
        parts = []
        native = getattr(message, 'provider_content', None)
        if message.role == 'assistant' and native and native.get('model') == model:
            parts = copy.deepcopy(native['parts'])
        elif message.role == 'tool':
            try:
                result = json.loads(message.text)
            except (ValueError, TypeError):
                result = message.text
            parts = [{'functionResponse': {
                'name': message.name or call_names.get(message.tool_call_id, 'tool'),
                'response': result if isinstance(result, dict) else {'result': result},
            }}]
            if message.tool_call_id in native_ids:
                parts[0]['functionResponse']['id'] = native_ids[message.tool_call_id]
        else:
            if message.text:
                parts.append({'text': message.text})
            for call in message.tool_calls:
                # Histórico de outro modelo não possui assinatura Gemini válida.
                parts.append({'functionCall': {'name': call.name, 'args': call.arguments},
                              'thoughtSignature': 'skip_thought_signature_validator'})
            for attachment in message.attachments:
                data = attachment.data
                if isinstance(data, bytes):
                    data = base64.b64encode(data).decode('ascii')
                elif data.startswith('data:'):
                    data = data.split(',', 1)[1]
                parts.append({'inlineData': {'mimeType': attachment.mime_type, 'data': data}})
        for call in message.tool_calls:
            call_names[call.id] = call.name
        if message.role == 'assistant':
            raw_calls = [p['functionCall'] for p in parts if 'functionCall' in p]
            for call, raw in zip(message.tool_calls, raw_calls):
                if raw.get('id'):
                    native_ids[call.id] = raw['id']
        if not parts:
            continue
        # Agrupa resultados paralelos em um único turno de usuário.
        if contents and contents[-1]['role'] == role and role == 'user':
            contents[-1]['parts'].extend(parts)
        else:
            contents.append({'role': role, 'parts': parts})
    body = {'contents': contents, 'safetySettings': [
        {'category': category, 'threshold': 'BLOCK_NONE'}
        for category in ('HARM_CATEGORY_HARASSMENT', 'HARM_CATEGORY_HATE_SPEECH',
                         'HARM_CATEGORY_SEXUALLY_EXPLICIT', 'HARM_CATEGORY_DANGEROUS_CONTENT')
    ]}
    if model in FLASH_LITE_MODELS:
        system.append(FLASH_LITE_ANTI_HALLUCINATION_PROMPT)
    if system:
        body['systemInstruction'] = {'parts': [{'text': '\n\n'.join(system)}]}
    generation = {}
    for attr, key in (('temperature', 'temperature'), ('top_p', 'topP'), ('max_tokens', 'maxOutputTokens')):
        value = getattr(config, attr)
        if attr == 'temperature' and model.startswith('gemini-'):
            continue
        if value is not None:
            generation[key] = value
    # LOW/HIGH são suportados pela família 3; 2.5 usa orçamento de tokens.
    level = str(config.thinking_level or 'low').lower()
    if model.startswith('gemini-3') and 'robotics' not in model:
        generation['thinkingConfig'] = {'thinkingLevel': 'HIGH' if level in ('high', 'xhigh', 'max') else 'LOW'}
    elif model.startswith('gemini-2.5'):
        budget = {'none': 0, 'minimal': 0, 'low': 1024, 'medium': 4096,
                  'high': 8192, 'xhigh': 16384, 'max': 24576}.get(level, 1024)
        if 'pro' in model:
            budget = max(128, budget)
        generation['thinkingConfig'] = {'thinkingBudget': budget}
    if config.response_format:
        generation['responseMimeType'] = 'application/json'
        schema = config.response_format.get('json_schema', {}).get('schema')
        if schema:
            generation['responseJsonSchema'] = schema
    body['generationConfig'] = generation
    if config.tools:
        declarations = []
        for tool in config.tools:
            fn = tool['function']
            declaration = {'name': fn['name'], 'description': fn.get('description', '')}
            if fn.get('parameters', {}).get('properties'):
                declaration['parametersJsonSchema'] = copy.deepcopy(fn['parameters'])
            declarations.append(declaration)
        body['tools'] = [{'functionDeclarations': declarations}]
        body['toolConfig'] = {'functionCallingConfig': {'mode': 'AUTO'}}
    return body


def parse_response(data, model):
    candidates = data.get('candidates') or []
    candidate = candidates[0] if candidates else {}
    parts = candidate.get('content', {}).get('parts', [])
    text = ''.join(p.get('text', '') for p in parts if not p.get('thought'))
    calls = [ZaiToolCall(name=p['functionCall']['name'],
                         arguments=p['functionCall'].get('args', {}),
                         id=p['functionCall'].get('id') or f'call_{uuid.uuid4().hex}')
             for p in parts if 'functionCall' in p]
    if data.get('promptFeedback', {}).get('blockReason'):
        raise GeminiContentBlockedError(data['promptFeedback']['blockReason'])
    finish = candidate.get('finishReason')
    if finish in ('SAFETY', 'RECITATION', 'BLOCKLIST', 'PROHIBITED_CONTENT', 'SPII',
                  'IMAGE_SAFETY', 'IMAGE_PROHIBITED_CONTENT', 'IMAGE_RECITATION'):
        raise GeminiContentBlockedError(finish)
    if finish and finish not in ('STOP', 'MAX_TOKENS'):
        raise RuntimeError(f'Gemini encerrou a resposta: {finish}')
    return ZaiResponse(text=text, tool_calls=calls, usage=data.get('usageMetadata'),
                       model=data.get('modelVersion') or model, finish_reason=finish,
                       provider_content={'model': model, 'parts': copy.deepcopy(parts)})


def log_gemini_usage(usage, model, ttft=None):
    # Registra também respostas sem usageMetadata para garantir o rodapé.
    usage = usage or {}
    log_zai_usage({'prompt_tokens': usage.get('promptTokenCount'),
                   'prompt_tokens_details': {'cached_tokens': usage.get('cachedContentTokenCount')},
                   'completion_tokens': usage.get('candidatesTokenCount'),
                   'completion_tokens_details': {'reasoning_tokens': usage.get('thoughtsTokenCount')},
                   'total_tokens': usage.get('totalTokenCount')}, model, ttft=ttft)


class GeminiChatSession(ZaiChatSession):
    def send(self, payload):
        previous = self._history
        messages = previous + _payload_to_messages(payload)
        response = self.client.complete(self.model, messages, self.config)
        self._history = messages + [ZaiMessage(
            role='assistant', text=response.text, tool_calls=response.tool_calls,
            provider_content=response.provider_content)]
        return response

    @trace_model
    def stream(self, payload):
        messages = self._history + _payload_to_messages(payload)
        parts, calls, texts = [], [], []
        usage, response_model = None, self.model
        usage_logged = False
        finish_reason = None
        notificar_primeiro_token(self.model)
        started = time.perf_counter()
        ttft = None
        stream = self.client.stream_content(self.model, messages, self.config)
        try:
            for data in stream:
                first('first_provider_event')
                if any(part.get('thought') and part.get('text')
                       for candidate in data.get('candidates', [])
                       for part in candidate.get('content', {}).get('parts', [])):
                    first('first_reasoning')
                if ttft is None and any(
                    part.get('text') or part.get('functionCall')
                    for candidate in (data.get('candidates') or [])[:1]
                    for part in candidate.get('content', {}).get('parts', [])
                ):
                    ttft = time.perf_counter() - started
                    notificar_primeiro_token(data.get("modelVersion") or self.model, ttft)
                response = parse_response(data, self.model)
                finish_reason = response.finish_reason or finish_reason
                parts.extend(response.provider_content['parts'])
                calls.extend(response.tool_calls)
                usage = response.usage or usage
                response_model = response.model
                if response.text:
                    first('first_content')
                    texts.append(response.text)
                    yield ZaiStreamEvent(text_delta=response.text, model=response_model)
        finally:
            stream.close()
        if not finish_reason:
            # Um EOF limpo no HTTP não garante que a geração terminou. Tenta
            # obter uma resposta confirmada sem repetir o texto já entregue.
            if usage:
                log_gemini_usage(usage, response_model, ttft=ttft)
            recovered = self.client.complete(self.model, messages, self.config)
            usage_logged = True  # complete já registra o consumo da recuperação.
            emitted_text = ''.join(texts)
            if (recovered.finish_reason not in ('STOP', 'MAX_TOKENS')
                    or not (recovered.text or recovered.tool_calls)
                    or not (recovered.text or '').startswith(emitted_text)):
                raise RuntimeError(
                    'O fluxo do Gemini terminou sem confirmar o fim da resposta e '
                    'não foi possível recuperar uma resposta compatível com o texto já exibido.'
                )
            suffix = (recovered.text or '')[len(emitted_text):]
            parts = recovered.provider_content['parts']
            calls = recovered.tool_calls
            texts = [recovered.text or '']
            usage = recovered.usage
            response_model = recovered.model
            finish_reason = recovered.finish_reason
            if suffix:
                first('first_content')
                yield ZaiStreamEvent(text_delta=suffix, model=response_model)
        if not texts and not calls:
            raise RuntimeError('Gemini retornou uma resposta vazia.')
        self._history = messages + [ZaiMessage(
            role='assistant', text=''.join(texts), tool_calls=calls,
            provider_content={'model': self.model, 'parts': parts})]
        if not usage_logged:
            log_gemini_usage(usage, response_model, ttft=ttft)
        yield ZaiStreamEvent(tool_calls=calls, usage=usage, model=response_model,
                             finish_reason=finish_reason)


class GeminiClient:
    def __init__(self, api_key, *, timeout=45.0, http_client=None):
        if not api_key:
            raise RuntimeError('GEMINI_API_KEY não configurada. Use a chave Google AI Studio nas configurações ou no .env.')
        self._key = api_key
        from ayla_http import connection_limits
        self._httpx_client = http_client or httpx.Client(timeout=timeout, limits=connection_limits())
        self.timeout = timeout

    def _check(self, response):
        if response.is_success:
            return
        response.read()
        try:
            message = response.json().get('error', {}).get('message', 'Falha na API')
        except ValueError:
            message = 'Falha na API'
        raise GeminiAPIError(response.status_code, str(message).replace(self._key, '[chave omitida]'))

    def _url(self, model, method):
        model = model.removeprefix('models/')
        if not re.fullmatch(r'gemini-[a-zA-Z0-9_.-]+', model):
            raise ValueError('Nome de modelo Gemini inválido.')
        return f'{BASE_URL}/models/{model}:{method}'

    def create_session(self, model, config=None, history=None):
        return GeminiChatSession(self, model.removeprefix('models/'), config, history)

    @trace_model
    def complete(self, model, messages, config=None):
        model = model.removeprefix('models/')
        config = config or ZaiChatConfig()
        with stage('request_build'):
            body = request_body(model, messages, config)
        emit('provider_dispatch')
        response = self._httpx_client.post(
            self._url(model, 'generateContent'), headers={'x-goog-api-key': self._key},
            json=body, timeout=config.request_timeout or self.timeout)
        first('first_provider_event')
        self._check(response)
        result = parse_response(response.json(), model)
        if result.text:
            first('first_content')
        if not result.text and not result.tool_calls:
            raise RuntimeError('Gemini retornou uma resposta vazia.')
        log_gemini_usage(result.usage, result.model)
        return result

    def stream_content(self, model, messages, config):
        with stage('request_build'):
            body = request_body(model, messages, config)
        emit('provider_dispatch')
        with self._httpx_client.stream(
            'POST', self._url(model, 'streamGenerateContent'), params={'alt': 'sse'},
            headers={'x-goog-api-key': self._key}, json=body,
            timeout=config.request_timeout or self.timeout,
        ) as response:
            self._check(response)
            event = []
            for line in response.iter_lines():
                if line.startswith('data:'):
                    event.append(line[5:].lstrip())
                elif not line and event:
                    yield json.loads('\n'.join(event))
                    event = []
            if event:
                yield json.loads('\n'.join(event))

    def list_chat_models(self):
        models, token = [], None
        while True:
            params = {'pageSize': 1000}
            if token:
                params['pageToken'] = token
            response = self._httpx_client.get(f'{BASE_URL}/models', params=params,
                                               headers={'x-goog-api-key': self._key})
            self._check(response)
            data = response.json()
            models.extend(m['name'].removeprefix('models/') for m in data.get('models', []) if chat_model(m))
            token = data.get('nextPageToken')
            if not token:
                return list(dict.fromkeys(models))

    def close(self):
        self._httpx_client.close()
