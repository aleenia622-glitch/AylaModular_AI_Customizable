"""Abre links, pesquisa no YouTube, gera QR Codes e traduz textos."""
import sys
import os
import urllib.parse
import webbrowser
import requests
from pathlib import Path
from datetime import datetime

def _obter_diretorio_base() -> Path:
    if "__file__" in globals() and __file__:
        try:
            return Path(__file__).resolve().parents[2]
        except Exception:
            pass
    return Path.cwd()

caminho_base = _obter_diretorio_base()
if str(caminho_base) not in sys.path:
    sys.path.insert(0, str(caminho_base))

try:
    import ayla_state
except Exception:
    ayla_state = None

if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []


# ══════════════════════════════════════════════════════════
#  1. ABRIR URL / SITE
# ══════════════════════════════════════════════════════════

def abrir_url(url: str) -> str:
    """
    Abre um link ou site no navegador padrão do Windows.
    """
    try:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        webbrowser.open(url)
        return f"✅ Abrindo no navegador: {url}"
    except Exception as e:
        return f"Erro ao abrir URL: {e}"


# ══════════════════════════════════════════════════════════
#  2. PESQUISAR NO YOUTUBE
# ══════════════════════════════════════════════════════════

def pesquisar_youtube(query: str) -> str:
    """
    Pesquisa um vídeo/termo no YouTube e abre o resultado no navegador.
    """
    try:
        termo_encoded = urllib.parse.quote(query)
        url = f"https://www.youtube.com/results?search_query={termo_encoded}"
        webbrowser.open(url)
        return f"▶️ Pesquisando no YouTube por '{query}' e abrindo no navegador!"
    except Exception as e:
        return f"Erro ao pesquisar no YouTube: {e}"


# ══════════════════════════════════════════════════════════
#  3. GERAR QR CODE
# ══════════════════════════════════════════════════════════

def gerar_qrcode(texto: str) -> str:
    """
    Gera uma imagem de QR Code a partir de um texto ou link e salva na pasta de fotos.
    """
    try:
        texto_codificado = urllib.parse.quote(texto)
        url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={texto_codificado}"
        
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return "❌ Não consegui gerar o QR Code. O serviço pode estar temporariamente indisponível. 🥺"
            
        pasta_fotitos = caminho_base / "Aylafotitos"
        pasta_fotitos.mkdir(parents=True, exist_ok=True)
        caminho = str(pasta_fotitos / f"qrcode_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
        
        with open(caminho, "wb") as f:
            f.write(resp.content)
            
        if ayla_state and hasattr(ayla_state, "ULTIMA_IMAGEM_GERADA"):
            ayla_state.ULTIMA_IMAGEM_GERADA.set(caminho)
            
        return f"📱 QR Code criado com sucesso! Salvo em: `{caminho}`. Enviando a imagem... ✨"
    except Exception as e:
        return f"❌ Erro ao gerar QR Code: {e}"


# ══════════════════════════════════════════════════════════
#  4. TRADUZIR TEXTO
# ══════════════════════════════════════════════════════════

def traduzir_texto(texto: str, de: str = "pt", para: str = "en") -> str:
    """
    Traduz um texto entre idiomas usando a API MyMemory.
    """
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
            return f"❌ Problema na tradução: {erro} 🥺"
    except Exception as e:
        return f"❌ Erro ao traduzir texto: {e}"


TOOL_MAP["abrir_url"] = abrir_url
TOOL_MAP["pesquisar_youtube"] = pesquisar_youtube
TOOL_MAP["gerar_qrcode"] = gerar_qrcode
TOOL_MAP["traduzir_texto"] = traduzir_texto
TOOL_MAP["utilitarios_rapidos"] = abrir_url

FUNCTION_DECLARATIONS.append({
    "name": "abrir_url",
    "description": "Abre um link ou site no navegador padrão do Windows.",
    "parameters": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "A URL ou link do site a ser aberto (ex: 'https://google.com')."}
        },
        "required": ["url"]
    }
})

FUNCTION_DECLARATIONS.append({
    "name": "pesquisar_youtube",
    "description": "Pesquisa um termo ou vídeo no YouTube e abre o resultado no navegador.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "O que você quer pesquisar no YouTube."}
        },
        "required": ["query"]
    }
})

FUNCTION_DECLARATIONS.append({
    "name": "gerar_qrcode",
    "description": "Gera um QR Code a partir de um texto ou link e salva a imagem.",
    "parameters": {
        "type": "object",
        "properties": {
            "texto": {"type": "string", "description": "O texto ou URL que será convertido em QR Code."}
        },
        "required": ["texto"]
    }
})

FUNCTION_DECLARATIONS.append({
    "name": "traduzir_texto",
    "description": "Traduz um texto de um idioma para outro.",
    "parameters": {
        "type": "object",
        "properties": {
            "texto": {"type": "string", "description": "O texto que você quer traduzir."},
            "de": {"type": "string", "description": "Código do idioma de origem (ex: 'pt', 'en', 'es', 'fr', 'ja')."},
            "para": {"type": "string", "description": "Código do idioma de destino (ex: 'en', 'pt', 'es', 'fr', 'ja')."}
        },
        "required": ["texto", "de", "para"]
    }
})
