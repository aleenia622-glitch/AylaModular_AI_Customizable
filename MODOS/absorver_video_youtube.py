import os
import re
import sys
import time
import tempfile
from pathlib import Path
import yt_dlp

# Garante compatibilidade se o arquivo for executado/importado individualmente
if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

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
    if d['status'] == 'downloading':
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
                sys.stdout.write(f"\r📥 [YouTube] Progresso: [{barra}] {percent:.1f}% ({speed_str}, ETA: {eta_str})")
                sys.stdout.flush()
            except Exception:
                try:
                    sys.stdout.write(f"\r[YouTube] Progresso: [{barra}] {percent:.1f}% ({speed_str}, ETA: {eta_str})")
                    sys.stdout.flush()
                except Exception:
                    pass
    elif d['status'] == 'finished':
        try:
            sys.stdout.write("\r📥 [YouTube] Download concluído! Processando arquivo...               \n")
            sys.stdout.flush()
        except Exception:
            try:
                sys.stdout.write("\r[YouTube] Download concluído! Processando arquivo...               \n")
                sys.stdout.flush()
            except Exception:
                pass

def absorver_video_youtube(url: str, pergunta: str = "") -> str:
    """
    Absorve o conteúdo de um vídeo do YouTube através do link (URL).
    Analisa as legendas do vídeo ou o áudio dele para responder a perguntas
    ou descrever o que é falado no vídeo.
    """
    url_limpa = url.strip()
    video_id = obter_video_id(url_limpa)
    if not video_id:
        return "⚠️ Não consegui extrair o ID do vídeo a partir deste link. Por favor, envie um link válido do YouTube!"

    # 1. Obter metadados do vídeo usando yt-dlp
    print(f"🎬 [YouTube] Obtendo metadados para o vídeo ID {video_id}...")
    ydl_opts = {
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'socket_timeout': 30,
        'extractor_args': {'youtube': {'player_client': ['android']}}
    }
    
    titulo = "Vídeo do YouTube"
    canal = "Desconhecido"
    duracao = 0
    descricao = ""
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url_limpa, download=False)
            titulo = info.get('title', titulo)
            canal = info.get('uploader', canal)
            duracao = info.get('duration', 0)
            descricao = info.get('description', '')
    except Exception as e:
        print(f"Aviso ao obter metadados via yt-dlp: {e}")

    # 2. Tentar obter a transcrição/legendas do vídeo
    transcricao = ""
    metodo_obtencao = "Legendas de texto automáticas/manuais"
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        api = YouTubeTranscriptApi()
        transcript_list = api.list(video_id)
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
    except Exception as e:
        print(f"Não foi possível obter legendas de texto automáticas/manuais: {e}")

    # 3. Fallback: Se não tem transcrição de texto, baixar áudio e transcrever se o vídeo for curto (<= 10 minutos)
    if not transcricao.strip():
        if duracao > 0 and duracao <= 600:
            print(f"🎙️ [YouTube] Sem legendas de texto para vídeo de {duracao}s. Baixando áudio para transcrever...")
            
            temp_dir = Path(tempfile.gettempdir())
            audio_out = temp_dir / f"ayla_audio_yt_{video_id}.%(ext)s"
            
            ydl_dl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': str(audio_out),
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True,
                'socket_timeout': 30,
                'progress_hooks': [progresso_hook],
                'extractor_args': {'youtube': {'player_client': ['android']}}
            }
            
            audio_file_path = None
            try:
                with yt_dlp.YoutubeDL(ydl_dl_opts) as ydl:
                    ydl.download([url_limpa])
                
                arquivos_baixados = list(temp_dir.glob(f"ayla_audio_yt_{video_id}.*"))
                if arquivos_baixados:
                    audio_file_path = arquivos_baixados[0]
                    
                    # Usar Google Gemini File API para transcrição (disponível tanto no modo genai quanto openrouter)
                    metodo_obtencao = "Transcrição de áudio via Inteligência Artificial (Gemini)"
                    bot_ref = globals().get("bot")
                    if bot_ref and hasattr(bot_ref, "genai_client") and bot_ref.genai_client:
                        client = bot_ref.genai_client
                        
                        print("☁️ Fazendo upload do áudio para o Gemini...")
                        file_ref = client.files.upload(file=audio_file_path)
                        
                        while file_ref.state.name == "PROCESSING":
                            time.sleep(1.5)
                            file_ref = client.files.get(name=file_ref.name)
                        
                        if file_ref.state.name == "ACTIVE":
                            print("🧠 Transcrevendo áudio do YouTube...")
                            prompt_transcricao = (
                                "Você é o assistente que está transcrevendo um áudio do YouTube para a Ayla. "
                                "Por favor, faça uma transcrição detalhada em português ou um resumo estruturado "
                                "com os principais pontos discutidos no áudio, para que a Ayla possa responder à usuária."
                            )
                            if pergunta:
                                prompt_transcricao += f"\nResponda também especificamente a esta pergunta se possível: '{pergunta}'"
                                
                            response = client.models.generate_content(
                                model="gemini-2.5-flash",
                                contents=[file_ref, prompt_transcricao]
                            )
                            transcricao = response.text
                            
                        client.files.delete(name=file_ref.name)
                    else:
                        transcricao = "[Erro: O cliente Gemini não pôde ser inicializado para a transcrição do áudio]"
            except Exception as ex:
                transcricao = f"[Erro durante a transcrição do áudio: {ex}]"
            finally:
                if audio_file_path and audio_file_path.exists():
                    try:
                        audio_file_path.unlink()
                    except Exception:
                        pass
        elif duracao > 600:
            metodo_obtencao = "Somente Metadados (Vídeo muito longo para transcrição de áudio)"
            transcricao = "⚠️ Este vídeo não possui legendas de texto disponíveis e tem mais de 10 minutos de duração. Por limitações de desempenho, não posso transcrever o áudio de vídeos longos."
        else:
            metodo_obtencao = "Somente Metadados (Duração desconhecida)"
            transcricao = "⚠️ Não consegui acessar as legendas deste vídeo e não sei sua duração para baixar o áudio com segurança."

    # Limita o tamanho da transcrição para não estourar o prompt
    limite_caracteres = 40000
    if len(transcricao) > limite_caracteres:
        transcricao = transcricao[:limite_caracteres] + f"\n\n[...Conteúdo truncado. Mostrados apenas os primeiros {limite_caracteres} caracteres da transcrição...]"

    resultado = (
        f"📺 **Informações do Vídeo Absorvido:**\n"
        f"• **Título:** {titulo}\n"
        f"• **Canal:** {canal}\n"
        f"• **Duração:** {duracao} segundos\n"
        f"• **Método de Leitura:** {metodo_obtencao}\n\n"
        f"📖 **Transcrição / Resumo do Conteúdo:**\n"
        f"{transcricao}\n\n"
        f"📝 **Descrição do Vídeo:**\n"
        f"{descricao[:1000] + '...' if len(descricao) > 1000 else descricao}"
    )
    return resultado

TOOL_MAP["absorver_video_youtube"] = absorver_video_youtube
FUNCTION_DECLARATIONS.append({
    "name": "absorver_video_youtube",
    "description": (
        "Absorve o conteúdo de um vídeo do YouTube através do link (URL). "
        "Analisa as legendas do vídeo ou o áudio dele para responder a perguntas "
        "ou descrever o que é falado no vídeo."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "O link completo do vídeo do YouTube (deve começar com http ou https)."
            },
            "pergunta": {
                "type": "string",
                "description": "Opcional. Uma pergunta específica ou instrução da usuária sobre o vídeo (ex: 'De que fala o vídeo?', 'Resuma o vídeo', 'Quem é a pessoa que está falando?')."
            }
        },
        "required": ["url"]
    }
})
