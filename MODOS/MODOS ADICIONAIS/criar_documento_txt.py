"""
📄 Módulo: Criação de Documentos de Texto (.txt)
Permite que a Ayla crie documentos de texto simples para o(a) usuário(a).
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

        # Define a pasta de saída (DocumentosCriados)
        pasta_documentos = Path(__file__).resolve().parents[2] / "DocumentosCriados"
        pasta_documentos.mkdir(parents=True, exist_ok=True)
        
        caminho_final = pasta_documentos / nome_arquivo

        # Cria e escreve no arquivo com codificação UTF-8
        with open(caminho_final, "w", encoding="utf-8") as f:
            f.write(conteudo)

        # Sinaliza para a Ayla enviar o arquivo no Discord
        import ayla_state
        ayla_state.ULTIMA_IMAGEM_GERADA.set(str(caminho_final))

        return (
            f"📄 Documento de Texto (.txt) criado com sucesso!\n"
            f"📁 Arquivo: {nome_arquivo}\n"
            f"📍 Salvo em: {caminho_final} e enviado no Discord!"
        )

    except Exception as e:
        return f"❌ Erro ao criar o documento de texto: {e}"

# ── Registro da ferramenta ──
if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

TOOL_MAP["criar_documento_txt"] = criar_documento_txt

# Se já houver uma declaração idêntica, remove-a antes de registrar
for i, fd in enumerate(FUNCTION_DECLARATIONS):
    if fd["name"] == "criar_documento_txt":
        FUNCTION_DECLARATIONS.pop(i)
        break

FUNCTION_DECLARATIONS.append({
    "name": "criar_documento_txt",
    "description": (
        "Cria um documento de texto simples (.txt) com o conteúdo fornecido. "
        "Ideal para salvar notas rápidas, rascunhos, listas de tarefas ou textos simples. O arquivo é salvo em DocumentosCriados e enviado no Discord."
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
