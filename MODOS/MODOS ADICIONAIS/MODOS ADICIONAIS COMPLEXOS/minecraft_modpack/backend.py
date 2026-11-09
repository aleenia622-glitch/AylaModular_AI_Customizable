"""Modrinth v2; nenhuma operação externa ocorre durante o import."""
import hashlib
import json
from pathlib import Path
import re
import tempfile
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
import zipfile

from ayla_paths import project_path
from ayla_verificacao import ResultadoFerramenta

API = 'https://api.modrinth.com/v2'
LIMITE = ('Compatibilidade declarada no Modrinth e integridade dos arquivos; '
          'Minecraft e loader não foram instalados nem executados. '
          'Conflitos não declarados pelos autores podem existir.')


def resultado(data, evidencias=(), erro=False):
    return ResultadoFerramenta(json.dumps(data, ensure_ascii=False),
                               'falhou' if erro else 'verificado', evidencias, LIMITE)


def identificador(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise ValueError('Informe IDs ou slugs do Modrinth, sem URLs.')
    return value


def parametros(versao, loader):
    if not isinstance(versao, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', versao):
        raise ValueError('Versão do Minecraft inválida.')
    if not isinstance(loader, str) or loader.lower() not in ('forge', 'fabric'):
        raise ValueError('Loader deve ser forge ou fabric.')
    return loader.lower()


def api(route, **params):
    url = API + route + ('?' + urlencode(params) if params else '')
    req = Request(url, headers={'User-Agent': 'Ayla-Minecraft-Modpack/1.0',
                                'Accept': 'application/json'})
    with urlopen(req, timeout=45) as response:
        return json.load(response)


class Resolver:
    def __init__(self, minecraft, loader):
        self.minecraft, self.loader = minecraft, loader
        self.projects, self.versions, self.pins = {}, {}, {}
        self.steps = 0

    def project(self, ref):
        ref = identificador(ref)
        if ref not in self.projects:
            p = api('/project/' + ref)
            if p.get('project_type') != 'mod':
                raise ValueError(f'{ref} não é um mod.')
            self.projects[ref] = self.projects[p['id']] = p
        return self.projects[ref]

    def compatible(self, v):
        return self.minecraft in v.get('game_versions', []) and self.loader in v.get('loaders', [])

    def candidates(self, project, pin=None):
        if pin:
            identificador(pin)
            if pin not in self.pins:
                self.pins[pin] = api('/version/' + pin)
            v = self.pins[pin]
            return [v] if v['project_id'] == project and self.compatible(v) else []
        if project not in self.versions:
            values = api('/project/' + project + '/version',
                         game_versions=json.dumps([self.minecraft]),
                         loaders=json.dumps([self.loader]))
            self.versions[project] = sorted(
                [v for v in values if self.compatible(v)],
                key=lambda v: (v.get('version_type') == 'release', v.get('date_published', '')),
                reverse=True)
        return self.versions[project]

    def dependency(self, d):
        pid, pin = d.get('project_id'), d.get('version_id')
        if pin:
            identificador(pin)
            if pin not in self.pins:
                self.pins[pin] = api('/version/' + pin)
            actual = self.pins[pin]['project_id']
            if pid and pid != actual:
                raise ValueError('Dependência com projeto e versão divergentes.')
            pid = actual
        if not pid:
            raise ValueError('Dependência obrigatória sem projeto/versão resolvível: ' + str(d))
        return self.project(pid)['id'], pin

    def conflict(self, selected):
        for v in selected.values():
            for d in v.get('dependencies', []):
                if d['dependency_type'] == 'incompatible':
                    if d.get('version_id'):
                        if any(x['id'] == d['version_id'] for x in selected.values()):
                            return True
                    elif d.get('project_id') in selected:
                        return True
        return False

    def solve(self, pending, selected=None):
        selected = selected or {}
        self.steps += 1
        if self.steps > 10000 or len(selected) > 200:
            raise ValueError('Limite de resolução atingido (200 mods/10000 tentativas). Reduza a seleção.')
        if not pending:
            return selected
        (pid, pin), *rest = pending
        if pid in selected:
            if pin and selected[pid]['id'] != pin:
                return None
            return self.solve(rest, selected)
        for v in self.candidates(pid, pin):
            chosen = {**selected, pid: v}
            if self.conflict(chosen):
                continue
            deps = [self.dependency(d) for d in v.get('dependencies', [])
                    if d['dependency_type'] == 'required']
            solved = self.solve(deps + rest, chosen)
            if solved is not None:
                return solved
        return None


def pesquisar_mods_minecraft(versao_minecraft, loader, consulta='', limite=10, offset=0):
    try:
        loader = parametros(versao_minecraft, loader)
        if type(limite) is not int or not 1 <= limite <= 50 or type(offset) is not int or offset < 0:
            raise ValueError('limite deve estar entre 1 e 50; offset deve ser inteiro não negativo.')
        data = api('/search', query=consulta, limit=limite, offset=offset,
                   facets=json.dumps([['project_type:mod'], ['versions:' + versao_minecraft],
                                      ['categories:' + loader]]))
        resolver = Resolver(versao_minecraft, loader)
        hits = []
        for h in data['hits']:
            versions = resolver.candidates(h['project_id'])
            if versions:
                hits.append({'id': h['project_id'], 'slug': h['slug'], 'nome': h['title'],
                             'descricao': h.get('description', ''), 'versao_mod': versions[0]['version_number'],
                             'url': 'https://modrinth.com/mod/' + h['slug']})
        return resultado({'mods': hits, 'total_busca': data['total_hits'],
                          'proximo_offset': offset + len(data['hits']),
                          'minecraft': versao_minecraft, 'loader': loader},
                         [f'Modrinth consultado; {len(hits)} projetos com versão compatível conferida.'])
    except Exception as exc:
        return resultado({'erro': str(exc)}, erro=True)


def arquivo_mod(v):
    files = [f for f in v.get('files', []) if f['filename'].lower().endswith('.jar')
             and f.get('file_type') not in ('sources-jar', 'dev-jar', 'javadoc-jar')]
    primary = [f for f in files if f.get('primary')]
    if not primary and len(files) != 1:
        raise ValueError(f'Arquivo JAR principal ausente ou ambíguo: {v["id"]}.')
    f = (primary or files)[0]
    name = f['filename']
    if Path(name).name != name or '\\' in name or ':' in name or any(ord(c) < 32 for c in name):
        raise ValueError('Nome de arquivo inseguro no Modrinth.')
    url = urlsplit(f['url'])
    if url.scheme != 'https' or url.hostname != 'cdn.modrinth.com' or url.username or url.port not in (None, 443):
        raise ValueError('Download fora do CDN HTTPS do Modrinth.')
    if not re.fullmatch(r'[a-fA-F0-9]{128}', f.get('hashes', {}).get('sha512', '')):
        raise ValueError('SHA-512 ausente ou inválido.')
    if type(f.get('size')) is not int or not 0 < f['size'] <= 512 * 1024 * 1024:
        raise ValueError('Tamanho inválido ou superior a 512 MiB.')
    return f


def conferir(path, f):
    digest = hashlib.sha512()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    if path.stat().st_size != f['size'] or digest.hexdigest() != f['hashes']['sha512'].lower():
        raise ValueError('Tamanho/hash divergente: ' + path.name)
    with zipfile.ZipFile(path) as jar:
        if not jar.namelist():
            raise ValueError('JAR vazio: ' + path.name)


def baixar(f, path):
    req = Request(f['url'], headers={'User-Agent': 'Ayla-Minecraft-Modpack/1.0'})
    with urlopen(req, timeout=60) as response, path.open('xb') as out:
        size = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > f['size']:
                raise ValueError('Download excedeu tamanho declarado.')
            out.write(chunk)
    conferir(path, f)


def criar_modpack_minecraft(versao_minecraft, loader, mods, pasta_destino='',
                            nome='Modpack Ayla', versao_loader=''):
    try:
        loader = parametros(versao_minecraft, loader)
        if not isinstance(mods, list) or not 1 <= len(mods) <= 100:
            raise ValueError('Informe uma lista de 1 a 100 IDs/slugs de mods.')
        if not isinstance(nome, str) or not nome.strip():
            raise ValueError('Nome do modpack obrigatório.')
        if versao_loader and not re.fullmatch(r'[A-Za-z0-9_.+-]+', versao_loader):
            raise ValueError('Versão do loader inválida.')
        if not isinstance(pasta_destino, str):
            raise ValueError('Nome da pasta deve ser texto.')
        # Compatibilidade com chamadas antigas: aproveita só o último nome,
        # nunca o caminho Windows/Linux fornecido pelo modelo.
        folder = pasta_destino.replace('\\', '/').rstrip('/').split('/')[-1] if pasta_destino.strip() else nome
        folder = re.sub(r'[^\w .-]', '_', folder).strip(' .')[:100]
        if not folder:
            raise ValueError('Nome de pasta inválido.')
        base = project_path('DocumentosCriados', 'modpacks').resolve()
        dest = base / folder
        if dest.is_symlink():
            raise ValueError('A pasta de destino não pode ser um link simbólico.')
        if dest.exists():
            raise ValueError('A pasta de destino já existe. Escolha uma nova pasta para preservar os arquivos.')
        resolver = Resolver(versao_minecraft, loader)
        roots = list(dict.fromkeys(resolver.project(m)['id'] for m in mods))
        selected = resolver.solve([(p, None) for p in roots])
        if selected is None:
            raise ValueError('Não há conjunto compatível com as dependências e incompatibilidades declaradas.')
        records, names = [], set()
        for pid, v in selected.items():
            f = arquivo_mod(v)
            if f['filename'].casefold() in names:
                raise ValueError('Dois mods usam o mesmo nome de arquivo: ' + f['filename'])
            names.add(f['filename'].casefold())
            records.append({'projeto': pid, 'nome': resolver.project(pid)['title'],
                            'versao_id': v['id'], 'versao': v['version_number'],
                            'dependencia': pid not in roots, 'dependencias': v.get('dependencies', []),
                            'arquivo': 'mods/' + f['filename'], 'download': f})
        if sum(r['download']['size'] for r in records) > 2 * 1024**3:
            raise ValueError('Modpack excede limite de download de 2 GiB.')
        manifest = {'formato': 'ayla-modpack', 'versao_formato': 1, 'nome': nome,
                    'minecraft': versao_minecraft, 'loader': loader, 'versao_loader': versao_loader or None,
                    'fonte': 'modrinth', 'mods': records}
        instructions = (f'{nome}\nMinecraft: {versao_minecraft}\nLoader: {loader} '
                        f'{versao_loader or "(selecionar versão compatível no launcher)"}\n\n'
                        'Crie uma instância com essa versão do Minecraft e instale o loader indicado.\n'
                        'Copie o conteúdo da pasta mods para a pasta mods da instância.\n'
                        'manifest.json é um inventário Ayla, não um manifest CurseForge.\n' + LIMITE + '\n')
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.ayla-modpack-', dir=dest.parent) as temp:
            stage = Path(temp) / 'pack'
            (stage / 'mods').mkdir(parents=True)
            for r in records:
                baixar(r['download'], stage / r['arquivo'])
            (stage / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
            (stage / 'INSTALACAO.txt').write_text(instructions, encoding='utf-8')
            # mkdir exclusivo também protege contra um destino criado durante os downloads.
            dest.mkdir()
            try:
                for child in stage.iterdir():
                    child.rename(dest / child.name)
                if json.loads((dest / 'manifest.json').read_text(encoding='utf-8')) != manifest:
                    raise ValueError('Manifest diverge após gravação.')
                if (dest / 'INSTALACAO.txt').read_text(encoding='utf-8') != instructions:
                    raise ValueError('Instruções divergem após gravação.')
                for r in records:
                    conferir(dest / r['arquivo'], r['download'])
            except Exception:
                # A pasta foi criada por esta execução; pode conter artefatos parciais.
                raise ValueError(f'Falha na publicação/verificação; inspecione a pasta parcial {dest}.')
        return resultado({'pasta': str(dest), 'manifest': str(dest / 'manifest.json'),
                          'minecraft': versao_minecraft, 'loader': loader,
                          'versao_loader': versao_loader or None,
                          'mods': [{k: r[k] for k in ('nome', 'projeto', 'versao', 'dependencia')} for r in records],
                          'total_mods': len(roots), 'total_dependencias': len(records) - len(roots)},
                         [f'{len(records)} JARs relidos, tamanho e SHA-512 conferidos em {dest / "mods"}.',
                          'Manifest JSON e instruções relidos e comparados integralmente.',
                          'Versão do Minecraft, loader e dependências obrigatórias conferidos na API.'])
    except Exception as exc:
        return resultado({'erro': str(exc)}, erro=True)


def declarations():
    common = {'versao_minecraft': {'type': 'string', 'description': 'Versão exata, por exemplo 1.20.1.'},
              'loader': {'type': 'string', 'enum': ['forge', 'fabric']}}
    return [
        {'name': 'pesquisar_mods_minecraft',
         'description': 'Pesquisa/lista mods Modrinth e confere versões para Minecraft e Forge/Fabric. Consulta vazia lista populares.',
         'parameters': {'type': 'object', 'properties': {**common,
             'consulta': {'type': 'string'}, 'limite': {'type': 'integer'}, 'offset': {'type': 'integer'}},
             'required': ['versao_minecraft', 'loader']}},
        {'name': 'criar_modpack_minecraft',
         'description': 'Monta modpack em pasta NOVA: baixa JARs Modrinth, resolve dependências obrigatórias e gera manifest Ayla e instruções. Não instala/executa Minecraft. Opcionais/embutidas não são baixadas automaticamente.',
         'parameters': {'type': 'object', 'properties': {**common,
             'mods': {'type': 'array', 'items': {'type': 'string'}, 'description': 'IDs ou slugs retornados pela pesquisa.'},
             'pasta_destino': {'type': 'string', 'description': 'Nome opcional da subpasta. Sempre salvo em DocumentosCriados/modpacks da Ayla; caminhos externos são ignorados, aproveitando somente o último nome.'}, 'nome': {'type': 'string'},
             'versao_loader': {'type': 'string', 'description': 'Versão desejada do loader; registrada para instalação manual, não validada.'}},
             'required': ['versao_minecraft', 'loader', 'mods']}}
    ]
