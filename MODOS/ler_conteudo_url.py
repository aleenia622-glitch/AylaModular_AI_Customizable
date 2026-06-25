import requests
from bs4 import BeautifulSoup
import re

# Garante compatibilidade se o arquivo for executado/importado individualmente
if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
}

def ler_conteudo_url(url: str) -> str:
    """
    Acessa uma URL (link da web) e extrai o texto principal para leitura em segundo plano.
    """
    url_limpa = url.strip()
    if not url_limpa.startswith("http://") and not url_limpa.startswith("https://"):
        return "⚠️ URL inválida. O link deve começar com http:// ou https://"
        
    try:
        r = requests.get(url_limpa, headers=_HEADERS, timeout=10, allow_redirects=True)
        if r.status_code != 200:
            return f"❌ Erro ao acessar o site. Código de status HTTP: {r.status_code}"

        soup = BeautifulSoup(r.text, "html.parser")

        # Remove scripts, estilos e elementos irrelevantes
        for tag in soup(["script", "style", "nav", "footer", "aside",
                         "header", "form", "noscript", "svg", "iframe"]):
            tag.decompose()

        # Tenta extrair do conteúdo principal primeiro
        container = soup.find("article") or soup.find("main")
        if not container:
            container = soup.find("body") or soup

        paragrafos = container.find_all("p")
        texto = "\n".join(p.get_text(separator=" ", strip=True) for p in paragrafos)
        
        # Limpa espaços excessivos
        texto = re.sub(r"[ \t]+", " ", texto)
        texto = re.sub(r"\n{3,}", "\n\n", texto).strip()

        if len(texto) < 50:
            # Fallback para pegar todo o texto visível caso não ache parágrafos
            texto = container.get_text(separator="\n", strip=True)
            texto = re.sub(r"[ \t]+", " ", texto)
            texto = re.sub(r"\n{3,}", "\n\n", texto).strip()

        if not texto:
            return "⚠️ Não consegui extrair nenhum texto legível desta URL."

        # Limite máximo de caracteres retornado para não sobrecarregar
        limite = 15000
        if len(texto) > limite:
            texto = texto[:limite] + f"\n\n[...Conteúdo truncado. Mostrados apenas os primeiros {limite} caracteres...]"

        return f"📖 **Conteúdo da URL:** ({url_limpa})\n\n{texto}"
    except Exception as e:
        return f"❌ Erro ao tentar ler o site: {e}"

TOOL_MAP["ler_conteudo_url"] = ler_conteudo_url
FUNCTION_DECLARATIONS.append({
    "name": "ler_conteudo_url",
    "description": "Acessa um link da internet (URL) fornecido pelo usuário e lê todo o conteúdo textual da página em segundo plano, sem abrir o navegador.",
    "parameters": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "A URL/link completo a ser lido (deve iniciar com http:// ou https://)"}
        },
        "required": ["url"]
    }
})
