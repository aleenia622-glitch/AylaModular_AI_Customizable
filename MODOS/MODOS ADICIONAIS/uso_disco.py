# uso_disco.py - Disk usage summary for all drives

def uso_disco():
    """Retorna o uso de disco de todas as unidades encontradas."""
    try:
        drives = ['C:', 'D:', 'E:', 'F:']
        resultado = []
        for drive in drives:
            path = drive + '\\'
            if os.path.exists(path):
                try:
                    usage = shutil.disk_usage(path)
                    total_gb = usage.total / (1024 ** 3)
                    used_gb = usage.used / (1024 ** 3)
                    free_gb = usage.free / (1024 ** 3)
                    percent = (usage.used / usage.total) * 100
                    resultado.append(
                        f"💾 {drive}\n"
                        f"  Total: {total_gb:.2f} GB\n"
                        f"  Usado: {used_gb:.2f} GB ({percent:.1f}%)\n"
                        f"  Livre: {free_gb:.2f} GB"
                    )
                except Exception as e:
                    resultado.append(f"💾 {drive} - Erro ao ler: {e}")
        if not resultado:
            return "Nenhuma unidade de disco encontrada."
        return "\n\n".join(resultado)
    except Exception as e:
        return f"Erro ao verificar uso de disco: {e}"

TOOL_MAP["uso_disco"] = uso_disco

FUNCTION_DECLARATIONS.append({
    "name": "uso_disco",
    "description": "Mostra o uso de disco (total, usado, livre) de todas as unidades de disco encontradas (C:, D:, E:, F:).",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": []
    }
})
