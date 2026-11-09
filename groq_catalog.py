"""Catálogo de geração de texto Groq; referência oficial em 2026-10-22."""
import os

CATALOG_DATE = '2026-10-22'
CATALOG_SOURCE = 'https://console.groq.com/docs/models'
LIMITS_SOURCE = 'https://console.groq.com/docs/rate-limits'
# Prefixo explícito evita colisão com outros provedores OpenAI-compatíveis.
TEXT_MODELS = (
    'openai/gpt-oss-120b', 'openai/gpt-oss-20b', 'qwen/qwen3.8-27b',
    'openai/gpt-oss-safeguard-20b', 'llama-3.1-8b-instant',
    'llama-3.3-70b-versatile', 'meta-models/muse-spark-open',
    'minimaxai/minimax-m2.7',
)
GROQ_MODELS = tuple('groq:' + name for name in TEXT_MODELS)
# RPM, RPD, TPM, TPD. Referência, não garantia de cota da organização.
FREE_LIMITS = {
    'openai/gpt-oss-120b': (30, 1000, 8000, 200000),
    'openai/gpt-oss-20b': (30, 1000, 8000, 200000),
    'qwen/qwen3.8-27b': (30, 1000, 8000, 200000),
    'openai/gpt-oss-safeguard-20b': (3, 1000, 2000, 200000),
}
ENTERPRISE_MODELS = frozenset(TEXT_MODELS[4:])


def model_id(model):
    return str(model).removeprefix('groq:')


def is_groq(model):
    return str(model).startswith('groq:') or str(model) in TEXT_MODELS


def groq_key(settings=None):
    return str((settings or {}).get('groq_api_key') or os.getenv('GROQ_API_KEY') or '').strip()


def chat_model(model):
    name = str(model.get('id', ''))
    return bool(name and model.get('active', True) and not any(
        part in name.lower() for part in ('whisper', 'orpheus', 'tts', 'embedding',
                                         'prompt-guard', 'transcribe')))


def access_label(model):
    name = model_id(model)
    limits = FREE_LIMITS.get(name)
    if limits:
        rpm, rpd, tpm, tpd = limits
        label = f'Groq · referência Free: {rpm} req/min · {rpd} req/dia · {tpm} TPM combinado · {tpd} tokens/dia · ITPM/OTPM podem ser menores na conta'
    elif name in ENTERPRISE_MODELS:
        label = 'Groq · Enterprise: acesso sujeito a contrato; sem cota gratuita publicada'
    else:
        label = 'Groq · acesso e limites dependem da organização; consulte o console'
    if 'safeguard' in name:
        label += ' · modelo especializado em moderação, sem ferramentas locais'
    return label


def output_limit(settings=None):
    try:
        return max(128, min(65536, int((settings or {}).get('groq_max_tokens', 2048))))
    except (TypeError, ValueError, OverflowError):
        return 2048
