def controle_volume(acao: str, valor: int = 50) -> str:
    if not PYCAW_OK: return "pycaw não instalado para controle exato."
    try:
        import comtypes
        comtypes.CoInitialize()
        try:
            devices = AudioUtilities.GetSpeakers()
            if hasattr(devices, "EndpointVolume"):
                vol_ctrl = devices.EndpointVolume
            else:
                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                vol_ctrl = cast(interface, POINTER(IAudioEndpointVolume))
            if acao == "mute": vol_ctrl.SetMute(1, None)
            elif acao == "unmute": vol_ctrl.SetMute(0, None)
            elif acao == "definir":
                vol_ctrl.SetMute(0, None)
                vol_ctrl.SetMasterVolumeLevelScalar(max(0.0, min(1.0, valor / 100.0)), None)
            return f"✅ Volume: {acao} {valor if acao=='definir' else ''}"
        finally:
            comtypes.CoUninitialize()
    except Exception as e: return f"Erro pycaw: {e}"

TOOL_MAP["controle_volume"] = controle_volume
FUNCTION_DECLARATIONS.append({"name": "controle_volume", "description": "Volume de áudio (mute/unmute/definir)", "parameters": {"type": "object", "properties": {"acao": {"type": "string"}, "valor": {"type": "integer"}}}})
