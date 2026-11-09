"""Modelos Gemini de conversa; fontes oficiais conferidas em 2026-10-04."""
import os

CATALOG_DATE = '2026-10-04'
CATALOG_SOURCE = 'https://ai.google.dev/gemini-api/docs/models'
FREE_TIER_SOURCE = 'https://ai.google.dev/gemini-api/docs/pricing'
# Somente generateContent com texto e ferramentas; mídia/Live têm seletores próprios.
GEMINI_MODELS = (
    'gemini-3.8-flash', 'gemini-3.7-flash', 'gemini-3.6-flash',
    'gemini-3.5-flash', 'gemini-3.5-flash-lite', 'gemini-3.1-flash-lite',
    'gemini-3-flash-preview', 'gemini-2.5-flash', 'gemini-2.5-flash-lite',
    'gemini-2.5-pro', 'gemini-3.1-pro-preview',
    'gemini-3.1-pro-preview-customtools', 'gemini-robotics-er-2-preview',
    'gemini-flash-latest', 'gemini-flash-lite-latest', 'gemini-pro-latest',
)
PAID_ONLY = {'gemini-3.1-pro-preview', 'gemini-3.1-pro-preview-customtools'}
RETIRED = {'gemini-2.0-flash', 'gemini-2.0-flash-lite', 'gemini-3-pro-preview',
           'gemini-3.1-flash-lite-preview', 'gemini-2.5-computer-use-preview-10-2025'}


def is_gemini(model):
    return str(model).removeprefix('models/').startswith('gemini-')


def chat_model(model):
    name = str(model.get('name', '')).removeprefix('models/')
    return (is_gemini(name) and name not in RETIRED
            and 'generateContent' in model.get('supportedGenerationMethods', [])
            and not any(s in name for s in ('image', 'tts', 'audio', 'live',
                                           'transcribe', 'embedding', 'omni', 'computer-use')))


def gemini_key(settings=None):
    return str((settings or {}).get('gemini_api_key') or os.getenv('GEMINI_API_KEY')
               or os.getenv('GOOGLE_API_KEY') or '').strip()


def access_label(model):
    name = str(model).removeprefix('models/')
    if name in PAID_ONLY:
        return 'Google AI Studio · sem cota gratuita na API'
    if name.endswith('-latest') or name not in GEMINI_MODELS:
        return 'Google AI Studio · disponibilidade e cota dependem da conta/modelo'
    suffix = ' · acesso legado sujeito à conta' if name.startswith('gemini-2.5-') else ''
    return 'Google AI Studio · possui camada gratuita, sujeita à cota da conta' + suffix
