import sys
import os
import subprocess
import tempfile
from pathlib import Path

base_dir = Path(__file__).resolve().parents[2]
if str(base_dir) not in sys.path:
    sys.path.append(str(base_dir))
import ayla_state

if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

def enviar_notificacao_windows(titulo: str = "🩵 Ayla", mensagem: str = "") -> str:
    """
    Envia uma notificação visual nativa (Toast Notification) no canto da tela do Windows 11.
    """
    tit = (titulo or "🩵 Ayla").strip()
    msg = (mensagem or "Oi Mamãe! Lembrete da Ayla!").strip()

    # Tenta usar win10toast / plyer primeiro se instalado
    try:
        from win10toast import ToastNotifier
        toaster = ToastNotifier()
        toaster.show_toast(tit, msg, duration=5, threaded=True)
        return f"🔔 Notificação enviada para o Windows: '{tit} - {msg}'"
    except Exception:
        pass

    try:
        from plyer import notification
        notification.notify(title=tit, message=msg, app_name="Ayla", timeout=5)
        return f"🔔 Notificação enviada para o Windows: '{tit} - {msg}'"
    except Exception:
        pass

    # Fallback nativo via script PowerShell
    try:
        tit_esc = tit.replace("'", "''")
        msg_esc = msg.replace("'", "''")
        ps_code = (
            "Add-Type -AssemblyName System.Windows.Forms\n"
            "$n = New-Object System.Windows.Forms.NotifyIcon\n"
            "$n.Icon = [System.Drawing.SystemIcons]::Information\n"
            f"$n.BalloonTipTitle = '{tit_esc}'\n"
            f"$n.BalloonTipText = '{msg_esc}'\n"
            "$n.Visible = $true\n"
            "$n.ShowBalloonTip(5000)\n"
            "Start-Sleep -Seconds 5\n"
        )
        tf = tempfile.NamedTemporaryFile(suffix=".ps1", delete=False, mode="w", encoding="utf-8")
        tf.write(ps_code)
        tf.close()

        subprocess.Popen(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", tf.name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        )
        return f"🔔 Notificação nativa enviada para a área de trabalho do Windows: '{tit} - {msg}'"
    except Exception as e:
        return f"⚠️ Erro ao enviar notificação no Windows: {e}"

TOOL_MAP["enviar_notificacao_windows"] = enviar_notificacao_windows
FUNCTION_DECLARATIONS.append({
    "name": "enviar_notificacao_windows",
    "description": "Exibe um aviso/notificação pop-up nativo no canto da tela do Windows 11. Use para mandar avisos visuais no computador.",
    "parameters": {
        "type": "object",
        "properties": {
            "titulo": {"type": "string", "description": "Título da notificação. Padrão: '🩵 Ayla'"},
            "mensagem": {"type": "string", "description": "Mensagem ou texto do aviso a ser exibido no Windows."}
        },
        "required": ["mensagem"]
    }
})
