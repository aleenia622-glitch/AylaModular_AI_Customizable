"""Métricas sem conteúdo, credenciais, cabeçalhos ou mensagens de exceção.

Logger ayla.performance em INFO; cada linha é JSON correlacionado. Nenhuma
chamada de rede é criada pela instrumentação. Ausência de usage não vira zero.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import json
import logging
from functools import wraps
import inspect
import os
from time import perf_counter

_logger = logging.getLogger('ayla.performance')
if os.getenv('AYLA_PERF_LOG') == '1':
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(message)s'))
    _logger.addHandler(handler)
    _logger.setLevel(logging.INFO)
    _logger.propagate = False
_trace = ContextVar('ayla_performance_trace', default=None)
_request = ContextVar('ayla_performance_request', default=None)


@dataclass
class Trace:
    interaction: str
    started: float = field(default_factory=perf_counter)
    calls: int = 0
    last_model: str = ''


def emit(event, **numbers):
    trace = _trace.get()
    if trace is None:
        return
    record = dict(interaction=trace.interaction, event=event,
                  elapsed_ms=round((perf_counter() - trace.started) * 1000, 3))
    request = _request.get()
    if request:
        record.update(round=request['round'], model=request['model'])
    elif trace.calls:
        record.update(round=trace.calls, model=trace.last_model)
    # Os chamadores passam somente métricas numéricas, nunca payloads.
    record.update({k: v for k, v in numbers.items() if isinstance(v, (int, float, bool))})
    try:
        _logger.info(json.dumps(record, ensure_ascii=False))
    except Exception:
        pass  # Observabilidade nunca interrompe a resposta.


def begin(interaction, started=None):
    token = _trace.set(Trace(interaction, started=perf_counter() if started is None else started))
    emit('interaction_start')
    return token


def end(token):
    trace = _trace.get()
    try:
        emit('interaction_end', model_calls=trace.calls)
    finally:
        _trace.reset(token)


@contextmanager
def stage(name, **numbers):
    started = perf_counter()
    ok = False
    try:
        yield
        ok = True
    finally:
        emit(name, duration_ms=(perf_counter() - started) * 1000, success=ok, **numbers)


def measured(name, function, *args, **kwargs):
    with stage(name):
        return function(*args, **kwargs)


@contextmanager
def request(model):
    trace = _trace.get()
    if trace is None:
        yield
        return
    trace.calls += 1
    trace.last_model = model
    token = _request.set(dict(round=trace.calls, model=model, first=set()))
    try:
        with stage('generation_total'):
            emit('request_start')
            yield
    finally:
        _request.reset(token)


def first(event):
    current = _request.get()
    if current is not None and event not in current['first']:
        current['first'].add(event)
        emit(event)


def trace_model(function):
    def scope(obj, args, kwargs):
        model = getattr(obj, 'model', None) or kwargs.get('model') or (args[0] if args else '')
        return request(model)
    if inspect.isgeneratorfunction(function):
        @wraps(function)
        def stream(obj, *args, **kwargs):
            with scope(obj, args, kwargs):
                yield from function(obj, *args, **kwargs)
        return stream
    @wraps(function)
    def complete(obj, *args, **kwargs):
        with scope(obj, args, kwargs):
            return function(obj, *args, **kwargs)
    return complete
