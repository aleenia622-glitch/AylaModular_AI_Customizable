"""Cliente restrito à API oficial; respostas pequenas e credenciais locais."""
import json
import os
import re
from functools import wraps
from pathlib import Path

import requests
from ayla_paths import BASE_DIR

API = 'https://www.moltbook.com/api/v1'


def credentials_path():
    return Path(os.environ.get('MOLTBOOK_CREDENTIALS_FILE', str(BASE_DIR / 'moltbook_credentials.json'))).expanduser()


def api_key():
    key = os.environ.get('MOLTBOOK_API_KEY', '').strip()
    if key:
        return key
    for path in (credentials_path(), Path.home() / '.config/moltbook/credentials.json'):
        if path.is_file():
            data = json.loads(path.read_text(encoding='utf-8'))
            key = str(data.get('api_key', '')).strip()
            if key:
                return key
    return ''


def segment(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise ValueError('Informe um ID ou nome válido, sem URL ou barras.')
    return value


def required(value, name, maximum=40000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f'{name}: texto obrigatório, máximo {maximum} caracteres.')
    return value


def choice(value, options):
    if value not in options:
        raise ValueError('Valor inválido. Opções: ' + ', '.join(options))
    return value


def limit(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 20:
        raise ValueError('limite deve ser um inteiro entre 1 e 20.')
    return value


def compact(data, text_limit=700, item_limit=20):
    """Limita conteúdo, preservando IDs, cursores e desafios de verificação."""
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if key.lower() in {'api_key', 'authorization', 'access_token', 'token'}:
                continue
            if key in {'content', 'description', 'body', 'content_preview'} and isinstance(value, str):
                result[key] = value[:text_limit]
                if len(value) > text_limit:
                    result[key + '_truncado'] = True
                    result[key + '_total_caracteres'] = len(value)
            elif isinstance(value, list):
                result[key] = [compact(v, text_limit, item_limit) for v in value[:item_limit]]
                if len(value) > item_limit:
                    result[key + '_omitidos'] = len(value) - item_limit
            else:
                result[key] = compact(value, text_limit, item_limit)
        return result
    if isinstance(data, list):
        return [compact(v, text_limit, item_limit) for v in data[:item_limit]]
    return data


def request(method, path, *, params=None, payload=None, files=None, auth=True):
    if not path.startswith('/') or '..' in path or '?' in path or '#' in path:
        raise ValueError('Rota inválida.')
    key = api_key() if auth else ''
    if auth and not key:
        return {'success': False, 'error': 'Configure MOLTBOOK_API_KEY no .env e reinicie a Ayla, ou use moltbook_perfil com acao=registrar.'}
    headers = {'Accept': 'application/json', 'User-Agent': 'Ayla-Moltbook/1.0'}
    if key:
        headers['Authorization'] = 'Bearer ' + key
    try:
        response = requests.request(method, API + path, headers=headers, params=params,
                                    json=payload, files=files, timeout=(10, 40), allow_redirects=False)
    except requests.RequestException:
        return {'success': False, 'error': 'Falha de rede ou timeout. Resultado incerto: consulte antes de repetir uma publicação.'}
    if 300 <= response.status_code < 400:
        return {'success': False, 'error': 'Redirecionamento bloqueado para proteger a credencial.', 'http_status': response.status_code}
    try:
        data = response.json()
    except ValueError:
        return {'success': False, 'http_status': response.status_code, 'error': 'A API retornou uma resposta não JSON.'}
    if not isinstance(data, dict):
        data = {'data': data}
    data['http_status'] = response.status_code
    data.setdefault('success', response.ok)
    if not response.ok:
        data['success'] = False
    if response.headers.get('Retry-After'):
        data['retry_after'] = response.headers['Retry-After']
    rate_headers = {name: response.headers.get(header) for name, header in (
        ('limite', 'X-RateLimit-Limit'), ('restantes', 'X-RateLimit-Remaining'),
        ('reinicia_em', 'X-RateLimit-Reset')) if response.headers.get(header) is not None}
    if rate_headers:
        data['limites_api'] = rate_headers
    if response.ok and method == 'POST' and path != '/verify':
        def pending(node):
            if not isinstance(node, dict):
                return False
            return (node.get('verification_required') is True or
                    node.get('verification_status') == 'pending' or
                    bool(node.get('verification')) or
                    any(pending(node.get(k)) for k in ('post', 'comment', 'submolt', 'data')))
        if pending(data):
            data['pendente_verificacao'] = True
            data['orientacao_verificacao'] = 'Conteúdo ainda não confirmado como público. Resolva o desafio e use verificar antes do expires_at; não recrie o conteúdo para verificar.'
    return data


def tool(fn):
    @wraps(fn)
    def wrapped(**kwargs):
        try:
            data = compact(fn(**kwargs))
            result = json.dumps(data, ensure_ascii=False)
            key = api_key()
            return result.replace(key, '[credencial omitida]') if key else result
        except (ValueError, TypeError, OSError):
            return json.dumps({'success': False, 'error': 'Parâmetros, arquivo ou configuração inválidos. Confira os campos e caminhos informados.'}, ensure_ascii=False)
    return wrapped


def verify(code, answer):
    required(code, 'codigo', 500)
    if not isinstance(answer, str) or not re.fullmatch(r'-?\d+\.\d{2}', answer):
        raise ValueError('resposta deve ter duas casas decimais, por exemplo 15.00.')
    return request('POST', '/verify', payload={'verification_code': code, 'answer': answer})
