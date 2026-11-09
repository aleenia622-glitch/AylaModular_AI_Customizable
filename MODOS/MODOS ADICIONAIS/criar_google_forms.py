"""Gera um script para a usuária executar e criar um Google Forms com as perguntas fornecidas."""
import json
import uuid

import ayla_state
from ayla_paths import project_path


TIPOS = {
    'texto': 'addTextItem',
    'paragrafo': 'addParagraphTextItem',
    'multipla_escolha': 'addMultipleChoiceItem',
    'caixas_selecao': 'addCheckboxItem',
    'lista': 'addListItem',
    'data': 'addDateItem',
    'hora': 'addTimeItem',
}
COM_OPCOES = {'multipla_escolha', 'caixas_selecao', 'lista'}


def _texto(valor, campo, limite=10000):
    if not isinstance(valor, str) or not valor.strip() or len(valor) > limite:
        raise ValueError(f'{campo} deve ser um texto não vazio com até {limite} caracteres.')
    return valor.strip()


def _gerar_script(titulo, perguntas, descricao):
    titulo = _texto(titulo, 'titulo', 300)
    if not isinstance(descricao, str) or len(descricao) > 10000:
        raise ValueError('descricao deve ser um texto com até 10000 caracteres.')
    if not isinstance(perguntas, list) or not 1 <= len(perguntas) <= 200:
        raise ValueError('Informe entre 1 e 200 perguntas.')
    normalizadas = []
    for indice, pergunta in enumerate(perguntas, 1):
        if not isinstance(pergunta, dict):
            raise ValueError(f'Pergunta {indice} deve ser um objeto.')
        tipo = pergunta.get('tipo', 'texto')
        if not isinstance(tipo, str) or tipo not in TIPOS:
            raise ValueError(f'Tipo inválido na pergunta {indice}. Use: {", ".join(TIPOS)}.')
        obrigatoria = pergunta.get('obrigatoria', False)
        if not isinstance(obrigatoria, bool):
            raise ValueError(f'obrigatoria da pergunta {indice} deve ser booleano.')
        item = {'titulo': _texto(pergunta.get('titulo'), f'titulo da pergunta {indice}'),
                'metodo': TIPOS[tipo], 'obrigatoria': obrigatoria}
        ajuda = pergunta.get('ajuda', '')
        if not isinstance(ajuda, str) or len(ajuda) > 10000:
            raise ValueError(f'ajuda da pergunta {indice} deve ser texto com até 10000 caracteres.')
        item['ajuda'] = ajuda
        opcoes = pergunta.get('opcoes', [])
        if tipo in COM_OPCOES:
            if not isinstance(opcoes, list) or not 1 <= len(opcoes) <= 100:
                raise ValueError(f'Pergunta {indice} precisa de 1 a 100 opções.')
            item['opcoes'] = [_texto(o, f'opção da pergunta {indice}', 1000) for o in opcoes]
            if len(set(item['opcoes'])) != len(item['opcoes']):
                raise ValueError(f'Pergunta {indice} tem opções repetidas.')
        elif opcoes:
            raise ValueError(f'Pergunta {indice}: este tipo não aceita opções.')
        normalizadas.append(item)
    dados = json.dumps({'titulo': titulo, 'descricao': descricao, 'perguntas': normalizadas}, ensure_ascii=True)
    return '''// COMO USAR:
// 1. Abra https://script.google.com e crie um novo projeto.
// 2. Cole TODO este arquivo no editor, substituindo o conteúdo inicial.
// 3. Selecione criarFormularioAyla e clique em Executar; autorize sua conta.
// 4. O link de edição aparecerá no Registro de execução.
// O formulário é criado como rascunho. Revise e publique no Google Forms.
// Executar novamente este mesmo projeto retorna o formulário já criado.
function criarFormularioAyla() {
  const dados = DADOS_FORMULARIO;
  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    const props = PropertiesService.getScriptProperties();
    const chave = 'ayla_form_' + Utilities.base64EncodeWebSafe(
      Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, JSON.stringify(dados)));
    const anterior = props.getProperty(chave);
    if (anterior) {
      const existente = FormApp.openById(anterior);
      console.log('Editar: ' + existente.getEditUrl());
      return existente.getEditUrl();
    }
    const form = FormApp.create(dados.titulo, false);
    try {
      form.setDescription(dados.descricao);
      dados.perguntas.forEach(function(p) {
        const item = form[p.metodo]();
        item.setTitle(p.titulo).setRequired(p.obrigatoria);
        if (p.ajuda) item.setHelpText(p.ajuda);
        if (p.opcoes) item.setChoiceValues(p.opcoes);
      });
      props.setProperty(chave, form.getId());
    } catch (erro) {
      DriveApp.getFileById(form.getId()).setTrashed(true);
      throw erro;
    }
    console.log('Editar e publicar: ' + form.getEditUrl());
    return form.getEditUrl();
  } finally {
    lock.releaseLock();
  }
}
'''.replace('DADOS_FORMULARIO', dados)


def tool_criar_google_forms(titulo, perguntas, descricao=''):
    """Valida, gera e agenda o anexo pela infraestrutura de arquivos da Ayla."""
    try:
        script = _gerar_script(titulo, perguntas, descricao)
    except ValueError as exc:
        return f'⚠️ Não criei o formulário: {exc}'
    try:
        pasta = project_path('ArquivosGerados', 'formularios')
        pasta.mkdir(parents=True, exist_ok=True)
        arquivo = pasta / f'formulario_{uuid.uuid4().hex}.gs'
        arquivo.write_text(script, encoding='utf-8')
    except OSError as exc:
        return f'⚠️ Não consegui salvar o script do formulário: {exc}'
    ayla_state.ULTIMA_IMAGEM_GERADA.set(str(arquivo))
    return (
        f'📋 Script do formulário "{titulo}" gerado com {len(perguntas)} perguntas.\n'
        f'Arquivo para anexar: {arquivo}\n'
        'Para criar na sua conta: abra https://script.google.com, crie um projeto, '
        'cole o conteúdo do arquivo e execute criarFormularioAyla. Autorize quando o Google pedir. '
        'O link de edição aparecerá no Registro de execução. Revise e publique no Google Forms. '
        'Este arquivo é um script; não é importado diretamente pelo Google Forms.'
    )


if 'TOOL_MAP' not in globals():
    TOOL_MAP = {}
if 'FUNCTION_DECLARATIONS' not in globals():
    FUNCTION_DECLARATIONS = []

TOOL_MAP['criar_google_forms'] = tool_criar_google_forms
FUNCTION_DECLARATIONS.append({
    'name': 'criar_google_forms',
    'description': 'Cria e envia em uma única chamada um arquivo .gs pronto para gerar um Google Forms. Forneça todas as perguntas nesta chamada. A usuária cola o script no Google Apps Script e executa; não há upload direto no Forms. Não exige credenciais Google na Ayla.',
    'parameters': {
        'type': 'OBJECT',
        'properties': {
            'titulo': {'type': 'STRING', 'description': 'Título do formulário.'},
            'descricao': {'type': 'STRING', 'description': 'Descrição opcional do formulário.'},
            'perguntas': {
                'type': 'ARRAY', 'description': 'Todas as perguntas, em ordem (1 a 200).',
                'items': {
                    'type': 'OBJECT',
                    'properties': {
                        'titulo': {'type': 'STRING'},
                        'tipo': {'type': 'STRING', 'enum': list(TIPOS)},
                        'obrigatoria': {'type': 'BOOLEAN'},
                        'ajuda': {'type': 'STRING'},
                        'opcoes': {'type': 'ARRAY', 'items': {'type': 'STRING'}, 'description': 'Obrigatórias para multipla_escolha, caixas_selecao e lista; omitir nos outros tipos.'},
                    },
                    'required': ['titulo', 'tipo'],
                },
            },
        },
        'required': ['titulo', 'perguntas'],
    },
})
