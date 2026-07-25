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
                sys.stdout.write(f"\r📥 [Vídeo] Progresso: [{barra}] {percent:.1f}% ({speed_str}, ETA: {eta_str})")
                sys.stdout.flush()
            except Exception:
                try:
                    sys.stdout.write(f"\r[Vídeo] Progresso: [{barra}] {percent:.1f}% ({speed_str}, ETA: {eta_str})")
                    sys.stdout.flush()
                except Exception:
                    pass
    elif d['status'] == 'finished':
        try:
            sys.stdout.write("\r📥 [Vídeo] Download concluído! Processando arquivo...               \n")
            sys.stdout.flush()
        except Exception:
            try:
                sys.stdout.write("\r[Vídeo] Download concluído! Processando arquivo...               \n")
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
        # Se for erro relacionado a restrição de idade ou login
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
                f"1. Se o Microsoft Edge estiver aberto, feche-o completamente e tente novamente (o script tentará ler os cookies dele).\n"
                f"2. Ou exporte os cookies do seu navegador para um arquivo chamado `cookies.txt` e salve na pasta principal do projeto (`{base_dir}`)."
            )
            raise Exception(msg_erro_detalhado)
        else:
            raise e

def absorver_video(url: str, pergunta: str = "") -> str:
    """
    Absorve o conteúdo de um vídeo através do link (URL).
    Analisa as legendas do vídeo ou o áudio dele para responder a perguntas
    ou descrever o que é falado no vídeo.
    """
    url_limpa = url.strip()
    video_id = obter_video_id(url_limpa)

    # 1. Obter metadados do vídeo usando yt-dlp
    print(f"🎬 [Vídeo] Obtendo metadados para o vídeo {url_limpa}...")
    ydl_opts = {
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'socket_timeout': 30,
        'extractor_args': {'youtube': {'player_client': ['android']}}
    }
    
    titulo = "Vídeo"
    canal = "Desconhecido"
    duracao = 0
    descricao = ""
    erro_metadados = None
    info = None
    
    try:
        _, info, metodo = executar_ytdl_com_fallback(ydl_opts, url_limpa, download=False)
        if info:
            titulo = info.get('title', titulo)
            canal = info.get('uploader', canal)
            duracao = info.get('duration', 0)
            descricao = info.get('description', '')
            if not video_id:
                video_id = info.get('id')
    except Exception as e:
        erro_metadados = e
        print(f"Aviso ao obter metadados via yt-dlp: {e}")

    if not video_id:
        video_id = hashlib.md5(url_limpa.encode('utf-8')).hexdigest()[:8]

    # 2. Tentar obter a transcrição/legendas do vídeo (apenas para YouTube de forma rápida via API)
    transcricao = ""
    metodo_obtencao = "Legendas de texto automáticas/manuais"
    
    eh_youtube = obter_video_id(url_limpa) is not None
    if eh_youtube:
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
            print(f"🎙️ [Vídeo] Sem legendas de texto para vídeo de {duracao}s. Baixando áudio para transcrever...")
            
            temp_dir = Path(tempfile.gettempdir())
            audio_out = temp_dir / f"ayla_audio_vid_{video_id}.%(ext)s"
            
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
                executar_ytdl_com_fallback(ydl_dl_opts, url_limpa, download=True)
                
                arquivos_baixados = list(temp_dir.glob(f"ayla_audio_vid_{video_id}.*"))
                if arquivos_baixados:
                    audio_file_path = arquivos_baixados[0]
                    
                    # Tentar transcrição via Groq Whisper (como no modo live em ayla_gui.py)
                    try:
                        from dotenv import load_dotenv
                        load_dotenv()
                    except ImportError:
                        pass
                    
                    groq_key = os.getenv("GROQ_API_KEY", "").strip()
                    transcricao_sucesso = False
                    
                    if groq_key:
                        try:
                            print("🎙️ [Vídeo] Tentando transcrição via Groq Whisper...")
                            import requests
                            url = "https://api.groq.com/openai/v1/audio/transcriptions"
                            headers = {
                                "Authorization": f"Bearer {groq_key}"
                            }
                            audio_bytes = audio_file_path.read_bytes()
                            files = {
                                "file": (audio_file_path.name, audio_bytes)
                            }
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
                                    is_hallucination = False
                                    hallucination_patterns = [
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
                                            is_hallucination = True
                                            break
                                    if is_hallucination and len(text) < 120:
                                        print(f"⚠️ [Vídeo] Alucinação do Whisper detectada e descartada: '{text}'")
                                        text = ""
                                
                                if text:
                                    transcricao = text
                                    metodo_obtencao = "Transcrição de áudio via Groq Whisper"
                                    transcricao_sucesso = True
                                    print(f"🎉 [Vídeo] Transcrição Groq concluída com sucesso! ({len(transcricao)} caracteres)")
                            else:
                                print(f"Aviso: Falha no Groq Whisper (Status {response.status_code}): {response.text}")
                        except Exception as e:
                            print(f"Aviso: Erro ao usar Groq Whisper: {e}")
                    
                    # Fallback: Usar Google Gemini File API para transcrição se o Whisper falhar ou não estiver configurado
                    if not transcricao_sucesso:
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
                                print("🧠 Transcrevendo áudio do vídeo...")
                                prompt_transcricao = (
                                    "Você é o assistente que está transcrevendo um áudio de vídeo para a Ayla. "
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
            metodo_obtencao = "Somente Metadados (Falha ao obter duração)"
            if erro_metadados:
                transcricao = f"⚠️ Não consegui acessar as legendas nem baixar o áudio deste vídeo.\n\nDetalhes do erro:\n{erro_metadados}"
            else:
                transcricao = "⚠️ Não consegui acessar as legendas deste vídeo e não sei sua duração para baixar o áudio com segurança."

    # Limita o tamanho da transcrição para não estourar o prompt
    limite_caracteres = 40000
    if len(transcricao) > limite_caracteres:
        transcricao = transcricao[:limite_caracteres] + f"\n\n[...Conteúdo truncado. Mostrados apenas os primeiros {limite_caracteres} caracteres da transcrição...]"

    resultado = (
        f"📺 **Informações do Vídeo Absorvido:**\n"
        f"• **Título:** {titulo}\n"
        f"• **Canal/Autor:** {canal}\n"
        f"• **Duração:** {duracao} segundos\n"
        f"• **Método de Leitura:** {metodo_obtencao}\n\n"
        f"📖 **Transcrição / Resumo do Conteúdo:**\n"
        f"{transcricao}\n\n"
        f"📝 **Descrição do Vídeo:**\n"
        f"{descricao[:1000] + '...' if len(descricao) > 1000 else descricao}"
    )
    return resultado

TOOL_MAP["absorver_video"] = absorver_video
FUNCTION_DECLARATIONS.append({
    "name": "absorver_video",
    "description": (
        "Absorve o conteúdo de um vídeo através do link (URL). "
        "Analisa as legendas do vídeo ou o áudio dele para responder a perguntas "
        "ou descrever o que é falado no vídeo."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "O link completo do vídeo (deve começar com http ou https)."
            },
            "pergunta": {
                "type": "string",
                "description": "Opcional. Uma pergunta específica ou instrução da usuária sobre o vídeo (ex: 'De que fala o vídeo?', 'Resuma o vídeo', 'Quem é a pessoa que está falando?')."
            }
        },
        "required": ["url"]
    }
})
