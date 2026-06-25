# listar_processos_top.py - Top processes by memory usage

def listar_processos_top(quantidade=10):
    """Lista os top N processos por uso de memória."""
    try:
        if not PSUTIL_OK:
            return "Erro: psutil não está disponível."
        quantidade = int(quantidade)
        processos = []
        for proc in psutil.process_iter(['pid', 'name', 'memory_info', 'cpu_percent']):
            try:
                info = proc.info
                mem_mb = info['memory_info'].rss / (1024 * 1024) if info['memory_info'] else 0
                processos.append({
                    'pid': info['pid'],
                    'name': info['name'] or 'N/A',
                    'mem_mb': mem_mb,
                    'cpu': info['cpu_percent'] or 0.0
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        processos.sort(key=lambda x: x['mem_mb'], reverse=True)
        top = processos[:quantidade]
        if not top:
            return "Nenhum processo encontrado."
        linhas = [f"🔝 Top {len(top)} processos por uso de memória:\n"]
        linhas.append(f"{'#':<4} {'Nome':<30} {'PID':<8} {'Memória (MB)':<14} {'CPU %':<8}")
        linhas.append("-" * 68)
        for i, p in enumerate(top, 1):
            linhas.append(f"{i:<4} {p['name']:<30} {p['pid']:<8} {p['mem_mb']:<14.1f} {p['cpu']:<8.1f}")
        total_mem = sum(p['mem_mb'] for p in top)
        linhas.append(f"\n📊 Memória total dos top {len(top)}: {total_mem:.1f} MB")
        return "\n".join(linhas)
    except Exception as e:
        return f"Erro ao listar processos: {e}"

TOOL_MAP["listar_processos_top"] = listar_processos_top

FUNCTION_DECLARATIONS.append({
    "name": "listar_processos_top",
    "description": "Lista os processos que mais consomem memória no sistema, mostrando nome, PID, uso de memória em MB e porcentagem de CPU.",
    "parameters": {
        "type": "object",
        "properties": {
            "quantidade": {
                "type": "integer",
                "description": "Quantidade de processos a listar (padrão: 10)."
            }
        },
        "required": []
    }
})
