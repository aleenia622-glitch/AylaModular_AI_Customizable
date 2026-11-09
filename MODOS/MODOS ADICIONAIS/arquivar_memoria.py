"""Arquiva memórias sem apagá-las e retira seu uso automático."""


def arquivar_memoria(chave: str, motivo: str = "") -> str:
    resultado = arquivar_memoria_estruturada(chave, motivo)
    return ("📦 " if resultado.get("ok") else "⚠️ ") + resultado.get("mensagem", "Não foi possível arquivar a memória.")


TOOL_MAP["arquivar_memoria"] = arquivar_memoria
FUNCTION_DECLARATIONS.append({
    "name": "arquivar_memoria",
    "description": "Arquiva uma memória desatualizada ou pouco útil. Ela deixa de ser usada automaticamente, mas continua recuperável.",
    "parameters": {
        "type": "object",
        "properties": {
            "chave": {"type": "string", "description": "Chave exata da memória a arquivar."},
            "motivo": {"type": "string", "description": "Motivo breve do arquivamento."}
        },
        "required": ["chave"]
    }
})
