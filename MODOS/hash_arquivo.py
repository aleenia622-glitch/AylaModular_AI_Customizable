
def hash_arquivo(caminho: str, algoritmo: str = "sha256") -> str:
    """Calcula o hash de um arquivo usando o algoritmo especificado."""
    try:
        import hashlib

        caminho_arq = Path(caminho)
        if not caminho_arq.exists():
            return f"❌ Arquivo não encontrado: {caminho}"
        if not caminho_arq.is_file():
            return f"❌ O caminho não aponta para um arquivo: {caminho}"

        algoritmo = algoritmo.lower().strip()
        algoritmos_validos = {"md5", "sha1", "sha256"}
        if algoritmo not in algoritmos_validos:
            return f"❌ Algoritmo inválido. Use: {', '.join(sorted(algoritmos_validos))}"

        h = hashlib.new(algoritmo)
        tamanho_arquivo = caminho_arq.stat().st_size

        with open(caminho_arq, "rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                h.update(chunk)

        hash_hex = h.hexdigest()

        # Formatar tamanho
        if tamanho_arquivo < 1024:
            tam_str = f"{tamanho_arquivo} bytes"
        elif tamanho_arquivo < 1024 * 1024:
            tam_str = f"{tamanho_arquivo / 1024:.2f} KB"
        elif tamanho_arquivo < 1024 * 1024 * 1024:
            tam_str = f"{tamanho_arquivo / (1024*1024):.2f} MB"
        else:
            tam_str = f"{tamanho_arquivo / (1024*1024*1024):.2f} GB"

        return (
            f"🔑 **Hash do Arquivo**\n\n"
            f"📁 **Arquivo:** {caminho_arq.name}\n"
            f"📂 **Caminho:** {caminho_arq}\n"
            f"📏 **Tamanho:** {tam_str}\n"
            f"🔧 **Algoritmo:** {algoritmo.upper()}\n"
            f"🔒 **Hash:** `{hash_hex}`"
        )
    except Exception as e:
        return f"❌ Erro ao calcular hash: {e}"

TOOL_MAP["hash_arquivo"] = hash_arquivo

FUNCTION_DECLARATIONS.append({
    "name": "hash_arquivo",
    "description": "Calcula o hash (checksum) de um arquivo usando MD5, SHA1 ou SHA256.",
    "parameters": {
        "type": "object",
        "properties": {
            "caminho": {
                "type": "string",
                "description": "Caminho completo do arquivo."
            },
            "algoritmo": {
                "type": "string",
                "description": "Algoritmo de hash: 'md5', 'sha1' ou 'sha256'. Padrão: 'sha256'.",
                "enum": ["md5", "sha1", "sha256"]
            }
        },
        "required": ["caminho"]
    }
})
