def pesquisar_youtube(query: str) -> str:
    """Pesquisa no YouTube e abre o primeiro resultado"""
    try:
        url_busca = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
        webbrowser.open(url_busca)
        return f"▶️ Abri o YouTube com a busca: '{query}'"
    except Exception as e:
        return f"Erro: {e}"

TOOL_MAP["pesquisar_youtube"] = pesquisar_youtube
FUNCTION_DECLARATIONS.append({"name": "pesquisar_youtube", "description": "Pesquisa algo no YouTube e abre no navegador.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}})
