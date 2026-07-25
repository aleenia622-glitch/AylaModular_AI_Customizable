import sys
import os
from pathlib import Path

base_dir = Path(__file__).resolve().parents[2]
if str(base_dir) not in sys.path:
    sys.path.append(str(base_dir))
import ayla_state
import io
import time
import base64
import winsound
import subprocess
from pathlib import Path

try: import pyautogui; PYAUTOGUI_OK = True
except ImportError: PYAUTOGUI_OK = False

def notificar_windows(titulo: str = "📸 Ayla - Visão de Tela", mensagem: str = "Print da tela capturado com sucesso!"):
    try:
        winsound.MessageBeep(winsound.MB_ICONASTERISK)
    except Exception:
        pass

    try:
        ps_script = f"""
        [reflection.assembly]::loadwithpartialname('System.Windows.Forms') | Out-Null
        $n = New-Object System.Windows.Forms.NotifyIcon
        $n.Icon = [System.Drawing.SystemIcons]::Information
        $n.BalloonTipTitle = '{titulo}'
        $n.BalloonTipText = '{mensagem}'
        $n.Visible = $True
        $n.ShowBalloonTip(3000)
        """
        b64 = base64.b64encode(ps_script.encode('utf-16le')).decode('utf-8')
        subprocess.Popen(['powershell', '-NoProfile', '-NonInteractive', '-EncodedCommand', b64], creationflags=0x08000000)
    except Exception as e:
        print(f"⚠️ Erro ao notificar no Windows: {e}")

def ver_tela_atual() -> str:
    if not PYAUTOGUI_OK: return "pyautogui não instalado."
    try:
        print("Va ate o que voce quer que eu veja em 5 segundos.....")
        for segundos_restantes in range(5, 0, -1):
            print(f"👀 Olhando a tela em {segundos_restantes}...")
            time.sleep(1)

        # Captura o print diretamente na memória RAM (sem salvar no disco)
        img = pyautogui.screenshot()
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        img_bytes = buffer.getvalue()
        
        # Notificação sonora e visual do Windows quando o print for concluído
        notificar_windows("📸 Ayla - Visão de Tela", "Print da tela capturado com sucesso!")

        # Envia o print da tela no fluxo principal do Gemini para que ele analise no contexto correto
        ultimas_imagens = ayla_state.ULTIMAS_IMAGENS_MODULO.get()
        if ultimas_imagens is None:
            ultimas_imagens = []
            ayla_state.ULTIMAS_IMAGENS_MODULO.set(ultimas_imagens)
        ultimas_imagens.append((img_bytes, "image/png"))

        return "✅ Olhinhos ativados! Vi a sua tela atual. Analise-a com atenção e responda ao usuário."
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Erro: {e}"

TOOL_MAP["ver_tela_atual"] = ver_tela_atual
FUNCTION_DECLARATIONS.append({"name": "ver_tela_atual", "description": "Tira print da tela do PC e analisa.", "parameters": {"type": "object", "properties": {}}})
