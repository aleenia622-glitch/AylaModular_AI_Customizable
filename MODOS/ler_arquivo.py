def ler_arquivo(caminho: str) -> str:
    try:
        p = Path(caminho).expanduser().resolve()
        if not p.is_file(): return f"Arquivo não encontrado: {p}"
        if p.stat().st_size > 2_000_000: return "Arquivo muito grande (mais de 2MB)."
        content = p.read_text(encoding="utf-8", errors="replace")
        return content if content.strip() else "(arquivo vazio)"
    except Exception as e: return f"Erro: {e}"

TOOL_MAP["ler_arquivo"] = ler_arquivo
FUNCTION_DECLARATIONS.append({"name": "ler_arquivo", "description": "Lê texto de arquivo", "parameters": {"type": "object", "properties": {"caminho": {"type": "string"}}}})
