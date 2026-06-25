def limpar_memoria_ram() -> str:
    try:
        cmd = "[System.GC]::Collect(); Clear-History"
        executar_comando(cmd)
        if PYPERCLIP_OK:
            try: pyperclip.copy('')
            except: pass
        return "✅ Joguei o lixo da memória RAM fora! Sistema limpinho."
    except Exception as e: return f"Erro: {e}"

TOOL_MAP["limpar_memoria_ram"] = limpar_memoria_ram
FUNCTION_DECLARATIONS.append({"name": "limpar_memoria_ram", "description": "Faz faxina rápida na RAM.", "parameters": {"type": "object", "properties": {}}})
