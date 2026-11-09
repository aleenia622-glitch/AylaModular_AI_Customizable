"""Lista as memórias salvas, com opção de incluir as arquivadas."""
def consultar_memorias(incluir_arquivadas: bool = False, limite: int = 50) -> str:
    resultados = buscar_memorias_estruturadas(
        consulta="",
        limite=limite,
        escopos_permitidos={"privada", "publica"},
        incluir_arquivadas=incluir_arquivadas,
    )
    if not resultados:
        return "Caderninho vazio ou sem memórias ativas."
    return "🧠 Meu caderninho (ordenado por importância):\n" + formatar_memorias_encontradas(resultados)

TOOL_MAP["consultar_memorias"] = consultar_memorias
FUNCTION_DECLARATIONS.append({
    "name": "consultar_memorias",
    "description": "Consulta todas as memórias, preferências e momentos especiais sobre a usuario Usuario guardados no caderninho de memórias persistente.",
    "parameters": {
        "type": "object",
        "properties": {
            "incluir_arquivadas": {"type": "boolean", "description": "Inclui memórias arquivadas na listagem."},
            "limite": {"type": "integer", "description": "Quantidade máxima de memórias exibidas (1 a 50)."}
        }
    }
})
