"""Cliente interno da Ayla para a API Chat Completions da Z.ai.

As mensagens e chamadas de ferramenta usam diretamente o protocolo
OpenAI-compatible exposto pela Z.ai. Este modulo nao emula interfaces de outros
provedores.
"""

from __future__ import annotations

import base64
import binascii
import io
import json
import re
import subprocess
import time
import uuid
import wave
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from threading import Lock
from typing import Any, Iterable, Iterator
from ayla_performance import trace_model, stage, emit, first


__all__ = [
    "ZaiChatConfig",
    "ZaiAttachment",
    "ZaiToolCall",
    "ZaiToolResult",
    "ZaiMessage",
    "ZaiResponse",
    "ZaiStreamEvent",
    "ZaiChatSession",
    "ZaiClient",
    "coletar_uso_zai",
    "observar_primeiro_token",
    "log_zai_usage",
    "obter_gasto_total_sessao_zai",
    "obter_gasto_total_acumulado_zai",
    "salvar_consumo_zai",
    "resetar_gasto_total_sessao_zai",
]


_ZAI_BASE_URL = "https://api.z.ai/api/paas/v4/"
_ZAI_DEFAULT_MODEL = "glm-5.3-flash"
# Preços por 1 milhão de tokens; fonte e data de consulta em ayla_model_policy.py:
# https://docs.z.ai/guides/overview/pricing
from ayla_model_policy import PRICES
from ayla_consumo import RegistroConsumo
from pathlib import Path
_ZAI_PRICES_PER_MILLION = {
    name: {"input": rates[0], "cached_input": rates[1] if rates[1] is not None else rates[0],
           "output": rates[2]} for name, rates in PRICES.items()
}
_GASTO_TOTAL_SESSAO_ZAI = 0.0
_GASTO_TOTAL_SESSAO_LOCK = Lock()
_REGISTRO_CONSUMO_ZAI = RegistroConsumo(Path(__file__).resolve().with_name('ayla_consumo_zai.json'))


def salvar_consumo_zai() -> None:
    """Salva um snapshot idempotente; repetir não duplica o gasto."""
    with _GASTO_TOTAL_SESSAO_LOCK:
        _REGISTRO_CONSUMO_ZAI.salvar(_GASTO_TOTAL_SESSAO_ZAI)


def obter_gasto_total_acumulado_zai() -> float:
    with _GASTO_TOTAL_SESSAO_LOCK:
        return _REGISTRO_CONSUMO_ZAI.total(_GASTO_TOTAL_SESSAO_ZAI)


def obter_gasto_total_sessao_zai() -> float:
    """Retorna o custo estimado acumulado desde o início do processo."""
    with _GASTO_TOTAL_SESSAO_LOCK:
        return _GASTO_TOTAL_SESSAO_ZAI


def resetar_gasto_total_sessao_zai() -> None:
    """Reinicia o acumulador; útil ao iniciar explicitamente uma nova sessão."""
    global _GASTO_TOTAL_SESSAO_ZAI
    with _GASTO_TOTAL_SESSAO_LOCK:
        _REGISTRO_CONSUMO_ZAI.salvar(_GASTO_TOTAL_SESSAO_ZAI)
        _REGISTRO_CONSUMO_ZAI.nova_sessao()
        _GASTO_TOTAL_SESSAO_ZAI = 0.0


def _somar_gasto_total_sessao_zai(cost: float | None) -> None:
    if cost is None:
        return
    global _GASTO_TOTAL_SESSAO_ZAI
    with _GASTO_TOTAL_SESSAO_LOCK:
        _GASTO_TOTAL_SESSAO_ZAI += cost
        try:
            _REGISTRO_CONSUMO_ZAI.salvar(_GASTO_TOTAL_SESSAO_ZAI)
        except Exception as exc:
            print(f'⚠️ Não foi possível salvar o consumo Z.ai ({type(exc).__name__}); valor mantido nesta sessão.')


def _format_usage_message(
    models: Iterable[str],
    prompt: int | None,
    cached: int | None,
    completion: int | None,
    reasoning: int | None,
    total: int | None,
    cost: float | None,
    ttft: float | None = None,
) -> str:
    model_names = list(models) or ["desconhecido"]
    from gemini_catalog import is_gemini
    timing = f" | ⏱ Primeiro token: {ttft:.2f}s" if ttft is not None else ""
    if all(is_gemini(name) for name in model_names):
        return f"model={'+'.join(model_names)}" + timing
    fields = [f"model={'+'.join(model_names)}"]
    for name, value in (
        ("input", prompt),
        ("cached_input", cached),
        ("output", completion),
        ("reasoning", reasoning),
        ("total", total),
    ):
        if value is not None:
            fields.append(f"{name}={value}")
    message = "📊 " + " ".join(fields)
    if cost is not None:
        formatted_cost = f"{cost:.6f}".replace(".", ",")
        message += f" | 💰 Custo estimado: US$ {formatted_cost}"
    return message + timing


class _ZaiUsageCollector(list[str]):
    """Mantem um unico resumo com o uso acumulado da interacao atual."""

    def __init__(self) -> None:
        super().__init__()
        self.models: list[str] = []
        self.totals: dict[str, int | None] = {
            "prompt": None,
            "cached": None,
            "completion": None,
            "reasoning": None,
            "total": None,
        }
        self.cost: float | None = None
        self.ttft: float | None = None

    def add_usage(
        self,
        *,
        model: str,
        prompt: int | None,
        cached: int | None,
        completion: int | None,
        reasoning: int | None,
        total: int | None,
        cost: float | None,
        ttft: float | None = None,
    ) -> None:
        if not self.models:
            self.ttft = ttft
        if model not in self.models:
            self.models.append(model)
        for name, value in (
            ("prompt", prompt),
            ("cached", cached),
            ("completion", completion),
            ("reasoning", reasoning),
            ("total", total),
        ):
            if value is not None:
                self.totals[name] = (self.totals[name] or 0) + value
        if cost is not None:
            self.cost = (self.cost or 0.0) + cost

        self[:] = [
            _format_usage_message(
                self.models,
                self.totals["prompt"],
                self.totals["cached"],
                self.totals["completion"],
                self.totals["reasoning"],
                self.totals["total"],
                self.cost,
                self.ttft,
            )
        ]


_USO_ZAI: ContextVar[_ZaiUsageCollector | None] = ContextVar("uso_zai", default=None)


@contextmanager
def coletar_uso_zai():
    """Coleta um resumo acumulado da resposta sem misturar tarefas paralelas."""
    linhas = _ZaiUsageCollector()
    token = _USO_ZAI.set(linhas)
    try:
        yield linhas
    finally:
        _USO_ZAI.reset(token)


_TOKEN_OBSERVER = ContextVar("token_observer", default=None)


@contextmanager
def observar_primeiro_token(callback):
    """Observa início e TTFT da requisição na interação corrente."""
    token = _TOKEN_OBSERVER.set(callback)
    try:
        yield
    finally:
        _TOKEN_OBSERVER.reset(token)


def notificar_primeiro_token(model, ttft=None):
    callback = _TOKEN_OBSERVER.get()
    if callback:
        callback(model, ttft)


@dataclass
class ZaiChatConfig:
    system_prompt: str = ""
    tools: list[dict[str, Any]] = field(default_factory=list)
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    thinking_level: str = "low"
    response_format: dict[str, Any] | None = None
    # Limpeza entre turnos; o raciocínio da sequência atual de ferramentas
    # continua sendo reenviado. False exige um histórico completo e intacto.
    clear_thinking: bool = True
    request_timeout: float | None = None


@dataclass
class ZaiAttachment:
    data: bytes | str
    mime_type: str
    filename: str = "attachment"


@dataclass
class ZaiToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    id: str | None = None


@dataclass
class ZaiToolResult:
    name: str
    result: Any
    call_id: str


@dataclass
class ZaiMessage:
    role: str
    text: str = ""
    attachments: list[ZaiAttachment] = field(default_factory=list)
    tool_calls: list[ZaiToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None
    reasoning_content: str | None = None
    provider_content: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.role not in {"system", "user", "assistant", "tool"}:
            raise ValueError(f"Role Z.ai invalida: {self.role!r}")
        if self.role == "tool" and not self.tool_call_id:
            raise ValueError("Mensagem de ferramenta exige tool_call_id.")
        if self.attachments and self.role != "user":
            raise ValueError("Anexos so podem ser enviados em mensagens de usuario.")
        if self.tool_calls and self.role != "assistant":
            raise ValueError("tool_calls so podem existir em mensagens do assistente.")
        if self.reasoning_content is not None and self.role != "assistant":
            raise ValueError("reasoning_content so pode existir em mensagens do assistente.")

    @classmethod
    def user(
        cls,
        text: str = "",
        attachments: Iterable[ZaiAttachment] | None = None,
    ) -> "ZaiMessage":
        return cls(role="user", text=str(text or ""), attachments=list(attachments or []))

    @classmethod
    def assistant(
        cls,
        text: str = "",
        tool_calls: Iterable[ZaiToolCall] | None = None,
        reasoning_content: str | None = None,
    ) -> "ZaiMessage":
        return cls(role="assistant", text=str(text or ""), tool_calls=list(tool_calls or []),
                   reasoning_content=reasoning_content)

    @classmethod
    def tool(cls, tool_result: ZaiToolResult) -> "ZaiMessage":
        if not isinstance(tool_result, ZaiToolResult):
            raise TypeError("ZaiMessage.tool espera um ZaiToolResult.")
        return cls(
            role="tool",
            text=_tool_result_text(tool_result.result),
            tool_call_id=str(tool_result.call_id),
            name=str(tool_result.name),
        )


@dataclass
class ZaiResponse:
    text: str = ""
    tool_calls: list[ZaiToolCall] = field(default_factory=list)
    usage: Any = None
    model: str | None = None
    reasoning_content: str | None = None
    provider_content: dict[str, Any] | None = None
    finish_reason: str | None = None


@dataclass
class ZaiStreamEvent:
    text_delta: str = ""
    tool_calls: list[ZaiToolCall] = field(default_factory=list)
    usage: Any = None
    model: str | None = None
    finish_reason: str | None = None
    # Conteúdo completo somente no evento final; nunca misturado ao texto visível.
    reasoning_content: str | None = None


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump(exclude_none=True))
    if hasattr(value, "__dict__"):
        return {
            str(key): _json_safe(item)
            for key, item in vars(value).items()
            if not str(key).startswith("_") and item is not None
        }
    return value


def _tool_result_text(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(_json_safe(result), ensure_ascii=False, default=str)


def _normalizar_argumentos(raw_arguments: Any) -> dict[str, Any]:
    if isinstance(raw_arguments, dict):
        return raw_arguments
    if raw_arguments is None or raw_arguments == "":
        return {}
    if isinstance(raw_arguments, str):
        try:
            parsed = json.loads(raw_arguments)
        except Exception as exc:
            return {
                "_invalid_arguments": raw_arguments,
                "_reason": f"invalid JSON: {exc}",
            }
        if isinstance(parsed, dict):
            return parsed
        return {
            "_invalid_arguments": raw_arguments,
            "_reason": "arguments must be a JSON object",
        }
    return {
        "_invalid_arguments": str(raw_arguments),
        "_reason": "unsupported arguments type",
    }


def _attachment_to_api(attachment: ZaiAttachment) -> dict[str, Any]:
    mime = str(attachment.mime_type or "application/octet-stream")
    raw = attachment.data or b""
    if isinstance(raw, str):
        encoded = raw
    else:
        encoded = base64.b64encode(bytes(raw)).decode("ascii")
    data_url = f"data:{mime};base64,{encoded}"

    if mime.startswith("image/"):
        return {"type": "image_url", "image_url": {"url": data_url}}
    if mime.startswith("video/"):
        return {"type": "video_url", "video_url": {"url": data_url}}
    if mime.startswith("audio/"):
        raise ValueError("Áudio precisa ser transcrito antes do chat.")
    return {
        "type": "file",
        "file": {"filename": attachment.filename, "file_data": data_url},
    }


def _message_to_api(message: ZaiMessage) -> dict[str, Any]:
    if not isinstance(message, ZaiMessage):
        raise TypeError("O historico Z.ai deve conter apenas ZaiMessage.")

    if message.role == "tool":
        result: dict[str, Any] = {
            "role": "tool",
            "tool_call_id": str(message.tool_call_id),
            "content": str(message.text or ""),
        }
        if message.name:
            result["name"] = str(message.name)
        return result

    if message.role == "assistant":
        result = {"role": "assistant", "content": message.text or None}
        if message.reasoning_content is not None:
            result["reasoning_content"] = message.reasoning_content
        if message.tool_calls:
            result["tool_calls"] = [
                {
                    "id": str(call.id or f"call_{uuid.uuid4().hex}"),
                    "type": "function",
                    "function": {
                        "name": str(call.name),
                        "arguments": json.dumps(
                            _json_safe(call.arguments),
                            ensure_ascii=False,
                            default=str,
                        ),
                    },
                }
                for call in message.tool_calls
            ]
        return result

    if not message.attachments:
        return {"role": message.role, "content": str(message.text or "")}

    content: list[dict[str, Any]] = []
    if message.text:
        content.append({"type": "text", "text": str(message.text)})
    content.extend(_attachment_to_api(attachment) for attachment in message.attachments)
    return {"role": message.role, "content": content}


def _validate_attachment_mix(messages: Iterable[ZaiMessage]) -> None:
    """A restrição file + image/video vale para a requisição inteira."""
    has_file = has_visual = False
    for message in messages:
        if not isinstance(message, ZaiMessage):
            raise TypeError("O historico Z.ai deve conter apenas ZaiMessage.")
        for attachment in message.attachments:
            mime = str(attachment.mime_type or "application/octet-stream")
            if mime.startswith(("image/", "video/")):
                has_visual = True
            elif not mime.startswith("audio/"):
                has_file = True
    if has_file and has_visual:
        raise ValueError(
            "A Z.ai não aceita documentos junto com imagens ou vídeos na mesma "
            "requisição. Envie-os em conversas separadas, sem esses anexos no histórico."
        )


def _payload_to_messages(payload: Any) -> list[ZaiMessage]:
    if isinstance(payload, str):
        return [ZaiMessage.user(payload)]
    if isinstance(payload, ZaiMessage):
        return [payload]
    if isinstance(payload, ZaiAttachment):
        return [ZaiMessage.user(attachments=[payload])]
    if isinstance(payload, ZaiToolResult):
        return [ZaiMessage.tool(payload)]
    if not isinstance(payload, (list, tuple)):
        raise TypeError(
            "Payload Z.ai deve ser texto, mensagem, anexo, resultado de ferramenta ou lista."
        )

    items = list(payload)
    if not items:
        return []
    if all(isinstance(item, ZaiMessage) for item in items):
        return list(items)
    if all(isinstance(item, ZaiAttachment) for item in items):
        return [ZaiMessage.user(attachments=items)]
    if all(isinstance(item, ZaiToolResult) for item in items):
        return [ZaiMessage.tool(item) for item in items]
    if all(isinstance(item, (str, ZaiAttachment)) for item in items):
        text = "\n".join(item for item in items if isinstance(item, str))
        attachments = [item for item in items if isinstance(item, ZaiAttachment)]
        return [ZaiMessage.user(text=text, attachments=attachments)]
    raise TypeError("Listas de payload Z.ai nao podem misturar tipos de mensagem incompativeis.")


def _assistant_response(message: Any, usage: Any, default_model: str, result: Any) -> ZaiResponse:
    raw_text = _attr(message, "content", "") or ""
    if isinstance(raw_text, list):
        raw_text = "".join(
            str(_attr(item, "text", "") or "")
            for item in raw_text
            if _attr(item, "type", "") == "text"
        )

    tool_calls: list[ZaiToolCall] = []
    for raw_call in _attr(message, "tool_calls", []) or []:
        function = _attr(raw_call, "function", None)
        name = str(_attr(function, "name", "") or "").strip()
        if not name:
            continue
        tool_calls.append(
            ZaiToolCall(
                name=name,
                arguments=_normalizar_argumentos(_attr(function, "arguments", None)),
                id=str(_attr(raw_call, "id", "") or f"call_{uuid.uuid4().hex}"),
            )
        )

    return ZaiResponse(
        text=str(raw_text),
        tool_calls=tool_calls,
        usage=usage,
        model=str(_attr(result, "model", default_model) or default_model),
        reasoning_content=_attr(message, "reasoning_content", None),
        finish_reason=_attr((_attr(result, "choices", None) or [None])[0], "finish_reason", None),
    )


def _usage_number(usage: Any, path: tuple[str, ...]) -> int | None:
    current = usage
    for name in path:
        current = _attr(current, name, None)
        if current is None:
            return None
    try:
        return int(current)
    except (TypeError, ValueError):
        return None


def log_zai_usage(usage: Any, model: str | None = None, ttft: float | None = None,
                  *, pricing_time=None) -> None:
    if not usage and ttft is None:
        return
    prompt = _usage_number(usage, ("prompt_tokens",))
    cached = _usage_number(usage, ("prompt_tokens_details", "cached_tokens"))
    if cached is None:
        cached = _usage_number(usage, ("prompt_cache_hit_tokens",))
    completion = _usage_number(usage, ("completion_tokens",))
    reasoning = _usage_number(usage, ("completion_tokens_details", "reasoning_tokens"))
    total = _usage_number(usage, ("total_tokens",))
    emit('usage', prompt_tokens=prompt, cached_tokens=cached,
         completion_tokens=completion, reasoning_tokens=reasoning)
    model_name = model or "desconhecido"
    from deepseek_catalog import is_deepseek, billing_rates
    deepseek = is_deepseek(model_name)
    prices = billing_rates(model_name, pricing_time) if deepseek else _ZAI_PRICES_PER_MILLION.get(model_name)
    cost = None
    if prices is not None and prompt is not None and completion is not None:
        cached_tokens = min(prompt, max(0, cached or 0))
        cost = (
            (prompt - cached_tokens) * prices["input"]
            + cached_tokens * prices["cached_input"]
            + completion * prices["output"]
        ) / 1_000_000
    # O rodapé agrega provedores; os históricos persistentes ficam separados.
    if deepseek:
        from deepseek_consumo import somar_gasto_deepseek
        somar_gasto_deepseek(cost)
    else:
        _somar_gasto_total_sessao_zai(cost)
    message = _format_usage_message(
        [model_name], prompt, cached, completion, reasoning, total, cost, ttft
    )
    collected = _USO_ZAI.get()
    if collected is not None:
        from gemini_catalog import is_gemini
        collected.add_usage(
            model=model_name,
            prompt=prompt,
            cached=cached,
            completion=completion,
            reasoning=reasoning,
            total=total,
            cost=cost,
            ttft=None if is_gemini(model_name) else ttft,
        )
    print(message)


class ZaiIncompleteResponseError(RuntimeError):
    """Resposta sem conclusão válida; não deve provocar continuação automática."""


def _validate_finish_reason(reason: str | None, provider: str = "Z.ai") -> None:
    reason = str(reason or "").lower()
    if reason in {"stop", "tool_calls"}:
        return
    descriptions = {
        "length": "A resposta atingiu o limite de saída e ficou incompleta.",
        "max_tokens": "A resposta atingiu o limite de saída e ficou incompleta.",
        "network_error": f"A resposta foi interrompida por uma falha de rede da API {provider}.",
        "model_context_window_exceeded": f"A conversa excedeu o limite de contexto da API {provider}.",
        "sensitive": f"A resposta foi interrompida pelo filtro de conteúdo da API {provider}.",
    }
    raise ZaiIncompleteResponseError(descriptions.get(
        reason, f"A API {provider} não confirmou uma conclusão válida da resposta."
    ))


class ZaiChatSession:
    def __init__(
        self,
        client: "ZaiClient",
        model: str,
        config: ZaiChatConfig | None = None,
        history: Iterable[ZaiMessage] | None = None,
    ):
        self.client = client
        self.model = str(model)
        self.config = config or ZaiChatConfig()
        self._history = list(history or [])
        if not all(isinstance(message, ZaiMessage) for message in self._history):
            raise TypeError("O historico da sessao deve conter apenas ZaiMessage.")

    def get_history(self) -> list[ZaiMessage]:
        return list(self._history)

    def send(self, payload: Any) -> ZaiResponse:
        new_messages = _payload_to_messages(payload)
        previous_history = self._history
        self._history = previous_history + new_messages
        try:
            if any(str(a.mime_type).startswith("audio/") for m in self._history for a in m.attachments):
                self._history = self.client._prepare_messages(self._history)
            response = self.client.complete(
                model=self.model,
                messages=self._history,
                config=self.config,
            )
            _validate_finish_reason(response.finish_reason, getattr(self.client, "provider_name", "Z.ai"))
        except BaseException:
            self._history = previous_history
            raise

        if response.text or response.tool_calls or response.reasoning_content is not None:
            self._history.append(
                ZaiMessage.assistant(text=response.text, tool_calls=response.tool_calls,
                                     reasoning_content=response.reasoning_content)
            )
        return response

    @trace_model
    def stream(self, payload: Any) -> Iterator[ZaiStreamEvent]:
        new_messages = _payload_to_messages(payload)
        previous_history = self._history
        self._history = previous_history + new_messages
        try:
            if any(str(a.mime_type).startswith("audio/") for m in self._history for a in m.attachments):
                self._history = self.client._prepare_messages(self._history)
            notificar_primeiro_token(self.model)
            started = time.perf_counter()
            ttft = None
            raw_stream = self.client._stream(
                model=self.model,
                messages=self._history,
                config=self.config,
            )
        except BaseException:
            self._history = previous_history
            raise

        full_text: list[str] = []
        full_reasoning: list[str] = []
        tool_fragments: dict[int, dict[str, str]] = {}
        usage = None
        response_model = self.model
        finish_reason = None
        pricing_time = None
        try:
            for chunk in raw_stream:
                first('first_provider_event')  # Chunk decodificado pelo SDK, não byte SSE.
                chunk_usage = _attr(chunk, "usage", None)
                if chunk_usage:
                    usage = chunk_usage
                pricing_time = _attr(chunk, '_pricing_time', pricing_time)
                response_model = str(_attr(chunk, "model", response_model) or response_model)
                choices = _attr(chunk, "choices", []) or []
                if not choices:
                    continue
                finish_reason = _attr(choices[0], "finish_reason", None) or finish_reason
                delta = _attr(choices[0], "delta", None)
                if ttft is None and (
                    _attr(delta, "content", None)
                    or _attr(delta, "reasoning_content", None)
                    or any(_attr(_attr(call, "function", None), "name", None)
                           or _attr(_attr(call, "function", None), "arguments", None)
                           for call in _attr(delta, "tool_calls", []) or [])
                ):
                    ttft = time.perf_counter() - started
                    notificar_primeiro_token(response_model, ttft)
                reasoning_delta = _attr(delta, "reasoning_content", None)
                if reasoning_delta is not None:
                    if reasoning_delta:
                        first('first_reasoning')
                    full_reasoning.append(reasoning_delta)
                text_delta = _attr(delta, "content", None)
                if text_delta:
                    first('first_content')
                    text_delta = str(text_delta)
                    full_text.append(text_delta)
                    yield ZaiStreamEvent(text_delta=text_delta, model=response_model)

                for raw_call in _attr(delta, "tool_calls", []) or []:
                    try:
                        index = int(_attr(raw_call, "index", 0) or 0)
                    except (TypeError, ValueError):
                        index = 0
                    fragment = tool_fragments.setdefault(
                        index,
                        {"id": "", "name": "", "arguments": ""},
                    )
                    call_id = _attr(raw_call, "id", None)
                    if call_id and not fragment["id"]:
                        fragment["id"] = str(call_id)
                    function = _attr(raw_call, "function", None)
                    name = _attr(function, "name", None)
                    arguments = _attr(function, "arguments", None)
                    if name:
                        fragment["name"] += str(name)
                    if arguments:
                        if isinstance(arguments, dict):
                            fragment["arguments"] += json.dumps(arguments, ensure_ascii=False)
                        else:
                            fragment["arguments"] += str(arguments)
        except BaseException:
            self._history = previous_history
            raise
        finally:
            close = getattr(raw_stream, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass

        tool_calls: list[ZaiToolCall] = []
        for index in sorted(tool_fragments):
            fragment = tool_fragments[index]
            if not fragment["name"]:
                continue
            tool_calls.append(
                ZaiToolCall(
                    name=fragment["name"],
                    arguments=_normalizar_argumentos(fragment["arguments"]),
                    id=fragment["id"] or f"call_{uuid.uuid4().hex}",
                )
            )

        log_zai_usage(usage, response_model, ttft=ttft, pricing_time=pricing_time)
        try:
            _validate_finish_reason(finish_reason, getattr(self.client, "provider_name", "Z.ai"))
        except ZaiIncompleteResponseError:
            self._history = previous_history
            raise

        response_text = "".join(full_text)
        reasoning_content = "".join(full_reasoning) if full_reasoning else None
        if response_text or tool_calls or reasoning_content is not None:
            self._history.append(
                ZaiMessage.assistant(text=response_text, tool_calls=tool_calls,
                                     reasoning_content=reasoning_content)
            )
        if tool_calls or usage is not None or reasoning_content is not None or finish_reason:
            yield ZaiStreamEvent(
                tool_calls=tool_calls,
                usage=usage,
                model=response_model,
                reasoning_content=reasoning_content,
                finish_reason=finish_reason,
            )


class ZaiClient:
    def __init__(
        self,
        api_key: str,
        *,
        timeout: float = 45.0,
        http_client: Any = None,
        base_url: str = _ZAI_BASE_URL,
    ):
        if not api_key or not str(api_key).strip():
            raise RuntimeError("ZAI_API_KEY nao configurada.")
        try:
            import httpx
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "Dependencia ausente: instale 'openai>=1.0' e 'httpx'."
            ) from exc

        if http_client is None:
            from ayla_http import connection_limits
            http_client = httpx.Client(
                limits=connection_limits(),
                timeout=httpx.Timeout(
                    timeout,
                    connect=min(15.0, timeout),
                    read=timeout,
                    write=timeout,
                ),
                http2=False,
            )
        self._httpx_client = http_client
        self._sdk_client = OpenAI(
            api_key=str(api_key).strip(),
            base_url=base_url,
            timeout=timeout,
            max_retries=0,
            http_client=http_client,
        )
        self._closed = False

    def create_session(
        self,
        model: str = _ZAI_DEFAULT_MODEL,
        config: ZaiChatConfig | None = None,
        history: Iterable[ZaiMessage] | None = None,
    ) -> ZaiChatSession:
        return ZaiChatSession(self, model=model, config=config, history=history)

    @trace_model
    def complete(
        self,
        model: str,
        messages: Iterable[ZaiMessage],
        config: ZaiChatConfig | None = None,
    ) -> ZaiResponse:
        config = config or ZaiChatConfig()
        with stage('request_build'):
            request_messages = self._request_messages(self._prepare_messages(messages), config)
            kwargs = self._request_kwargs(model=model, messages=request_messages, config=config, stream=False)
        emit('provider_dispatch')
        result = self._sdk_client.chat.completions.create(**kwargs)
        first('first_provider_event')
        choices = _attr(result, "choices", []) or []
        message = _attr(choices[0], "message", None) if choices else None
        usage = _attr(result, "usage", None)
        response = _assistant_response(message, usage, model, result)
        if response.text:
            first('first_content')
        log_zai_usage(usage, response.model)
        _validate_finish_reason(response.finish_reason)
        return response

    def _stream(
        self,
        model: str,
        messages: Iterable[ZaiMessage],
        config: ZaiChatConfig | None = None,
    ):
        config = config or ZaiChatConfig()
        with stage('request_build'):
            request_messages = self._request_messages(self._prepare_messages(messages), config)
            kwargs = self._request_kwargs(model=model, messages=request_messages, config=config, stream=True)
        emit('provider_dispatch')
        return self._sdk_client.chat.completions.create(**kwargs)

    def transcribe_audio(self, attachment: ZaiAttachment) -> str:
        """Converte áudio para WAV e transcreve em blocos de até 30 segundos."""
        mime = str(attachment.mime_type).lower().split(";", 1)[0]
        if not mime.startswith("audio/"):
            raise ValueError("O anexo não é um áudio.")
        raw = attachment.data
        if isinstance(raw, str):
            encoded = raw.split(",", 1)[1] if raw.startswith("data:") else raw
            try:
                raw = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise ValueError("Áudio Base64 inválido.") from exc
        raw = bytes(raw)
        if not raw:
            raise ValueError("O áudio está vazio.")
        max_bytes = 25 * 1024 * 1024
        if len(raw) > max_bytes:
            raise ValueError("O áudio excede o limite de 25 MB da transcrição Z.ai.")
        if mime not in {"audio/wav", "audio/x-wav", "audio/wave"}:
            try:
                conversion = subprocess.run(
                    ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
                     "-i", "pipe:0", "-vn", "-ac", "1", "-ar", "16000",
                     "-c:a", "pcm_s16le", "-f", "wav", "pipe:1"],
                    input=raw, capture_output=True, timeout=120, check=False,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                raise RuntimeError("FFmpeg indisponível ou demorou demais para converter o áudio.") from exc
            if conversion.returncode != 0 or not conversion.stdout:
                raise ValueError("Não foi possível converter o áudio para WAV.")
            raw = conversion.stdout
        chunks = [raw]
        try:
            with wave.open(io.BytesIO(raw), "rb") as source:
                params = source.getparams()
                frames_per_chunk = min(30 * source.getframerate(),
                                       (max_bytes - 128) // (source.getnchannels() * source.getsampwidth()))
                if source.getnframes() > frames_per_chunk:
                    chunks = []
                    while frames := source.readframes(frames_per_chunk):
                        out = io.BytesIO()
                        with wave.open(out, "wb") as dest:
                            dest.setparams((params.nchannels, params.sampwidth,
                                            params.framerate, 0, "NONE", "not compressed"))
                            dest.writeframes(frames)
                        chunks.append(out.getvalue())
        except (wave.Error, EOFError, ZeroDivisionError) as exc:
            raise ValueError("Áudio WAV inválido ou sem codificação PCM suportada.") from exc
        texts = []
        for chunk in chunks:
            kwargs = {"model": "glm-asr-2512",
                      "file": ("speech.wav", chunk, "audio/wav")}
            if texts:
                kwargs["prompt"] = " ".join(texts)[-7999:]
            result = self._sdk_client.audio.transcriptions.create(**kwargs)
            text = _attr(result, "text", None)
            if not isinstance(text, str):
                raise RuntimeError("A Z.ai não retornou o texto da transcrição.")
            if text.strip():
                texts.append(text.strip())
        return " ".join(texts)

    def _prepare_messages(self, messages: Iterable[ZaiMessage]) -> list[ZaiMessage]:
        native = list(messages)
        _validate_attachment_mix(native)
        prepared = []
        for message in native:
            audio = [a for a in message.attachments if str(a.mime_type).startswith("audio/")]
            if not audio:
                prepared.append(message)
                continue
            notes = []
            attachments = []
            audio_index = 0
            for attachment in message.attachments:
                if not str(attachment.mime_type).startswith("audio/"):
                    attachments.append(attachment)
                    continue
                audio_index += 1
                try:
                    transcript = self.transcribe_audio(attachment)
                except Exception as exc:
                    notes.append(f"[Áudio {audio_index} não pôde ser analisado: transcrição indisponível. Informe ao usuário que precisa reenviar o áudio ou usar outro formato.]")
                    print(f"⚠️ [Z.ai] Áudio {audio_index} não processado ({exc}).")
                else:
                    notes.append(
                        f"[Transcrição do áudio {audio_index}]\n{transcript or '[Sem fala reconhecida]'}"
                    )
            text = "\n\n".join([message.text] + notes).lstrip("\n")
            prepared.append(replace(message, text=text, attachments=attachments))
        return prepared

    @staticmethod
    def _request_messages(
        messages: Iterable[ZaiMessage],
        config: ZaiChatConfig,
    ) -> list[dict[str, Any]]:
        native_messages = list(messages or [])
        _validate_attachment_mix(native_messages)
        request_messages: list[dict[str, Any]] = []
        if config.system_prompt:
            request_messages.append({"role": "system", "content": config.system_prompt})
        request_messages.extend(_message_to_api(message) for message in native_messages)
        if not request_messages or all(
            message.get("role") in {"system", "assistant"}
            for message in request_messages
        ):
            raise RuntimeError(
                "A requisicao precisa conter ao menos uma mensagem de usuario ou ferramenta."
            )
        return request_messages

    @staticmethod
    def _request_kwargs(
        model: str,
        messages: list[dict[str, Any]],
        config: ZaiChatConfig,
        stream: bool,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": str(model),
            "messages": messages,
            "stream": stream,
        }
        if config.request_timeout is not None:
            kwargs["timeout"] = float(config.request_timeout)
        if config.temperature is not None:
            kwargs["temperature"] = float(config.temperature)
        if config.top_p is not None:
            kwargs["top_p"] = float(config.top_p)
        if config.max_tokens is not None:
            kwargs["max_tokens"] = int(config.max_tokens)
        if config.response_format:
            kwargs["response_format"] = _json_safe(config.response_format)

        tools = [_json_safe(tool) for tool in config.tools]
        if tools:
            for tool in tools:
                if not isinstance(tool, dict) or tool.get("type") != "function":
                    raise ValueError("Ferramentas Z.ai devem usar o formato type=function.")
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        thinking_level = str(config.thinking_level or "low").strip().lower()
        if thinking_level not in {"none", "minimal", "low", "medium", "high", "xhigh", "max"}:
            raise ValueError(f"Nível de raciocínio inválido: {thinking_level!r}")
        match = re.match(r"glm-(\d+)(?:\.(\d+))?(?:-|$)", str(model).lower())
        version = (int(match[1]), int(match[2] or 0)) if match else (0, 0)
        extra_body: dict[str, Any] = {}
        if version >= (4, 5):
            thinking_type = "enabled"
            if str(model).lower() == "glm-4.7-flash":
                thinking_type = "disabled"
            elif version < (5, 2) and thinking_level in {"none", "minimal"}:
                thinking_type = "disabled"
            extra_body["thinking"] = {"type": thinking_type, "clear_thinking": config.clear_thinking}
        if version == (5, 3):
            # Esta família tem raciocínio obrigatório e apenas três níveis.
            extra_body["reasoning_effort"] = {"none": "low", "minimal": "low",
                                               "medium": "high", "xhigh": "max"}.get(thinking_level, thinking_level)
        elif version >= (5, 2):
            # O GLM-5.2 interpreta none/minimal como pular raciocínio.
            extra_body["reasoning_effort"] = thinking_level
        if config.temperature is not None and float(config.temperature) == 0.0:
            extra_body["do_sample"] = False
        if stream and tools and version >= (4, 6):
            extra_body["tool_stream"] = True
        kwargs["extra_body"] = extra_body
        return kwargs

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._sdk_client.close()
        except Exception:
            try:
                self._httpx_client.close()
            except Exception:
                pass
