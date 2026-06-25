# encontrar_arquivos_duplicados.py - Encontra arquivos duplicados por hash MD5

def encontrar_arquivos_duplicados(pasta):
    """Encontra arquivos duplicados em uma pasta usando hash MD5."""
    try:
        import hashlib

        pasta = pasta.strip()

        if not os.path.exists(pasta):
            return f"❌ Pasta não encontrada: {pasta}"
        if not os.path.isdir(pasta):
            return f"❌ O caminho não é uma pasta: {pasta}"

        hashes = {}
        arquivos_processados = 0
        erros = 0

        for raiz, dirs, arquivos in os.walk(pasta):
            # Ignorar pastas ocultas
            dirs[:] = [d for d in dirs if not d.startswith('.')]

            for arquivo in arquivos:
                caminho = os.path.join(raiz, arquivo)
                try:
                    # Ignorar arquivos muito grandes (> 500MB)
                    tamanho = os.path.getsize(caminho)
                    if tamanho > 500 * 1024 * 1024:
                        continue
                    if tamanho == 0:
                        continue

                    hash_md5 = hashlib.md5()
                    with open(caminho, "rb") as f:
                        for bloco in iter(lambda: f.read(8192), b""):
                            hash_md5.update(bloco)

                    digest = hash_md5.hexdigest()
                    if digest not in hashes:
                        hashes[digest] = []
                    hashes[digest].append((caminho, tamanho))
                    arquivos_processados += 1
                except (PermissionError, OSError):
                    erros += 1
                    continue

        # Filtrar apenas duplicatas
        duplicatas = {h: files for h, files in hashes.items() if len(files) > 1}

        if not duplicatas:
            return f"✅ Nenhum arquivo duplicado encontrado!\n\n📄 Arquivos analisados: {arquivos_processados}"

        def formatar_tamanho(tamanho_bytes):
            if tamanho_bytes >= 1024 * 1024 * 1024:
                return f"{tamanho_bytes / (1024**3):.1f} GB"
            elif tamanho_bytes >= 1024 * 1024:
                return f"{tamanho_bytes / (1024**2):.1f} MB"
            elif tamanho_bytes >= 1024:
                return f"{tamanho_bytes / 1024:.1f} KB"
            else:
                return f"{tamanho_bytes} B"

        total_duplicatas = sum(len(files) - 1 for files in duplicatas.values())
        espaco_desperdicado = sum(files[0][1] * (len(files) - 1) for files in duplicatas.values())

        linhas = [
            "🔍 **Arquivos Duplicados Encontrados**",
            f"📁 Pasta: {pasta}",
            "",
            f"📄 Arquivos analisados: {arquivos_processados:,}",
            f"🔁 Grupos de duplicatas: {len(duplicatas)}",
            f"📋 Total de cópias extras: {total_duplicatas}",
            f"💾 Espaço desperdiçado: {formatar_tamanho(espaco_desperdicado)}",
        ]

        if erros > 0:
            linhas.append(f"⚠️ Arquivos com erro de acesso: {erros}")

        linhas.append("")

        # Mostrar até 10 grupos de duplicatas
        for i, (h, files) in enumerate(list(duplicatas.items())[:10], 1):
            tamanho_str = formatar_tamanho(files[0][1])
            linhas.append(f"📦 **Grupo {i}** ({tamanho_str} cada, {len(files)} cópias):")
            for caminho, _ in files:
                rel = os.path.relpath(caminho, pasta)
                linhas.append(f"  • {rel}")
            linhas.append("")

        if len(duplicatas) > 10:
            linhas.append(f"... e mais {len(duplicatas) - 10} grupos de duplicatas.")

        return "\n".join(linhas)
    except Exception as e:
        return f"❌ Erro ao buscar duplicatas: {e}"

TOOL_MAP["encontrar_arquivos_duplicados"] = encontrar_arquivos_duplicados

FUNCTION_DECLARATIONS.append({
    "name": "encontrar_arquivos_duplicados",
    "description": "Encontra arquivos duplicados em uma pasta usando hash MD5. Mostra grupos de arquivos idênticos.",
    "parameters": {
        "type": "object",
        "properties": {
            "pasta": {
                "type": "string",
                "description": "Caminho da pasta onde buscar arquivos duplicados."
            }
        },
        "required": ["pasta"]
    }
})
