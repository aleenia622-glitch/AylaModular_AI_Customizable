"""Controla a reprodução de mídia e consulta o que está tocando no computador."""
from ayla_platform import IS_WINDOWS, run_command
import sys
import asyncio


if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []


def controlar_midia(acao: str) -> str:
    """
    Controla a mídia do sistema (pausar, reproduzir, avançar, retroceder).
    """
    acao = acao.lower().strip()
    
    try:
        if not IS_WINDOWS:
            actions = {'play': 'play', 'pause': 'pause', 'playpause': 'play-pause',
                       'next': 'next', 'avançar': 'next', 'proxima': 'next', 'pular': 'next',
                       'prev': 'previous', 'previous': 'previous', 'voltar': 'previous', 'anterior': 'previous'}
            if acao not in actions:
                return 'Ação desconhecida. Use play, pause, playpause, next ou prev.'
            run_command(['playerctl', actions[acao]])
            return '✅ Comando enviado ao reprodutor.'
        import pyautogui
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


async def _obter_midia_async():
    try:
        from winsdk.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as MediaManager
        
        # Pega a sessão principal de mídia
        manager = await MediaManager.request_async()
        session = manager.get_current_session()
        
        if session is None:
            return "🎵 Não tem nenhuma música ou vídeo tocando no momento no Windows."
            
        media_props = await session.try_get_media_properties_async()
        app_id = session.source_app_user_model_id
        
        titulo = media_props.title or "Desconhecido"
        artista = media_props.artist or "Desconhecido"
        
        return f"🎵 **Tocando agora no PC:**\n• **Música/Vídeo:** {titulo}\n• **Artista/Canal:** {artista}\n• **Aplicativo:** {app_id}"
    except ImportError:
        return "⚠️ Para ler qual música está tocando, a usuario precisa instalar o módulo `winsdk`. Peça para ela rodar `pip install winsdk` no terminal."
    except Exception as e:
        return f"❌ Não consegui ler a mídia atual: {e}"


def ver_midia_tocando() -> str:
    """
    Retorna o título e o artista da música/vídeo que está tocando no Windows.
    """
    try:
        if not IS_WINDOWS:
            return run_command(['playerctl', 'metadata', '--format', '{{title}} — {{artist}} ({{playerName}})'])
        # Pega o event loop atual e roda a função assíncrona
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import threading
            resultado = ["Erro"]
            
            def run_in_new_loop():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                resultado[0] = new_loop.run_until_complete(_obter_midia_async())
                new_loop.close()
                
            t = threading.Thread(target=run_in_new_loop)
            t.start()
            t.join()
            return resultado[0]
        else:
            return loop.run_until_complete(_obter_midia_async())
    except Exception as e:
        return f"❌ Erro na ponte async/sync: {e}"


TOOL_MAP["controlar_midia"] = controlar_midia
TOOL_MAP["ver_midia_tocando"] = ver_midia_tocando
TOOL_MAP["tocando_agora"] = ver_midia_tocando

FUNCTION_DECLARATIONS.append({
    "name": "controlar_midia",
    "description": "Controla a música ou vídeo que está tocando no computador da Usuario. Você pode pausar, dar play, pular para a próxima ou voltar para a anterior.",
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

FUNCTION_DECLARATIONS.append({
    "name": "ver_midia_tocando",
    "description": "Lê o sistema do sistema para descobrir exatamente qual é o nome da música ou vídeo que está tocando agora (e quem é o artista).",
    "parameters": {
        "type": "object",
        "properties": {}
    }
})
