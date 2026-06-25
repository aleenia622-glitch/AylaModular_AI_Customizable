def ajustar_brilho(porcentagem: int) -> str:
    val = max(0, min(100, porcentagem))
    cmd = f"Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | Invoke-CimMethod -MethodName WmiSetBrightness -Arguments @{{Timeout = 0; Brightness = {val}}}"
    executar_comando(cmd)
    return f"💡 Brilho do monitor ajustado para {val}%!"

TOOL_MAP["ajustar_brilho"] = ajustar_brilho
FUNCTION_DECLARATIONS.append({"name": "ajustar_brilho", "description": "Altera o brilho do monitor (0–100).", "parameters": {"type": "object", "properties": {"porcentagem": {"type": "integer"}}, "required": ["porcentagem"]}})
