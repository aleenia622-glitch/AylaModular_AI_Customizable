"""Captura uma imagem de uma janela pelo título."""
from ayla_platform import capture_screen, list_windows
import re
from ayla_paths import project_path
from datetime import datetime as _file_datetime
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import ayla_state
def screenshot_janela(titulo):
    try:
        windows = [w for w in list_windows() if titulo.casefold() in w['title'].casefold()]
        if not windows:
            return f'Nenhuma janela encontrada: {titulo}'
        window = windows[0]
        region = window['region']
        if region[2] <= 0 or region[3] <= 0:
            return 'Janela minimizada ou com dimensões inválidas. Restaure-a antes de capturar.'
        screenshot = capture_screen(region=region)
        folder = project_path('Aylafotitos')
        folder.mkdir(parents=True, exist_ok=True)
        title = re.sub(r'[^\w .-]', '_', titulo)[:50]
        path = folder / f"janela_{title}_{_file_datetime.now():%Y%m%d_%H%M%S_%f}.png"
        screenshot.save(path)
        ayla_state.ULTIMA_IMAGEM_GERADA.set(str(path))
        return f"📸 Janela: {window['title']}\nSalva em: {path}"
    except Exception as exc:
        return f'Erro ao capturar janela: {exc}'

TOOL_MAP["screenshot_janela"] = screenshot_janela

FUNCTION_DECLARATIONS.append({
    "name": "screenshot_janela",
    "description": "Captura um screenshot de uma janela específica pelo título e salva na pasta Aylafotitos.",
    "parameters": {
        "type": "object",
        "properties": {
            "titulo": {
                "type": "string",
                "description": "Título (ou parte do título) da janela a ser capturada."
            }
        },
        "required": ["titulo"]
    }
})
