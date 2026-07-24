import sys
import os

# Adiciona o diretório base para importar ayla_state
PASTA_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PASTA_RAIZ not in sys.path:
    sys.path.append(PASTA_RAIZ)

import ayla_state

# Garante compatibilidade se o arquivo for executado/importado individualmente
if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []


def ver_tarefas_ativas() -> str:
    """
    Retorna a lista de tarefas longas que a Ayla está executando no momento.
    """
    tarefas = ayla_state.listar_tarefas()
    if not tarefas:
        return "Nenhuma tarefa longa sendo processada neste exato milissegundo."
    
    resposta = "Minhas tarefas ativas no momento (eu posso estar fazendo isso em outra aba):\n"
    for idx, desc in enumerate(tarefas, start=1):
        resposta += f"{idx}. {desc}\n"
    return resposta

TOOL_MAP["ver_tarefas_ativas"] = ver_tarefas_ativas
FUNCTION_DECLARATIONS.append({
    "name": "ver_tarefas_ativas",
    "description": "Verifica quais tarefas a Ayla está processando no momento (como gerar imagem, baixar vídeo, etc). Use isso se você quiser saber se está ocupada ou se já terminou algo.",
    "parameters": {
        "type": "object",
        "properties": {}
    }
})
