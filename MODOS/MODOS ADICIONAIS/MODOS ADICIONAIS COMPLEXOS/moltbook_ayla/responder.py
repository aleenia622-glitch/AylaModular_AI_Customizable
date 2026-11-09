"""Descoberta de discussões e interação, sem loops autônomos."""
from .common import choice, limit, request, required, segment, tool, verify


@tool
def executar(acao, post_id='', comentario_id='', conteudo='', busca='', comunidade='',
             ordem='new', limite=5, cursor='', feed='global', tipo='posts',
             voto='upvote', codigo='', resposta='', inicio=0):
    if acao == 'feed':
        choice(feed, ['global', 'pessoal', 'seguindo'])
        params = {'sort': choice(ordem, ['hot', 'new', 'top', 'rising'] if feed == 'global' else ['hot', 'new', 'top']), 'limit': limit(limite)}
        if cursor:
            params['cursor'] = cursor
        if comunidade:
            if feed != 'global':
                raise ValueError('comunidade exige feed global.')
            params['submolt'] = segment(comunidade)
        if feed == 'seguindo':
            params['filter'] = 'following'
        return request('GET', '/posts' if feed == 'global' else '/feed', params=params)
    if acao == 'buscar':
        return request('GET', '/search', params={'q': required(busca, 'busca', 500),
                       'type': choice(tipo, ['posts', 'comments', 'all']), 'limit': limit(limite), 'cursor': cursor})
    if acao == 'ler':
        if isinstance(inicio, bool) or not isinstance(inicio, int) or inicio < 0:
            raise ValueError('inicio deve ser um inteiro não negativo.')
        data = request('GET', '/posts/' + segment(post_id))
        post = data.get('post', data.get('data', {}))
        if isinstance(post, dict) and isinstance(post.get('content'), str):
            content = post['content']
            post['content'] = content[inicio:inicio + 700]
            post['total_caracteres'] = len(content)
            post['proximo_inicio'] = inicio + 700 if inicio + 700 < len(content) else None
        return data
    if acao == 'comentarios':
        return request('GET', '/posts/' + segment(post_id) + '/comments',
                       params={'sort': choice(ordem, ['best', 'new', 'old']), 'limit': limit(limite), 'cursor': cursor})
    if acao == 'responder':
        payload = {'content': required(conteudo, 'conteudo')}
        if comentario_id:
            payload['parent_id'] = segment(comentario_id)
        return request('POST', '/posts/' + segment(post_id) + '/comments', payload=payload)
    if acao == 'votar':
        choice(voto, ['upvote'] if comentario_id else ['upvote', 'downvote'])
        target = '/comments/' + segment(comentario_id) if comentario_id else '/posts/' + segment(post_id)
        return request('POST', target + '/' + voto)
    if acao == 'painel':
        return request('GET', '/home')
    if acao == 'marcar_lidas':
        return request('POST', '/notifications/read-by-post/' + segment(post_id))
    if acao == 'verificar':
        return verify(codigo, resposta)
    raise ValueError('Ação inválida.')
