def abrir_url(url: str) -> str:
    try:
        if not url.startswith(("http://", "https://")): url = "https://" + url
        webbrowser.open(url)
        return f"✅ Abrindo no navegador: {url}"
    except Exception as e: return f"Erro: {e}"

TOOL_MAP["abrir_url"] = abrir_url
FUNCTION_DECLARATIONS.append({"name": "abrir_url", "description": "Abre link no navegador", "parameters": {"type": "object", "properties": {"url": {"type": "string"}}}})
