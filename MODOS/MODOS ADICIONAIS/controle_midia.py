import sys
import pyautogui

if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

def controlar_midia(acao: str) -> str:
    """
    Controla a mídia do Windows (pausar, reproduzir, avançar, retroceder).
    """
    acao = acao.lower().strip()
    
    try:
        if acao in ["play", "pause", "playpause"]:
            pyautogui.press('playpause')
            return "▶️/⏸️ Apertei o botão de Play/Pause na mídia do PC!"
        elif acao in ["next", "avançar", "proxima", "pular"]:
            pyautogui.press('nexttrack')
            return "⏭️ Apertei o botão para avançar para a próxima música/vídeo!"
        elif acao in ["prev", "previous", "voltar", "anterior"]:
            pyautogui.press('prevtrack')
            return "⏮️ Apertei o botão para voltar para a música/vídeo anterior!"
        else:
            return "⚠️ Ação desconhecida. Use 'play', 'pause', 'next' ou 'prev'."
    except Exception as e:
        return f"❌ Erro ao tentar controlar a mídia: {e}"

TOOL_MAP["controlar_midia"] = controlar_midia

FUNCTION_DECLARATIONS.append({
    "name": "controlar_midia",
    "description": "Controla a música ou vídeo que está tocando no computador da Alêenia. Você pode pausar, dar play, pular para a próxima ou voltar para a anterior.",
    "parameters": {
        "type": "object",
        "properties": {
            "acao": {
                "type": "string",
                "enum": ["playpause", "next", "prev"],
                "description": "Qual ação você quer tomar: 'playpause' (para pausar ou dar play), 'next' (para pular pra próxima), 'prev' (para voltar a anterior)."
            }
        },
        "required": ["acao"]
    }
})
