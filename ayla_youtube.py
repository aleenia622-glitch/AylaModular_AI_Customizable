"""Pesquisa, abertura, legendas e biblioteca local do YouTube."""
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import json
import re
import threading
import uuid
import webbrowser

BIBLIOTECA = Path(__file__).resolve().parent / 'ayla_youtube_biblioteca.json'
_LOCK = threading.RLock()


def extrair_video_id(value):
    value = str(value).strip()
    if re.fullmatch(r'[A-Za-z0-9_-]{11}',value): return value
    url = urlparse(value)
    host = (url.hostname or '').lower()
    if host in {'youtu.be','www.youtu.be'}:
        candidate = url.path.strip('/').split('/')[0]
    elif host in {'youtube.com','www.youtube.com','m.youtube.com','music.youtube.com'}:
        parts = url.path.strip('/').split('/')
        candidate = parse_qs(url.query).get('v',[''])[0]
        if parts[0] in {'shorts','embed','live'} and len(parts)>1: candidate = parts[1]
    else:
        return ''
    return candidate if re.fullmatch(r'[A-Za-z0-9_-]{11}',candidate) else ''


def pesquisar_youtube(query, limite=5):
    from yt_dlp import YoutubeDL
    limit = max(1,min(int(limite),15))
    video_id = extrair_video_id(query)
    target = f'https://www.youtube.com/watch?v={video_id}' if video_id else f'ytsearch{limit}:{query}'
    with YoutubeDL({'quiet':True,'no_warnings':True,'skip_download':True,'extract_flat':'in_playlist','socket_timeout':20,'retries':1}) as client:
        data = client.extract_info(target,download=False)
    entries = list((data or {}).get('entries') or [data])
    result = []
    for item in entries[:limit]:
        if not item: continue
        identifier = item.get('id','')
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}',identifier): continue
        duration = item.get('duration')
        result.append({'id':identifier,'title':item.get('title') or identifier,
                       'url':f'https://www.youtube.com/watch?v={identifier}',
                       'channel':item.get('channel') or item.get('uploader') or 'YouTube',
                       'duration':f'{int(duration)//60}:{int(duration)%60:02d}' if duration else '',
                       'views':item.get('view_count') or ''})
    return result


def lancar_video(nome_ou_link, abrir_no_pc=True):
    try:
        videos = pesquisar_youtube(nome_ou_link,1)
        if not videos: return {'sucesso':False,'erro':'Nenhum vídeo encontrado.'}
        video=videos[0]
        if abrir_no_pc and not webbrowser.open(video['url']):
            return {'sucesso':False,'erro':'Não consegui abrir o navegador. Link: '+video['url']}
        return {'sucesso':True,'video':video,'url':video['url']}
    except Exception as exc: return {'sucesso':False,'erro':str(exc)}


def obter_transcricao(video_id_ou_url):
    identifier=extrair_video_id(video_id_ou_url)
    if not identifier: return {'sucesso':False,'video_id':'','erro':'ID ou URL de vídeo inválido.'}
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        api=YouTubeTranscriptApi()
        if hasattr(api,'fetch'):
            transcript=api.fetch(identifier,languages=['pt','pt-BR','en'])
            lines=[part.text for part in transcript]
        else:
            lines=[part['text'] for part in api.get_transcript(identifier,languages=['pt','pt-BR','en'])]
        return {'sucesso':True,'video_id':identifier,'texto':'\n'.join(lines),'total_linhas':len(lines)}
    except Exception as exc: return {'sucesso':False,'video_id':identifier,'erro':str(exc)}


def carregar_biblioteca():
    with _LOCK:
        if not BIBLIOTECA.exists(): return []
        data=json.loads(BIBLIOTECA.read_text(encoding='utf-8'))
        if not isinstance(data,list): raise ValueError('Biblioteca inválida; gravação cancelada.')
        return data


def _salvar(data):
    temp=BIBLIOTECA.with_name(BIBLIOTECA.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        temp.replace(BIBLIOTECA)
    finally: temp.unlink(missing_ok=True)


def salvar_video_na_biblioteca(video,nota=''):
    try:
        with _LOCK:
            identifier=extrair_video_id(video.get('id') or video.get('url',''))
            if not identifier: raise ValueError('Vídeo inválido.')
            data=[v for v in carregar_biblioteca() if v.get('id')!=identifier]
            data.append({**video,'id':identifier,'note':str(nota)})
            _salvar(data)
        return {'sucesso':True}
    except Exception as exc: return {'sucesso':False,'erro':str(exc)}


def remover_video_da_biblioteca(video_id_ou_url):
    identifier=extrair_video_id(video_id_ou_url)
    with _LOCK:
        data=carregar_biblioteca()
        kept=[v for v in data if v.get('id')!=identifier]
        if len(kept)==len(data): return {'sucesso':False,'erro':'Vídeo não encontrado.'}
        _salvar(kept)
        return {'sucesso':True}
