"""Lista memórias na lixeira e restaura itens removidos."""


def restaurar_memoria(chave_ou_identificador: str, sobrescrever: bool = False) -> str:
    resultado = restaurar_memoria_estruturada(chave_ou_identificador, sobrescrever)
    return ("♻️ " if resultado.get("ok") else "⚠️ ") + resultado.get("mensagem", "Não foi possível restaurar a memória.")


def consultar_lixeira_memoria(limite: int = 20) -> str:
    itens = listar_lixeira_memoria(limite)
    if not itens:
        return "🗑️ A lixeira de memórias está vazia."
    linhas = [f"- {item['chave']} | removida em {item['removida_em']} | id: {item['identificador']}" for item in itens]
    return "🗑️ Lixeira de memórias:\n" + "\n".join(linhas)


TOOL_MAP["restaurar_memoria"] = restaurar_memoria
TOOL_MAP["consultar_lixeira_memoria"] = consultar_lixeira_memoria
FUNCTION_DECLARATIONS.extend([
    {
        "name": "restaurar_memoria",
        "description": "Restaura uma memória que foi movida para a lixeira. Use primeiro consultar_lixeira_memoria se não souber a chave.",
        "parameters": {
            "type": "object",
            "properties": {
                "chave_ou_identificador": {"type": "string", "description": "Chave original ou identificador exibido na lixeira."},
                "sobrescrever": {"type": "boolean", "description": "True somente se uma memória atual com a mesma chave puder ser substituída."}
            },
            "required": ["chave_ou_identificador"]
        }
    },
    {
        "name": "consultar_lixeira_memoria",
        "description": "Lista memórias removidas que ainda podem ser restauradas.",
        "parameters": {"type": "object", "properties": {"limite": {"type": "integer", "description": "Quantidade máxima de itens, de 1 a 100."}}}
    }
])
