import os
import re
import requests
from bs4 import BeautifulSoup

# Garante compatibilidade se o arquivo for executado/importado individualmente
if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

# ── Lazy import do ddgs (motor de busca Google/Bing via DuckDuckGo) ──
try:
    from ddgs import DDGS
    DDGS_OK = True
except ImportError:
    try:
        from duckduckgo_search import DDGS
        DDGS_OK = True
    except ImportError:
        DDGS_OK = False

# ══════════════════════════════════════════════════════════
#  CONFIGURAÇÕES
# ══════════════════════════════════════════════════════════

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
}

_MAX_CHARS_POR_FONTE = 3000   # limite de texto extraído por fonte
_MAX_FONTES          = 5      # quantas fontes tentar buscar
_MAX_RESULTADO_TOTAL = 15000  # limite total da resposta

# ══════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════

def _limpar_texto(texto: str) -> str:
    """Remove espaços excessivos e linhas em branco duplicadas."""
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def _extrair_texto_pagina(url: str) -> str | None:
    """Baixa a página e extrai o texto principal (parágrafos)."""
    try:
        r = requests.get(url, headers=_HEADERS, timeout=8, allow_redirects=True)
        if r.status_code != 200:
            return None

        soup = BeautifulSoup(r.text, "html.parser")

        # Remove scripts, estilos, nav, footer, aside, header
        for tag in soup(["script", "style", "nav", "footer", "aside",
                         "header", "form", "noscript", "svg", "iframe"]):
            tag.decompose()

        # Tenta extrair do <article> ou <main> primeiro (conteúdo principal)
        container = soup.find("article") or soup.find("main")
        if not container:
            container = soup.find("body") or soup

        paragrafos = container.find_all("p")
        texto = "\n".join(p.get_text(separator=" ", strip=True) for p in paragrafos)
        texto = _limpar_texto(texto)

        if len(texto) < 80:
            return None  # página vazia ou sem conteúdo útil

        return texto[:_MAX_CHARS_POR_FONTE]
    except Exception:
        return None


def _identificar_fonte(url: str) -> str:
    """Retorna um nome legível para a fonte baseado no domínio."""
    try:
        from urllib.parse import urlparse
        dominio = urlparse(url).netloc.lower().replace("www.", "")

        fontes_conhecidas = {
            "brasil.elpais.com": "El País Brasil",
            "g1.globo.com": "G1",
            "bbc.com": "BBC",
            "uol.com.br": "UOL",
            "terra.com.br": "Terra",
            "infopedia.pt": "Infopédia",
            "britannica.com": "Britannica",
            "infoescola.com": "InfoEscola",
            "todamateria.com.br": "Toda Matéria",
            "mundoeducacao.uol.com.br": "Mundo Educação",
            "brasilescola.uol.com.br": "Brasil Escola",
            "significados.com.br": "Significados",
            "suapesquisa.com": "Sua Pesquisa",
            "alura.com.br": "Alura",
            "aws.amazon.com": "AWS",
            "developer.mozilla.org": "MDN",
            "stackoverflow.com": "StackOverflow",
            "medium.com": "Medium",
            "github.com": "GitHub",
            "www.espn.com.br": "ESPN",
            "ge.globo.com": "globo esporte",
        }

        for chave, nome in fontes_conhecidas.items():
            if chave in dominio:
                return nome

        partes = dominio.split(".")
        if len(partes) >= 2:
            return partes[-2].capitalize()
        return dominio.capitalize()
    except Exception:
        return "Web"


# ══════════════════════════════════════════════════════════
#  FALLBACK — Wikipedia API (caso o DDGS falhe)
# ══════════════════════════════════════════════════════════

def _fallback_wikipedia(busca: str) -> str | None:
    """Busca na Wikipedia como fallback se o motor principal falhar."""
    search_url = "https://pt.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "list": "search",
        "srsearch": busca,
        "format": "json",
        "utf8": 1
    }
    headers_wiki = {"User-Agent": "AylaBot/2.0 (pesquisa silenciosa)"}

    try:
        r = requests.get(search_url, params=params, headers=headers_wiki, timeout=5)
        if r.status_code != 200:
            return None

        data = r.json()
        search_results = data.get("query", {}).get("search", [])
        if not search_results:
            return None

        results = []
        for item in search_results[:3]:
            title = item.get("title")
            pageid = item.get("pageid")

            content_params = {
                "action": "query",
                "prop": "extracts",
                "exintro": 1,
                "explaintext": 1,
                "pageids": pageid,
                "format": "json"
            }
            cr = requests.get(search_url, params=content_params, headers=headers_wiki, timeout=5)
            if cr.status_code == 200:
                cdata = cr.json()
                pages = cdata.get("query", {}).get("pages", {})
                extract = pages.get(str(pageid), {}).get("extract", "")
                if extract:
                    results.append(f"🔍 **Wikipedia — {title}**\n{extract[:_MAX_CHARS_POR_FONTE]}\n")

        if results:
            corpo = "\n---\n".join(results)
            return (
                f"📚 **Resultados da pesquisa (via Wikipedia)** — \"{busca}\"\n\n"
                f"{corpo}\n\n"
                f"🔗 **Fonte:** Wikipedia (pt.wikipedia.org)"
            )
    except Exception:
        pass
    return None


# ══════════════════════════════════════════════════════════
#  FUNÇÃO PRINCIPAL — Pesquisa multi-fonte via Google Search
# ══════════════════════════════════════════════════════════

def pesquisar_na_internet(busca: str) -> str:
    """
    Pesquisa informações na internet usando o Google Search como motor principal,
    consultando múltiplas fontes (não só Wikipedia).
    Retorna conteúdo extraído de cada página encontrada com as fontes identificadas.
    Tudo silenciosamente em segundo plano, sem abrir o navegador.
    """

    # ── Tentativa 1: DDGS (motor principal — Google/Bing) ──
    if DDGS_OK:
        try:
            ddgs = DDGS()
            resultados_busca = ddgs.text(busca, max_results=_MAX_FONTES + 3)

            if resultados_busca:
                resultados = []
                fontes_usadas = []

                for item in resultados_busca:
                    if len(resultados) >= _MAX_FONTES:
                        break

                    url = item.get("href", "")
                    titulo = item.get("title", "")
                    snippet = item.get("body", "")

                    if not url:
                        continue

                    nome_fonte = _identificar_fonte(url)

                    # Tenta extrair conteúdo mais completo da página
                    texto_pagina = _extrair_texto_pagina(url)

                    if texto_pagina:
                        # Usa o conteúdo extraído (mais completo)
                        bloco = f"🔍 **[{nome_fonte}]({url})** — {titulo}\n{texto_pagina}\n"
                    elif snippet:
                        # Se falhar, usa o snippet do motor de busca
                        bloco = f"🔍 **[{nome_fonte}]({url})** — {titulo}\n{snippet}\n"
                    else:
                        continue

                    fontes_usadas.append(f"[{nome_fonte}]({url})")
                    resultados.append(bloco)

                if resultados:
                    corpo = "\n---\n".join(resultados)

                    if len(corpo) > _MAX_RESULTADO_TOTAL:
                        corpo = corpo[:_MAX_RESULTADO_TOTAL] + "\n\n[...resultado truncado...]"

                    rodape_fontes = "\n".join(f"  • {f}" for f in fontes_usadas)
                    return (
                        f"📚 **Resultados da pesquisa** — \"{busca}\"\n\n"
                        f"{corpo}\n\n"
                        f"🔗 **Fontes consultadas:**\n{rodape_fontes}"
                    )
        except Exception as e:
            print(f"⚠️ DDGS falhou, tentando fallback Wikipedia: {e}")

    # ── Tentativa 2: Fallback Wikipedia ──
    resultado_wiki = _fallback_wikipedia(busca)
    if resultado_wiki:
        return resultado_wiki

    # ── Nenhuma fonte funcionou ──
    if not DDGS_OK:
        return (
            "❌ O motor de busca não está disponível. "
            "Instale com: pip install ddgs beautifulsoup4"
        )

    return f"ℹ️ Nenhum resultado encontrado para '{busca}'."


TOOL_MAP["pesquisar_na_internet"] = pesquisar_na_internet
FUNCTION_DECLARATIONS.append({
    "name": "pesquisar_na_internet",
    "description": "Busca informações na internet usando o Google Search como motor principal, consultando múltiplas fontes (não só Wikipedia). Extrai e resume conteúdo relevante de cada página encontrada, tudo em segundo plano sem abrir o navegador.",
    "parameters": {
        "type": "object",
        "properties": {
            "busca": {"type": "string", "description": "Termo ou pergunta a ser pesquisado na internet via Google"}
        },
        "required": ["busca"]
    }
})
