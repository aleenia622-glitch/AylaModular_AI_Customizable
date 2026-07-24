def ler_janelas_abertas() -> str:
    return executar_comando('Get-Process | Where-Object {$_.MainWindowTitle} | Select-Object -ExpandProperty MainWindowTitle')

TOOL_MAP["ler_janelas_abertas"] = ler_janelas_abertas
FUNCTION_DECLARATIONS.append({"name": "ler_janelas_abertas", "description": "Vê as janelas abertas no PC.", "parameters": {"type": "object", "properties": {}}})
