"""Lê textos, imagens e arquivos copiados para a área de transferência."""
from ayla_platform import IS_WINDOWS, read_clipboard
import tempfile
import os
import sys
import json
import ctypes
import subprocess
import mimetypes
from pathlib import Path
from datetime import datetime

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


# Extensões de mídia reconhecidas
EXT_VIDEO = {
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v",
    ".3gp", ".ogv", ".ts", ".mts", ".m2ts", ".vob", ".3g2", ".mpg",
    ".mpeg", ".m2v", ".divx", ".asf", ".f4v", ".rm", ".rmvb"
}
EXT_AUDIO = {
    ".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".opus", ".wma",
    ".aiff", ".m4r", ".mp2", ".amr", ".alac", ".ape", ".caf", ".oga",
    ".mid", ".midi", ".ac3"
}
EXT_IMAGEM = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".tif",
    ".ico", ".heic", ".svg", ".avif"
}


def tamanho_formatado(tamanho_bytes: int) -> str:
    """Formata o tamanho em bytes para uma string legível (B, KB, MB, GB, TB)."""
    if tamanho_bytes is None or tamanho_bytes < 0:
        return "0 B"
    num = float(tamanho_bytes)
    for unidade in ['B', 'KB', 'MB', 'GB', 'TB']:
        if num < 1024.0:
            return f"{num:.2f} {unidade}"
        num /= 1024.0
    return f"{num:.2f} PB"


def formatar_duracao(segundos: float) -> str:
    """Formata duração em segundos para HH:MM:SS ou MM:SS."""
    if segundos is None or segundos < 0:
        return "Desconhecida"
    total_seg = int(round(segundos))
    horas = total_seg // 3600
    minutos = (total_seg % 3600) // 60
    segs = total_seg % 60
    if horas > 0:
        return f"{horas:02d}:{minutos:02d}:{segs:02d}"
    else:
        return f"{minutos:02d}:{segs:02d}"


def classificar_resolucao(largura: int, altura: int) -> str:
    """Retorna uma classificação amigável para resoluções de vídeo e imagem."""
    if not largura or not altura:
        return ""
    w, h = largura, altura
    pixels = w * h

    orientacao = "Horizontal (Landscape)"
    if h > w:
        orientacao = "Vertical (TikTok/Reels/Shorts)"
    elif h == w:
        orientacao = "Quadrada (1:1)"

    if pixels >= 3840 * 2160:
        padrao = "4K Ultra HD"
    elif pixels >= 2560 * 1440:
        padrao = "2K / 1440p QHD"
    elif pixels >= 1920 * 1080:
        padrao = "1080p Full HD"
    elif pixels >= 1280 * 720:
        padrao = "720p HD"
    elif pixels >= 854 * 480:
        padrao = "480p SD"
    else:
        padrao = f"{min(w, h)}p"

    return f"{w}x{h} ({padrao} • {orientacao})"


def extrair_snapshot_video(caminho_video: str, posicao_relativa: float = 0.3) -> tuple[bytes | None, str | None]:
    """
    Extrai um frame (snapshot visual) de um arquivo de vídeo local como bytes (JPEG).
    Tenta primeiro via OpenCV (cv2) e faz fallback para FFmpeg se necessário.
    Retorna uma tupla (bytes_imagem, mime_type) ou (None, None).
    """
    caminho_path = Path(caminho_video)
    if not caminho_path.exists():
        return None, None

    # 1. Tentativa via OpenCV (cv2)
    try:
        import cv2
        cap = cv2.VideoCapture(str(caminho_path.resolve()))
        if cap.isOpened():
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames > 0:
                frame_alvo = max(0, int(total_frames * posicao_relativa))
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_alvo)

            ret, frame = cap.read()
            if not ret or frame is None:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = cap.read()

            cap.release()

            if ret and frame is not None:
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 85]
                sucesso, buffer = cv2.imencode('.jpg', frame, encode_param)
                if sucesso:
                    return buffer.tobytes(), "image/jpeg"
    except Exception as e:
        print(f"Aviso cv2 snapshot: {e}")

    # 2. Fallback via FFmpeg
    try:
        cmd = [
            "ffmpeg", "-ss", "00:00:01",
            "-i", str(caminho_path.resolve()),
            "-vframes", "1",
            "-f", "image2pipe",
            "-vcodec", "mjpeg",
            "pipe:1"
        ]
        creationflags = 0x08000000 if os.name == 'nt' else 0
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
            timeout=10
        )
        if proc.returncode == 0 and proc.stdout:
            return proc.stdout, "image/jpeg"
    except Exception as e:
        print(f"Aviso ffmpeg snapshot: {e}")

    return None, None


def extrair_audio_stream(caminho_video: str, arquivo_saida_wav: str = None) -> str | None:
    """
    Extrai a faixa de áudio de um vídeo local e salva como arquivo .wav/.mp3 temporário
    pronto para ser lido/transcrito por ferramentas locais como absorver_video ou Whisper.
    """
    caminho_path = Path(caminho_video)
    if not caminho_path.exists():
        return None

    if not arquivo_saida_wav:
        import tempfile
        import hashlib
        temp_dir = Path(tempfile.gettempdir())
        vid_id = hashlib.md5(str(caminho_path.resolve()).encode('utf-8')).hexdigest()[:8]
        arquivo_saida_wav = str(temp_dir / f"ayla_audio_stream_{vid_id}.wav")

    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(caminho_path.resolve()),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            arquivo_saida_wav
        ]
        creationflags = 0x08000000 if os.name == 'nt' else 0
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
            timeout=30
        )
        if proc.returncode == 0 and os.path.exists(arquivo_saida_wav):
            return arquivo_saida_wav
    except Exception as e:
        print(f"Erro extrair_audio_stream ffmpeg: {e}")

    return None



def extrair_metadados_midia(caminho: str) -> dict:
    """
    Extrai metadados completos de um arquivo de mídia (vídeo, áudio ou imagem)
    utilizando ffprobe (se disponível) com fallbacks para cv2, PIL e wave.
    """
    caminho_path = Path(caminho)
    if not caminho_path.exists():
        return {"erro": f"Arquivo não encontrado: {caminho}"}

    ext = caminho_path.suffix.lower()
    tamanho_bytes = caminho_path.stat().st_size
    tamanho_str = tamanho_formatado(tamanho_bytes)
    data_modificacao = datetime.fromtimestamp(caminho_path.stat().st_mtime).strftime("%d/%m/%Y %H:%M:%S")

    tipo_midia = "desconhecido"
    if ext in EXT_VIDEO:
        tipo_midia = "video"
    elif ext in EXT_AUDIO:
        tipo_midia = "audio"
    elif ext in EXT_IMAGEM:
        tipo_midia = "imagem"

    info = {
        "nome": caminho_path.name,
        "caminho": str(caminho_path.resolve()),
        "extensao": ext,
        "tamanho_bytes": tamanho_bytes,
        "tamanho_str": tamanho_str,
        "data_modificacao": data_modificacao,
        "tipo_midia": tipo_midia,
        "detalhes": {}
    }

    # 1. Tentativa via ffprobe
    ffprobe_ok = False
    try:
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format", "-show_streams",
            str(caminho_path)
        ]
        creationflags = 0x08000000 if os.name == 'nt' else 0
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            creationflags=creationflags
        )
        if proc.returncode == 0 and proc.stdout.strip():
            dados_ffprobe = json.loads(proc.stdout)
            fmt = dados_ffprobe.get("format", {})
            streams = dados_ffprobe.get("streams", [])

            duracao_sec = None
            if "duration" in fmt:
                try:
                    duracao_sec = float(fmt["duration"])
                except (ValueError, TypeError):
                    pass

            bitrate_total = None
            if "bit_rate" in fmt:
                try:
                    bitrate_total = int(fmt["bit_rate"]) // 1000
                except (ValueError, TypeError):
                    pass

            info["detalhes"]["duracao_segundos"] = duracao_sec
            info["detalhes"]["duracao_formatada"] = formatar_duracao(duracao_sec) if duracao_sec is not None else None
            info["detalhes"]["bitrate_kbps"] = bitrate_total
            info["detalhes"]["formato_longo"] = fmt.get("format_long_name") or fmt.get("format_name")

            tags = fmt.get("tags", {})
            if tags:
                tag_dict = {k.lower(): v for k, v in tags.items()}
                if "title" in tag_dict: info["detalhes"]["titulo"] = tag_dict["title"]
                if "artist" in tag_dict: info["detalhes"]["artista"] = tag_dict["artist"]
                if "album" in tag_dict: info["detalhes"]["album"] = tag_dict["album"]
                if "genre" in tag_dict: info["detalhes"]["genero"] = tag_dict["genre"]
                if "track" in tag_dict: info["detalhes"]["faixa"] = tag_dict["track"]
                if "date" in tag_dict or "year" in tag_dict:
                    info["detalhes"]["ano"] = tag_dict.get("date") or tag_dict.get("year")

            video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
            audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

            if video_stream:
                if info["tipo_midia"] == "desconhecido":
                    info["tipo_midia"] = "video"
                info["detalhes"]["video_codec"] = video_stream.get("codec_name")
                w = video_stream.get("width")
                h = video_stream.get("height")
                if w and h:
                    info["detalhes"]["largura"] = w
                    info["detalhes"]["altura"] = h
                    info["detalhes"]["resolucao"] = classificar_resolucao(w, h)

                r_fps = video_stream.get("r_frame_rate", "")
                if "/" in r_fps:
                    try:
                        num, den = map(float, r_fps.split("/"))
                        if den > 0:
                            info["detalhes"]["fps"] = round(num / den, 2)
                    except Exception:
                        pass

                dar = video_stream.get("display_aspect_ratio")
                if dar and dar != "N/A":
                    info["detalhes"]["proporcao_tela"] = dar

                nb_frames = video_stream.get("nb_frames")
                if nb_frames and nb_frames != "N/A":
                    try:
                        info["detalhes"]["total_quadros"] = int(nb_frames)
                    except Exception:
                        pass

            if audio_stream:
                if info["tipo_midia"] == "desconhecido" and not video_stream:
                    info["tipo_midia"] = "audio"
                info["detalhes"]["audio_codec"] = audio_stream.get("codec_name")
                info["detalhes"]["canais"] = audio_stream.get("channels")
                try:
                    s_rate = int(audio_stream.get("sample_rate", 0))
                    info["detalhes"]["amostragem_hz"] = s_rate
                    info["detalhes"]["amostragem_khz"] = f"{s_rate / 1000:.1f} kHz"
                except Exception:
                    pass

                bits = audio_stream.get("bits_per_raw_sample") or audio_stream.get("bits_per_sample")
                if bits and str(bits) != "0":
                    info["detalhes"]["profundidade_bits"] = f"{bits} bits"

            ffprobe_ok = True
    except Exception as e:
        print(f"Aviso ffprobe: {e}")

    # 2. Fallbacks secundários (cv2, PIL, wave)
    if not ffprobe_ok or not info["detalhes"].get("resolucao"):
        if info["tipo_midia"] == "video":
            try:
                import cv2
                cap = cv2.VideoCapture(str(caminho_path))
                if cap.isOpened():
                    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                    cap.release()

                    if width > 0 and height > 0:
                        info["detalhes"]["largura"] = width
                        info["detalhes"]["altura"] = height
                        info["detalhes"]["resolucao"] = classificar_resolucao(width, height)
                    if fps > 0:
                        info["detalhes"]["fps"] = round(fps, 2)
                    if fps > 0 and frame_count > 0:
                        dur_sec = frame_count / fps
                        info["detalhes"]["duracao_segundos"] = dur_sec
                        info["detalhes"]["duracao_formatada"] = formatar_duracao(dur_sec)
                        info["detalhes"]["total_quadros"] = int(frame_count)
            except Exception as e:
                print(f"Aviso cv2 fallback: {e}")

        elif info["tipo_midia"] == "imagem":
            try:
                from PIL import Image, ExifTags
                with Image.open(caminho_path) as img:
                    w, h = img.width, img.height
                    info["detalhes"]["largura"] = w
                    info["detalhes"]["altura"] = h
                    info["detalhes"]["resolucao"] = classificar_resolucao(w, h)
                    info["detalhes"]["formato_imagem"] = img.format
                    info["detalhes"]["modo_cor"] = img.mode

                    try:
                        exif = img._getexif()
                        if exif:
                            exif_dict = {}
                            for tag, val in exif.items():
                                tag_name = ExifTags.TAGS.get(tag, tag)
                                if tag_name in ['Make', 'Model', 'DateTimeOriginal', 'ExposureTime', 'FNumber', 'ISOSpeedRatings']:
                                    exif_dict[tag_name] = str(val)
                            if exif_dict:
                                info["detalhes"]["exif"] = exif_dict
                    except Exception:
                        pass
            except Exception as e:
                print(f"Aviso PIL fallback: {e}")

        elif info["tipo_midia"] == "audio" and ext == ".wav":
            try:
                import wave
                with wave.open(str(caminho_path), 'rb') as w:
                    nchannels = w.getnchannels()
                    framerate = w.getframerate()
                    nframes = w.getnframes()
                    dur_sec = nframes / float(framerate) if framerate > 0 else 0
                    info["detalhes"]["duracao_segundos"] = dur_sec
                    info["detalhes"]["duracao_formatada"] = formatar_duracao(dur_sec)
                    info["detalhes"]["canais"] = nchannels
                    info["detalhes"]["amostragem_hz"] = framerate
                    info["detalhes"]["amostragem_khz"] = f"{framerate / 1000:.1f} kHz"
            except Exception as e:
                print(f"Aviso wave fallback: {e}")

    return info


def processar_pasta_clipboard(pasta_path: str) -> str:
    """
    Processa um caminho de diretório/pasta copiado para a área de transferência,
    mapeando arquivos de mídia e apresentando um relatório detalhado.
    """
    p = Path(pasta_path)
    if not p.is_dir():
        return f"⚠️ **Diretório não encontrado:** `{pasta_path}`"

    videos, audios, imagens, outros = [], [], [], []
    for item in p.rglob("*"):
        if item.is_file():
            ext = item.suffix.lower()
            if ext in EXT_VIDEO:
                videos.append(item)
            elif ext in EXT_AUDIO:
                audios.append(item)
            elif ext in EXT_IMAGEM:
                imagens.append(item)
            else:
                outros.append(item)

    total_arquivos = len(videos) + len(audios) + len(imagens) + len(outros)

    linhas = [
        f"📁 **Pasta copiada para a Área de Transferência (Ctrl+C):** `{p.name}`",
        f"• 📍 **Caminho:** `{p.resolve()}`",
        f"• 📊 **Conteúdo Total:** {total_arquivos} arquivos"
    ]
    if videos:
        linhas.append(f"  🎬 **Vídeos ({len(videos)}):** " + ", ".join([f"`{v.name}`" for v in videos[:5]]) + ("..." if len(videos) > 5 else ""))
        if ayla_state and hasattr(ayla_state, "ULTIMO_ANEXO_VIDEO"):
            ayla_state.ULTIMO_ANEXO_VIDEO.set(str(videos[0].resolve()))
    if audios:
        linhas.append(f"  🎵 **Áudios ({len(audios)}):** " + ", ".join([f"`{a.name}`" for a in audios[:5]]) + ("..." if len(audios) > 5 else ""))
        if ayla_state and hasattr(ayla_state, "ULTIMO_ANEXO_AUDIO"):
            ayla_state.ULTIMO_ANEXO_AUDIO.set(str(audios[0].resolve()))
    if imagens:
        linhas.append(f"  🖼️ **Imagens ({len(imagens)}):** " + ", ".join([f"`{i.name}`" for i in imagens[:5]]) + ("..." if len(imagens) > 5 else ""))

    linhas.append("\n💖 *usuario Usuario, examinei a pasta que você copiou! Se quiser analisar um arquivo de mídia específico dentro dela, basta me pedir!*")
    return "\n".join(linhas)


def processar_arquivo_clipboard(arquivo_path: str) -> str:
    """
    Processa um caminho de arquivo capturado da área de transferência,
    extrai seus metadados (se for mídia) e anexa ao estado da Ayla.
    """
    p = Path(arquivo_path)
    if not p.exists():
        return f"⚠️ **Arquivo não encontrado:** `{arquivo_path}`"

    if p.is_dir():
        return processar_pasta_clipboard(arquivo_path)

    meta = extrair_metadados_midia(arquivo_path)
    tipo_midia = meta.get("tipo_midia", "desconhecido")
    det = meta.get("detalhes", {})

    if tipo_midia == "video":
        if ayla_state:
            if hasattr(ayla_state, "ULTIMO_ANEXO_VIDEO"):
                ayla_state.ULTIMO_ANEXO_VIDEO.set(str(p.resolve()))
            if hasattr(ayla_state, "ULTIMO_ARQUIVO_MIDIA"):
                ayla_state.ULTIMO_ARQUIVO_MIDIA.set(str(p.resolve()))

        # Anexa o vídeo completo (caminho + mime) ao fluxo multimodal da Z.ai
        mime_video, _ = mimetypes.guess_type(str(p.resolve()))
        mime_video = mime_video or "video/mp4"
        if ayla_state:
            imgs = ayla_state.ULTIMAS_IMAGENS_MODULO.get() or []
            imgs.append((str(p.resolve()), mime_video))
            ayla_state.ULTIMAS_IMAGENS_MODULO.set(imgs)

        linhas = [
            f"🎬 **Vídeo copiado para a Área de Transferência (Ctrl+C):** `{p.name}`",
            f"• 📍 **Caminho:** `{p.resolve()}`",
            f"• 📏 **Tamanho:** {meta['tamanho_str']}",
            f"• 📅 **Modificado em:** {meta['data_modificacao']}"
        ]
        if det.get("duracao_formatada"):
            dur_str = det['duracao_formatada']
            if det.get("duracao_segundos"):
                dur_str += f" ({det['duracao_segundos']:.1f}s)"
            linhas.append(f"• ⏱️ **Duração:** {dur_str}")
        if det.get("resolucao"):
            res_str = det['resolucao']
            if det.get("proporcao_tela"):
                res_str += f" ({det['proporcao_tela']})"
            linhas.append(f"• 🖥️ **Resolução:** {res_str}")
        if det.get("fps"):
            linhas.append(f"• 🎞️ **Taxa de Quadros:** {det['fps']} FPS")
        if det.get("video_codec"):
            linhas.append(f"• 🧩 **Codec de Vídeo:** {det['video_codec']}")
        if det.get("audio_codec"):
            aud_str = det['audio_codec']
            if det.get("amostragem_khz"):
                aud_str += f", {det['amostragem_khz']}"
            if det.get("canais"):
                aud_str += f" ({det['canais']} canais)"
            linhas.append(f"• 🎵 **Áudio Embutido:** {aud_str}")
        if det.get("bitrate_kbps"):
            linhas.append(f"• 📊 **Bitrate Total:** {det['bitrate_kbps']} kbps")
        if det.get("titulo"):
            linhas.append(f"• 🏷️ **Título:** {det['titulo']}")

        linhas.append("• 📹 **Vídeo Completo Anexado:** O vídeo completo foi anexado diretamente ao meu sistema (Z.ai GLM) para análise completa! 👁️🎙️")

        linhas.append(
            "\n💖 *usuario Usuario, anexei o vídeo completo aos meus olhos e ouvidos!* "
            "Você já pode me fazer qualquer pergunta sobre o vídeo inteiro!"
        )
        return "\n".join(linhas)

    elif tipo_midia == "audio":
        if ayla_state:
            if hasattr(ayla_state, "ULTIMO_ANEXO_AUDIO"):
                ayla_state.ULTIMO_ANEXO_AUDIO.set(str(p.resolve()))
            if hasattr(ayla_state, "ULTIMO_ARQUIVO_MIDIA"):
                ayla_state.ULTIMO_ARQUIVO_MIDIA.set(str(p.resolve()))

        linhas = [
            f"🎵 **Áudio copiado para a Área de Transferência (Ctrl+C):** `{p.name}`",
            f"• 📍 **Caminho:** `{p.resolve()}`",
            f"• 📏 **Tamanho:** {meta['tamanho_str']}",
            f"• 📅 **Modificado em:** {meta['data_modificacao']}"
        ]
        if det.get("duracao_formatada"):
            dur_str = det['duracao_formatada']
            if det.get("duracao_segundos"):
                dur_str += f" ({det['duracao_segundos']:.1f}s)"
            linhas.append(f"• ⏱️ **Duração:** {dur_str}")
        if det.get("audio_codec"):
            linhas.append(f"• 🧩 **Codec:** {det['audio_codec']}")
        if det.get("canais"):
            c_str = f"{det['canais']} canais"
            if det['canais'] == 1: c_str = "Mono (1 canal)"
            elif det['canais'] == 2: c_str = "Estéreo (2 canais)"
            elif det['canais'] >= 6: c_str = f"Surround {det['canais']}.1"
            linhas.append(f"• 🔊 **Canais:** {c_str}")
        if det.get("amostragem_khz"):
            linhas.append(f"• 🎚️ **Amostragem:** {det['amostragem_khz']}")
        if det.get("profundidade_bits"):
            linhas.append(f"• 🔢 **Profundidade de Bits:** {det['profundidade_bits']}")
        if det.get("bitrate_kbps"):
            linhas.append(f"• 📊 **Bitrate:** {det['bitrate_kbps']} kbps")

        tags_str = []
        if det.get("titulo"): tags_str.append(f"Título: {det['titulo']}")
        if det.get("artista"): tags_str.append(f"Artista: {det['artista']}")
        if det.get("album"): tags_str.append(f"Álbum: {det['album']}")
        if det.get("genero"): tags_str.append(f"Gênero: {det['genero']}")
        if det.get("ano"): tags_str.append(f"Ano: {det['ano']}")
        if tags_str:
            linhas.append(f"• 🏷️ **Metadados / ID3:** {', '.join(tags_str)}")

        linhas.append(
            "\n💖 *usuario Usuario, o áudio foi registrado no meu sistema!* "
            "Diga o que deseja fazer com ele (ex: **transcrever voz, analisar som, converter formato**)."
        )
        return "\n".join(linhas)

    elif tipo_midia == "imagem":
        try:
            bytes_img = p.read_bytes()
            mime, _ = mimetypes.guess_type(str(p))
            mime = mime or "image/png"
            if ayla_state:
                imgs = ayla_state.ULTIMAS_IMAGENS_MODULO.get() or []
                imgs.append((bytes_img, mime))
                ayla_state.ULTIMAS_IMAGENS_MODULO.set(imgs)
                if hasattr(ayla_state, "ULTIMO_ANEXO_IMAGEM"):
                    ayla_state.ULTIMO_ANEXO_IMAGEM.set((bytes_img, mime))
        except Exception as e_img:
            print(f"Aviso ao carregar bytes da imagem {p.name}: {e_img}")

        linhas = [
            f"🖼️ **Imagem copiada para a Área de Transferência (Ctrl+C):** `{p.name}`",
            f"• 📍 **Caminho:** `{p.resolve()}`",
            f"• 📏 **Tamanho:** {meta['tamanho_str']}",
            f"• 📅 **Modificado em:** {meta['data_modificacao']}"
        ]
        if det.get("resolucao"):
            linhas.append(f"• 📐 **Resolução:** {det['resolucao']}")
        if det.get("formato_imagem"):
            modo_str = f" ({det['modo_cor']})" if det.get("modo_cor") else ""
            linhas.append(f"• 🎨 **Formato / Cor:** {det['formato_imagem']}{modo_str}")
        if det.get("exif"):
            exif_items = [f"{k}: {v}" for k, v in det["exif"].items()]
            linhas.append(f"• 📷 **Câmera/EXIF:** {', '.join(exif_items)}")

        linhas.append("\n💖 *usuario Usuario, a imagem foi anexada diretamente aos meus olhos! Pode me fazer perguntas sobre ela!*")
        return "\n".join(linhas)

    else:
        linhas = [
            f"📂 **Arquivo copiado para a Área de Transferência (Ctrl+C):** `{p.name}`",
            f"• 📍 **Caminho:** `{p.resolve()}`",
            f"• 📏 **Tamanho:** {meta['tamanho_str']}",
            f"• 📎 **Extensão:** {p.suffix if p.suffix else 'Sem extensão'}",
            f"• 📅 **Modificado em:** {meta['data_modificacao']}"
        ]
        if meta['tamanho_bytes'] < 50000:
            try:
                conteudo = p.read_text(encoding="utf-8", errors="ignore").strip()
                if conteudo:
                    if len(conteudo) > 1000:
                        conteudo = conteudo[:1000] + "\n... [Truncado]"
                    linhas.append(f"\n📝 **Prévia do Conteúdo:**\n```\n{conteudo}\n```")
            except Exception:
                pass

        linhas.append("\n💡 *usuario Usuario, você pode me pedir para ler ou processar o conteúdo completo deste arquivo com a ferramenta `ler_arquivo`.*")
        return "\n".join(linhas)


def ler_clipboard_ctypes() -> tuple[str, any]:
    """
    Fallback usando Win32 CAPI (ctypes) para ler o clipboard caso o pywin32 falhe.
    Retorna ('files', list_of_paths) ou ('text', string_text) ou (None, None).
    """
    if not IS_WINDOWS:
        return None, None
    user32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32

    CF_HDROP = 15
    CF_UNICODETEXT = 13

    if not user32.OpenClipboard(None):
        return None, None

    try:
        if user32.IsClipboardFormatAvailable(CF_HDROP):
            hdrop = user32.GetClipboardData(CF_HDROP)
            if hdrop:
                count = shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
                arquivos = []
                for i in range(count):
                    buf_len = shell32.DragQueryFileW(hdrop, i, None, 0)
                    buf = ctypes.create_unicode_buffer(buf_len + 1)
                    shell32.DragQueryFileW(hdrop, i, buf, buf_len + 1)
                    arquivos.append(buf.value)
                if arquivos:
                    return "files", arquivos

        if user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            hglobal = user32.GetClipboardData(CF_UNICODETEXT)
            if hglobal:
                user32.GlobalLock.restype = ctypes.c_wchar_p
                ptr = user32.GlobalLock(hglobal)
                if ptr:
                    texto = str(ptr)
                    user32.GlobalUnlock(hglobal)
                    return "text", texto
    except Exception as e:
        print(f"Aviso ctypes clipboard: {e}")
    finally:
        user32.CloseClipboard()

    return None, None


def ler_area_transferencia() -> str:
    """
    Lê o conteúdo atual da área de transferência (Ctrl+C).
    Consegue ler:
    1. Imagens copiadas diretamente (prints, navegador, área de transferência).
    2. Arquivos de mídia copiados no Explorer ou via caminho de texto (vídeos .mp4, áudios .mp3/.wav, imagens),
       extraindo metadados completos (duração, resolução, codecs, taxa de bits, tags)
       e anexando os arquivos ao estado interno da Ayla para a usuario Usuario.
    3. Pastas inteiras contendo mídia.
    4. Arquivos gerais copiados (caminho, metadados e prévia).
    5. Textos puros copiados (com estatísticas de linhas e caracteres).
    """
    if not IS_WINDOWS:
        try:
            kind, data = read_clipboard()
            if kind == 'files':
                return '\n\n---\n\n'.join(processar_arquivo_clipboard(p) for p in data) or 'Nenhum arquivo local copiado.'
            if kind == 'image':
                if ayla_state:
                    images = ayla_state.ULTIMAS_IMAGENS_MODULO.get() or []
                    images.append((data, 'image/png'))
                    ayla_state.ULTIMAS_IMAGENS_MODULO.set(images)
                    ayla_state.ULTIMO_ANEXO_IMAGEM.set((data, 'image/png'))
                return '🖼️ Imagem da área de transferência anexada para análise.'
            if kind == 'text':
                paths = [line.strip().strip('"') for line in data.splitlines() if line.strip()]
                if paths and all(Path(p).is_absolute() and Path(p).exists() for p in paths):
                    return '\n\n---\n\n'.join(processar_arquivo_clipboard(p) for p in paths)
                return '📝 Texto copiado:\n' + data[:10000]
            return 'Área de transferência vazia ou formato não suportado.'
        except Exception as exc:
            return f'Não foi possível ler o clipboard: {exc}. Use wl-clipboard no Wayland ou xclip no X11.'
    # 1. Tenta ler imagem pura na área de transferência (PrintScreen, Cópia Web)
    try:
        from PIL import ImageGrab
        imagem = ImageGrab.grabclipboard()
        if imagem and hasattr(imagem, 'save'):
            pasta_temp = tempfile.gettempdir()
            os.makedirs(pasta_temp, exist_ok=True)
            caminho_img = os.path.join(pasta_temp, "ayla_clipboard.png")
            imagem.save(caminho_img, "PNG")

            with open(caminho_img, "rb") as f:
                bytes_img = f.read()

            tamanho_str = tamanho_formatado(len(bytes_img))
            largura, altura = imagem.size
            modo = getattr(imagem, 'mode', 'RGB')
            res_classificacao = classificar_resolucao(largura, altura)

            if ayla_state:
                imagens_atuais = ayla_state.ULTIMAS_IMAGENS_MODULO.get() or []
                imagens_atuais.append((bytes_img, "image/png"))
                ayla_state.ULTIMAS_IMAGENS_MODULO.set(imagens_atuais)
                if hasattr(ayla_state, "ULTIMO_ANEXO_IMAGEM"):
                    ayla_state.ULTIMO_ANEXO_IMAGEM.set((bytes_img, "image/png"))

            return (
                f"🖼️ **Imagem copiada da Área de Transferência (Ctrl+C):**\n"
                f"• 📏 **Tamanho:** {tamanho_str}\n"
                f"• 📐 **Resolução:** {res_classificacao}\n"
                f"• 🎨 **Formato / Modo:** PNG ({modo})\n\n"
                f"💖 *usuario Usuario, capturei a imagem da sua área de transferência e já anexei aos meus olhos! Diga o que deseja que eu faça com ela!*"
            )
    except Exception as e:
        print(f"Aviso ao tentar ler imagem do clipboard com PIL: {e}")

    # 2. Tenta via pywin32
    win32_ok = False
    resultado = None

    try:
        import win32clipboard
        win32clipboard.OpenClipboard()
        try:
            if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_HDROP):
                dados = win32clipboard.GetClipboardData(win32clipboard.CF_HDROP)
                if dados:
                    blocos = [processar_arquivo_clipboard(f) for f in dados]
                    resultado = "\n\n---\n\n".join(blocos)
                    win32_ok = True
            elif win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                dados = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                if dados:
                    texto = str(dados).strip()
                    linhas = [l.strip().strip('"').strip("'") for l in texto.splitlines() if l.strip()]
                    caminhos_cand = []
                    for l in linhas:
                        cand = l
                        if cand.lower().startswith("file:///"):
                            cand = cand[8:]
                        elif cand.lower().startswith("file://"):
                            cand = cand[7:]
                        caminhos_cand.append(cand)

                    arquivos_validos = [c for c in caminhos_cand if Path(c).exists()]
                    if arquivos_validos and len(arquivos_validos) == len(caminhos_cand):
                        blocos = [processar_arquivo_clipboard(c) for c in arquivos_validos]
                        resultado = "\n\n---\n\n".join(blocos)
                        win32_ok = True
                    else:
                        tamanho_char = len(texto)
                        linhas_count = len(texto.splitlines())
                        palavras_count = len(texto.split())

                        texto_exibicao = texto
                        if len(texto_exibicao) > 10000:
                            texto_exibicao = texto_exibicao[:10000] + "\n... [Texto truncado]"

                        resultado = (
                            f"📝 **Texto copiado da Área de Transferência (Ctrl+C):**\n"
                            f"📊 *Estatísticas:* {tamanho_char:,} caracteres, {palavras_count:,} palavras, {linhas_count:,} linhas.\n\n"
                            f"```\n{texto_exibicao}\n```"
                        )
                        win32_ok = True
        finally:
            win32clipboard.CloseClipboard()
    except Exception as e_win32:
        print(f"Aviso pywin32 clipboard: {e_win32}")

    # 3. Fallback via ctypes se pywin32 não funcionou ou falhou
    if not win32_ok or not resultado:
        tipo, dados = ler_clipboard_ctypes()
        if tipo == "files" and dados:
            blocos = [processar_arquivo_clipboard(f) for f in dados]
            resultado = "\n\n---\n\n".join(blocos)
        elif tipo == "text" and dados:
            texto = str(dados).strip()
            linhas = [l.strip().strip('"').strip("'") for l in texto.splitlines() if l.strip()]
            caminhos_cand = []
            for l in linhas:
                cand = l
                if cand.lower().startswith("file:///"):
                    cand = cand[8:]
                elif cand.lower().startswith("file://"):
                    cand = cand[7:]
                caminhos_cand.append(cand)

            arquivos_validos = [c for c in caminhos_cand if Path(c).exists()]
            if arquivos_validos and len(arquivos_validos) == len(caminhos_cand):
                blocos = [processar_arquivo_clipboard(c) for c in arquivos_validos]
                resultado = "\n\n---\n\n".join(blocos)
            else:
                tamanho_char = len(texto)
                linhas_count = len(texto.splitlines())
                palavras_count = len(texto.split())

                texto_exibicao = texto
                if len(texto_exibicao) > 10000:
                    texto_exibicao = texto_exibicao[:10000] + "\n... [Texto truncado]"

                resultado = (
                    f"📝 **Texto copiado da Área de Transferência (Ctrl+C):**\n"
                    f"📊 *Estatísticas:* {tamanho_char:,} caracteres, {palavras_count:,} palavras, {linhas_count:,} linhas.\n\n"
                    f"```\n{texto_exibicao}\n```"
                )

    if not resultado:
        resultado = "📋 A área de transferência está vazia ou contém um formato não suportado."

    return resultado


TOOL_MAP["ler_area_transferencia"] = ler_area_transferencia

FUNCTION_DECLARATIONS.append({
    "name": "ler_area_transferencia",
    "description": "Lê o conteúdo da área de transferência (Ctrl+C) do sistema. Suporta textos, prints de imagem e arquivos/pastas de mídia (vídeos .mp4, áudios .mp3/.wav, fotos), extraindo metadados detalhados (duração, resolução, codecs, taxa de bits) e anexando os arquivos ao estado da Ayla para a usuario Usuario.",
    "parameters": {
        "type": "object",
        "properties": {}
    }
})
