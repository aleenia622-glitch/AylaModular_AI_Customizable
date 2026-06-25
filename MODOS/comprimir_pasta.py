
def comprimir_pasta(pasta: str, destino: str = "") -> str:
    """Comprime uma pasta inteira em um arquivo ZIP."""
    try:
        pasta_path = Path(pasta)
        if not pasta_path.exists():
            return f"❌ Pasta não encontrada: {pasta}"
        if not pasta_path.is_dir():
            return f"❌ O caminho não aponta para uma pasta: {pasta}"

        if destino:
            destino_path = Path(destino)
            # Remover extensão .zip se o usuário incluiu, pois make_archive adiciona
            if destino_path.suffix.lower() == ".zip":
                destino_base = str(destino_path.with_suffix(""))
            else:
                destino_base = str(destino_path)
        else:
            destino_base = str(pasta_path.parent / pasta_path.name)

        arquivo_zip = shutil.make_archive(destino_base, 'zip', pasta_path)
        zip_path = Path(arquivo_zip)
        tamanho = zip_path.stat().st_size

        # Formatar tamanho
        if tamanho < 1024:
            tam_str = f"{tamanho} bytes"
        elif tamanho < 1024 * 1024:
            tam_str = f"{tamanho / 1024:.2f} KB"
        elif tamanho < 1024 * 1024 * 1024:
            tam_str = f"{tamanho / (1024*1024):.2f} MB"
        else:
            tam_str = f"{tamanho / (1024*1024*1024):.2f} GB"

        # Contar arquivos na pasta
        num_arquivos = sum(1 for _ in pasta_path.rglob("*") if _.is_file())

        return (
            f"📦 **Pasta Comprimida com Sucesso!**\n\n"
            f"📂 **Pasta original:** {pasta_path}\n"
            f"📁 **Arquivos comprimidos:** {num_arquivos}\n"
            f"💾 **Arquivo ZIP:** {zip_path}\n"
            f"📏 **Tamanho do ZIP:** {tam_str}"
        )
    except Exception as e:
        return f"❌ Erro ao comprimir pasta: {e}"

TOOL_MAP["comprimir_pasta"] = comprimir_pasta

FUNCTION_DECLARATIONS.append({
    "name": "comprimir_pasta",
    "description": "Comprime uma pasta inteira em um arquivo ZIP.",
    "parameters": {
        "type": "object",
        "properties": {
            "pasta": {
                "type": "string",
                "description": "Caminho completo da pasta a ser comprimida."
            },
            "destino": {
                "type": "string",
                "description": "Caminho de destino para o arquivo ZIP (opcional). Se não informado, cria na mesma localização da pasta."
            }
        },
        "required": ["pasta"]
    }
})
