import sys
import os
sys.path.append(r"C:\Users\Aleenia\Documents\AI")
import ayla_state
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
    Acessa uma URL (link da web) e extrai o texto principal para leitura em segundo plano,
    além de baixar na memória e anexar até 10 imagens da página no mesmo turno da conversa.
    """
    url_limpa = url.strip()
    if not url_limpa.startswith("http://") and not url_limpa.startswith("https://"):
        return "⚠️ URL inválida. O link deve começar com http:// ou https://"
        
    try:
        r = requests.get(url_limpa, headers=_HEADERS, timeout=10, allow_redirects=True)
        if r.status_code != 200:
            return f"❌ Erro ao acessar o site. Código de status HTTP: {r.status_code}"

        soup = BeautifulSoup(r.text, "html.parser")

        # --- Extração e Download de Imagens ---
        from urllib.parse import urljoin
        import mimetypes
        import sys

        # Tenta carregar a classe de tipos do google-genai
        try:
            from google.genai import types as genai_types
        except ImportError:
            genai_types = globals().get("genai_types")

        img_tags = soup.find_all("img")
        img_urls = []
        for img in img_tags:
            src = img.get("src")
            if not src:
                continue
            abs_src = urljoin(url_limpa, src)
            if abs_src.startswith("http://") or abs_src.startswith("https://"):
                if abs_src not in img_urls:
                    img_urls.append(abs_src)
            if len(img_urls) >= 10:
                break

        ultimas_imagens = ayla_state.ULTIMAS_IMAGENS_MODULO.get()
        if ultimas_imagens is None:
            ultimas_imagens = []
            ayla_state.ULTIMAS_IMAGENS_MODULO.set(ultimas_imagens)

        imagens_baixadas_info = []

        for idx, img_url in enumerate(img_urls):
            try:
                img_resp = requests.get(img_url, headers=_HEADERS, timeout=5)
                if img_resp.status_code != 200:
                    continue
                content_type = img_resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
                allowed_mimes = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/heic", "image/heif", "image/gif"}
                if content_type not in allowed_mimes:
                    continue

                img_bytes = img_resp.content
                if len(img_bytes) < 1024:  # Ignora pixels de rastreamento/ícones decorativos minúsculos
                    continue
                
                # Guess extension
                ext = mimetypes.guess_extension(content_type) or ".png"
                if ext == ".jpe":
                    ext = ".jpg"
                
                ultimas_imagens.append((img_bytes, content_type))
                imagens_baixadas_info.append(f"🖼️ Imagem {len(imagens_baixadas_info)+1}: {img_url}")
            except Exception as e:
                print(f"⚠️ Erro ao baixar imagem da URL {img_url}: {e}")


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
            texto = "[Nenhum conteúdo textual legível encontrado]"

        # Limite máximo de caracteres retornado para não sobrecarregar
        limite = 15000
        if len(texto) > limite:
            texto = texto[:limite] + f"\n\n[...Conteúdo truncado. Mostrados apenas os primeiros {limite} caracteres...]"

        resultado = f"📖 **Conteúdo da URL:** ({url_limpa})\n\n{texto}"
        
        if imagens_baixadas_info:
            resumo_imgs = "\n".join(imagens_baixadas_info)
            resultado += f"\n\n⚡ **Imagens Anexadas Automaticamente ({len(imagens_baixadas_info)}/10):**\n{resumo_imgs}\n\n*Nota: Estas imagens foram injetadas diretamente na sua visão/contexto atual. Por favor, analise-as agora e incorpore suas observações na sua resposta final de forma natural.*"
        
        return resultado
    except Exception as e:
        return f"❌ Erro ao tentar ler o site: {e}"

TOOL_MAP["ler_conteudo_url"] = ler_conteudo_url
FUNCTION_DECLARATIONS.append({
    "name": "ler_conteudo_url",
    "description": "Acessa um link da internet (URL) fornecido pelo usuário, lê todo o conteúdo textual da página em segundo plano e extrai e anexa automaticamente até 10 imagens presentes na página diretamente ao seu contexto para análise visual imediata.",
    "parameters": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "A URL/link completo a ser lido (deve iniciar com http:// ou https://)"}
        },
        "required": ["url"]
    }
})
