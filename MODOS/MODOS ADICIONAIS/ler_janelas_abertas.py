"""Lista os títulos das janelas abertas no computador."""
from ayla_platform import IS_WINDOWS, list_windows
from ayla_file_ops import executar_powershell

def ler_janelas_abertas() -> str:
    if not IS_WINDOWS:
        try:
            return '\n'.join(w['title'] for w in list_windows()) or 'Nenhuma janela encontrada.'
        except Exception as exc:
            return f'Não foi possível listar janelas: {exc}'
    return executar_powershell('Get-Process | Where-Object {$_.MainWindowTitle} | Select-Object -ExpandProperty MainWindowTitle')

TOOL_MAP["ler_janelas_abertas"] = ler_janelas_abertas
FUNCTION_DECLARATIONS.append({"name": "ler_janelas_abertas", "description": "Vê as janelas abertas no PC.", "parameters": {"type": "object", "properties": {}}})
