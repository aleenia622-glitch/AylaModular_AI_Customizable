"""Consulta o uso de CPU, memória RAM e discos."""
from pathlib import Path
from ayla_paths import BASE_DIR
try: import psutil; PSUTIL_OK = True
except ImportError: PSUTIL_OK = False
from ayla_file_ops import executar_powershell

def info_sistema() -> str:
    if not PSUTIL_OK: return "Instale psutil para consultar CPU, RAM e disco."
    try:
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage(str(BASE_DIR.anchor))
        lines = [
            f"🖥️ CPU: {psutil.cpu_percent(interval=1)}%",
            f"🧠 RAM: {mem.used/1024**3:.1f}GB / {mem.total/1024**3:.1f}GB ({mem.percent}%)",
            f"💾 Disco do sistema: {disk.used/1024**3:.1f}GB usados / {disk.total/1024**3:.1f}GB ({disk.percent}%)"
        ]
        return "\n".join(lines)
    except Exception as e: return f"Erro: {e}"

TOOL_MAP["info_sistema"] = info_sistema
FUNCTION_DECLARATIONS.append({"name": "info_sistema", "description": "Exibe o uso atual de CPU (%), memória RAM (usada/total) e espaço do disco do sistema do computador da Usuario.", "parameters": {"type": "object", "properties": {}}})
