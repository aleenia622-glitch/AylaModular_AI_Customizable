# ping_site.py - Check if a website is online

def ping_site(url):
    """Verifica se um site está online e retorna status e tempo de resposta."""
    try:
        from datetime import datetime
        url = str(url).strip()
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        inicio = datetime.now()
        response = requests.get(url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        tempo = (datetime.now() - inicio).total_seconds()
        status = response.status_code
        if 200 <= status < 300:
            emoji = "✅"
            estado = "Online"
        elif 300 <= status < 400:
            emoji = "↪️"
            estado = "Redirecionamento"
        elif 400 <= status < 500:
            emoji = "⚠️"
            estado = "Erro do cliente"
        else:
            emoji = "❌"
            estado = "Erro do servidor"
        resultado = (
            f"{emoji} {estado}\n\n"
            f"🌐 URL: {url}\n"
            f"📊 Status Code: {status}\n"
            f"⏱️ Tempo de resposta: {tempo:.3f}s\n"
            f"📦 Tamanho da resposta: {len(response.content)} bytes"
        )
        return resultado
    except requests.exceptions.Timeout:
        return f"⏰ Timeout: o site {url} não respondeu em 10 segundos."
    except requests.exceptions.ConnectionError:
        return f"❌ Erro de conexão: não foi possível conectar a {url}."
    except requests.exceptions.MissingSchema:
        return f"❌ URL inválida: {url}"
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Erro ao verificar site: {e}"

TOOL_MAP["ping_site"] = ping_site

FUNCTION_DECLARATIONS.append({
    "name": "ping_site",
    "description": "Verifica se um site está online, retornando o status code HTTP, tempo de resposta e tamanho da resposta.",
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL do site a verificar (ex: google.com ou https://google.com)."
            }
        },
        "required": ["url"]
    }
})
