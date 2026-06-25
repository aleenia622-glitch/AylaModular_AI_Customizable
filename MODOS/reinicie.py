import os
import sys
import subprocess
import time
import threading

# Garante compatibilidade se o arquivo for executado/importado individualmente
if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

def reinicie() -> str:
    """
    Reinicia a Ayla: abre um novo terminal executando o script Ayla.py e encerra o processo atual.
    """
    try:
        # Pega o caminho absoluto do script principal em execução (Ayla.py)
        script_path = os.path.abspath(sys.argv[0])
        cwd = os.path.dirname(script_path)
        
        # Abre um novo terminal cmd e executa o script python Ayla.py
        subprocess.Popen(["cmd", "/c", "start", "python", script_path], cwd=cwd, shell=True)
        
        # Executa o encerramento do processo atual em uma thread separada com atraso de 1.5s
        # para dar tempo da Ayla enviar a mensagem de confirmação para o Discord/Terminal
        def self_destruct():
            time.sleep(1.5)
            os._exit(0)
            
        threading.Thread(target=self_destruct, daemon=True).start()
        
        return "🔄 Reiniciando meu corpinho! Estou abrindo uma nova janelinha de terminal e fechando esta sessão. Já volto! <:ayla_feliz:1508877425394712727>"
    except Exception as e:
        return f"❌ Erro ao tentar reiniciar: {e}"

# Registro no TOOL_MAP e nas declarações da Ayla
TOOL_MAP["reinicie"] = reinicie
FUNCTION_DECLARATIONS.append({
    "name": "reinicie",
    "description": "Reinicia a Ayla, abrindo um novo terminal com a execução do bot e encerrando o processo atual.",
    "parameters": {"type": "object", "properties": {}}
})
