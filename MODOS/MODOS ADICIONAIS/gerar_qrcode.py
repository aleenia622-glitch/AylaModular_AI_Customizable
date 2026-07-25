import sys
import os
from pathlib import Path

base_dir = Path(__file__).resolve().parents[2]
if str(base_dir) not in sys.path:
    sys.path.append(str(base_dir))
from datetime import datetime

def gerar_qrcode(texto: str) -> str:
    """
    Gera um QR Code fofinho com o texto ou link enviado!
    """
    try:
        texto_codificado = quote(texto)
        url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={texto_codificado}"
        
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return "❌ Ih... Não consegui gerar o QR Code. O servidor de QR Code está dodói? 🥺"
            
        PASTA_AYLA = base_dir / "Aylafotitos"
        PASTA_AYLA.mkdir(parents=True, exist_ok=True)
        from datetime import datetime as dt
        caminho = str(PASTA_AYLA / f"qrcode_{dt.now().strftime('%Y%m%d_%H%M%S')}.png")
        with open(caminho, "wb") as f:
            f.write(resp.content)
            
        ayla_state.ULTIMA_IMAGEM_GERADA.set(caminho)
        return f"📱 Prontinho! Criei um QR Code com muito carinho para você! Baixei em {caminho} e já vou te enviar! ✨"
    except Exception as e:
        return f"❌ Ayla teve um probleminha para gerar o QR Code: {e}"

TOOL_MAP["gerar_qrcode"] = gerar_qrcode
TOOL_MAP["gerar_qrcode"] = gerar_qrcode

if "gerar_qrcode" not in [fd["name"] for fd in FUNCTION_DECLARATIONS]:
    FUNCTION_DECLARATIONS.append({
        "name": "gerar_qrcode",
        "description": "Gera um QR Code a partir de um texto ou link e envia a imagem no chat.",
        "parameters": {
            "type": "object",
            "properties": {
                "texto": {"type": "string", "description": "O texto ou URL que será convertido em QR Code"}
            },
            "required": ["texto"]
        }
    })
