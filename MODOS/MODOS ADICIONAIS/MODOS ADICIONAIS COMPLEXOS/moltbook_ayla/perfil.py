"""Identidade, avatar, cadastro e assinaturas."""
import json
import os

from ayla_paths import resolve_path
from .common import api_key, credentials_path, request, required, segment, tool


def registrar(nome, descricao):
    if api_key():
        return {'success': False, 'error': 'Já existe uma credencial configurada. Use consultar ou status.'}
    payload = {'name': segment(nome), 'description': required(descricao, 'descricao', 2000)}
    path = credentials_path()
    # Reserva o arquivo antes de criar a conta; evita perder a chave por falta de acesso
    # e impede dois cadastros simultâneos. Falhas incertas exigem revisão humana.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump({'cadastro_pendente': True, 'agent_name': nome}, stream)
        stream.flush()
        os.fsync(stream.fileno())
        data = request('POST', '/agents/register', payload=payload, auth=False)
        agent = data.get('agent', {})
        key = agent.get('api_key') if isinstance(agent, dict) else None
        if key:
            stream.seek(0)
            json.dump({'api_key': key, 'agent_name': nome, 'claim_url': agent.get('claim_url'),
                       'verification_code': agent.get('verification_code')}, stream, ensure_ascii=False)
            stream.truncate()
            stream.flush()
            os.fsync(stream.fileno())
            return {'success': True, 'claim_url': agent.get('claim_url'),
                    'verification_code': agent.get('verification_code'),
                    'mensagem': 'Chave salva localmente. O responsável precisa concluir o vínculo no claim_url.'}
        return data


@tool
def executar(acao, nome='', descricao=None, arquivo='', comunidade=''):
    if acao == 'registrar':
        return registrar(nome, descricao)
    if acao == 'consultar':
        if nome:
            return request('GET', '/agents/profile', params={'name': segment(nome)})
        return request('GET', '/agents/me')
    if acao == 'status':
        return request('GET', '/agents/status')
    if acao == 'vinculo':
        path = credentials_path()
        data = json.loads(path.read_text(encoding='utf-8'))
        return {k: data.get(k) for k in ('agent_name', 'claim_url', 'verification_code', 'cadastro_pendente')}
    if acao == 'editar':
        if not isinstance(descricao, str) or len(descricao) > 2000:
            raise ValueError('Informe descricao com até 2000 caracteres.')
        return request('PATCH', '/agents/me', payload={'description': descricao})
    if acao == 'foto':
        path = resolve_path(required(arquivo, 'arquivo', 4096))
        # Valida os bytes, não apenas a extensão, antes de enviar um arquivo local.
        from PIL import Image
        with path.open('rb') as stream:
            if not 0 < os.fstat(stream.fileno()).st_size <= 500 * 1024:
                raise ValueError('A foto deve ter até 500 KB.')
            with Image.open(stream) as image:
                fmt = image.format
                image.verify()
            mime = {'JPEG': 'image/jpeg', 'PNG': 'image/png', 'GIF': 'image/gif', 'WEBP': 'image/webp'}.get(fmt)
            if not mime:
                raise ValueError('Use JPEG, PNG, GIF ou WebP.')
            stream.seek(0)
            return request('POST', '/agents/me/avatar', files={'file': (path.name, stream, mime)})
    if acao == 'remover_foto':
        return request('DELETE', '/agents/me/avatar')
    if acao in {'seguir', 'deixar_seguir'}:
        return request('POST' if acao == 'seguir' else 'DELETE', '/agents/' + segment(nome) + '/follow')
    if acao in {'inscrever', 'desinscrever'}:
        return request('POST' if acao == 'inscrever' else 'DELETE', '/submolts/' + segment(comunidade) + '/subscribe')
    raise ValueError('Ação inválida.')
