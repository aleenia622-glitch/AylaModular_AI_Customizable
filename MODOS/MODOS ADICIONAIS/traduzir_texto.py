import urllib.parse
import requests

def traduzir_texto(texto: str, de: str = "pt", para: str = "en") -> str:
    """Traduz texto usando a API gratuita MyMemory."""
    try:
        texto_codificado = urllib.parse.quote(texto)
        url = f'https://api.mymemory.translated.net/get?q={texto_codificado}&langpair={de}|{para}'
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        dados = resp.json()

        if dados.get("responseStatus") == 200:
            traducao = dados["responseData"]["translatedText"]
            return (
                f"🌐 **Tradução da Ayla!** ✨ ({de} → {para})\n\n"
                f"**Original:**\n{texto}\n\n"
                f"**Traduzido:**\n{traducao}"
            )
        else:
            erro = dados.get("responseDetails", "Erro desconhecido")
            return f"❌ Aconteceu um probleminha na tradução: {erro} 🥺"
    except Exception as e:
        return f"❌ Desculpa, aconteceu um erro ao traduzir o texto: {e} 💔"

TOOL_MAP["traduzir_texto"] = traduzir_texto
TOOL_MAP["traduzir_texto"] = traduzir_texto

if "traduzir_texto" not in [fd["name"] for fd in FUNCTION_DECLARATIONS]:
    FUNCTION_DECLARATIONS.append({
        "name": "traduzir_texto",
        "description": "Traduz um texto de um idioma para outro de forma super fofa! 🌐🌸",
        "parameters": {
            "type": "object",
            "properties": {
                "texto": {
                    "type": "string",
                    "description": "O texto que você quer traduzir."
                },
                "de": {
                    "type": "string",
                    "description": "Código do idioma de origem (ex: 'pt', 'en', 'es', 'fr', 'ja')."
                },
                "para": {
                    "type": "string",
                    "description": "Código do idioma de destino (ex: 'en', 'pt', 'es', 'fr', 'ja')."
                }
            },
            "required": ["texto", "de", "para"]
        }
    })
