def info_sistema() -> str:
    if not PSUTIL_OK: return executar_comando("Get-CimInstance Win32_OperatingSystem | Select FreePhysicalMemory,TotalVisibleMemorySize | Format-List")
    try:
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\")
        lines = [
            f"🖥️ CPU: {psutil.cpu_percent(interval=1)}%",
            f"🧠 RAM: {mem.used/1024**3:.1f}GB / {mem.total/1024**3:.1f}GB ({mem.percent}%)",
            f"💾 Disco C: {disk.used/1024**3:.1f}GB usados / {disk.total/1024**3:.1f}GB ({disk.percent}%)"
        ]
        return "\n".join(lines)
    except Exception as e: return f"Erro: {e}"

TOOL_MAP["info_sistema"] = info_sistema
FUNCTION_DECLARATIONS.append({"name": "info_sistema", "description": "Info CPU/RAM/Disco", "parameters": {"type": "object", "properties": {}}})
