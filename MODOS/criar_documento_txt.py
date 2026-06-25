"""
📄 Módulo: Criação de Documentos de Texto (.txt)
Permite que a Ayla crie documentos de texto simples para a Alêenia.
"""

def criar_documento_txt(nome_arquivo: str, conteudo: str) -> str:
    """
    Cria um arquivo de texto simples (.txt) com o conteúdo fornecido.
    
    Args:
        nome_arquivo (str): Nome do arquivo (ex: 'anotacoes.txt').
        conteudo (str): O texto que deve ser inserido no documento.
    """
    try:
        from pathlib import Path

        nome_original = (nome_arquivo or "").strip()
        if (
            not nome_original
            or Path(nome_original).is_absolute()
            or any(parte == ".." for parte in Path(nome_original).parts)
            or "/" in nome_original
            or "\\" in nome_original
        ):
            return "⚠️ Use apenas o nome do arquivo, sem caminho, subpastas ou '..'."

        # Garante que o nome do arquivo termine com .txt
        nome_arquivo = nome_original
        if not nome_arquivo.lower().endswith(".txt"):
            nome_arquivo += ".txt"

        # Define a pasta de saída
        projeto_raiz = Path(__file__).resolve().parent.parent
        pasta_documentos = projeto_raiz / "DocumentosCriados"
        pasta_documentos.mkdir(parents=True, exist_ok=True)
        
        caminho_final = pasta_documentos / nome_arquivo

        # Cria e escreve no arquivo com codificação UTF-8
        with open(caminho_final, "w", encoding="utf-8") as f:
            f.write(conteudo)

        return (
            f"📄 Documento de Texto (.txt) criado com sucesso!\n"
            f"📁 Arquivo: {nome_arquivo}\n"
            f"📍 Salvo em: {caminho_final}"
        )

    except Exception as e:
        return f"❌ Erro ao criar o documento de texto: {e}"

# ── Registro da ferramenta ──
TOOL_MAP["criar_documento_txt"] = criar_documento_txt
FUNCTION_DECLARATIONS.append({
    "name": "criar_documento_txt",
    "description": (
        "Cria um documento de texto simples (.txt) com o conteúdo fornecido. "
        "Ideal para salvar notas rápidas, rascunhos, listas de tarefas ou textos simples."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "nome_arquivo": {
                "type": "string",
                "description": "O nome do arquivo a ser criado (ex: 'anotacoes.txt')."
            },
            "conteudo": {
                "type": "string",
                "description": "O texto completo que deve constar no arquivo."
            }
        },
        "required": ["nome_arquivo", "conteudo"]
    }
})
