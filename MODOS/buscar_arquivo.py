
def buscar_arquivo(pasta: str, padrao: str) -> str:
    """Busca arquivos por padrão de nome em uma árvore de diretórios."""
    try:
        import fnmatch

        pasta_path = Path(pasta)
        if not pasta_path.exists():
            return f"❌ Pasta não encontrada: {pasta}"
        if not pasta_path.is_dir():
            return f"❌ O caminho não aponta para uma pasta: {pasta}"

        resultados = []
        limite = 50

        for raiz, dirs, arquivos in os.walk(pasta_path):
            for nome in arquivos:
                if fnmatch.fnmatch(nome.lower(), padrao.lower()):
                    caminho_completo = Path(raiz) / nome
                    try:
                        tamanho = caminho_completo.stat().st_size
                    except OSError:
                        tamanho = 0
                    resultados.append((caminho_completo, tamanho))
                    if len(resultados) >= limite:
                        break
            if len(resultados) >= limite:
                break

        if not resultados:
            return f"🔍 Nenhum arquivo encontrado com o padrão '{padrao}' em {pasta}"

        linhas = [
            f"🔍 **Busca de Arquivos**\n",
            f"📂 **Pasta:** {pasta}",
            f"🔎 **Padrão:** {padrao}",
            f"📝 **Resultados encontrados:** {len(resultados)}"
        ]

        if len(resultados) >= limite:
            linhas.append(f"⚠️ Limite de {limite} resultados atingido.\n")
        else:
            linhas.append("")

        for caminho, tamanho in resultados:
            # Formatar tamanho
            if tamanho < 1024:
                tam_str = f"{tamanho} B"
            elif tamanho < 1024 * 1024:
                tam_str = f"{tamanho / 1024:.1f} KB"
            elif tamanho < 1024 * 1024 * 1024:
                tam_str = f"{tamanho / (1024*1024):.1f} MB"
            else:
                tam_str = f"{tamanho / (1024*1024*1024):.1f} GB"
            linhas.append(f"📄 `{caminho.name}` ({tam_str})\n   📂 {caminho.parent}")

        return "\n".join(linhas)
    except Exception as e:
        return f"❌ Erro ao buscar arquivos: {e}"

TOOL_MAP["buscar_arquivo"] = buscar_arquivo

FUNCTION_DECLARATIONS.append({
    "name": "buscar_arquivo",
    "description": "Busca arquivos por padrão de nome (ex: '*.jpg', '*.txt', 'relatorio*') em uma pasta e subpastas. Retorna até 50 resultados com tamanhos.",
    "parameters": {
        "type": "object",
        "properties": {
            "pasta": {
                "type": "string",
                "description": "Caminho da pasta raiz para iniciar a busca."
            },
            "padrao": {
                "type": "string",
                "description": "Padrão de nome do arquivo (ex: '*.jpg', '*.txt', 'relatorio*', '*.py')."
            }
        },
        "required": ["pasta", "padrao"]
    }
})
