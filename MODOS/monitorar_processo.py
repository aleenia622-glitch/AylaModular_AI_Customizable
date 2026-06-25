
def monitorar_processo(nome_processo):
    """Monitora um processo específico pelo nome usando psutil."""
    try:
        if not PSUTIL_OK:
            return "❌ psutil não está disponível neste sistema."

        encontrados = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info', 'num_threads', 'create_time', 'cmdline']):
            try:
                if nome_processo.lower() in proc.info['name'].lower():
                    info = proc.info
                    mem = info['memory_info']
                    mem_mb = mem.rss / (1024 * 1024) if mem else 0
                    try:
                        inicio = datetime.datetime.fromtimestamp(info['create_time']).strftime('%d/%m/%Y %H:%M:%S')
                    except Exception:
                        inicio = "Desconhecido"
                    try:
                        cmdline = ' '.join(info['cmdline']) if info['cmdline'] else "N/A"
                    except Exception:
                        cmdline = "N/A"
                    encontrados.append(
                        f"🔹 **{info['name']}**\n"
                        f"   PID: {info['pid']}\n"
                        f"   CPU: {info['cpu_percent']:.1f}%\n"
                        f"   Memória: {mem_mb:.1f} MB\n"
                        f"   Threads: {info['num_threads']}\n"
                        f"   Iniciado em: {inicio}\n"
                        f"   Comando: {cmdline[:200]}"
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        if not encontrados:
            return f"🔍 Nenhum processo encontrado com o nome '{nome_processo}'."

        header = f"📊 **Processos encontrados para '{nome_processo}'** ({len(encontrados)} resultado(s)):\n\n"
        return header + "\n\n".join(encontrados)
    except Exception as e:
        return f"❌ Erro ao monitorar processo: {e}"

TOOL_MAP["monitorar_processo"] = monitorar_processo

FUNCTION_DECLARATIONS.append({
    "name": "monitorar_processo",
    "description": "Monitora um processo específico pelo nome, retornando PID, uso de CPU, memória, threads, hora de início e linha de comando.",
    "parameters": {
        "type": "object",
        "properties": {
            "nome_processo": {
                "type": "string",
                "description": "Nome (ou parte do nome) do processo a ser monitorado."
            }
        },
        "required": ["nome_processo"]
    }
})
