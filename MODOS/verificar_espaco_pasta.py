# verificar_espaco_pasta.py - Verificar espaço usado por uma pasta

def verificar_espaco_pasta(pasta):
    """Verifica o espaço total usado por uma pasta com detalhamento por tipo."""
    try:
        p = Path(pasta)
        if not p.exists():
            return f"❌ Pasta não encontrada: {pasta}"
        if not p.is_dir():
            return f"❌ O caminho não é uma pasta: {pasta}"

        def tamanho_legivel(tamanho_bytes):
            for unidade in ['B', 'KB', 'MB', 'GB', 'TB']:
                if tamanho_bytes < 1024.0:
                    return f"{tamanho_bytes:.2f} {unidade}"
                tamanho_bytes /= 1024.0
            return f"{tamanho_bytes:.2f} PB"

        tamanho_total = 0
        total_arquivos = 0
        total_pastas = 0
        extensoes = {}
        maiores_arquivos = []
        erros = 0

        for raiz, dirs, arquivos in os.walk(str(p)):
            total_pastas += len(dirs)
            for arquivo in arquivos:
                caminho_completo = os.path.join(raiz, arquivo)
                try:
                    tamanho = os.path.getsize(caminho_completo)
                    tamanho_total += tamanho
                    total_arquivos += 1

                    # Agrupar por extensão
                    ext = Path(arquivo).suffix.lower() if Path(arquivo).suffix else "(sem extensão)"
                    if ext not in extensoes:
                        extensoes[ext] = {"count": 0, "size": 0}
                    extensoes[ext]["count"] += 1
                    extensoes[ext]["size"] += tamanho

                    # Rastrear maiores arquivos
                    maiores_arquivos.append((caminho_completo, tamanho))
                except (PermissionError, OSError):
                    erros += 1

        # Ordenar maiores arquivos
        maiores_arquivos.sort(key=lambda x: x[1], reverse=True)
        top_5 = maiores_arquivos[:5]

        # Ordenar extensões por tamanho
        extensoes_ordenadas = sorted(extensoes.items(), key=lambda x: x[1]["size"], reverse=True)

        resultado = f"📁 **Análise de Espaço: {p.name}**\n"
        resultado += f"📍 `{p.resolve()}`\n\n"
        resultado += f"📏 **Tamanho total:** {tamanho_legivel(tamanho_total)} ({tamanho_total:,} bytes)\n"
        resultado += f"📄 **Total de arquivos:** {total_arquivos:,}\n"
        resultado += f"📂 **Total de subpastas:** {total_pastas:,}\n"
        if erros:
            resultado += f"⚠️ **Arquivos inacessíveis:** {erros}\n"

        # Breakdown por extensão (top 10)
        resultado += f"\n📊 **Distribuição por tipo** (top 10):\n"
        for ext, info in extensoes_ordenadas[:10]:
            pct = (info["size"] / tamanho_total * 100) if tamanho_total > 0 else 0
            barra = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            resultado += f"  `{ext:15s}` {barra} {pct:5.1f}% | {info['count']:,} arquivos | {tamanho_legivel(info['size'])}\n"

        # Top 5 maiores arquivos
        if top_5:
            resultado += f"\n🏆 **Top 5 maiores arquivos:**\n"
            for i, (caminho_arq, tam) in enumerate(top_5, 1):
                nome_arq = Path(caminho_arq).name
                caminho_rel = os.path.relpath(caminho_arq, str(p))
                resultado += f"  {i}. **{nome_arq}** - {tamanho_legivel(tam)}\n"
                resultado += f"     📍 `{caminho_rel}`\n"

        return resultado
    except PermissionError:
        return f"❌ Sem permissão para acessar: {pasta}"
    except Exception as e:
        return f"❌ Erro ao verificar espaço: {str(e)}"

TOOL_MAP["verificar_espaco_pasta"] = verificar_espaco_pasta

FUNCTION_DECLARATIONS.append({
    "name": "verificar_espaco_pasta",
    "description": "Verifica o espaço total usado por uma pasta recursivamente, com detalhamento por tipo de arquivo e lista dos 5 maiores arquivos.",
    "parameters": {
        "type": "object",
        "properties": {
            "pasta": {
                "type": "string",
                "description": "Caminho da pasta a ser analisada."
            }
        },
        "required": ["pasta"]
    }
})
