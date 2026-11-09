"""Catálogo da API oficial DeepSeek, consultado em 2026-10-26."""
import os
from datetime import datetime, timezone

CATALOG_DATE = '2026-10-26'
CATALOG_SOURCE = 'https://api-docs.deepseek.com/api/list-models/'
BASE_URL = 'https://api.deepseek.com'
CHAT_MODELS = ('deepseek-flash', 'deepseek-v4-pro')
DEEPSEEK_MODELS = tuple('deepseek:' + name for name in CHAT_MODELS)
VISION_MODELS = frozenset({'deepseek-flash'})
CONTEXT_WINDOW = 1048576
MAX_OUTPUT_TOKENS = 393216
PRICING_DATE = '2026-10-27'
PRICING_SOURCE = 'https://api-docs.deepseek.com/quick_start/pricing/'
# Entrada sem cache, entrada em cache, saída; USD / 1 milhão de tokens.
PEAK_PRICES = {
    'deepseek-flash': (0.30, 0.006, 1.20),
    'deepseek-v4-pro': (1.32, 0.044, 3.96),
}


def is_peak_time(at=None):
    """Faixa de pico publicada, em UTC; descontos de feriados não cadastrados."""
    at = datetime.now(timezone.utc) if at is None else at
    if at.tzinfo is None:
        raise ValueError('O horário de cobrança precisa incluir o fuso.')
    utc = at.astimezone(timezone.utc)
    return utc.weekday() < 5 and (1 <= utc.hour < 4 or 6 <= utc.hour < 10)


def billing_rates(model, at=None):
    rates = PEAK_PRICES.get(model_id(model))
    if rates is None:
        return None
    # Estimativa conservadora: descontos de feriados chineses não cadastrados.
    divisor = 1 if is_peak_time(at) else 2
    return dict(zip(('input', 'cached_input', 'output'), (v / divisor for v in rates)))


def model_id(model):
    return str(model).removeprefix('deepseek:')


def is_deepseek(model):
    return str(model).startswith('deepseek:') or str(model) in CHAT_MODELS


def deepseek_key(settings=None):
    return str((settings or {}).get('deepseek_api_key')
               or os.getenv('DEEPSEEK_API_KEY') or '').strip()


def chat_model(model):
    return bool(model.get('active', True) and model_id(model.get('id', '')) in CHAT_MODELS)


def access_label(model):
    modalities = 'texto e imagens' if model_id(model) in VISION_MODELS else 'texto'
    label = (f'DeepSeek · API oficial · {modalities} · contexto de {CONTEXT_WINDOW:,} tokens · '
            f'saída até {MAX_OUTPUT_TOKENS:,} tokens · cobrança por uso; requer saldo na conta')
    rates = PEAK_PRICES.get(model_id(model))
    if rates:
        label += (f' · pico: entrada US$ {rates[0]:g}, cache US$ {rates[1]:g}, '
                  f'saída US$ {rates[2]:g} / 1M tokens · fora do pico: metade '
                  f'· preços consultados em {PRICING_DATE}')
    return label
