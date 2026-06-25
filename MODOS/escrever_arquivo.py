def escrever_arquivo(caminho: str, conteudo: str, modo: str = "w") -> str:
    try:
        p = Path(caminho).expanduser().resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, modo, encoding="utf-8") as f: f.write(conteudo)
        return f"Arquivo atualizado: {p}"
    except Exception as e: return f"Erro: {e}"

TOOL_MAP["escrever_arquivo"] = escrever_arquivo
FUNCTION_DECLARATIONS.append({"name": "escrever_arquivo", "description": "Escreve texto em arquivo", "parameters": {"type": "object", "properties": {"caminho": {"type": "string"}, "conteudo": {"type": "string"}, "modo": {"type": "string"}}}})
