"""Executa comandos Bash no Linux ou PowerShell no Windows."""
from ayla_platform import shell_command
from ayla_paths import BASE_DIR
import subprocess
from ayla_verificacao import ResultadoFerramenta

def executar_comando(comando: str, timeout: int = 30) -> str:
    try:
        result = subprocess.run(shell_command(comando), cwd=BASE_DIR, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
        stdout, stderr = result.stdout.strip(), result.stderr.strip()
        if result.returncode != 0:
            return ResultadoFerramenta(
                f"Erro (código {result.returncode}): {stderr or stdout or 'Processo terminou com falha, sem mensagem.'}",
                'falhou', [f'Código de saída: {result.returncode}.'])
        return ResultadoFerramenta(stdout or "Comando executado (sem saída).", 'verificado',
            ['Processo terminou com código de saída 0.'],
            'Confirma apenas o término do processo; confira o estado de destino antes de afirmar que o objetivo foi atingido.')
    except subprocess.TimeoutExpired: return f"Timeout após {timeout}s."
    except Exception as e: return f"Erro: {e}"

TOOL_MAP["executar_comando"] = executar_comando
FUNCTION_DECLARATIONS.append({"name": "executar_comando", "description": "Executa comando Bash no Linux ou PowerShell no Windows", "parameters": {"type": "object", "properties": {"comando": {"type": "string",
                    "description": "Comando exato em Bash no Linux ou PowerShell no Windows."}}, "required": ["comando"]}})
