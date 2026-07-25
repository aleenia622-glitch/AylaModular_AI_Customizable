"""
📄 Módulo: Criação de Documentos Word (.docx)
Permite que a Ayla crie documentos de texto formatados para o(a) usuário(a).
"""

def criar_documento_docx(nome_arquivo: str, conteudo: str) -> str:
    """
    Cria um documento do Word (.docx) com o conteúdo fornecido.
    
    Args:
        nome_arquivo (str): Nome do arquivo (ex: 'trabalho.docx').
        conteudo (str): O texto que deve ser inserido no documento.
    """
    try:
        import docx # python-docx
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

        # Garante que o nome do arquivo termine com .docx
        nome_arquivo = nome_original
        if not nome_arquivo.lower().endswith(".docx"):
            nome_arquivo += ".docx"

        # Define a pasta de saída (DocumentosCriados)
        pasta_documentos = Path(r"C:\Users\Aleenia\Documents\AI\DocumentosCriados")
        pasta_documentos.mkdir(parents=True, exist_ok=True)
        
        caminho_final = pasta_documentos / nome_arquivo

        # Cria o documento
        doc = docx.Document()
        
        # Adiciona o conteúdo. 
        # Se o conteúdo tiver quebras de linha, cria parágrafos separados.
        for linha in conteudo.splitlines():
            doc.add_paragraph(linha)

        # Salva o arquivo
        doc.save(str(caminho_final))

        # Sinaliza para a Ayla enviar o arquivo no Discord
        import ayla_state
        ayla_state.ULTIMA_IMAGEM_GERADA.set(str(caminho_final))

        return (
            f"📄 Documento Word criado com sucesso!\n"
            f"📁 Arquivo: {nome_arquivo}\n"
            f"📍 Salvo em: {caminho_final} e enviado no Discord!"
        )

    except ImportError:
        return (
            "⚠️ A biblioteca `python-docx` não está instalada!\n"
            "Por favor, execute: `pip install python-docx` para que eu possa criar documentos Word."
        )
    except Exception as e:
        return f"❌ Erro ao criar o documento Word: {e}"

# ── Registro da ferramenta ──
if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

TOOL_MAP["criar_documento_docx"] = criar_documento_docx

# Se já houver uma declaração idêntica, remove-a antes de registrar
for i, fd in enumerate(FUNCTION_DECLARATIONS):
    if fd["name"] == "criar_documento_docx":
        FUNCTION_DECLARATIONS.pop(i)
        break

FUNCTION_DECLARATIONS.append({
    "name": "criar_documento_docx",
    "description": (
        "Cria um documento de texto do Microsoft Word (.docx) com o conteúdo fornecido. "
        "Ideal para criar trabalhos, cartas, listas ou qualquer documento formal. O arquivo é salvo em DocumentosCriados e enviado no Discord."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "nome_arquivo": {
                "type": "string",
                "description": "O nome do arquivo a ser criado (ex: 'relatorio.docx')."
            },
            "conteudo": {
                "type": "string",
                "description": "O texto completo que deve constar no documento."
            }
        },
        "required": ["nome_arquivo", "conteudo"]
    }
})
