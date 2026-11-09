"""Contexto do Discord com autoria preservada nos papéis da API."""
import json
from ayla_emoji_context import normalizar_emojis_contexto

from zai_provider import ZaiMessage


INSTRUCOES_AUTORIA = ""


def mensagem_historica(message, bot_id, *, resposta_a=False):
    propria = message.author.id == bot_id
    role = 'assistant' if propria else 'user'
    texto = (message.content or '').strip()
    # Metadados de cobrança não fazem parte da fala da Ayla.
    if propria:
        texto = '\n'.join(line for line in texto.splitlines()
                          if not line.startswith('-# ')).strip()
    registro = {
        'origem': 'historico_discord',
        'mensagem_id': str(message.id),
        'autor_id': str(message.author.id),
        'autor_nome': message.author.display_name,
        'papel': 'Ayla (você)' if propria else 'participante',
        'texto': normalizar_emojis_contexto(texto),
        'figurinhas': [getattr(s, 'name', 'Figurinha') for s in getattr(message, 'stickers', [])],
        'anexos': [getattr(a, 'filename', 'Anexo') for a in getattr(message, 'attachments', [])],
        'resposta_a': resposta_a,
    }
    return ZaiMessage(role=role, text=json.dumps(registro, ensure_ascii=False))


async def obter_historico_canal(message, bot_id, limite=5):
    if limite <= 0 or not message.channel or not hasattr(message.channel, 'history'):
        return []
    recentes = []
    try:
        # Impede incluir a resposta em streaming ou mensagens posteriores ao pedido.
        async for item in message.channel.history(limit=limite, before=message, oldest_first=False):
            if item.id >= message.id:
                continue
            recentes.append(item)
    except Exception as exc:
        print(f'⚠️ Erro ao obter histórico do canal: {exc}')
    return [mensagem_historica(item, bot_id) for item in sorted(recentes, key=lambda m: m.id)]
