import subprocess
from pathlib import Path

# Garante compatibilidade se o arquivo for executado/importado individualmente
if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

def abrir_desistalador() -> str:
    """
    Abre o aplicativo Desistalador.exe localizado na pasta raiz do bot.
    """
    try:
        caminho = Path(__file__).resolve().parent.parent / "Desistalador.exe"
        if caminho.exists():
            subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", f"Start-Process '{str(caminho)}'"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return "✅ Abrindo o desistalador!"
        else:
            return "⚠️ O arquivo Desistalador.exe não foi encontrado na pasta raiz do bot."
    except Exception as e:
        return f"❌ Erro ao abrir o desistalador: {e}"

TOOL_MAP["abrir_desistalador"] = abrir_desistalador
FUNCTION_DECLARATIONS.append({
    "name": "abrir_desistalador",
    "description": "Abre o desinstalador (Desistalador.exe) na pasta raiz do bot.",
    "parameters": {
        "type": "object",
        "properties": {}
    }
})
