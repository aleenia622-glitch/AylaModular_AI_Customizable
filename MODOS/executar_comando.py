def executar_comando(comando: str, timeout: int = 30) -> str:
    try:
        result = subprocess.run(["powershell", comando], capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
        stdout, stderr = result.stdout.strip(), result.stderr.strip()
        if result.returncode != 0 and stderr: return f"Erro (código {result.returncode}): {stderr}\n{stdout}".strip()
        return stdout or "Comando executado (sem saída)."
    except subprocess.TimeoutExpired: return f"Timeout após {timeout}s."
    except Exception as e: return f"Erro: {e}"

TOOL_MAP["executar_comando"] = executar_comando
FUNCTION_DECLARATIONS.append({"name": "executar_comando", "description": "Executa comando PowerShell", "parameters": {"type": "object", "properties": {"comando": {"type": "string"}}}})
