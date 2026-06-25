def renomear_arquivo(caminho: str, novo_nome: str) -> str:
    try:
        p = Path(caminho).expanduser().resolve()
        p.rename(p.parent / novo_nome)
        return f"✅ Renomeado para: {novo_nome}"
    except Exception as e: return f"Erro: {e}"

TOOL_MAP["renomear_arquivo"] = renomear_arquivo
FUNCTION_DECLARATIONS.append({"name": "renomear_arquivo", "description": "Renomeia arquivo", "parameters": {"type": "object", "properties": {"caminho": {"type": "string"}, "novo_nome": {"type": "string"}}}})
