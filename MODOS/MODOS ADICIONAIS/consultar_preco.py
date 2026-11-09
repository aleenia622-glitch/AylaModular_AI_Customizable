"""Pesquisa preços de produtos e itens na internet."""
import urllib.parse
import os
import requests
import json
import re

if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []


def consultar_preco(produto: str) -> str:
    """
    Pesquisa o preço atual de um produto na internet quando o usuário pergunta quanto custa.
    """
    if not produto or not produto.strip():
        return "⚠️ Por favor, informe qual produto você deseja saber o preço!"

    termo = produto.strip()
    
    # 1. Tenta buscar via Tavily API se disponível
    tavily_key = os.environ.get("TAVILY_API_KEY", "")
    query = f"preço atual {termo} comprar brasil"
    
    precos_encontrados = []
    fontes = []

    if tavily_key:
        try:
            resp = requests.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": tavily_key,
                    "query": query,
                    "search_depth": "basic",
                    "include_answer": True,
                    "max_results": 5
                },
                timeout=12
            )
            if resp.status_code == 200:
                data = resp.json()
                resposta_tavily = data.get("answer", "")
                results = data.get("results", [])
                
                # Extrai menções de valores em R$
                for res in results:
                    snippet = res.get("content", "")
                    title = res.get("title", "")
                    url = res.get("url", "")
                    # Regex para identificar R$ XXX,XX ou R$ XXX
                    valores = re.findall(r'R\$\s?[\d\.\,]+', snippet + " " + title)
                    if valores:
                        for v in valores[:2]:
                            if v not in precos_encontrados:
                                precos_encontrados.append(v)
                    if url and len(fontes) < 3:
                        fontes.append(f"• [{title[:60]}]({url})")

                if resposta_tavily:
                    msg = f"🏷️ **Preço de '{termo}':**\n\n{resposta_tavily.strip()}"
                    if fontes:
                        msg += "\n\n🌐 **Fontes encontradas:**\n" + "\n".join(fontes)
                    return msg
        except Exception as e:
            print(f"⚠️ Erro ao consultar preço via Tavily: {e}")

    # Fallback via DuckDuckGo HTML se Tavily não retornar
    try:
        url_ddg = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        resp = requests.get(url_ddg, headers=headers, timeout=10)
        if resp.status_code == 200:
            html = resp.text
            valores = re.findall(r'R\$\s?[\d\.\,]+', html)
            for v in valores:
                if v not in precos_encontrados and len(v) < 15:
                    precos_encontrados.append(v)
                if len(precos_encontrados) >= 5:
                    break
    except Exception:
        pass

    if precos_encontrados:
        valores_fmt = ", ".join(precos_encontrados[:4])
        return (
            f"🏷️ **Preço estimado de '{termo}':**\n"
            f"Valores encontrados no mercado: **{valores_fmt}**\n\n"
            f"💡 *Nota: Os preços podem variar dependendo da loja, modelo específico ou estoque.*"
        )

    return f"🔍 Pesquisei por '{termo}', mas não consegui obter o preço exato no momento. Recomendo verificar em sites de busca ou lojas principais!"


TOOL_MAP["consultar_preco"] = consultar_preco
TOOL_MAP["monitorar_precos"] = consultar_preco

FUNCTION_DECLARATIONS.append({
    "name": "consultar_preco",
    "description": "Pesquisa quanto custa um produto, eletrônico, jogo ou item na internet e retorna o preço atual do mercado.",
    "parameters": {
        "type": "object",
        "properties": {
            "produto": {
                "type": "string",
                "description": "Nome do produto ou item para verificar o preço (ex: 'PlayStation 5', 'iPhone 15', 'RTX 4060')."
            }
        },
        "required": ["produto"]
    }
})
