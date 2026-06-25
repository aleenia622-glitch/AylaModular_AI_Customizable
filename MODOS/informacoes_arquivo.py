# informacoes_arquivo.py - Informações detalhadas de arquivo/pasta

def informacoes_arquivo(caminho):
    """Retorna informações detalhadas sobre um arquivo ou pasta."""
    try:
        p = Path(caminho)
        if not p.exists():
            return f"❌ Caminho não encontrado: {caminho}"

        def tamanho_legivel(tamanho_bytes):
            for unidade in ['B', 'KB', 'MB', 'GB', 'TB']:
                if tamanho_bytes < 1024.0:
                    return f"{tamanho_bytes:.2f} {unidade}"
                tamanho_bytes /= 1024.0
            return f"{tamanho_bytes:.2f} PB"

        stat = p.stat()
        criado = datetime.datetime.fromtimestamp(stat.st_ctime).strftime("%d/%m/%Y %H:%M:%S")
        modificado = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%d/%m/%Y %H:%M:%S")
        acessado = datetime.datetime.fromtimestamp(stat.st_atime).strftime("%d/%m/%Y %H:%M:%S")
        somente_leitura = not os.access(str(p), os.W_OK)

        resultado = f"📋 **Informações: {p.name}**\n\n"
        resultado += f"📍 **Caminho completo:** `{p.resolve()}`\n"

        if p.is_file():
            resultado += f"📄 **Tipo:** Arquivo\n"
            resultado += f"📎 **Extensão:** {p.suffix if p.suffix else 'Sem extensão'}\n"
            resultado += f"📏 **Tamanho:** {tamanho_legivel(stat.st_size)} ({stat.st_size:,} bytes)\n"
        elif p.is_dir():
            resultado += f"📁 **Tipo:** Pasta\n"
            total_arquivos = 0
            total_pastas = 0
            tamanho_total = 0
            try:
                for item in p.rglob('*'):
                    if item.is_file():
                        total_arquivos += 1
                        try:
                            tamanho_total += item.stat().st_size
                        except (PermissionError, OSError):
                            pass
                    elif item.is_dir():
                        total_pastas += 1
            except PermissionError:
                pass
            resultado += f"📊 **Total de arquivos:** {total_arquivos:,}\n"
            resultado += f"📊 **Total de subpastas:** {total_pastas:,}\n"
            resultado += f"📏 **Tamanho total:** {tamanho_legivel(tamanho_total)} ({tamanho_total:,} bytes)\n"

        resultado += f"\n🕐 **Criado em:** {criado}\n"
        resultado += f"🕐 **Modificado em:** {modificado}\n"
        resultado += f"🕐 **Acessado em:** {acessado}\n"
        resultado += f"🔒 **Somente leitura:** {'Sim' if somente_leitura else 'Não'}\n"

        if p.is_file():
            resultado += f"📖 **Leitura:** {'✅' if os.access(str(p), os.R_OK) else '❌'}\n"
            resultado += f"✏️ **Escrita:** {'✅' if os.access(str(p), os.W_OK) else '❌'}\n"
            resultado += f"▶️ **Execução:** {'✅' if os.access(str(p), os.X_OK) else '❌'}\n"

        return resultado
    except PermissionError:
        return f"❌ Sem permissão para acessar: {caminho}"
    except Exception as e:
        return f"❌ Erro ao obter informações: {str(e)}"

TOOL_MAP["informacoes_arquivo"] = informacoes_arquivo

FUNCTION_DECLARATIONS.append({
    "name": "informacoes_arquivo",
    "description": "Retorna informações detalhadas sobre um arquivo ou pasta: nome, extensão, tamanho, datas, permissões e contagem de arquivos (para pastas).",
    "parameters": {
        "type": "object",
        "properties": {
            "caminho": {
                "type": "string",
                "description": "Caminho completo do arquivo ou pasta a ser analisado."
            }
        },
        "required": ["caminho"]
    }
})
