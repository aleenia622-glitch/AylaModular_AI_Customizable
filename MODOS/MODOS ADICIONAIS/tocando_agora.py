import asyncio

if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

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
        return "⚠️ Para ler qual música está tocando, a Mamãe precisa instalar o módulo `winsdk`. Peça para ela rodar `pip install winsdk` no terminal."
    except Exception as e:
        return f"❌ Não consegui ler a mídia atual: {e}"

def ver_midia_tocando() -> str:
    """
    Retorna o título e o artista da música/vídeo que está tocando no Windows.
    """
    try:
        # Pega o event loop atual e roda a função asyncrona
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

TOOL_MAP["ver_midia_tocando"] = ver_midia_tocando

FUNCTION_DECLARATIONS.append({
    "name": "ver_midia_tocando",
    "description": "Lê o sistema do Windows para descobrir exatamente qual é o nome da música ou vídeo que está tocando agora (e quem é o artista).",
    "parameters": {
        "type": "object",
        "properties": {}
    }
})
