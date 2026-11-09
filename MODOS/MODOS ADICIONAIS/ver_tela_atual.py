"""Captura e analisa a tela atual do computador."""
from pathlib import Path
from ayla_platform import capture_screen, notify
import sys
import os
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import ayla_state
import io
import time
import base64
import subprocess
from pathlib import Path


def notificar_windows(titulo="📸 Ayla - Visão de Tela", mensagem="Print da tela capturado com sucesso!"):
    notify(titulo, mensagem)

def ver_tela_atual() -> str:
    try:
        print("Va ate o que voce quer que eu veja em 5 segundos.....")
        for segundos_restantes in range(5, 0, -1):
            print(f"👀 Olhando a tela em {segundos_restantes}...")
            time.sleep(1)

        # Captura o print diretamente na memória RAM (sem salvar no disco)
        img = capture_screen()
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        img_bytes = buffer.getvalue()
        
        # Notificação sonora e visual do Windows quando o print for concluído
        notificar_windows("📸 Ayla - Visão de Tela", "Print da tela capturado com sucesso!")

        # Envia o print da tela no fluxo principal da Z.ai para análise no contexto correto
        ultimas_imagens = ayla_state.ULTIMAS_IMAGENS_MODULO.get()
        if ultimas_imagens is None:
            ultimas_imagens = []
            ayla_state.ULTIMAS_IMAGENS_MODULO.set(ultimas_imagens)
        ultimas_imagens.append((img_bytes, "image/png"))

        return "✅ Olhinhos ativados! Vi a sua tela atual. Analise-a com atenção e responda à Usuario."
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Erro: {e}"

TOOL_MAP["ver_tela_atual"] = ver_tela_atual
FUNCTION_DECLARATIONS.append({"name": "ver_tela_atual", "description": "Tira print da tela do PC e analisa.", "parameters": {"type": "object", "properties": {}}})
