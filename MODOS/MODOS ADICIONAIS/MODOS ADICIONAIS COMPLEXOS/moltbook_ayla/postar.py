"""Posts, comunidades e moderação da API oficial Moltbook 1.12.0."""
import re
from urllib.parse import urlsplit
from .common import choice, limit, request, required, segment, tool, verify

ACOES = [
    'publicar', 'excluir', 'ler', 'feed', 'buscar', 'painel',
    'comunidades', 'comunidade', 'feed_comunidade', 'criar_comunidade',
    'editar_comunidade', 'inscrever', 'desinscrever', 'fixar', 'desafixar',
    'moderadores', 'adicionar_moderador', 'remover_moderador',
    'etiquetas', 'cargos', 'criar_etiqueta', 'anexar_etiqueta',
    'atribuir_cargo', 'remover_anexo', 'verificar',
]
CORES = ['emerald', 'rose', 'amber', 'sky', 'violet', 'slate', 'indigo', 'teal', 'pink', 'orange']


def pagina_local(data, inicio, limite):
    """Listagens sem paginação documentada: não perder itens no compactador."""
    if isinstance(inicio, bool) or not isinstance(inicio, int) or inicio < 0:
        raise ValueError('inicio deve ser inteiro não negativo.')
    limit(limite)
    def slice_lists(node):
        if not isinstance(node, dict):
            return
        for key, value in list(node.items()):
            if isinstance(value, list):
                node[key] = value[inicio:inicio + limite]
                node[key + '_total'] = len(value)
                node[key + '_proximo_inicio'] = inicio + limite if inicio + limite < len(value) else None
            elif key == 'data':
                slice_lists(value)
    slice_lists(data)
    return data


@tool
def executar(acao, titulo='', conteudo='', comunidade='', url='', post_id='',
             codigo='', resposta='', tipo='', ordem='new', limite=5, cursor='',
             inicio=0, busca='', feed='global', nome_exibicao='', descricao=None,
             permitir_crypto=False, cor_banner=None, cor_tema=None, agente='',
             solicitante_id='', chave='', rotulo='', cor='slate', categoria='tag',
             instrucao=None, cadencia_minutos=None, etiqueta_id='', agente_id='', anexo_id=''):
    choice(acao, ACOES)
    if acao == 'publicar':
        payload = {'title': required(titulo, 'titulo', 300), 'submolt_name': segment(comunidade or 'general')}
        post_type = choice(tipo or ('link' if url else 'text'), ['text', 'link', 'image'])
        payload['type'] = post_type
        if not isinstance(conteudo, str):
            raise ValueError('conteudo deve ser texto.')
        if conteudo:
            payload['content'] = required(conteudo, 'conteudo')
        if url:
            required(url, 'url')
            parsed = urlsplit(url)
            if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError('URL HTTP(S) inválida ou com credenciais.')
            payload['url'] = url
        if post_type in {'link', 'image'} and not url:
            raise ValueError('Posts link/image exigem url pública.')
        return request('POST', '/posts', payload=payload)
    if acao == 'excluir':
        return request('DELETE', '/posts/' + segment(post_id))
    if acao in {'fixar', 'desafixar'}:
        return request('POST' if acao == 'fixar' else 'DELETE', '/posts/' + segment(post_id) + '/pin')
    if acao in {'ler', 'feed', 'buscar', 'painel'}:
        from .responder import executar as responder
        return responder.__wrapped__(acao=acao, post_id=post_id, inicio=inicio, ordem=ordem,
                                     limite=limite, cursor=cursor, busca=busca, feed=feed,
                                     comunidade=comunidade,
                                     tipo=tipo or 'posts')
    comunidade = comunidade or 'general'
    if acao == 'comunidades':
        # Valide antes da chamada de rede.
        pagina_local({}, inicio, limite)
        return pagina_local(request('GET', '/submolts'), inicio, limite)
    if acao == 'comunidade':
        params = {'requester_id': segment(solicitante_id)} if solicitante_id else None
        return request('GET', '/submolts/' + segment(comunidade), params=params)
    if acao == 'feed_comunidade':
        params = {'sort': choice(ordem, ['hot', 'new', 'top', 'rising']), 'limit': limit(limite)}
        if cursor:
            params['cursor'] = required(cursor, 'cursor')
        return request('GET', '/submolts/' + segment(comunidade) + '/feed', params=params)
    if acao == 'criar_comunidade':
        if not isinstance(comunidade, str) or not re.fullmatch(r'[a-z0-9-]{2,30}', comunidade):
            raise ValueError('comunidade: 2–30 caracteres minúsculos, números ou hífens.')
        if not isinstance(permitir_crypto, bool):
            raise ValueError('permitir_crypto deve ser booleano.')
        payload = {'name': comunidade, 'display_name': required(nome_exibicao, 'nome_exibicao'),
                   'allow_crypto': permitir_crypto}
        if descricao is not None:
            if not isinstance(descricao, str):
                raise ValueError('descricao deve ser texto.')
            payload['description'] = descricao
        return request('POST', '/submolts', payload=payload)
    if acao == 'editar_comunidade':
        payload = {}
        if descricao is not None:
            if not isinstance(descricao, str):
                raise ValueError('descricao deve ser texto.')
            payload['description'] = descricao
        for name, value in [('banner_color', cor_banner), ('theme_color', cor_tema)]:
            if value is not None:
                if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
                    raise ValueError('Cores devem usar #RRGGBB.')
                payload[name] = value
        if not payload:
            raise ValueError('Informe descricao, cor_banner ou cor_tema.')
        return request('PATCH', '/submolts/' + segment(comunidade) + '/settings', payload=payload)
    if acao in {'inscrever', 'desinscrever'}:
        return request('POST' if acao == 'inscrever' else 'DELETE', '/submolts/' + segment(comunidade) + '/subscribe')
    if acao in {'moderadores', 'etiquetas', 'cargos'}:
        endpoint = {'moderadores': 'moderators', 'etiquetas': 'labels', 'cargos': 'roles'}[acao]
        pagina_local({}, inicio, limite)
        return pagina_local(request('GET', '/submolts/' + segment(comunidade) + '/' + endpoint), inicio, limite)
    if acao in {'adicionar_moderador', 'remover_moderador'}:
        payload = {'agent_name': segment(agente)}
        if acao == 'adicionar_moderador':
            payload['role'] = 'moderator'
        return request('POST' if acao == 'adicionar_moderador' else 'DELETE',
                       '/submolts/' + segment(comunidade) + '/moderators', payload=payload)
    if acao == 'criar_etiqueta':
        payload = {'key': segment(chave), 'label': required(rotulo, 'rotulo'),
                   'color': choice(cor, CORES), 'kind': choice(categoria, ['tag', 'status', 'role'])}
        if instrucao is not None or cadencia_minutos is not None:
            if categoria != 'role':
                raise ValueError('instrucao/cadencia_minutos só se aplicam a role.')
            if instrucao is not None:
                payload['prompt'] = required(instrucao, 'instrucao')
            if cadencia_minutos is not None:
                if isinstance(cadencia_minutos, bool) or not isinstance(cadencia_minutos, int) or cadencia_minutos < 0:
                    raise ValueError('cadencia_minutos deve ser inteiro não negativo.')
                payload['cadence_minutes'] = cadencia_minutos
        return request('POST', '/submolts/' + segment(comunidade) + '/labels', payload=payload)
    if acao in {'anexar_etiqueta', 'atribuir_cargo'}:
        cargo = acao == 'atribuir_cargo'
        payload = {'label_definition_id': segment(etiqueta_id), 'target_type': 'agent' if cargo else 'post',
                   'target_id': segment(agente_id if cargo else post_id)}
        if cargo:
            payload['placement'] = 'metadata'
        return request('POST', '/labels/attach', payload=payload)
    if acao == 'remover_anexo':
        return request('DELETE', '/labels/attach/' + segment(anexo_id))
    if acao == 'verificar':
        return verify(codigo, resposta)
