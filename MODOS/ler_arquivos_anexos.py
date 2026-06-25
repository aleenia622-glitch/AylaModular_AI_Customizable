import io
import asyncio
from pathlib import Path

# Garante compatibilidade se o arquivo for executado/importado individualmente
if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

def ler_arquivos_anexos() -> str:
    """
    Baixa e lê o conteúdo em texto de qualquer arquivo ou documento (como .txt, .py, .pdf, .json, .csv)
    que o usuário tenha enviado em anexo na mensagem atual do Discord.
    """
    # Recupera o contexto da mensagem ativa do bot
    ctx = globals().get("CONTEXTO_ATIVO")
    if not ctx:
        return "⚠️ Nenhum contexto de mensagem ou interação ativo no momento."

    # Verifica se há anexos no objeto de mensagem ou interação
    attachments = []
    if hasattr(ctx, "attachments") and ctx.attachments:
        attachments = ctx.attachments
    elif hasattr(ctx, "message") and ctx.message and ctx.message.attachments:
        attachments = ctx.message.attachments

    if not attachments:
        return "⚠️ Nenhum arquivo anexado foi encontrado na mensagem atual."

    extensoes_texto = {
        ".txt", ".md", ".py", ".json", ".js", ".ts", ".html", ".css", 
        ".csv", ".ini", ".env", ".xml", ".yaml", ".yml", ".log", 
        ".cfg", ".bat", ".sh", ".properties", ".toml"
    }

    # Como ler_arquivos_anexos é síncrona (chamada via thread do Gemini),
    # mas a API do Discord (read) é assíncrona, precisamos rodar o download de forma síncrona
    # usando asyncio.run_coroutine_threadsafe no loop do bot.
    global_bot = globals().get("bot")
    if not global_bot or not hasattr(global_bot, "loop"):
        return "⚠️ O bot não está pronto para baixar anexos."

    resultados = []

    for anexo in attachments:
        nome_arquivo = anexo.filename
        ext = Path(nome_arquivo).suffix.lower()

        # Baixa os bytes do anexo de forma thread-safe
        futuro = asyncio.run_coroutine_threadsafe(anexo.read(), global_bot.loop)
        try:
            arq_bytes = futuro.result(timeout=30)
        except Exception as e:
            resultados.append(f"❌ **{nome_arquivo}**: Falha ao baixar o arquivo ({e})")
            continue

        # Processamento de PDF
        if ext == ".pdf":
            try:
                import pypdf
                reader = pypdf.PdfReader(io.BytesIO(arq_bytes))
                texto_pdf = ""
                for i, page in enumerate(reader.pages):
                    texto_pdf += f"--- Página {i+1} ---\n" + (page.extract_text() or "") + "\n"
                texto_pdf = texto_pdf.strip()
                if not texto_pdf:
                    texto_pdf = "[PDF sem texto legível ou escaneado/imagem]"
                resultados.append(f"📄 **{nome_arquivo} (PDF)**:\n{texto_pdf}")
            except ImportError:
                resultados.append(
                    f"⚠️ **{nome_arquivo} (PDF)**: Para ler PDFs, é necessário instalar a biblioteca pypdf no computador (rode: `pip install pypdf`)."
                )
            except Exception as e:
                resultados.append(f"❌ **{nome_arquivo} (PDF)**: Erro ao extrair texto ({e})")
            continue

        # Processamento de arquivos de texto e código
        if ext in extensoes_texto or (anexo.content_type and anexo.content_type.startswith("text/")):
            try:
                texto_conteudo = arq_bytes.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    texto_conteudo = arq_bytes.decode("latin-1")
                except Exception as e:
                    resultados.append(f"❌ **{nome_arquivo}**: Erro de decodificação ({e})")
                    continue
            
            # Limita tamanho para não estourar contexto excessivamente se for gigante
            limite = 15000
            if len(texto_conteudo) > limite:
                texto_conteudo = texto_conteudo[:limite] + f"\n\n[...Conteúdo muito longo, truncado em {limite} caracteres...]"
            
            resultados.append(f"📝 **{nome_arquivo}**:\n{texto_conteudo}")
            continue

        # Se for imagem ou mídia
        if anexo.content_type and (
            anexo.content_type.startswith("image/") or 
            anexo.content_type.startswith("audio/") or 
            anexo.content_type.startswith("video/")
        ):
            resultados.append(f"🖼️ **{nome_arquivo}**: Este é um arquivo de mídia (imagem/áudio/vídeo) e já foi enviado para a visão/audição principal do Gemini.")
            continue

        resultados.append(f"⚠️ **{nome_arquivo}**: Tipo de arquivo não suportado para leitura textual direta.")

    return "\n\n================================\n\n".join(resultados)

TOOL_MAP["ler_arquivos_anexos"] = ler_arquivos_anexos
FUNCTION_DECLARATIONS.append({
    "name": "ler_arquivos_anexos",
    "description": "Lê o conteúdo em formato texto de arquivos e documentos (como planilhas .csv, textos .txt, documentos .pdf ou códigos de programação .py, .json) que o usuário anexou/enviou na mensagem atual do Discord.",
    "parameters": {
        "type": "object",
        "properties": {}
    }
})
