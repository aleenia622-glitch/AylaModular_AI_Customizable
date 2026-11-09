"""Evidências de execução: leitura de volta, validação de formatos e estado real.

Os verificadores nunca repetem a ação. Resultado sem verificador permanece
explicitamente não verificado, mesmo quando a ferramenta escreve 'sucesso'.
"""
from ayla_paths import resolve_path
from contextvars import ContextVar
import ast
import json
from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET


EVIDENCIAS = ContextVar('ayla_evidencias_ferramenta', default=None)

INSTRUCOES_VERIFICACAO = ""


class ResultadoFerramenta(str):
    """Preserva compatibilidade textual e carrega o estado para o núcleo."""
    def __new__(cls, texto, estado='nao_verificado', evidencias=(), limite=''):
        obj = super().__new__(cls, texto)
        obj.estado = estado
        obj.evidencias = list(evidencias)
        obj.limite = limite
        return obj

    def para_modelo(self, limite_texto=8000):
        texto = str(self)
        if len(texto) > limite_texto:
            texto = texto[:limite_texto] + '\n[Resultado truncado.]'
        return {'result': texto, 'verificacao': {
            'estado': self.estado, 'evidencias': self.evidencias[-10:], 'limite': self.limite}}


def registrar_evidencia(texto):
    evidencias = EVIDENCIAS.get()
    if evidencias is not None:
        evidencias.append(texto)


def conferir_texto_gravado(caminho, esperado):
    """Relê o arquivo e compara todo o conteúdo; não executa código criado."""
    path = Path(caminho)
    lido = path.read_text(encoding='utf-8')
    if lido != esperado.replace('\r\n', '\n').replace('\r', '\n'):
        raise ValueError(f'Verificação falhou: conteúdo gravado difere do solicitado em {path.name}.')
    if path.suffix.lower() == '.py':
        ast.parse(lido, filename=str(path))
    elif path.suffix.lower() == '.json':
        json.loads(lido)
    registrar_evidencia(f'Arquivo relido e conteúdo integral conferido: {path}.')


def gravar_texto_conferido(caminho, conteudo):
    if Path(caminho).suffix.lower() in {'.docx', '.xlsx', '.pptx', '.pdf'}:
        raise ValueError('Este formato exige um editor específico; gravar texto direto corromperia o arquivo.')
    Path(caminho).write_text(conteudo, encoding='utf-8')
    conferir_texto_gravado(caminho, conteudo)


def conferir_docx_gravado(caminho, esperado):
    path = Path(caminho)
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError('Verificação falhou: documento Word corrompido.')
        root = ET.fromstring(archive.read('word/document.xml'))
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    paragraphs = []
    for paragraph in root.findall('w:body/w:p', ns):
        parts = []
        for node in paragraph.iter():
            if node.tag == '{' + ns['w'] + '}t':
                parts.append(node.text or '')
            elif node.tag == '{' + ns['w'] + '}tab':
                parts.append('\t')
        paragraphs.append(''.join(parts))
    if paragraphs != esperado.splitlines():
        raise ValueError('Verificação falhou: o texto do Word difere do solicitado.')
    registrar_evidencia(f'DOCX reaberto e todos os parágrafos conferidos: {path}.')


def retorno_falhou(value):
    if isinstance(value, ResultadoFerramenta):
        return value.estado == 'falhou'
    if value is None or value is False:
        return True
    if isinstance(value, dict):
        return (value.get('ok') is False or value.get('sucesso') is False
                or value.get('returncode', 0) != 0
                or str(value.get('status', '')).lower() in {'erro', 'falha', 'failed', 'error'})
    text = str(value).strip()
    if not text:
        return True
    return bool(re.match(
        r'^(?:[❌⚠🚫⏱][\ufe0f\s]*|(?:erro|falha|timeout|não consegui|nao consegui|'
        r'não foi possível|nao foi possivel|operação bloqueada)\b)', text, re.I))


def identidade_acao(nome, args):
    # Uma correção do mesmo destino resolve a falha; sucesso em outro arquivo não.
    if isinstance(args, dict):
        for field in ('chave', 'chave_ou_identificador', 'caminho', 'nome_arquivo'):
            if field in args:
                return nome, field, str(args[field])
    return nome, json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)


def verificar_arquivo(caminho: str, conteudo_esperado: str = None):
    """Ferramenta de consulta para conferir um arquivo sem modificá-lo."""
    path = resolve_path(caminho)
    token = EVIDENCIAS.set([])
    try:
        if not path.is_file():
            raise ValueError('O arquivo não existe.')
        size = path.stat().st_size
        ext = path.suffix.lower()
        if conteudo_esperado is not None:
            if ext == '.docx':
                conferir_docx_gravado(path, conteudo_esperado)
            else:
                conferir_texto_gravado(path, conteudo_esperado)
        elif ext in {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'}:
            from PIL import Image
            with Image.open(path) as picture:
                picture.verify()
            registrar_evidencia('Imagem reaberta e integridade verificada.')
        elif ext in {'.docx', '.xlsx', '.pptx', '.zip'}:
            with zipfile.ZipFile(path) as archive:
                if archive.testzip() is not None:
                    raise ValueError('Arquivo compactado corrompido.')
                member = {'.docx': 'word/document.xml', '.xlsx': 'xl/workbook.xml',
                          '.pptx': 'ppt/presentation.xml'}.get(ext)
                if member:
                    ET.fromstring(archive.read(member))
            registrar_evidencia('Pacote reaberto e estrutura principal validada.')
        elif ext == '.pdf':
            from pypdf import PdfReader
            reader = PdfReader(str(path), strict=True)
            if not reader.pages:
                raise ValueError('PDF sem páginas.')
            registrar_evidencia(f'PDF reaberto: {len(reader.pages)} páginas.')
        elif ext in {'.txt', '.md', '.csv', '.html', '.css', '.js', '.py', '.json'}:
            text = path.read_text(encoding='utf-8-sig')
            if ext == '.py':
                ast.parse(text)
            elif ext == '.json':
                json.loads(text)
            registrar_evidencia('Texto legível' + (' e sintaxe válida.' if ext in {'.py', '.json'} else '.'))
        else:
            with path.open('rb') as stream:
                stream.read(1)
            registrar_evidencia('Arquivo acessível para leitura; formato não validado.')
        registrar_evidencia(f'Arquivo existente: {path}; tamanho: {size} bytes.')
        return ResultadoFerramenta(f'Verificação de arquivo: {path.name}.', 'verificado', EVIDENCIAS.get(),
            'Validação limitada às evidências; não comprova qualidade visual, envio ou funcionamento de programas.')
    except Exception as exc:
        return ResultadoFerramenta(f'Erro na verificação de {path.name}: {exc}', 'falhou')
    finally:
        EVIDENCIAS.reset(token)


def verificar_memoria(nome, args, brain, before=None):
    """Lê o JSON principal no disco, sem aceitar cache ou backup como prova."""
    mem = json.loads(Path(brain.ARQUIVO_MEMORIA).read_text(encoding='utf-8-sig'))
    chave = args.get('chave', '')
    if nome == 'memorizar_informacao':
        normalized = brain._texto_memoria_normalizado(brain.normalizar_chave_memoria(chave))
        chave = next((k for k in mem if brain._texto_memoria_normalizado(k) == normalized), chave)
    if nome in {'memorizar_informacao', 'editar_memoria'}:
        expected = args.get('novo_valor') if nome == 'editar_memoria' else args.get('valor', args.get('value'))
        record = brain.normalizar_registro_memoria(chave, mem.get(chave, {}))
        if chave not in mem or brain._texto_memoria_normalizado(record.get('Valor')) != brain._texto_memoria_normalizado(expected):
            raise ValueError('A memória no disco não contém o valor solicitado.')
    elif nome == 'arquivar_memoria':
        if chave not in mem or mem[chave].get('status') != 'arquivada':
            raise ValueError('A memória não está arquivada no disco.')
    elif nome == 'apagar_memoria':
        trash = json.loads(Path(brain.ARQUIVO_MEMORIA_LIXEIRA).read_text(encoding='utf-8-sig'))
        if chave in mem or not any(isinstance(v, dict) and v.get('chave_original') == chave for v in trash.values()):
            raise ValueError('A remoção e a cópia na lixeira não foram confirmadas.')
    elif nome == 'restaurar_memoria':
        trash = json.loads(Path(brain.ARQUIVO_MEMORIA_LIXEIRA).read_text(encoding='utf-8-sig'))
        identifier = args.get('chave_ou_identificador', '')
        source = before or {}
        item_id = identifier if identifier in source else next(
            (k for k, v in sorted(source.items(), reverse=True)
             if isinstance(v, dict) and v.get('chave_original') == identifier), None)
        item = source.get(item_id, {})
        chave = item.get('chave_original')
        expected = brain.normalizar_registro_memoria(chave or '', item.get('registro', {}))
        if (not chave or chave not in mem or item_id in trash
                or mem[chave].get('status') != 'ativa'
                or mem[chave].get('Valor') != expected.get('Valor')):
            raise ValueError('A memória restaurada e a retirada da lixeira não foram confirmadas.')
    else:
        return
    registrar_evidencia(f'Estado da memória conferido no arquivo principal: {chave}.')


def concluir_verificacao(value, evidencias):
    if retorno_falhou(value):
        return ResultadoFerramenta(str(value), 'falhou')
    if isinstance(value, ResultadoFerramenta):
        return value
    if evidencias:
        return ResultadoFerramenta(str(value), 'verificado', evidencias,
            'Somente as condições listadas foram verificadas; envio, execução de código e efeitos externos exigem comprovação própria.')
    return ResultadoFerramenta(str(value), 'nao_verificado', (),
        'A ferramenta retornou, mas não há verificador automático para o efeito desta ação.')


def proteger_confirmacao(texto, falhas):
    """Evita uma confirmação categórica comum quando ainda há ações com falha."""
    if falhas and re.search(r'\b(pronto|prontinho|feito|conclu[ií]d[oa]|com sucesso)\b', texto, re.I):
        return ('Não consegui confirmar a conclusão de todas as ações.\n' + '\n'.join(
            f'• {nome}: {motivo}' for nome, motivo in list(falhas.values())[-5:]))
    return texto
