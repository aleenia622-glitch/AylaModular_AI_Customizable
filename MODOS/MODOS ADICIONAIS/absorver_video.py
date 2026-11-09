"""Analisa e resume vídeos ou áudios de links e arquivos locais usando áudio e imagens."""
from ayla_paths import resolve_path
from ayla_paths import ENV_PATH
import os
import re
import sys
import time
import tempfile
import hashlib
from pathlib import Path
import yt_dlp

# Garante compatibilidade se o arquivo for executado/importado individualmente
if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

PASTA_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PASTA_RAIZ not in sys.path:
    sys.path.append(PASTA_RAIZ)

try:
    import ayla_state
except ImportError:
    ayla_state = None


def obter_video_id(url: str) -> str | None:
    padroes = [
        r"(?:v=|\/v\/|embed\/|youtu\.be\/|shorts\/|\/embed\/|\/watch\?v=|\&v=)([^#\&\?]+)"
    ]
    for padrao in padroes:
        match = re.search(padrao, url)
        if match:
            return match.group(1)
    return None


def progresso_hook(d):
    if d.get('status') == 'downloading':
        total = d.get('total_bytes') or d.get('total_bytes_estimate')
        downloaded = d.get('downloaded_bytes', 0)
        if total:
            percent = (downloaded / total) * 100
            barra_tamanho = 30
            preenchido = int(round(barra_tamanho * downloaded / float(total)))
            barra = '#' * preenchido + '-' * (barra_tamanho - preenchido)
            speed = d.get('speed')
            speed_str = f"{speed / (1024 * 1024):.2f} MB/s" if speed else "N/A"
            eta = d.get('eta')
            eta_str = f"{eta}s" if eta is not None else "N/A"
            try:
                sys.stdout.write(f"\r📥 [Vídeo] Baixando: [{barra}] {percent:.1f}% ({speed_str}, ETA: {eta_str})")
                sys.stdout.flush()
            except Exception:
                pass
    elif d.get('status') == 'finished':
        try:
            sys.stdout.write("\r📥 [Vídeo] Download de mídia concluído! Processando arquivo...               \n")
            sys.stdout.flush()
        except Exception:
            pass


def executar_ytdl_com_fallback(opts_base, url, download=False):
    base_dir = Path(__file__).resolve().parents[2]
    cookies_txt = base_dir / "cookies.txt"

    # 1. Tenta com cookies.txt se o arquivo existir
    if cookies_txt.exists():
        opts = opts_base.copy()
        opts['cookiefile'] = str(cookies_txt)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                if download:
                    ydl.download([url])
                    return True, None, "cookies.txt"
                else:
                    info = ydl.extract_info(url, download=False)
                    return True, info, "cookies.txt"
        except Exception as e:
            print(f"Aviso: Falha ao usar cookies.txt: {e}")

    # 2. Tenta sem cookies
    try:
        with yt_dlp.YoutubeDL(opts_base) as ydl:
            if download:
                ydl.download([url])
                return True, None, "sem cookies"
            else:
                info = ydl.extract_info(url, download=False)
                return True, info, "sem cookies"
    except Exception as e:
        err_msg = str(e)
        if any(msg in err_msg for msg in ["confirm your age", "Sign in", "inappropriate", "cookies"]):
            browsers = ['edge', 'chrome', 'firefox', 'brave', 'opera', 'vivaldi']
            erros_navegadores = []
            for browser in browsers:
                opts = opts_base.copy()
                opts['cookiesfrombrowser'] = (browser,)
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        if download:
                            ydl.download([url])
                            return True, None, f"cookies do {browser}"
                        else:
                            info = ydl.extract_info(url, download=False)
                            return True, info, f"cookies do {browser}"
                except Exception as be:
                    msg_erro_b = str(be)
                    if "Permission denied" in msg_erro_b or "Could not copy" in msg_erro_b:
                        erros_navegadores.append(f"🔒 {browser} (está aberto e bloqueado)")
                    elif "could not find" in msg_erro_b or "FileNotFoundError" in msg_erro_b:
                        pass
                    else:
                        erros_navegadores.append(f"❌ {browser} ({msg_erro_b[:60]})")

            msg_erro_detalhado = (
                f"Este vídeo possui restrição de idade ou requer login para ser acessado.\n"
                f"Tentei obter a autorização automaticamente do seu navegador, mas:\n"
            )
            if erros_navegadores:
                msg_erro_detalhado += "\n".join(f"- {err}" for err in erros_navegadores) + "\n"
            else:
                msg_erro_detalhado += "- Nenhum navegador compatível com cookies ativos foi encontrado.\n"

            msg_erro_detalhado += (
                f"\n💡 **Como resolver:**\n"
                f"1. Se o Microsoft Edge estiver aberto, feche-o completamente e tente novamente.\n"
                f"2. Ou exporte os cookies para `cookies.txt` na pasta principal do projeto (`{base_dir}`)."
            )
            raise Exception(msg_erro_detalhado)
        else:
            raise e


def transcrever_audio_whisper(caminho_audio: str) -> str:
    """
    Transcreve a faixa de áudio utilizando a API do Groq Whisper (whisper-large-v3).
    Aplica filtro anti-alucinação para silêncios ou ruídos.
    """
    if not caminho_audio or not os.path.exists(caminho_audio):
        return ""

    try:
        from dotenv import load_dotenv
        load_dotenv(ENV_PATH)
    except ImportError:
        pass

    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if not groq_key:
        return ""

    try:
        import requests
        url_groq = "https://api.groq.com/openai/v1/audio/transcriptions"
        headers = {"Authorization": f"Bearer {groq_key}"}

        with open(caminho_audio, "rb") as f_aud:
            audio_bytes = f_aud.read()

        from whisper_audio import prepare_whisper_audio
        audio_bytes = prepare_whisper_audio(audio_bytes, caminho_audio)
        if not audio_bytes:
            print("[Whisper] Áudio sem fala descartado antes do envio.")
            return ""
        files = {"file": ("audio.wav", audio_bytes, "audio/wav")}
        data = {
            "model": "whisper-large-v3",
            "language": "pt",
            "response_format": "json",
            "prompt": "Se houver apenas silêncio, ruído, música de fundo ou estática, ignore totalmente e retorne vazio.",
            "temperature": 0.0
        }
        print("🎙️ [Whisper] Enviando trechos com fala para transcrição via Groq Whisper...")
        res = requests.post(url_groq, headers=headers, files=files, data=data, timeout=45)
        if res.status_code == 200:
            text = res.json().get("text", "").strip()
            if text:
                test_text = text.lower()
                hallucination_patterns = [
                    r"^\W*obrigad[ao]\W*$",
                    r"legenda(s)? por\b", r"legendado por\b", r"subtitles? by\b",
                    r"thank you for watching\b", r"obrigado por assistir\b",
                    r"inscreva-se no canal\b", r"acesse o nosso site\b",
                    r"opusdei\.pt", r"\bopus dei\b", r"amara\.org", r"legendas\.tv",
                    r"sônia ruberti", r"sonia ruberti", r"deixe seu like\b"
                ]
                for pattern in hallucination_patterns:
                    if re.search(pattern, test_text):
                        if len(text) < 120:
                            print(f"⚠️ [Whisper] Alucinação descartada: '{text}'")
                            return ""
                print(f"🎉 [Whisper] Transcrição concluída! ({len(text)} caracteres)")
                return text
        else:
            print(f"Aviso Groq Whisper status {res.status_code}: {res.text}")
    except Exception as e_groq:
        print(f"Aviso erro Groq Whisper: {e_groq}")

    return ""


def absorver_video_local(caminho_local: str) -> str:
    """
    Absorve e analisa um arquivo de vídeo local.
    Anexa o vídeo na íntegra para a visão da Ayla (ULTIMAS_IMAGENS_MODULO e ULTIMO_ANEXO_VIDEO)
    e transcreve a faixa de áudio com Whisper.
    """
    p = resolve_path(caminho_local).resolve()
    if not p.exists() or not p.is_file():
        return f"⚠️ **Arquivo de vídeo local não encontrado:** `{caminho_local}`"

    print(f"🎬 [Vídeo Local] Absorvendo vídeo local: {p.name}...")

    # Metadados e utilitários da área de transferência
    try:
        from area_transferencia import extrair_metadados_midia, extrair_audio_stream, EXT_VIDEO, EXT_AUDIO
    except ImportError:
        extrair_metadados_midia = None
        extrair_audio_stream = None
        EXT_VIDEO = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v"}
        EXT_AUDIO = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".opus"}

    meta = extrair_metadados_midia(str(p)) if extrair_metadados_midia else {}
    tipo_midia = meta.get("tipo_midia", "desconhecido")
    det = meta.get("detalhes", {})
    ext = p.suffix.lower()

    eh_video = tipo_midia == "video" or ext in EXT_VIDEO
    mime_type = "video/mp4" if eh_video else ("audio/mp3" if ext in EXT_AUDIO else "application/octet-stream")

    dur_str = det.get("duracao_formatada", "Desconhecida")
    if det.get("duracao_segundos"):
        dur_str += f" ({det['duracao_segundos']:.1f}s)"

    # 1. ANEXA O VÍDEO COMPLETO PARA A VISÃO DA AYLA
    if ayla_state:
        imgs = ayla_state.ULTIMAS_IMAGENS_MODULO.get() or []
        imgs.append((str(p), mime_type))
        ayla_state.ULTIMAS_IMAGENS_MODULO.set(imgs)
        if eh_video and hasattr(ayla_state, "ULTIMO_ANEXO_VIDEO"):
            ayla_state.ULTIMO_ANEXO_VIDEO.set(str(p))

    # 2. Extração de áudio e transcrição via Whisper
    transcricao = ""
    metodo_obtencao = "Whisper Audio Transcriber"
    audio_file_path = None
    temp_audio_gerado = False

    if eh_video and extrair_audio_stream:
        print("🎙️ [Vídeo Local] Extraindo faixa de áudio para o Whisper...")
        audio_file_path = extrair_audio_stream(str(p))
        if audio_file_path:
            temp_audio_gerado = True

    if not audio_file_path:
        audio_file_path = str(p)

    transcricao = transcrever_audio_whisper(audio_file_path)

    if temp_audio_gerado and audio_file_path and os.path.exists(audio_file_path):
        try:
            os.remove(audio_file_path)
        except Exception:
            pass

    if not transcricao.strip():
        transcricao = "⚠️ Não foi possível extrair a legenda/transcrição de texto do áudio (verifique a GROQ_API_KEY ou a faixa de áudio). No entanto, o vídeo foi totalmente anexado e enviado para a visão da Ayla!"

    resultado = (
        f"📺 **Informações do Vídeo Local Absorvido:**\n"
        f"• **Arquivo:** `{p.name}`\n"
        f"• **Caminho Local:** `{p}`\n"
        f"• **Tamanho:** {meta.get('tamanho_str', 'N/A')}\n"
        f"• **Duração:** {dur_str}\n"
        f"• **Status de Visão:** 🎥 Vídeo anexado na íntegra para a visão multimodal da Ayla! 👁️\n\n"
        f"📖 **Legenda / Transcrição do Vídeo (Whisper):**\n"
        f"{transcricao}"
    )
    return resultado


def absorver_video(url: str) -> str:
    """
    Absorve o conteúdo de um vídeo por link (URL web/YouTube) ou arquivo local.
    Baixa o vídeo completo em formato MP4 para que a Ayla possa assisti-lo com a visão multimodal,
    e transcreve a legenda/áudio com o Whisper.
    """
    url_limpa = url.strip().strip('"').strip("'")

    # Atalhos para arquivos copiados para a área de transferência ou anexos locais
    if url_limpa.lower() in ["local", "anexo", "clipboard", "area_transferencia", "copiado", "ultimo", ""]:
        caminho_anexo = None
        if ayla_state:
            caminho_anexo = (
                (ayla_state.ULTIMO_ANEXO_VIDEO.get() if hasattr(ayla_state, "ULTIMO_ANEXO_VIDEO") else None)
                or (ayla_state.ULTIMO_ANEXO_AUDIO.get() if hasattr(ayla_state, "ULTIMO_ANEXO_AUDIO") else None)
                or (ayla_state.ULTIMO_ARQUIVO_MIDIA.get() if hasattr(ayla_state, "ULTIMO_ARQUIVO_MIDIA") else None)
            )
        if caminho_anexo:
            url_limpa = caminho_anexo

    # Tratamento de prefixos file://
    if url_limpa.lower().startswith("file:///"):
        url_limpa = url_limpa[8:]
    elif url_limpa.lower().startswith("file://"):
        url_limpa = url_limpa[7:]

    # Verifica se é um caminho de arquivo local existente
    p_local = resolve_path(url_limpa)
    if p_local.exists() and p_local.is_file():
        return absorver_video_local(str(p_local.resolve()))

    video_id = obter_video_id(url_limpa)
    if not video_id:
        video_id = hashlib.md5(url_limpa.encode('utf-8')).hexdigest()[:8]

    # Configuração de diretório do buffer de vídeo
    base_dir = Path(__file__).resolve().parents[2]
    buffer_dir = base_dir / "Buffer de video"
    buffer_dir.mkdir(parents=True, exist_ok=True)

    # 1. Obter metadados do vídeo
    print(f"🎬 [Vídeo] Obtendo metadados para {url_limpa}...")
    ydl_opts_meta = {
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'socket_timeout': 30,
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}}
    }

    titulo = "Vídeo"
    canal = "Desconhecido"
    duracao = 0
    descricao = ""
    info = None

    try:
        _, info, _ = executar_ytdl_com_fallback(ydl_opts_meta, url_limpa, download=False)
        if info:
            titulo = info.get('title', titulo)
            canal = info.get('uploader', canal)
            duracao = info.get('duration', 0)
            descricao = info.get('description', '')
            if not video_id or video_id == hashlib.md5(url_limpa.encode('utf-8')).hexdigest()[:8]:
                video_id = info.get('id', video_id)
    except Exception as e:
        print(f"Aviso ao obter metadados via yt-dlp: {e}")

    # 2. BAIXAR O VÍDEO COMPLETO (.MP4) PARA A VISÃO DA AYLA
    print(f"📥 [Vídeo] Baixando vídeo completo (.mp4) para a visão da Ayla...")
    outtmpl_pattern = str(buffer_dir / f"ayla_vid_{video_id}.%(ext)s")

    ydl_dl_opts = {
        'format': 'bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]/bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/worst[ext=mp4]/worst',
        'outtmpl': outtmpl_pattern,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'socket_timeout': 60,
        'progress_hooks': [progresso_hook],
        'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
        'merge_output_format': 'mp4'
    }

    video_file_path = None
    try:
        executar_ytdl_com_fallback(ydl_dl_opts, url_limpa, download=True)
        arquivos_baixados = list(buffer_dir.glob(f"ayla_vid_{video_id}.*"))
        if arquivos_baixados:
            video_file_path = arquivos_baixados[0]
    except Exception as e_dl:
        print(f"⚠️ Erro ao baixar vídeo com qualidade baixa: {e_dl}. Tentando download básico em menor qualidade...")
        try:
            ydl_dl_opts['format'] = 'bestvideo[height<=360]/best[height<=360]/worst'
            executar_ytdl_com_fallback(ydl_dl_opts, url_limpa, download=True)
            arquivos_baixados = list(buffer_dir.glob(f"ayla_vid_{video_id}.*"))
            if arquivos_baixados:
                video_file_path = arquivos_baixados[0]
        except Exception as e_dl2:
            print(f"❌ Erro fatal ao baixar vídeo: {e_dl2}")

    # 3. REGISTRAR O VÍDEO NA VISÃO MULTIMODAL DA AYLA
    if video_file_path and video_file_path.exists() and ayla_state:
        vid_abs = str(video_file_path.resolve())
        print(f"👁️ [Vídeo] Anexando `{video_file_path.name}` aos olhos/visão da Ayla...")
        imgs = ayla_state.ULTIMAS_IMAGENS_MODULO.get() or []
        imgs.append((vid_abs, "video/mp4"))
        ayla_state.ULTIMAS_IMAGENS_MODULO.set(imgs)

        if hasattr(ayla_state, "ULTIMO_ANEXO_VIDEO"):
            ayla_state.ULTIMO_ANEXO_VIDEO.set(vid_abs)

    # 4. TRANSCRIÇÃO DA FAIXA DE ÁUDIO COM WHISPER
    transcricao = ""
    metodo_obtencao = "Groq Whisper (Faixa de Áudio Baixada)"

    # Se baixou o arquivo de vídeo/áudio, faz a transcrição com Whisper
    if video_file_path and video_file_path.exists():
        transcricao = transcrever_audio_whisper(str(video_file_path))

    # Fallback/Suplemento de legendas do YouTube se o Whisper não retornar texto
    if not transcricao.strip() and obter_video_id(url_limpa):
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            vid_yt_id = obter_video_id(url_limpa)
            api = YouTubeTranscriptApi()
            transcript_list = api.list(vid_yt_id)
            try:
                transcript = transcript_list.find_transcript(['pt', 'en', 'es'])
            except Exception:
                transcript = next(iter(transcript_list))
            dados = transcript.fetch()
            partes = []
            for d in dados:
                if hasattr(d, "text"):
                    partes.append(d.text)
                elif isinstance(d, dict) and "text" in d:
                    partes.append(d["text"])
                else:
                    partes.append(str(d))
            transcricao = " ".join(partes)
            metodo_obtencao = "Legendas do YouTube (YouTube Transcript API)"
        except Exception as e_yt:
            print(f"Aviso legendas YouTube: {e_yt}")

    if not transcricao.strip():
        transcricao = "⚠️ Não foi possível extrair texto de legendas automáticas. Porém, o vídeo foi completamente baixado e enviado para a visão da Ayla!"

    limite_caracteres = 40000
    if len(transcricao) > limite_caracteres:
        transcricao = transcricao[:limite_caracteres] + f"\n\n[...Conteúdo truncado. Mostrados os primeiros {limite_caracteres} caracteres...]"

    resultado = (
        f"📺 **Informações do Vídeo Absorvido:**\n"
        f"• **Título:** {titulo}\n"
        f"• **Canal/Autor:** {canal}\n"
        f"• **Duração:** {duracao} segundos\n"
        f"• **Método de Transcrição:** {metodo_obtencao}\n"
        f"• **Status de Visão:** 🎥 Vídeo completo baixado e anexado aos olhos da Ayla! 👁️\n\n"
        f"📖 **Legenda / Transcrição do Vídeo:**\n"
        f"{transcricao}\n\n"
        f"📝 **Descrição do Vídeo:**\n"
        f"{descricao[:1000] + '...' if len(descricao) > 1000 else descricao}"
    )
    return resultado


TOOL_MAP["absorver_video"] = absorver_video
FUNCTION_DECLARATIONS.append({
    "name": "absorver_video",
    "description": (
        "Absorve e analisa o conteúdo de um vídeo ou áudio, seja por link/URL (YouTube/web) "
        "ou por caminho de arquivo local (ex: .mp4, .mkv, .mp3, .wav ou área de transferência/clipboard). "
        "Baixa o vídeo completo em MP4 para os olhos/visão da Ayla e transcreve a faixa de áudio com o Whisper."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "O link completo do vídeo (http/https) OU o caminho do arquivo local (ou 'clipboard'/'local'/'anexo' para usar a mídia copiada)."
            }
        },
        "required": ["url"]
    }
})
