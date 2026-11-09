"""Lista pastas, lê e verifica arquivos e edita textos, documentos e planilhas."""
from ayla_paths import resolve_path
from ayla_paths import project_path, user_dir
from datetime import datetime as _file_datetime

import os
import sys
import io
import re
import csv
import json
import wave
import zipfile
import hashlib
import mimetypes
import datetime
from pathlib import Path

# Inclusão do diretório base do projeto
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
try:
    import ayla_state
except ImportError:
    ayla_state = None

if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

# ══════════════════════════════════════════════════════════
#  EXTENSÕES E CONFIGURAÇÕES
# ══════════════════════════════════════════════════════════

_EXT_TEXTO = {
    ".txt", ".py", ".json", ".md", ".csv", ".tsv", ".html", ".htm", ".css",
    ".js", ".ts", ".jsx", ".tsx", ".yaml", ".yml", ".xml", ".ini", ".env",
    ".bat", ".cmd", ".ps1", ".sh", ".bash", ".c", ".cpp", ".h", ".hpp",
    ".cs", ".java", ".rs", ".go", ".rb", ".php", ".sql", ".toml", ".cfg",
    ".log", ".properties", ".srt", ".vtt", ".reg", ".lua", ".dart", ".kt",
    ".r", ".vue", ".scss", ".sass", ".less", ".dockerfile", ".makefile"
}

_EXT_DOCS = {".pdf", ".docx", ".doc", ".pptx", ".ppt", ".rtf", ".odt"}
_EXT_PLANILHAS = {".xlsx", ".xls", ".csv", ".tsv", ".ods"}
_EXT_IMAGENS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".tiff", ".svg"}
_EXT_AUDIOS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".opus", ".webm", ".wma", ".aiff", ".mp2", ".3gp", ".m4r"}
_EXT_VIDEOS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v", ".3gp", ".ts"}
_EXT_COMPACTADOS = {".zip", ".tar", ".gz", ".tgz", ".bz2", ".7z", ".rar"}

_EXT_EDITAVEIS = _EXT_TEXTO | {".docx", ".xlsx", ".csv", ".tsv"}


# ══════════════════════════════════════════════════════════
#  UTILITÁRIOS AUXILIARES
# ══════════════════════════════════════════════════════════

def _formatar_tamanho(tamanho_bytes: int) -> str:
    """Retorna tamanho formatado em B, KB, MB, GB."""
    for unidade in ["B", "KB", "MB", "GB", "TB"]:
        if tamanho_bytes < 1024.0:
            return f"{tamanho_bytes:.2f} {unidade}"
        tamanho_bytes /= 1024.0
    return f"{tamanho_bytes:.2f} PB"


def _obter_icone_item(path: Path) -> str:
    """Retorna um ícone visual condizente com a extensão ou tipo de item."""
    if path.is_dir():
        return "📁"
    ext = path.suffix.lower()
    if ext == ".py":
        return "🐍"
    elif ext in (".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".env", ".xml"):
        return "⚙️"
    elif ext in _EXT_DOCS:
        return "📑"
    elif ext in _EXT_PLANILHAS:
        return "📊"
    elif ext in _EXT_IMAGENS:
        return "🖼️"
    elif ext in _EXT_AUDIOS:
        return "🎙️"
    elif ext in _EXT_VIDEOS:
        return "🎬"
    elif ext in _EXT_COMPACTADOS:
        return "📦"
    elif ext in (".exe", ".msi", ".bat", ".cmd", ".ps1", ".sh", ".bash"):
        return "⚡"
    elif ext in (".html", ".htm", ".css", ".js", ".ts", ".jsx", ".tsx", ".vue"):
        return "🌐"
    elif ext in _EXT_TEXTO:
        return "📄"
    return "📄"


def _resolver_caminho(caminho: str = "") -> Path:
    """Resolve caminhos absolutos ou relativos com tolerância inteligente (base padrão: pasta da instalação da Ayla)."""
    base_ai = project_path()
    p_str = (caminho or "").strip().strip('"').strip("'")
    if not p_str or p_str in (".", "./", ".\\"):
        return base_ai.resolve()

    p = resolve_path(p_str)
    if p.is_absolute() and p.exists():
        return p.resolve()

    # Tenta caminho relativo ao diretório base principal da Ayla e subpastas conhecidas
    candidatos = [
        base_ai / p_str,
        p,
        base_ai / "DocumentosCriados" / p_str,
        base_ai / "MODOS" / "MODOS ADICIONAIS" / p_str,
        base_ai / "MODOS" / "MODOS ADICIONAIS CONTINUOS" / p_str,
        base_ai / "MODOS" / "MODOS ESSENCIAIS" / p_str,
        user_dir('DESKTOP') / p_str,
        user_dir('DOCUMENTS') / p_str,
        user_dir('DOWNLOAD') / p_str,
    ]

    for cand in candidatos:
        if cand.exists():
            return cand.resolve()

    # Se não existe, retorna o caminho normalizado pretendido
    if p.is_absolute():
        return p.resolve()
    return (base_ai / p_str).resolve()


def _ler_conteudo_texto(caminho: Path) -> tuple[str, str]:
    """Lê arquivo de texto com fallback de encodings seguros."""
    encodings = ["utf-8-sig", "utf-8", "latin-1", "cp1252", "ascii"]
    for enc in encodings:
        try:
            texto = caminho.read_text(encoding=enc)
            return texto, enc
        except UnicodeDecodeError:
            continue
        except Exception:
            break
    try:
        return caminho.read_text(encoding="utf-8", errors="replace"), "utf-8 (com substituições)"
    except Exception as e:
        return f"❌ Erro ao ler texto: {e}", "desconhecido"


def _obter_chave_groq() -> str:
    """Recupera a chave de API do Groq."""
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
    return groq_key


# ══════════════════════════════════════════════════════════
#  EXTRATORES ESPECÍFICOS POR TIPO DE ARQUIVO
# ══════════════════════════════════════════════════════════

def _ler_pdf(caminho: Path, max_paginas: int = 50) -> str:
    """Extrai texto e informações de arquivo PDF usando pypdf."""
    try:
        import pypdf
        reader = pypdf.PdfReader(str(caminho))
        total_pags = len(reader.pages)
        paginas_texto = []

        limite = min(total_pags, max_paginas)
        for i in range(limite):
            try:
                txt = reader.pages[i].extract_text() or ""
                if txt.strip():
                    paginas_texto.append(f"📄 **[Página {i+1}/{total_pags}]**\n{txt.strip()}")
            except Exception as e:
                paginas_texto.append(f"⚠️ [Erro na página {i+1}: {e}]")

        resultado = f"📑 **Documento PDF:** `{caminho.name}` (Total: {total_pags} páginas)\n\n"
        resultado += "\n\n---\n\n".join(paginas_texto) if paginas_texto else "(Nenhum texto legível encontrado nas páginas)"
        if total_pags > max_paginas:
            resultado += f"\n\n⚠️ *Mostrando primeiras {max_paginas} de {total_pags} páginas.*"
        return resultado
    except Exception as e:
        return f"❌ Erro ao ler PDF `{caminho.name}`: {e}"


def _ler_docx(caminho: Path) -> str:
    """Extrai texto formatado de arquivo Word (.docx)."""
    try:
        import docx
        doc = docx.Document(str(caminho))
        partes = []

        for p in doc.paragraphs:
            if p.text.strip():
                partes.append(p.text)

        # Tabelas
        if doc.tables:
            partes.append("\n📊 **Tabelas no Documento:**")
            for t_idx, table in enumerate(doc.tables, 1):
                partes.append(f"\n--- Tabela {t_idx} ---")
                for row in table.rows:
                    cols = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                    partes.append(" | ".join(cols))

        texto_completo = "\n".join(partes)
        return (
            f"📄 **Documento Word (.docx):** `{caminho.name}`\n"
            f"📏 Total de parágrafos: {len(doc.paragraphs)} | Tabelas: {len(doc.tables)}\n\n"
            f"{texto_completo if texto_completo.strip() else '(Documento vazio)'}"
        )
    except Exception as e:
        return f"❌ Erro ao ler DOCX `{caminho.name}`: {e}"


def _ler_pptx(caminho: Path) -> str:
    """Extrai texto de slides do PowerPoint (.pptx)."""
    try:
        import xml.etree.ElementTree as ET
        with zipfile.ZipFile(str(caminho), "r") as z:
            slide_files = sorted([f for f in z.namelist() if f.startswith("ppt/slides/slide") and f.endswith(".xml")])
            if not slide_files:
                return f"📊 Apresentação PPTX `{caminho.name}` não contém slides com texto legível."

            slides_texto = []
            for idx, sfile in enumerate(slide_files, 1):
                xml_content = z.read(sfile)
                tree = ET.fromstring(xml_content)
                textos = [elem.text for elem in tree.iter() if elem.tag.endswith("}t") and elem.text]
                if textos:
                    slides_texto.append(f"📽️ **Slide {idx}:**\n" + " ".join(textos))

            return f"📽️ **Apresentação PowerPoint:** `{caminho.name}` ({len(slide_files)} slides)\n\n" + "\n\n".join(slides_texto)
    except Exception as e:
        return f"❌ Erro ao ler PPTX `{caminho.name}`: {e}"


def _ler_planilha_tabela(caminho: Path, aba: str = "", limite_linhas: int = 50) -> str:
    """Lê planilha Excel (.xlsx, .xls) ou CSV e formata em tabela legível."""
    ext = caminho.suffix.lower()
    try:
        if ext == ".csv":
            for enc in ("utf-8-sig", "utf-8", "latin-1"):
                try:
                    conteudo = caminho.read_text(encoding=enc)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                conteudo = caminho.read_text(encoding="utf-8", errors="replace")

            amostra = conteudo[:4096]
            try:
                dial = csv.Sniffer().sniff(amostra)
            except Exception:
                dial = csv.excel

            reader = list(csv.reader(conteudo.splitlines(), dialect=dial))
            if not reader:
                return f"📊 Planilha CSV `{caminho.name}` está vazia."

            colunas = reader[0]
            linhas = reader[1:limite_linhas+1]
            total_linhas = len(reader) - 1

            tabela = [f"📊 **Planilha CSV:** `{caminho.name}` (Total: {total_linhas} linhas, {len(colunas)} colunas)\n"]
            tabela.append(" | ".join(colunas))
            tabela.append("-" * min(80, max(20, len(" | ".join(colunas)))))
            for l in linhas:
                tabela.append(" | ".join(str(c) for c in l))
            if total_linhas > limite_linhas:
                tabela.append(f"\n... e mais {total_linhas - limite_linhas} linhas ocultas.")
            return "\n".join(tabela)

        elif ext in (".xlsx", ".xls"):
            import openpyxl
            wb = openpyxl.load_workbook(str(caminho), data_only=True, read_only=True)
            abas_disponiveis = wb.sheetnames

            ws = wb[aba] if aba and aba in abas_disponiveis else wb.active
            nome_aba_ativa = ws.title

            linhas_raw = list(ws.iter_rows(values_only=True))
            wb.close()

            if not linhas_raw:
                return f"📊 Planilha Excel `{caminho.name}` [Aba: {nome_aba_ativa}] está vazia."

            cabecalho = [str(c) if c is not None else "" for c in linhas_raw[0]]
            linhas_corpo = linhas_raw[1:limite_linhas+1]
            total = len(linhas_raw) - 1

            res = [
                f"📊 **Planilha Excel:** `{caminho.name}`",
                f"📑 **Aba:** `{nome_aba_ativa}` (Abas disponíveis: {', '.join(abas_disponiveis)})",
                f"📏 **Dimensões:** {total} linhas x {len(cabecalho)} colunas\n",
                " | ".join(cabecalho),
                "-" * min(80, max(20, len(" | ".join(cabecalho))))
            ]
            for row in linhas_corpo:
                linha_formatada = [str(cell) if cell is not None else "" for cell in row]
                res.append(" | ".join(linha_formatada))

            if total > limite_linhas:
                res.append(f"\n... e mais {total - limite_linhas} linhas ocultas.")
            return "\n".join(res)
        else:
            return f"❌ Formato de planilha não reconhecido: {ext}"
    except Exception as e:
        return f"❌ Erro ao ler planilha `{caminho.name}`: {e}"


def _ler_imagem(caminho: Path) -> str:
    """Extrai informações detalhadas de imagem (resolução, formato, modo, EXIF)."""
    try:
        from PIL import Image, ExifTags
        with Image.open(str(caminho)) as img:
            largura, altura = img.size
            formato = img.format or caminho.suffix.upper().replace(".", "")
            modo = img.mode

            frames = getattr(img, "n_frames", 1)
            tamanho = _formatar_tamanho(caminho.stat().st_size)

            exif_detalhes = []
            try:
                exif_data = img._getexif()
                if exif_data:
                    for tag_id, value in exif_data.items():
                        tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
                        if tag_name in ("DateTime", "Make", "Model", "Software", "Orientation"):
                            exif_detalhes.append(f"  - {tag_name}: {value}")
            except Exception:
                pass

            # Atualiza o estado da Ayla para possibilitar envio no Discord
            if ayla_state:
                ayla_state.ULTIMA_IMAGEM_GERADA.set(str(caminho))
                ayla_state.ULTIMO_ARQUIVO_MIDIA.set(str(caminho))

            res = (
                f"🖼️ **Imagem:** `{caminho.name}`\n"
                f"📍 **Caminho:** `{caminho}`\n"
                f"📐 **Resolução:** {largura}x{altura} px (Proporção: {largura/max(1,altura):.2f}:1)\n"
                f"🎨 **Formato / Modo de Cor:** {formato} ({modo})\n"
                f"💾 **Tamanho em Disco:** {tamanho}\n"
                f"🎞️ **Quadros (Frames):** {frames}\n"
            )
            if exif_detalhes:
                res += "📷 **Metadados EXIF:**\n" + "\n".join(exif_detalhes) + "\n"

            res += "✨ *Imagem sincronizada no contexto da Ayla.*"
            return res
    except Exception as e:
        return f"❌ Erro ao analisar imagem `{caminho.name}`: {e}"


def _ler_audio(caminho: Path, transcrever: bool = True) -> str:
    """Extrai metadados de áudio e transcreve a fala via Groq Whisper se disponível."""
    tamanho = _formatar_tamanho(caminho.stat().st_size)
    ext = caminho.suffix.lower()
    duracao_str = "Desconhecida"
    canais = "Desconhecido"
    taxa_hz = "Desconhecida"

    # Tentativa de ler metadados WAV padrão
    if ext == ".wav":
        try:
            with wave.open(str(caminho), "rb") as w:
                frames = w.getnframes()
                rate = w.getframerate()
                canais = str(w.getnchannels())
                taxa_hz = f"{rate} Hz"
                dur_sec = frames / float(rate)
                duracao_str = str(datetime.timedelta(seconds=int(dur_sec)))
        except Exception:
            pass

    # Transcrição via Groq Whisper se solicitado
    transcricao = ""
    if transcrever:
        groq_key = _obter_chave_groq()
        if groq_key:
            try:
                import requests
                url = "https://api.groq.com/openai/v1/audio/transcriptions"
                headers = {"Authorization": f"Bearer {groq_key}"}
                arq_bytes = caminho.read_bytes()
                safe_name = f"audio{ext or '.wav'}"

                files = {"file": (safe_name, arq_bytes)}
                data = {
                    "model": "whisper-large-v3",
                    "language": "pt",
                    "response_format": "json",
                    "temperature": 0.0
                }
                resp = requests.post(url, headers=headers, files=files, data=data, timeout=45)
                if resp.status_code == 200:
                    transcricao = resp.json().get("text", "").strip()
                else:
                    transcricao = f"[Erro na API Groq: status {resp.status_code}]"
            except Exception as e:
                transcricao = f"[Falha na transcrição: {e}]"
        else:
            transcricao = "[Chave GROQ_API_KEY não configurada para transcrição automática]"

    res = (
        f"🎙️ **Áudio:** `{caminho.name}`\n"
        f"📍 **Caminho:** `{caminho}`\n"
        f"💾 **Tamanho:** {tamanho} | **Extensão:** {ext}\n"
        f"⏱️ **Duração:** {duracao_str} | **Taxa:** {taxa_hz} | **Canais:** {canais}\n"
    )
    if transcricao:
        res += f"\n🗣️ **Transcrição de Voz (Whisper Large v3):**\n\"{transcricao}\""

    if ayla_state:
        ayla_state.ULTIMO_ARQUIVO_MIDIA.set(str(caminho))

    return res


def _ler_video(caminho: Path) -> str:
    """Extrai informações e metadados de arquivo de vídeo via OpenCV / MoviePy."""
    tamanho = _formatar_tamanho(caminho.stat().st_size)
    try:
        import cv2
        cap = cv2.VideoCapture(str(caminho))
        if not cap.isOpened():
            return f"🎥 **Vídeo:** `{caminho.name}` ({tamanho}) - Não foi possível abrir os streams de vídeo."

        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        largura = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        altura = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        fourcc_int = int(cap.get(cv2.CAP_PROP_FOURCC) or 0)
        cap.release()

        duracao_sec = (total_frames / fps) if fps > 0 else 0
        duracao_formatada = str(datetime.timedelta(seconds=int(duracao_sec)))

        codec = "".join([chr((fourcc_int >> 8 * i) & 0xFF) for i in range(4)]).strip()

        if ayla_state:
            ayla_state.ULTIMO_ARQUIVO_MIDIA.set(str(caminho))

        return (
            f"🎬 **Vídeo:** `{caminho.name}`\n"
            f"📍 **Caminho:** `{caminho}`\n"
            f"📐 **Resolução:** {largura}x{altura} px\n"
            f"⏱️ **Duração:** {duracao_formatada} ({duracao_sec:.2f}s)\n"
            f"🎞️ **FPS:** {fps:.2f} | **Total de Quadros:** {total_frames:,}\n"
            f"💾 **Tamanho em Disco:** {tamanho}\n"
            f"📼 **Codec FourCC:** `{codec or 'N/A'}`"
        )
    except Exception as e:
        return f"🎬 **Vídeo:** `{caminho.name}` ({tamanho}) | Informações básicas obtidas (Erro OpenCV: {e})"


def _ler_compactado(caminho: Path) -> str:
    """Lista arquivos dentro de arquivo compactado (.zip, .tar, etc.)."""
    try:
        if zipfile.is_zipfile(str(caminho)):
            with zipfile.ZipFile(str(caminho), "r") as z:
                infolist = z.infolist()
                total_arqs = len(infolist)
                tamanho_descompactado = sum(f.file_size for f in infolist)
                preview = [f"  - {f.filename} ({_formatar_tamanho(f.file_size)})" for f in infolist[:30]]

                res = (
                    f"📦 **Arquivo Compactado (ZIP):** `{caminho.name}`\n"
                    f"💾 **Tamanho compactado:** {_formatar_tamanho(caminho.stat().st_size)}\n"
                    f"📂 **Tamanho descompactado:** {_formatar_tamanho(tamanho_descompactado)}\n"
                    f"📄 **Total de itens:** {total_arqs}\n\n"
                    f"📋 **Conteúdo Interno (Primeiros {min(30, total_arqs)}):**\n" + "\n".join(preview)
                )
                if total_arqs > 30:
                    res += f"\n  ... e mais {total_arqs - 30} itens."
                return res
        return f"📦 Arquivo compactado `{caminho.name}` ({_formatar_tamanho(caminho.stat().st_size)})"
    except Exception as e:
        return f"❌ Erro ao ler compactado `{caminho.name}`: {e}"


# ══════════════════════════════════════════════════════════
#  FERRAMENTAS DE LISTAGEM DE DIRETÓRIO: listar_pasta / listar_diretorio
# ══════════════════════════════════════════════════════════

def listar_pasta(
    caminho: str = "",
    recursivo: bool = False,
    profundidade_max: int = 2,
    mostrar_ocultos: bool = False,
    ordenar_por: str = "tipo_e_nome",
    filtro_extensao: str = "",
    limite_itens: int = 150
) -> str:
    """
    Lista detalhadamente arquivos e subpastas de um diretório com tamanhos formatados,
    datas de modificação, contagens e estatísticas.
    
    Args:
        caminho (str): Caminho completo ou relativo do diretório (padrão: pasta principal pasta da instalação da Ayla).
        recursivo (bool): Se True, varre subdiretórios recursivamente até a profundidade especificada.
        profundidade_max (int): Profundidade máxima quando recursivo=True (padrão: 2).
        mostrar_ocultos (bool): Se True, inclui arquivos e pastas ocultos (iniciados por ponto ou ~$ de lock).
        ordenar_por (str): Critério de ordenação ('tipo_e_nome', 'nome', 'tamanho', 'data_modificacao').
        filtro_extensao (str): Extensão(ões) para filtrar arquivos (ex: '.py' ou '.txt, .json').
        limite_itens (int): Limite máximo de itens a exibir no relatório (padrão: 150).
    """
    try:
        path = _resolver_caminho(caminho)
        if not path.exists():
            return f"❌ Diretório não encontrado no sistema: `{caminho}`\n(Caminho resolvido: `{path}`)"

        if path.is_file():
            return (
                f"⚠️ O caminho fornecido é um arquivo e não um diretório:\n"
                f"📍 `{path}` ({_formatar_tamanho(path.stat().st_size)})\n"
                f"💡 Dica: Utilize `ler_arquivo(caminho='{path}')` para ler o seu conteúdo."
            )

        # Processamento de filtros de extensão
        filtros = []
        if filtro_extensao:
            for f in str(filtro_extensao).split(","):
                f_limpo = f.strip().lower()
                if f_limpo:
                    if not f_limpo.startswith("."):
                        f_limpo = f".{f_limpo}"
                    filtros.append(f_limpo)

        itens_coletados = []

        def _coletar(dir_atual: Path, nivel: int = 0):
            if nivel > profundidade_max:
                return
            try:
                entradas = list(dir_atual.iterdir())
            except PermissionError:
                rel = str(dir_atual.relative_to(path)) if dir_atual != path else dir_atual.name
                itens_coletados.append({
                    "path": dir_atual,
                    "rel": rel,
                    "is_dir": True,
                    "stat": None,
                    "filhos_qtd": None,
                    "erro": "Acesso negado (Permissão)",
                    "nivel": nivel
                })
                return
            except Exception as e:
                rel = str(dir_atual.relative_to(path)) if dir_atual != path else dir_atual.name
                itens_coletados.append({
                    "path": dir_atual,
                    "rel": rel,
                    "is_dir": True,
                    "stat": None,
                    "filhos_qtd": None,
                    "erro": str(e),
                    "nivel": nivel
                })
                return

            for entrada in entradas:
                nome = entrada.name
                if not mostrar_ocultos and (nome.startswith(".") or nome.startswith("~$")):
                    continue

                is_dir = entrada.is_dir()

                if not is_dir and filtros:
                    if entrada.suffix.lower() not in filtros:
                        continue

                try:
                    st = entrada.stat()
                except Exception:
                    st = None

                filhos_qtd = None
                if is_dir:
                    try:
                        filhos_qtd = len(list(entrada.iterdir()))
                    except Exception:
                        filhos_qtd = "?"

                rel = str(entrada.relative_to(path))
                itens_coletados.append({
                    "path": entrada,
                    "rel": rel,
                    "is_dir": is_dir,
                    "stat": st,
                    "filhos_qtd": filhos_qtd,
                    "erro": None,
                    "nivel": nivel
                })

                if is_dir and recursivo and (nivel + 1 <= profundidade_max):
                    _coletar(entrada, nivel + 1)

        _coletar(path, nivel=0)

        if not itens_coletados:
            msg_filtro = f" com filtro `{filtro_extensao}`" if filtro_extensao else ""
            return f"📂 **Diretório:** `{path}`\n\n*(A pasta está vazia ou nenhum item correspondeu aos critérios{msg_filtro})*"

        # Ordenação
        criterio = (ordenar_por or "tipo_e_nome").lower()
        if criterio == "tamanho":
            itens_coletados.sort(key=lambda x: (x["stat"].st_size if x["stat"] and not x["is_dir"] else -1), reverse=True)
        elif criterio == "data_modificacao":
            itens_coletados.sort(key=lambda x: (x["stat"].st_mtime if x["stat"] else 0), reverse=True)
        elif criterio == "nome":
            itens_coletados.sort(key=lambda x: x["rel"].lower())
        else:  # "tipo_e_nome"
            itens_coletados.sort(key=lambda x: (not x["is_dir"], x["rel"].lower()))

        # Totais
        total_geral = len(itens_coletados)
        total_pastas = sum(1 for it in itens_coletados if it["is_dir"])
        total_arquivos = sum(1 for it in itens_coletados if not it["is_dir"])
        tamanho_total = sum(it["stat"].st_size for it in itens_coletados if not it["is_dir"] and it["stat"])
        tamanho_total_fmt = _formatar_tamanho(tamanho_total)

        linhas_relatorio = []
        for it in itens_coletados[:limite_itens]:
            p_item = it["path"]
            icone = _obter_icone_item(p_item)
            st = it["stat"]

            # Data de modificação
            data_mod = "Data desconhecida"
            if st:
                try:
                    data_mod = _file_datetime.fromtimestamp(st.st_mtime).strftime("%d/%m/%Y %H:%M:%S")
                except Exception:
                    pass

            if it["erro"]:
                linhas_relatorio.append(f"  {icone} `{it['rel']}/` ⚠️ [Erro: {it['erro']}]")
            elif it["is_dir"]:
                qtd_str = f"{it['filhos_qtd']} itens" if it['filhos_qtd'] != "?" else "itens inacessíveis"
                linhas_relatorio.append(f"  {icone} `{it['rel']}/`  📁 [Pasta: {qtd_str}]  |  🕒 {data_mod}")
            else:
                tam_str = _formatar_tamanho(st.st_size) if st else "0 B"
                linhas_relatorio.append(f"  {icone} `{it['rel']}`  ({tam_str})  |  🕒 {data_mod}")

        cabecalho = (
            f"📂 **Listagem de Diretório:** `{path}`\n"
            f"📊 **Total de Itens:** {total_geral} ({total_pastas} pastas, {total_arquivos} arquivos)\n"
            f"💾 **Tamanho dos Arquivos:** {tamanho_total_fmt}\n"
        )
        if recursivo:
            cabecalho += f"🔄 **Modo Recursivo:** Ativado (Profundidade Máx: {profundidade_max})\n"
        if filtro_extensao:
            cabecalho += f"🔍 **Filtro Aplicado:** `{filtro_extensao}`\n"

        cabecalho += "\n" + "─" * 60 + "\n"

        corpo = "\n".join(linhas_relatorio)

        rodape = ""
        if total_geral > limite_itens:
            rodape = f"\n\n⚠️ *Exibindo os primeiros {limite_itens} de {total_geral} itens encontrados.*"

        return cabecalho + corpo + rodape

    except Exception as e:
        return f"❌ Erro ao listar diretório `{caminho}`: {e}"


def listar_diretorio(
    caminho: str = "",
    recursivo: bool = False,
    profundidade_max: int = 2,
    mostrar_ocultos: bool = False,
    ordenar_por: str = "tipo_e_nome",
    filtro_extensao: str = "",
    limite_itens: int = 150
) -> str:
    """
    Alias para listar_pasta. Lista arquivos e subpastas de um diretório com tamanhos formatados e datas.
    """
    return listar_pasta(
        caminho=caminho,
        recursivo=recursivo,
        profundidade_max=profundidade_max,
        mostrar_ocultos=mostrar_ocultos,
        ordenar_por=ordenar_por,
        filtro_extensao=filtro_extensao,
        limite_itens=limite_itens
    )


# ══════════════════════════════════════════════════════════
#  FERRAMENTA PRINCIPAL DE LEITURA: ler_arquivo
# ══════════════════════════════════════════════════════════

def ler_arquivo(
    caminho: str,
    linha_inicio: int = 1,
    linha_fim: int = None,
    transcrever_audio: bool = True,
    aba_planilha: str = "",
    limite_caracteres: int = 25000
) -> str:
    """
    Lê qualquer arquivo do computador: textos, códigos, documentos (PDF, Word, PPTX),
    planilhas (Excel, CSV), imagens (resolução/metadados), áudios (metadados + transcrição de fala),
    vídeos (resolução, FPS, duração), arquivos compactados e binários.
    
    Args:
        caminho (str): Caminho completo ou nome do arquivo a ser lido.
        linha_inicio (int): Linha inicial (1-indexed) caso queira ler um trecho específico de texto.
        linha_fim (int): Linha final (1-indexed) para arquivos de texto.
        transcrever_audio (bool): Se True, transcreve a fala de arquivos de áudio via Whisper.
        aba_planilha (str): Nome da aba se for planilha Excel (.xlsx).
        limite_caracteres (int): Limite máximo de caracteres no retorno para segurança.
    """
    try:
        path = _resolver_caminho(caminho)
        if not path.exists():
            return f"❌ Arquivo não encontrado no sistema: `{caminho}`\n(Caminho resolvido: `{path}`)"

        if path.is_dir():
            return listar_pasta(str(path))

        ext = path.suffix.lower()
        tamanho_bytes = path.stat().st_size
        tamanho_fmt = _formatar_tamanho(tamanho_bytes)

        # 1. Documentos
        if ext == ".pdf":
            return _ler_pdf(path)
        elif ext in (".docx", ".doc"):
            return _ler_docx(path)
        elif ext in (".pptx", ".ppt"):
            return _ler_pptx(path)

        # 2. Planilhas
        elif ext in _EXT_PLANILHAS:
            return _ler_planilha_tabela(path, aba=aba_planilha)

        # 3. Imagens
        elif ext in _EXT_IMAGENS:
            return _ler_imagem(path)

        # 4. Áudios
        elif ext in _EXT_AUDIOS:
            return _ler_audio(path, transcrever=transcrever_audio)

        # 5. Vídeos
        elif ext in _EXT_VIDEOS:
            return _ler_video(path)

        # 6. Compactados
        elif ext in _EXT_COMPACTADOS:
            return _ler_compactado(path)

        # 7. Arquivos de Texto / Código / Configurações / Formatos conhecidos
        else:
            texto, enc_usado = _ler_conteudo_texto(path)
            
            # Se for claramente binário (muitos bytes nulos) e não estiver na lista de texto
            if "\x00" in texto[:1024] and ext not in _EXT_TEXTO:
                sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
                mime, _ = mimetypes.guess_type(str(path))
                return (
                    f"💾 **Arquivo Binário:** `{path.name}`\n"
                    f"📍 Caminho: `{path}`\n"
                    f"📏 Tamanho: {tamanho_fmt} ({tamanho_bytes:,} bytes)\n"
                    f"🔒 SHA-256: `{sha256}`\n"
                    f"🏷️ MIME Type: `{mime or 'application/octet-stream'}`\n"
                    f"ℹ️ Este é um arquivo binário bruto e não pode ser exibido como texto comum."
                )

            linhas = texto.splitlines()
            total_linhas = len(linhas)

            inicio = max(1, int(linha_inicio or 1))
            fim = min(total_linhas, int(linha_fim)) if linha_fim is not None else total_linhas

            if inicio > total_linhas:
                return (
                    f"📄 **Arquivo:** `{path.name}` ({total_linhas} linhas, {tamanho_fmt})\n"
                    f"⚠️ Linha inicial solicitada ({inicio}) é maior que o total de linhas do arquivo ({total_linhas})."
                )

            linhas_selecionadas = linhas[inicio - 1:fim]
            linhas_formatadas = [f"{idx:4d} | {linha}" for idx, linha in enumerate(linhas_selecionadas, start=inicio)]

            cabecalho = (
                f"📄 **Arquivo:** `{path.name}`\n"
                f"📍 **Caminho:** `{path}`\n"
                f"📏 **Tamanho:** {tamanho_fmt} | **Linhas:** {inicio}-{fim} de {total_linhas} (Encoding: {enc_usado})\n\n"
            )

            corpo = "\n".join(linhas_formatadas)
            if len(corpo) > limite_caracteres:
                corpo = corpo[:limite_caracteres] + f"\n\n[...Conteúdo truncado por atingir o limite de {limite_caracteres} caracteres...]"

            return cabecalho + "```\n" + corpo + "\n```"

    except Exception as e:
        return f"❌ Erro ao ler arquivo `{caminho}`: {e}"


# ══════════════════════════════════════════════════════════
#  FERRAMENTA PRINCIPAL DE EDIÇÃO: editar_arquivo
# ══════════════════════════════════════════════════════════

from ayla_verificacao import gravar_texto_conferido, verificar_arquivo as _verificar_arquivo


def verificar_arquivo(caminho: str, conteudo_esperado: str = None):
    return _verificar_arquivo(str(_resolver_caminho(caminho)), conteudo_esperado)


def editar_arquivo(
    caminho: str,
    conteudo: str = None,
    linha: int = None,
    novo_texto_linha: str = None,
    modo_edicao: str = "substituir_tudo",
    texto_antigo: str = None,
    texto_novo: str = None,
    criar_se_nao_existir: bool = True,
    fazer_backup: bool = True
) -> str:
    """
    Edita arquivos de texto (.txt, .py, .json, .md, .csv, etc.), documentos e planilhas.
    Permite substituir o arquivo inteiro, alterar uma linha específica (1-indexed),
    inserir/deletar linhas ou substituir trechos de texto.
    
    Args:
        caminho (str): Caminho completo ou relativo do arquivo.
        conteudo (str): Conteúdo completo novo (usado em 'substituir_tudo' ou se linha não for informada).
        linha (int): Número da linha a ser modificada ou onde inserir (1-indexed).
        novo_texto_linha (str): Novo texto para a linha especificada.
        modo_edicao (str): Opções: 'substituir_tudo', 'substituir_linha', 'inserir_linha', 'deletar_linha', 'substituir_texto', 'anexar_ao_final'.
        texto_antigo (str): Trecho exato a ser procurado para substituição (modo 'substituir_texto').
        texto_novo (str): Trecho novo que substituirá o texto antigo.
        criar_se_nao_existir (bool): Cria o arquivo caso ele ainda não exista.
        fazer_backup (bool): Cria uma cópia de segurança (.bak) antes da modificação.
    """
    try:
        path = _resolver_caminho(caminho)
        ext = path.suffix.lower()

        # Proteção: Apenas arquivos de texto, documentos e planilhas editáveis
        if ext in _EXT_IMAGENS | _EXT_AUDIOS | _EXT_VIDEOS | _EXT_COMPACTADOS or ext in (".exe", ".dll", ".bin", ".iso"):
            return f"🚫 Operação bloqueada: Arquivos de mídia e binários ({ext}) não devem ser editados como texto para evitar corrupção."

        # Se o arquivo não existe
        if not path.exists():
            if not criar_se_nao_existir:
                return f"❌ Arquivo não encontrado e `criar_se_nao_existir` está desativado: `{path}`"
            path.parent.mkdir(parents=True, exist_ok=True)
            novo_conteudo_final = conteudo if conteudo is not None else (novo_texto_linha or "")
            gravar_texto_conferido(path, novo_conteudo_final)
            return f"✨ Arquivo novo criado com sucesso!\n📍 Caminho: `{path}`\n📏 Tamanho: {_formatar_tamanho(path.stat().st_size)}"

        # Backup de segurança
        if fazer_backup and path.exists():
            try:
                backup_path = path.with_suffix(path.suffix + ".bak")
                backup_path.write_bytes(path.read_bytes())
            except Exception:
                pass

        # Leitura do conteúdo atual
        texto_original, enc = _ler_conteudo_texto(path)
        linhas = texto_original.splitlines()
        total_original = len(linhas)

        # ── MODOS DE OPERAÇÃO ──

        # 1. Substituição de Linha Específica
        if modo_edicao == "substituir_linha" or (linha is not None and novo_texto_linha is not None and modo_edicao == "substituir_tudo" and conteudo is None):
            num_linha = int(linha)
            if num_linha < 1:
                return "⚠️ O número da linha deve ser maior ou igual a 1 (1-indexed)."
            
            texto_antigo_linha = ""
            if num_linha <= total_original:
                texto_antigo_linha = linhas[num_linha - 1]
                linhas[num_linha - 1] = novo_texto_linha
            else:
                # Preenche linhas vazias se a linha solicitada for além do fim
                while len(linhas) < num_linha - 1:
                    linhas.append("")
                linhas.append(novo_texto_linha)

            novo_conteudo = "\n".join(linhas) + ("\n" if texto_original.endswith("\n") else "")
            gravar_texto_conferido(path, novo_conteudo)

            return (
                f"✏️ **Linha {num_linha} modificada com sucesso!**\n"
                f"📄 Arquivo: `{path.name}`\n"
                f"🔴 **Antes:** `{texto_antigo_linha}`\n"
                f"🟢 **Depois:** `{novo_texto_linha}`\n"
                f"📊 Total de linhas: {len(linhas)}"
            )

        # 2. Inserção de Linha
        elif modo_edicao == "inserir_linha":
            if linha is None:
                return "⚠️ Informe o número da linha (`linha`) onde deseja inserir o novo texto."
            num_linha = max(1, int(linha))
            posicao = min(num_linha - 1, len(linhas))
            texto_inserir = novo_texto_linha if novo_texto_linha is not None else (conteudo or "")
            linhas.insert(posicao, texto_inserir)

            novo_conteudo = "\n".join(linhas) + ("\n" if texto_original.endswith("\n") else "")
            gravar_texto_conferido(path, novo_conteudo)

            return (
                f"➕ **Linha inserida na posição {num_linha}!**\n"
                f"📄 Arquivo: `{path.name}`\n"
                f"🟢 **Texto inserido:** `{texto_inserir}`\n"
                f"📊 Total de linhas: {len(linhas)}"
            )

        # 3. Deleção de Linha
        elif modo_edicao == "deletar_linha":
            if linha is None:
                return "⚠️ Informe o número da linha (`linha`) que deseja deletar."
            num_linha = int(linha)
            if num_linha < 1 or num_linha > total_original:
                return f"⚠️ Linha {num_linha} fora do intervalo válido (1 a {total_original})."

            linha_removida = linhas.pop(num_linha - 1)
            novo_conteudo = "\n".join(linhas) + ("\n" if texto_original.endswith("\n") else "")
            gravar_texto_conferido(path, novo_conteudo)

            return (
                f"🗑️ **Linha {num_linha} removida com sucesso!**\n"
                f"📄 Arquivo: `{path.name}`\n"
                f"🔴 **Removido:** `{linha_removida}`\n"
                f"📊 Total de linhas restantes: {len(linhas)}"
            )

        # 4. Substituição de Texto / Trecho
        elif modo_edicao == "substituir_texto":
            if texto_antigo is None or texto_novo is None:
                return "⚠️ Para o modo 'substituir_texto', informe `texto_antigo` e `texto_novo`."

            if texto_antigo not in texto_original:
                return f"⚠️ O trecho especificado em `texto_antigo` não foi encontrado no arquivo `{path.name}`."

            ocorrencias = texto_original.count(texto_antigo)
            novo_conteudo = texto_original.replace(texto_antigo, texto_novo)
            gravar_texto_conferido(path, novo_conteudo)

            return (
                f"🔄 **Texto substituído com sucesso!**\n"
                f"📄 Arquivo: `{path.name}`\n"
                f"🔢 Ocorrências substituídas: {ocorrencias}\n"
                f"🔴 **Antigo:** `{texto_antigo[:120]}`\n"
                f"🟢 **Novo:** `{texto_novo[:120]}`"
            )

        # 5. Anexar ao Final
        elif modo_edicao == "anexar_ao_final":
            texto_anexo = conteudo if conteudo is not None else (novo_texto_linha or "")
            separador = "\n" if not texto_original.endswith("\n") and texto_original else ""
            novo_conteudo = texto_original + separador + texto_anexo
            gravar_texto_conferido(path, novo_conteudo)

            return (
                f"📎 **Texto anexado ao final do arquivo!**\n"
                f"📄 Arquivo: `{path.name}`\n"
                f"📊 Novo total de linhas: {len(novo_conteudo.splitlines())}"
            )

        # 6. Substituição Total do Arquivo (Padrão)
        else:
            if conteudo is None:
                return "⚠️ Nenhum `conteudo` fornecido para substituir o arquivo."

            gravar_texto_conferido(path, conteudo)
            linhas_novas = len(conteudo.splitlines())

            return (
                f"📝 **Arquivo reescrito com sucesso!**\n"
                f"📄 Arquivo: `{path.name}`\n"
                f"📍 Caminho: `{path}`\n"
                f"📊 Linhas: de {total_original} para {linhas_novas}\n"
                f"💾 Tamanho: {_formatar_tamanho(path.stat().st_size)}"
            )

    except Exception as e:
        return f"❌ Erro ao editar arquivo `{caminho}`: {e}"


# ══════════════════════════════════════════════════════════
#  FERRAMENTA ESPECÍFICA: substituir_linha_arquivo
# ══════════════════════════════════════════════════════════

def substituir_linha_arquivo(caminho: str, linha: int, novo_texto: str) -> str:
    """
    Substitui diretamente uma linha específica (1-indexed) de um arquivo de texto.
    
    Args:
        caminho (str): Caminho do arquivo a ser modificado.
        linha (int): Número da linha a ser alterada (ex: 5).
        novo_texto (str): O novo conteúdo da linha.
    """
    return editar_arquivo(
        caminho=caminho,
        linha=linha,
        novo_texto_linha=novo_texto,
        modo_edicao="substituir_linha"
    )


# ══════════════════════════════════════════════════════════
#  REGISTRO DAS FERRAMENTAS NO SISTEMA DA AYLA
# ══════════════════════════════════════════════════════════

def buscar_em_arquivo(
    caminho: str,
    padrao: str,
    ignorar_maiusculas: bool = True,
    regex: bool = False,
    contexto_linhas: int = 2,
) -> str:
    """
    Busca um texto ou padrão regex dentro de um único arquivo e retorna as linhas com ocorrências,
    numeradas e com contexto. Útil para localizar rapidamente funções, variáveis ou trechos.

    Args:
        caminho (str): Caminho do arquivo a buscar.
        padrao (str): Texto ou expressão regular a localizar.
        ignorar_maiusculas (bool): Se True, busca sem diferenciar maiúsculas/minúsculas.
        regex (bool): Se True, trata o padrão como expressão regular.
        contexto_linhas (int): Linhas de contexto ao redor de cada ocorrência (padrão: 2).
    """
    import re as _re
    try:
        path = _resolver_caminho(caminho)
        if not path.exists() or not path.is_file():
            return f"❌ Arquivo não encontrado: `{caminho}`"

        texto, enc = _ler_conteudo_texto(path)
        linhas = texto.splitlines()
        total = len(linhas)

        flags = _re.IGNORECASE if ignorar_maiusculas else 0
        try:
            pat = _re.compile(padrao if regex else _re.escape(padrao), flags)
        except _re.error as e:
            return f"❌ Padrão regex inválido: {e}"

        matches = []
        for i, linha in enumerate(linhas):
            if pat.search(linha):
                matches.append(i)

        if not matches:
            return (
                f"🔍 Padrão `{padrao}` não encontrado em `{path.name}`.\n"
                f"📏 Arquivo tem {total} linhas."
            )

        blocos = []
        exibidos = set()
        for idx in matches:
            inicio = max(0, idx - contexto_linhas)
            fim = min(total, idx + contexto_linhas + 1)
            bloco = []
            for j in range(inicio, fim):
                if j in exibidos:
                    continue
                exibidos.add(j)
                prefixo = "▶" if j == idx else " "
                bloco.append(f"  {prefixo} {j+1:4d} │ {linhas[j]}")
            if bloco:
                blocos.append("\n".join(bloco))

        cabecalho = (
            f"🔍 **Busca em** `{path.name}` — padrão: `{padrao}`\n"
            f"✅ **{len(matches)} ocorrência(s)** encontrada(s) em {total} linhas\n"
            + "━" * 50 + "\n"
        )
        return cabecalho + "\n---\n".join(blocos)

    except Exception as e:
        return f"❌ Erro ao buscar em arquivo: {e}"


def register(tool_map, function_declarations):
    """Função padrão de registro dinâmico para a arquitetura da Ayla."""
    tool_map["ler_arquivo"] = ler_arquivo
    tool_map["editar_arquivo"] = editar_arquivo
    tool_map["substituir_linha_arquivo"] = substituir_linha_arquivo
    tool_map["listar_pasta"] = listar_pasta
    tool_map["listar_diretorio"] = listar_diretorio
    tool_map["verificar_arquivo"] = verificar_arquivo
    tool_map["buscar_em_arquivo"] = buscar_em_arquivo

    # Limpeza de declarações antigas se existirem
    nomes_nossos = {"ler_arquivo", "editar_arquivo", "substituir_linha_arquivo", "listar_pasta", "listar_diretorio", "verificar_arquivo", "buscar_em_arquivo"}
    for i in range(len(function_declarations) - 1, -1, -1):
        if function_declarations[i].get("name") in nomes_nossos:
            function_declarations.pop(i)

    function_declarations.append({
        "name": "verificar_arquivo",
        "description": "Confere existência, leitura e estrutura de um arquivo. Pode comparar o conteúdo esperado. Não modifica nem executa o arquivo.",
        "parameters": {"type": "object", "properties": {
            "caminho": {"type": "string", "description": "Caminho do arquivo a conferir."},
            "conteudo_esperado": {"type": "string", "description": "Texto completo esperado, opcional para comparar TXT, código ou parágrafos DOCX."}
        }, "required": ["caminho"]}
    })
    function_declarations.append({
        "name": "listar_pasta",
        "description": "Lista detalhadamente arquivos e subpastas de um diretório com nomes, tamanhos formatados, datas de modificação e resumo estatístico. Padrão: pasta principal pasta da instalação da Ayla.",
        "parameters": {
            "type": "object",
            "properties": {
                "caminho": {
                    "type": "string",
                    "description": "Caminho da pasta a listar (ex: 'MODOS', 'DocumentosCriados' ou caminho completo). Se vazio, lista a pasta principal da Ayla."
                },
                "recursivo": {
                    "type": "boolean",
                    "description": "Se True, lista subpastas recursivamente até a profundidade limite."
                },
                "profundidade_max": {
                    "type": "integer",
                    "description": "Profundidade máxima quando recursivo=True (padrão: 2)."
                },
                "mostrar_ocultos": {
                    "type": "boolean",
                    "description": "Se True, inclui arquivos e pastas ocultos (iniciados por ponto ou ~$ de lock)."
                },
                "ordenar_por": {
                    "type": "string",
                    "enum": ["tipo_e_nome", "nome", "tamanho", "data_modificacao"],
                    "description": "Critério de ordenação ('tipo_e_nome', 'nome', 'tamanho', 'data_modificacao')."
                },
                "filtro_extensao": {
                    "type": "string",
                    "description": "Filtra apenas arquivos com determinada extensão (ex: '.py' ou '.txt, .json')."
                },
                "limite_itens": {
                    "type": "integer",
                    "description": "Limite máximo de itens a exibir no relatório (padrão: 150)."
                }
            },
            "required": []
        }
    })

    function_declarations.append({
        "name": "listar_diretorio",
        "description": "Alias para listar_pasta. Lista arquivos e subpastas de um diretório com detalhes de tamanho e datas.",
        "parameters": {
            "type": "object",
            "properties": {
                "caminho": {
                    "type": "string",
                    "description": "Caminho da pasta a ser listada."
                },
                "recursivo": {
                    "type": "boolean",
                    "description": "Se True, lista subpastas recursivamente."
                },
                "profundidade_max": {
                    "type": "integer",
                    "description": "Profundidade máxima quando recursivo=True (padrão: 2)."
                },
                "mostrar_ocultos": {
                    "type": "boolean",
                    "description": "Se True, inclui arquivos/pastas ocultos."
                },
                "ordenar_por": {
                    "type": "string",
                    "enum": ["tipo_e_nome", "nome", "tamanho", "data_modificacao"],
                    "description": "Critério de ordenação (padrão: 'tipo_e_nome')."
                },
                "filtro_extensao": {
                    "type": "string",
                    "description": "Filtro de extensão de arquivo (ex: '.py')."
                },
                "limite_itens": {
                    "type": "integer",
                    "description": "Limite máximo de itens a listar."
                }
            },
            "required": []
        }
    })

    function_declarations.append({
        "name": "ler_arquivo",
        "description": "Lê qualquer arquivo do computador: textos, códigos (.py, .json, .txt), documentos (.pdf, .docx, .pptx), planilhas (.xlsx, .csv), imagens, áudios (com transcrição Whisper), vídeos e arquivos compactados.",
        "parameters": {
            "type": "object",
            "properties": {
                "caminho": {
                    "type": "string",
                    "description": "Caminho completo ou nome do arquivo a ser lido no computador."
                },
                "linha_inicio": {
                    "type": "integer",
                    "description": "Linha inicial (1-indexed) para leitura parcial de arquivos de texto."
                },
                "linha_fim": {
                    "type": "integer",
                    "description": "Linha final (1-indexed) para leitura parcial de arquivos de texto."
                },
                "transcrever_audio": {
                    "type": "boolean",
                    "description": "Se True, transcreve a fala de arquivos de áudio automaticamente usando Whisper."
                },
                "aba_planilha": {
                    "type": "string",
                    "description": "Nome da aba específica se for uma planilha Excel (.xlsx)."
                },
                "limite_caracteres": {
                    "type": "integer",
                    "description": "Limite máximo de caracteres a retornar para evitar estouro de contexto."
                }
            },
            "required": ["caminho"]
        }
    })

    function_declarations.append({
        "name": "editar_arquivo",
        "description": "Edita arquivos de texto (.txt, .py, .json, .md, .csv, etc.), documentos e planilhas. Permite reescrever o arquivo inteiro OU alterar/inserir/deletar uma linha específica OU substituir trechos de texto.",
        "parameters": {
            "type": "object",
            "properties": {
                "caminho": {
                    "type": "string",
                    "description": "Caminho do arquivo a ser modificado."
                },
                "conteudo": {
                    "type": "string",
                    "description": "Novo conteúdo completo do arquivo (para 'substituir_tudo' ou criação)."
                },
                "linha": {
                    "type": "integer",
                    "description": "Número da linha específica a ser alterada ou onde inserir/deletar (1-indexed)."
                },
                "novo_texto_linha": {
                    "type": "string",
                    "description": "Novo texto a ser colocado na linha informada."
                },
                "modo_edicao": {
                    "type": "string",
                    "enum": ["substituir_tudo", "substituir_linha", "inserir_linha", "deletar_linha", "substituir_texto", "anexar_ao_final"],
                    "description": "Modo de edição a executar."
                },
                "texto_antigo": {
                    "type": "string",
                    "description": "Trecho exato a ser localizado para substituição (modo 'substituir_texto')."
                },
                "texto_novo": {
                    "type": "string",
                    "description": "Novo trecho que substituirá o texto_antigo."
                },
                "criar_se_nao_existir": {
                    "type": "boolean",
                    "description": "Se True, cria o arquivo caso ele não exista."
                },
                "fazer_backup": {
                    "type": "boolean",
                    "description": "Se True, gera uma cópia de segurança (.bak) antes da alteração."
                }
            },
            "required": ["caminho"]
        }
    })

    function_declarations.append({
        "name": "substituir_linha_arquivo",
        "description": "Substitui diretamente uma linha específica (1-indexed) de um arquivo de texto pelo novo texto.",
        "parameters": {
            "type": "object",
            "properties": {
                "caminho": {
                    "type": "string",
                    "description": "Caminho do arquivo a ser modificado."
                },
                "linha": {
                    "type": "integer",
                    "description": "Número da linha a ser alterada (ex: 5)."
                },
                "novo_texto": {
                    "type": "string",
                    "description": "O novo texto da linha."
                }
            },
            "required": ["caminho", "linha", "novo_texto"]
        }
    })

    function_declarations.append({
        "name": "buscar_em_arquivo",
        "description": (
            "Busca um texto ou padrão regex dentro de um único arquivo e retorna as linhas com ocorrências, "
            "numeradas e com contexto. Útil para localizar rapidamente funções, variáveis, classes ou "
            "qualquer trecho específico sem precisar ler o arquivo inteiro."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "caminho": {
                    "type": "string",
                    "description": "Caminho do arquivo onde buscar."
                },
                "padrao": {
                    "type": "string",
                    "description": "Texto ou expressão regular a localizar."
                },
                "ignorar_maiusculas": {
                    "type": "boolean",
                    "description": "Se True, busca sem diferenciar maiúsculas/minúsculas (padrão: True)."
                },
                "regex": {
                    "type": "boolean",
                    "description": "Se True, trata o padrão como expressão regular."
                },
                "contexto_linhas": {
                    "type": "integer",
                    "description": "Linhas de contexto ao redor de cada ocorrência (padrão: 2)."
                }
            },
            "required": ["caminho", "padrao"]
        }
    })


# ── Auto-registro ao carregar via exec_module ou import ──
register(TOOL_MAP, FUNCTION_DECLARATIONS)
