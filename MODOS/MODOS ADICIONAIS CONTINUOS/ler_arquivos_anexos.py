"""Lê documentos e planilhas anexados e transcreve áudios anexados."""
from ayla_paths import project_path
import sys
import os
import io
import re
import zipfile
import asyncio
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
try:
    import ayla_state
except ImportError:
    ayla_state = None

if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

_EXTENSOES_DOCUMENTO = {
    ".txt", ".md", ".py", ".json", ".js", ".ts", ".html", ".css",
    ".csv", ".ini", ".env", ".xml", ".yaml", ".yml", ".log",
    ".cfg", ".bat", ".sh", ".properties", ".toml", ".pdf", ".docx",
    ".xlsx", ".pptx", ".doc", ".xls", ".ppt", ".rtf", ".sql", ".c",
    ".cpp", ".h", ".java"
}

_EXTENSOES_AUDIO = {
    ".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".opus", ".webm", ".wma", ".aiff", ".mp2", ".3gp", ".m4r"
}

def transcrever_audio_groq(arq_bytes: bytes, filename: str) -> str:
    """
    Transcreve um arquivo de áudio usando o modelo whisper-large-v3 da Groq API.
    """
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    
    if not groq_key:
        global_bot = globals().get("bot")
        if global_bot and hasattr(global_bot, "groq_api_key") and global_bot.groq_api_key:
            groq_key = str(global_bot.groq_api_key).strip()

    if not groq_key:
        env_path = project_path('.env')
        if env_path.exists():
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    if line.startswith("GROQ_API_KEY="):
                        groq_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
            except Exception:
                pass

    if not groq_key:
        return "❌ [Erro Groq Whisper]: Chave de API do Groq (GROQ_API_KEY) não encontrada nas configurações."

    try:
        import requests
        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        headers = {"Authorization": f"Bearer {groq_key}"}
        
        from whisper_audio import prepare_whisper_audio
        arq_bytes = prepare_whisper_audio(arq_bytes, filename)
        if not arq_bytes:
            return f"🎙️ **Áudio ({filename})**: Nenhuma fala detectada; áudio não enviado ao Whisper."
        safe_filename = "audio.wav"
        
        files = {"file": (safe_filename, arq_bytes)}
        data = {
            "model": "whisper-large-v3",
            "language": "pt",
            "response_format": "json",
            "prompt": "Se houver apenas silêncio, ruído, música de fundo ou estática de microfone, ignore totalmente e retorne vazio. Não transcreva legendas fantasma.",
            "temperature": 0.0
        }
        
        response = requests.post(url, headers=headers, files=files, data=data, timeout=30)
        if response.status_code == 200:
            res_json = response.json()
            text = res_json.get("text", "").strip()
            
            # Filtro de alucinações do Whisper quando há silêncio
            if text:
                test_text = text.lower().strip()
                hallucination_patterns = [
                    r"^\W*obrigad[ao]\W*$",
                    r"legenda(s)? por\b",
                    r"legendado por\b",
                    r"subtitles? by\b",
                    r"thank you for watching\b",
                    r"obrigado por assistir\b",
                    r"inscreva-se no canal\b",
                    r"acesse o nosso site\b",
                    r"acesse o site\b",
                    r"visite o nosso site\b",
                    r"visite o site\b",
                    r"opusdei\.pt",
                    r"\bopus dei\b",
                    r"amara\.org",
                    r"legendas\.tv",
                    r"sônia ruberti",
                    r"sonia ruberti",
                    r"deixe seu like\b",
                    r"deixe o seu like\b",
                    r"um grande abraço e até a próxima\b",
                    r"um abraço e até a próxima\b",
                    r"assista ao próximo vídeo\b",
                    r"assistir a este vídeo\b",
                    r"assistir ao vídeo\b",
                    r"deixe nos comentários\b",
                    r"deixe seu comentário\b",
                    r"não transcreva\b",
                    r"legendas fantasma\b"
                ]
                for pattern in hallucination_patterns:
                    if re.search(pattern, test_text):
                        if len(text) < 120:
                            text = ""
                        break

            if text:
                return f"🎙️ **Transcrição do Áudio ({filename}) via Groq Whisper (whisper-large-v3)**:\n\"{text}\""
            else:
                return f"🎙️ **Áudio ({filename})**: O áudio foi processado pelo Groq Whisper, mas parece conter apenas silêncio ou ruído sem fala inteligível."
        else:
            return f"❌ Erro ao transcrever áudio via Groq Whisper (Status {response.status_code}): {response.text}"
    except Exception as e:
        return f"❌ Erro de conexão com a API do Groq Whisper ao tentar transcrever {filename}: {e}"

def extrair_texto_pdf(arq_bytes: bytes) -> str:
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(arq_bytes))
        paginas = [p.extract_text() or "" for p in reader.pages]
        res = "\n".join([f"--- Página {i+1} ---\n{p}" for i, p in enumerate(paginas) if p.strip()])
        if res.strip(): return res.strip()
    except Exception:
        pass
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(arq_bytes))
        paginas = [p.extract_text() or "" for p in reader.pages]
        res = "\n".join([f"--- Página {i+1} ---\n{p}" for i, p in enumerate(paginas) if p.strip()])
        if res.strip(): return res.strip()
    except Exception:
        pass

    try:
        text_matches = re.findall(rb"\(([^\(\)]+)\)\s*TJ|\(([^\(\)]+)\)\s*Tj", arq_bytes)
        strings = []
        for m in text_matches:
            s = (m[0] or m[1]).decode("latin-1", errors="ignore").strip()
            if len(s) > 2:
                strings.append(s)
        if strings:
            return "--- Texto extraído brutamente do PDF ---\n" + "\n".join(strings)
    except Exception:
        pass
    return "[PDF sem texto legível ou em formato escaneado/imagem]"

def extrair_texto_docx(arq_bytes: bytes) -> str:
    try:
        import docx
        doc = docx.Document(io.BytesIO(arq_bytes))
        p_texts = [p.text for p in doc.paragraphs if p.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                row_txt = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                if row_txt:
                    p_texts.append(row_txt)
        if p_texts: return "\n".join(p_texts)
    except Exception:
        pass

    try:
        with zipfile.ZipFile(io.BytesIO(arq_bytes)) as zf:
            if "word/document.xml" in zf.namelist():
                xml_content = zf.read("word/document.xml")
                root = ET.fromstring(xml_content)
                texts = [node.text for node in root.iter() if node.tag.endswith("t") and node.text]
                if texts: return "".join(texts)
    except Exception:
        pass

    return "[Não foi possível extrair texto do documento Word (.docx)]"

def extrair_texto_xlsx(arq_bytes: bytes) -> str:
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(arq_bytes), data_only=True)
        linhas = []
        for sheetname in wb.sheetnames:
            sheet = wb[sheetname]
            linhas.append(f"--- Aba: {sheetname} ---")
            for row in sheet.iter_rows(values_only=True):
                vals = [str(v) for v in row if v is not None]
                if vals:
                    linhas.append(" | ".join(vals))
        if linhas: return "\n".join(linhas)
    except Exception:
        pass

    try:
        with zipfile.ZipFile(io.BytesIO(arq_bytes)) as zf:
            shared_strings = []
            if "xl/sharedStrings.xml" in zf.namelist():
                root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
                shared_strings = [node.text or "" for node in root.iter() if node.tag.endswith("t")]
            if shared_strings:
                return "--- Strings encontradas na planilha ---\n" + "\n".join(shared_strings)
    except Exception:
        pass

    return "[Não foi possível extrair texto da planilha Excel (.xlsx)]"

def extrair_texto_pptx(arq_bytes: bytes) -> str:
    try:
        import pptx
        prs = pptx.Presentation(io.BytesIO(arq_bytes))
        slides_text = []
        for idx, slide in enumerate(prs.slides):
            texts = []
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text:
                    texts.append(shape.text.strip())
            if texts:
                slides_text.append(f"--- Slide {idx+1} ---\n" + "\n".join(texts))
        if slides_text: return "\n\n".join(slides_text)
    except Exception:
        pass

    try:
        with zipfile.ZipFile(io.BytesIO(arq_bytes)) as zf:
            slide_files = [f for f in zf.namelist() if f.startswith("ppt/slides/slide") and f.endswith(".xml")]
            texts = []
            for sf in sorted(slide_files):
                root = ET.fromstring(zf.read(sf))
                st = [node.text for node in root.iter() if node.tag.endswith("t") and node.text]
                if st:
                    texts.append(" ".join(st))
            if texts: return "\n\n".join(texts)
    except Exception:
        pass

    return "[Não foi possível extrair texto da apresentação PowerPoint (.pptx)]"

def extrair_texto_documento(nome_arquivo: str, arq_bytes: bytes) -> str:
    ext = Path(nome_arquivo).suffix.lower()

    if ext == ".pdf":
        return extrair_texto_pdf(arq_bytes)
    elif ext == ".docx":
        return extrair_texto_docx(arq_bytes)
    elif ext in (".xlsx", ".xls"):
        return extrair_texto_xlsx(arq_bytes)
    elif ext == ".pptx":
        return extrair_texto_pptx(arq_bytes)

    for encoding in ("utf-8", "latin-1", "cp1252"):
        try:
            return arq_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue

    return arq_bytes.decode("utf-8", errors="replace")

def ler_arquivos_anexos() -> str:
    """
    Baixa e lê o conteúdo de qualquer arquivo anexado na mensagem atual do Discord.
    Para áudios, realiza a transcrição usando Groq Whisper (whisper-large-v3).
    Para documentos (.pdf, .docx, .xlsx, .pptx, .txt, .py, etc.), extrai e lê o conteúdo em texto.
    """
    ctx = ayla_state.CONTEXTO_ATIVO.get() if ayla_state else None
    if not ctx:
        return "⚠️ Nenhum contexto de mensagem ou interação ativo no momento."

    attachments = []
    if hasattr(ctx, "attachments") and ctx.attachments:
        attachments = ctx.attachments
    elif hasattr(ctx, "message") and ctx.message and ctx.message.attachments:
        attachments = ctx.message.attachments

    if not attachments:
        return "⚠️ Nenhum arquivo anexado foi encontrado na mensagem atual."

    global_bot = globals().get("bot")
    if not global_bot or not hasattr(global_bot, "loop"):
        return "⚠️ O bot não está pronto para baixar anexos."

    resultados = []
    for anexo in attachments:
        nome_arquivo = anexo.filename
        ext_lower = Path(nome_arquivo).suffix.lower()
        content_type = anexo.content_type or ""

        futuro = asyncio.run_coroutine_threadsafe(anexo.read(), global_bot.loop)
        try:
            arq_bytes = futuro.result(timeout=30)
        except Exception as e:
            resultados.append(f"❌ **{nome_arquivo}**: Falha ao baixar o arquivo ({e})")
            continue

        # Verificar se é áudio
        is_audio = content_type.startswith("audio/") or ext_lower in _EXTENSOES_AUDIO
        if is_audio:
            res_transcricao = transcrever_audio_groq(arq_bytes, nome_arquivo)
            resultados.append(res_transcricao)
            continue

        # Se for imagem ou vídeo (não áudio)
        if content_type.startswith("image/") or content_type.startswith("video/"):
            resultados.append(f"🖼️ **{nome_arquivo}**: Este é um arquivo de imagem/vídeo e é processado no fluxo multimodal da Z.ai.")
            continue

        texto_conteudo = extrair_texto_documento(nome_arquivo, arq_bytes)
        limite = 20000
        if len(texto_conteudo) > limite:
            texto_conteudo = texto_conteudo[:limite] + f"\n\n[...Conteúdo truncado em {limite} caracteres...]"

        resultados.append(f"📄 **{nome_arquivo}**:\n{texto_conteudo}")

    return "\n\n================================\n\n".join(resultados)

TOOL_MAP["ler_arquivos_anexos"] = ler_arquivos_anexos
FUNCTION_DECLARATIONS.append({
    "name": "ler_arquivos_anexos",
    "description": "Lê o conteúdo em texto de documentos anexados (PDF, Word, Excel, TXT, áudio).",
    "parameters": {
        "type": "object",
        "properties": {}
    }
})
