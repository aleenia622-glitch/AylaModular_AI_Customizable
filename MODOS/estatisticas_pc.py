# estatisticas_pc.py - Estatísticas detalhadas do PC usando psutil

def estatisticas_pc():
    """Retorna estatísticas detalhadas do PC: CPU, RAM, swap, uptime, processos."""
    try:
        if not PSUTIL_OK:
            return "❌ psutil não está disponível. Instale com: pip install psutil"

        import time

        # Uptime
        boot_time = datetime.datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.datetime.now() - boot_time
        dias = uptime.days
        horas = uptime.seconds // 3600
        minutos = (uptime.seconds % 3600) // 60

        # CPU
        cpu_count_logical = psutil.cpu_count(logical=True)
        cpu_count_physical = psutil.cpu_count(logical=False)
        cpu_freq = psutil.cpu_freq()
        cpu_percent = psutil.cpu_percent(interval=1)

        # RAM
        mem = psutil.virtual_memory()
        ram_total = mem.total / (1024 ** 3)
        ram_used = mem.used / (1024 ** 3)
        ram_percent = mem.percent

        # Swap
        swap = psutil.swap_memory()
        swap_total = swap.total / (1024 ** 3)
        swap_used = swap.used / (1024 ** 3)
        swap_percent = swap.percent

        # Top 3 processos por uso de memória
        processos = []
        for proc in psutil.process_iter(['pid', 'name', 'memory_percent', 'cpu_percent']):
            try:
                info = proc.info
                if info['memory_percent'] is not None:
                    processos.append(info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        processos.sort(key=lambda p: p.get('memory_percent', 0), reverse=True)
        top3 = processos[:3]

        # Formatação
        linhas = [
            "🖥️ **Estatísticas do PC**",
            "",
            f"⏰ **Uptime:** {dias}d {horas}h {minutos}m (ligado desde {boot_time.strftime('%d/%m/%Y %H:%M')})",
            "",
            "🔧 **CPU:**",
            f"  • Núcleos físicos: {cpu_count_physical}",
            f"  • Núcleos lógicos: {cpu_count_logical}",
        ]

        if cpu_freq:
            linhas.append(f"  • Frequência: {cpu_freq.current:.0f} MHz (max: {cpu_freq.max:.0f} MHz)")

        linhas.extend([
            f"  • Uso atual: {cpu_percent}%",
            "",
            "💾 **RAM:**",
            f"  • Total: {ram_total:.1f} GB",
            f"  • Em uso: {ram_used:.1f} GB ({ram_percent}%)",
            f"  • Livre: {(ram_total - ram_used):.1f} GB",
            "",
            "💿 **Swap:**",
            f"  • Total: {swap_total:.1f} GB",
            f"  • Em uso: {swap_used:.1f} GB ({swap_percent}%)",
            "",
            "📊 **Top 3 Processos (por uso de RAM):**",
        ])

        for i, proc in enumerate(top3, 1):
            nome = proc.get('name', 'N/A')
            pid = proc.get('pid', 'N/A')
            mem_pct = proc.get('memory_percent', 0)
            linhas.append(f"  {i}. {nome} (PID: {pid}) — RAM: {mem_pct:.1f}%")

        return "\n".join(linhas)
    except Exception as e:
        return f"❌ Erro ao obter estatísticas: {e}"

TOOL_MAP["estatisticas_pc"] = estatisticas_pc

FUNCTION_DECLARATIONS.append({
    "name": "estatisticas_pc",
    "description": "Exibe estatísticas detalhadas do PC: uptime, CPU, RAM, swap e top 3 processos.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": []
    }
})
