"""Representação textual dos emojis no contexto, antes da renderização Discord."""
import copy
import json
import re
import unicodedata
from pathlib import Path

CATALOG = Path(__file__).with_name('ayla_media.json')
EMOJI = re.compile(r'<a?:([A-Za-z0-9_]+):(\d+)>')


def normalizar_emojis_contexto(texto):
    if not texto or not EMOJI.search(texto):
        return texto
    try:
        catalog = json.loads(CATALOG.read_text(encoding='utf-8')).get('emojis', {})
    except (OSError, ValueError):
        catalog = {}
    def norm(name):
        name = unicodedata.normalize('NFD', name).encode('ascii', 'ignore').decode().lower()
        return re.sub(r'[^a-z0-9]', '', name)
    names, ids = {}, {}
    for label, value in catalog.items():
        names[norm(label)] = label
        match = EMOJI.fullmatch(value)
        if match:
            names[norm(match[1])] = label
            ids[match[2]] = label
    def replace(match):
        # O nome recupera inclusive IDs inventados que já entraram no histórico.
        label = names.get(norm(match[1])) or ids.get(match[2])
        return '%' + label + '%' if label else '[emoji externo: ' + match[1].replace('_', ' ') + ']'
    return EMOJI.sub(replace, texto)


def normalizar_mensagens_contexto(messages):
    result = []
    for original in messages:
        message = copy.deepcopy(original)
        if message.role in ('user', 'assistant', 'system'):
            message.text = normalizar_emojis_contexto(message.text)
            native = getattr(message, 'provider_content', None)
            if isinstance(native, dict):
                for part in native.get('parts', []):
                    if isinstance(part.get('text'), str) and not part.get('thought'):
                        part['text'] = normalizar_emojis_contexto(part['text'])
        result.append(message)
    return result
