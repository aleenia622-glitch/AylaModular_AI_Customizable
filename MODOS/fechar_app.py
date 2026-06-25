def fechar_app(nome_processo: str) -> str:
    try:
        nome = nome_processo.replace(".exe", "")
        subprocess.run(["powershell", "-NoProfile", "-Command", f"Stop-Process -Name '{nome}' -Force"], capture_output=True)
        return f"✅ Processo '{nome}' encerrado (se existia)."
    except Exception as e: return f"Erro: {e}"

TOOL_MAP["fechar_app"] = fechar_app
FUNCTION_DECLARATIONS.append({"name": "fechar_app", "description": "Fecha processo", "parameters": {"type": "object", "properties": {"nome_processo": {"type": "string"}}}})
