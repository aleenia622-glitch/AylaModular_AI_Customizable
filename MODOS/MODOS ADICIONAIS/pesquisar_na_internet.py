import sys
import os
sys.path.append(r"C:\Users\Aleenia\Documents\AI")
import ayla_state
import ipaddress
import re
import requests
import socket
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

# Garante compatibilidade se o arquivo for executado/importado individualmente
if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

# ── Lazy import do ddgs (motor de busca via DuckDuckGo - Fallback 1) ──
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

_MAX_BYTES_PAGINA    = 5 * 1024 * 1024
_MAX_BYTES_IMAGEM    = 10 * 1024 * 1024
_MAX_REDIRECTS       = 5

# ══════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════

def _limpar_texto(texto: str) -> str:
    """Remove espaços excessivos e linhas em branco duplicadas."""
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def _url_publica(url: str) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return False
        porta = parsed.port or (443 if parsed.scheme == "https" else 80)
        enderecos = socket.getaddrinfo(parsed.hostname, porta, type=socket.SOCK_STREAM)
        if not enderecos:
            return False
        return all(ipaddress.ip_address(item[4][0]).is_global for item in enderecos)
    except Exception:
        return False


def _abrir_url_publica(url: str, timeout: int):
    atual = url
    for _ in range(_MAX_REDIRECTS + 1):
        if not _url_publica(atual):
            return None
        resposta = requests.get(
            atual,
            headers=_HEADERS,
            timeout=timeout,
            allow_redirects=False,
            stream=True,
        )
        if resposta.status_code not in (301, 302, 303, 307, 308):
            return resposta
        destino = resposta.headers.get("Location")
        resposta.close()
        if not destino:
            return None
        atual = urljoin(atual, destino)
    return None


def _extrair_texto_pagina(url: str, max_chars_por_fonte: int = 1000) -> str | None:
    """Baixa a página e extrai o texto principal (parágrafos), além de coletar imagens."""
    try:
        resposta_pagina = _abrir_url_publica(url, timeout=8)
        if resposta_pagina is None:
            return None
        with resposta_pagina as r:
            if r.status_code != 200:
                return None
            tamanho = int(r.headers.get("Content-Length", "0") or 0)
            if tamanho > _MAX_BYTES_PAGINA:
                return None
            blocos = []
            recebido = 0
            for bloco in r.iter_content(chunk_size=64 * 1024):
                recebido += len(bloco)
                if recebido > _MAX_BYTES_PAGINA:
                    return None
                blocos.append(bloco)
            encoding = r.encoding or "utf-8"
            html = b"".join(blocos).decode(encoding, errors="replace")

        soup = BeautifulSoup(html, "html.parser")

        # --- Extração e Download de Imagens ---
        ultimas_imagens = ayla_state.ULTIMAS_IMAGENS_MODULO.get()
        if ultimas_imagens is not None and len(ultimas_imagens) < 10:
            img_tags = soup.find_all("img")
            img_urls = []
            for img in img_tags:
                src = img.get("src")
                if not src:
                    continue
                abs_src = urljoin(url, src)
                if abs_src.startswith("http://") or abs_src.startswith("https://"):
                    if abs_src not in img_urls:
                        img_urls.append(abs_src)
                if len(img_urls) >= 3 or len(ultimas_imagens) + len(img_urls) >= 10:
                    break

            for img_url in img_urls:
                if len(ultimas_imagens) >= 10:
                    break
                try:
                    resposta_imagem = _abrir_url_publica(img_url, timeout=3)
                    if resposta_imagem is None:
                        continue
                    with resposta_imagem as img_resp:
                        if img_resp.status_code != 200:
                            continue
                        content_type = img_resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
                        allowed_mimes = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/heic", "image/heif", "image/gif"}
                        if content_type not in allowed_mimes:
                            continue
                        tamanho = int(img_resp.headers.get("Content-Length", "0") or 0)
                        if tamanho > _MAX_BYTES_IMAGEM:
                            continue
                        blocos_img = []
                        recebido_img = 0
                        excedeu = False
                        for bloco in img_resp.iter_content(chunk_size=64 * 1024):
                            recebido_img += len(bloco)
                            if recebido_img > _MAX_BYTES_IMAGEM:
                                excedeu = True
                                break
                            blocos_img.append(bloco)
                        if excedeu:
                            continue
                        img_bytes = b"".join(blocos_img)
                    if len(img_bytes) < 1024:
                        continue
                    ultimas_imagens.append((img_bytes, content_type))
                except Exception:
                    pass

        # Remove scripts, estilos, nav, footer, etc.
        for tag in soup(["script", "style", "nav", "footer", "aside",
                         "header", "form", "noscript", "svg", "iframe"]):
            tag.decompose()

        container = soup.find("article") or soup.find("main")
        if not container:
            container = soup.find("body") or soup

        paragrafos = container.find_all("p")
        texto = "\n".join(p.get_text(separator=" ", strip=True) for p in paragrafos)
        texto = _limpar_texto(texto)

        if len(texto) < 80:
            return None

        return texto[:max_chars_por_fonte]
    except Exception:
        return None


def _identificar_fonte(url: str) -> str:
    """Retorna um nome legível para a fonte baseado no domínio."""
    try:
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


def _obter_tavily_api_key() -> str | None:
    """Obtém a chave de API da Tavily das variáveis de ambiente ou diretamente do arquivo .env."""
    key = os.getenv("TAVILY_API_KEY")
    if key and key.strip():
        return key.strip()

    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if not os.path.exists(env_path):
        env_path = r"C:\Users\Aleenia\Documents\AI\.env"

    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "TAVILY_API_KEY" in line:
                        partes = line.split("=", 1)
                        if len(partes) == 2 and partes[0].strip() == "TAVILY_API_KEY":
                            valor = partes[1].strip().split("#")[0].strip().strip("\"'")
                            if valor:
                                return valor
        except Exception:
            pass
    return None


def _busca_tavily(busca: str, fontes: int = 5, max_caracteres: int = 1000) -> str | None:
    """
    Pesquisa usando a API da Tavily (mecanismo principal).
    Retorna a string formatada com os resultados ou None em caso de falha/sem chave.
    """
    api_key = _obter_tavily_api_key()
    if not api_key:
        return None

    url_api = "https://api.tavily.com/search"
    payload = {
        "api_key": api_key,
        "query": busca,
        "search_depth": "basic",
        "include_images": True,
        "max_results": max(1, min(10, fontes))
    }

    try:
        resp = requests.post(url_api, json=payload, timeout=10)
        if resp.status_code != 200:
            print(f"⚠️ Tavily API retornou status code {resp.status_code}: {resp.text}")
            return None

        data = resp.json()
        search_results = data.get("results", [])
        if not search_results:
            return None

        max_resultado_total = min(30000, max(5000, fontes * max_caracteres + 2000))
        ultimas_imagens = ayla_state.ULTIMAS_IMAGENS_MODULO.get()
        if ultimas_imagens is None:
            ultimas_imagens = []
            ayla_state.ULTIMAS_IMAGENS_MODULO.set(ultimas_imagens)

        # Processar imagens adicionais retornadas pela API da Tavily se houver
        images_tavily = data.get("images", [])
        if images_tavily and isinstance(images_tavily, list):
            for img_url in images_tavily:
                if len(ultimas_imagens) >= 10:
                    break
                if isinstance(img_url, str) and (img_url.startswith("http://") or img_url.startswith("https://")):
                    try:
                        resposta_imagem = _abrir_url_publica(img_url, timeout=3)
                        if resposta_imagem and resposta_imagem.status_code == 200:
                            content_type = resposta_imagem.headers.get("Content-Type", "").split(";")[0].strip().lower()
                            allowed_mimes = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/heic", "image/heif", "image/gif"}
                            if content_type in allowed_mimes:
                                img_bytes = resposta_imagem.content
                                if 1024 <= len(img_bytes) <= _MAX_BYTES_IMAGEM:
                                    ultimas_imagens.append((img_bytes, content_type))
                    except Exception:
                        pass

        resultados = []
        fontes_usadas = []

        for item in search_results:
            if len(resultados) >= fontes:
                break

            url = item.get("url", "")
            titulo = item.get("title", "")
            snippet = item.get("content", "") or item.get("raw_content", "")

            if not url:
                continue

            nome_fonte = _identificar_fonte(url)

            # Tenta extrair conteúdo da página diretamente (e capturar mais imagens)
            texto_pagina = _extrair_texto_pagina(url, max_chars_por_fonte=max_caracteres)

            if texto_pagina:
                bloco = f"🔍 **[{nome_fonte}]({url})** — {titulo}\n{texto_pagina}\n"
            elif snippet:
                snippet_limpo = snippet[:max_caracteres]
                bloco = f"🔍 **[{nome_fonte}]({url})** — {titulo}\n{snippet_limpo}\n"
            else:
                continue

            fontes_usadas.append(f"[{nome_fonte}]({url})")
            resultados.append(bloco)

        if not resultados:
            return None

        corpo = "\n---\n".join(resultados)

        if len(corpo) > max_resultado_total:
            corpo = corpo[:max_resultado_total] + "\n\n[...resultado truncado...]"

        rodape_fontes = "\n".join(f"  • {f}" for f in fontes_usadas)

        resultado_final = (
            f"📚 **Resultados da pesquisa (via Tavily)** — \"{busca}\" (Fontes: {len(resultados)}, Max Chars: {max_caracteres})\n\n"
            f"{corpo}\n\n"
            f"🔗 **Fontes consultadas:**\n{rodape_fontes}"
        )

        resultado_final += (
            "\n\n🎀 **Mensagem do Sistema para Ayla:**\n"
            "O(a) usuário(a) gosta de saber de onde as informações vieram! Por favor, cite de forma explícita, "
            "fofa e natural no seu texto final as fontes que foram consultadas (ex: 'Olha, vi no site G1 que...', "
            "'De acordo com o Toda Matéria...', etc.). Não deixe de falar o nome das fontes na sua resposta! 🩵"
        )

        if ultimas_imagens:
            resultado_final += f"\n\n⚡ **Imagens Anexadas das Fontes ({len(ultimas_imagens)}/10):**\n*Nota: Estas imagens foram injetadas diretamente na sua visão/contexto atual. Por favor, analise-as agora e incorpore suas observações na sua resposta final de forma natural.*"

        return resultado_final

    except Exception as e:
        print(f"⚠️ Tavily API falhou: {e}")
        return None


# ══════════════════════════════════════════════════════════
#  FALLBACK 2 — Wikipedia API
# ══════════════════════════════════════════════════════════

def _fallback_wikipedia(busca: str, fontes: int = 3, max_caracteres: int = 1000) -> str | None:
    """Busca na Wikipedia como fallback se os motores principais falharem."""
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
        for item in search_results[:fontes]:
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
                    results.append(f"🔍 **Wikipedia — {title}**\n{extract[:max_caracteres]}\n")

        if results:
            corpo = "\n---\n".join(results)
            resultado_wiki = (
                f"📚 **Resultados da pesquisa (via Wikipedia)** — \"{busca}\"\n\n"
                f"{corpo}\n\n"
                f"🔗 **Fonte:** Wikipedia (pt.wikipedia.org)"
            )
            resultado_wiki += (
                "\n\n🎀 **Mensagem do Sistema para Ayla:**\n"
                "O(a) usuário(a) gosta de saber de onde as informações vieram! Por favor, cite de forma explícita, "
                "fofa e natural no seu texto final as fontes que foram consultadas (neste caso, a Wikipedia!). "
                "Não deixe de falar o nome das fontes na sua resposta! 🩵"
            )
            return resultado_wiki
    except Exception:
        pass
    return None


# ══════════════════════════════════════════════════════════
#  FUNÇÃO PRINCIPAL — Pesquisa com Tavily, DDGS e Wikipedia
# ══════════════════════════════════════════════════════════

def pesquisar_na_internet(busca: str = None, query: str = None, termo: str = None, fontes: int = 5, max_caracteres: int = 1000, **kwargs) -> str:
    """
    Pesquisa informações na internet usando a API da Tavily como mecanismo principal,
    com DuckDuckGo Search (DDGS) como 1º fallback e Wikipedia como 2º fallback.
    Consultando de 0 a 10 fontes e absorvendo de 1 a 10000 caracteres por fonte.
    Retorna conteúdo extraído de cada página encontrada com as fontes identificadas.
    Tudo silenciosamente em segundo plano, sem abrir o navegador.
    """
    termo_busca = busca or query or termo or kwargs.get("q") or kwargs.get("search") or kwargs.get("text")
    if not termo_busca:
        return "⚠️ Nenhum termo de busca fornecido para pesquisar."
    busca = termo_busca

    try:
        fontes = max(0, min(10, int(fontes)))
    except (ValueError, TypeError):
        fontes = 5

    try:
        max_caracteres = max(1, min(10000, int(max_caracteres)))
    except (ValueError, TypeError):
        max_caracteres = 1000

    if fontes == 0:
        return f"ℹ️ Pesquisa para '{busca}' cancelada pois a quantidade de fontes solicitada foi 0."

    ultimas_imagens = ayla_state.ULTIMAS_IMAGENS_MODULO.get()
    if ultimas_imagens is None:
        ultimas_imagens = []
        ayla_state.ULTIMAS_IMAGENS_MODULO.set(ultimas_imagens)

    # ── 1. Mecanismo Principal: Tavily API ──
    resultado_tavily = _busca_tavily(busca, fontes=fontes, max_caracteres=max_caracteres)
    if resultado_tavily:
        return resultado_tavily

    # ── 2. Fallback 1: DDGS (DuckDuckGo Search) ──
    if DDGS_OK:
        try:
            ddgs = DDGS()
            resultados_busca = ddgs.text(busca, max_results=fontes + 3)

            if resultados_busca:
                resultados = []
                fontes_usadas = []

                for item in resultados_busca:
                    if len(resultados) >= fontes:
                        break

                    url = item.get("href", "")
                    titulo = item.get("title", "")
                    snippet = item.get("body", "")

                    if not url:
                        continue

                    nome_fonte = _identificar_fonte(url)

                    # Tenta extrair conteúdo mais completo da página
                    texto_pagina = _extrair_texto_pagina(url, max_chars_por_fonte=max_caracteres)

                    if texto_pagina:
                        bloco = f"🔍 **[{nome_fonte}]({url})** — {titulo}\n{texto_pagina}\n"
                    elif snippet:
                        snippet_limpo = snippet[:max_caracteres]
                        bloco = f"🔍 **[{nome_fonte}]({url})** — {titulo}\n{snippet_limpo}\n"
                    else:
                        continue

                    fontes_usadas.append(f"[{nome_fonte}]({url})")
                    resultados.append(bloco)

                if resultados:
                    max_resultado_total = min(30000, max(5000, fontes * max_caracteres + 2000))
                    corpo = "\n---\n".join(resultados)

                    if len(corpo) > max_resultado_total:
                        corpo = corpo[:max_resultado_total] + "\n\n[...resultado truncado...]"

                    rodape_fontes = "\n".join(f"  • {f}" for f in fontes_usadas)

                    resultado_final = (
                        f"📚 **Resultados da pesquisa (via DuckDuckGo)** — \"{busca}\" (Fontes: {len(resultados)}, Max Chars: {max_caracteres})\n\n"
                        f"{corpo}\n\n"
                        f"🔗 **Fontes consultadas:**\n{rodape_fontes}"
                    )

                    resultado_final += (
                        "\n\n🎀 **Mensagem do Sistema para Ayla:**\n"
                        "O(a) usuário(a) gosta de saber de onde as informações vieram! Por favor, cite de forma explícita, "
                        "fofa e natural no seu texto final as fontes que foram consultadas (ex: 'Olha, vi no site G1 que...', "
                        "'De acordo com o Toda Matéria...', etc.). Não deixe de falar o nome das fontes na sua resposta! 🩵"
                    )

                    if ultimas_imagens:
                        resultado_final += f"\n\n⚡ **Imagens Anexadas das Fontes ({len(ultimas_imagens)}/10):**\n*Nota: Estas imagens foram injetadas diretamente na sua visão/contexto atual. Por favor, analise-as agora e incorpore suas observações na sua resposta final de forma natural.*"
                    return resultado_final
        except Exception as e:
            print(f"⚠️ DDGS falhou, tentando fallback Wikipedia: {e}")

    # ── 3. Fallback 2: Wikipedia API ──
    resultado_wiki = _fallback_wikipedia(busca, fontes=fontes, max_caracteres=max_caracteres)
    if resultado_wiki:
        return resultado_wiki

    # ── Nenhuma fonte funcionou ──
    return f"ℹ️ Nenhum resultado encontrado para '{busca}'."


TOOL_MAP["pesquisar_na_internet"] = pesquisar_na_internet
FUNCTION_DECLARATIONS.append({
    "name": "pesquisar_na_internet",
    "description": "Busca informações na internet usando a API da Tavily como mecanismo principal (com fallbacks para DuckDuckGo e Wikipedia), consultando de 0 a 10 fontes e absorvendo de 1 a 10000 caracteres por fonte. Extrai e resume conteúdo relevante com imagens. Tudo em segundo plano sem abrir o navegador.",
    "parameters": {
        "type": "object",
        "properties": {
            "busca": {
                "type": "string",
                "description": "Termo ou pergunta a ser pesquisado na internet"
            },
            "fontes": {
                "type": "integer",
                "description": "Quantidade de fontes/páginas a pesquisar (de 0 a 10). Padrão: 5. Se 0, a pesquisa é cancelada."
            },
            "max_caracteres": {
                "type": "integer",
                "description": "Quantidade máxima de caracteres a absorver/extrair por fonte (de 1 a 10000). Padrão: 1000."
            }
        },
        "required": ["busca"]
    }
})
