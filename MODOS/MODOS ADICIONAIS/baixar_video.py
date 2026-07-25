import os
import re
import sys
import hashlib
from pathlib import Path
import yt_dlp

# Garante compatibilidade se o arquivo for executado/importado individualmente
if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

def limpar_nome_arquivo(nome: str) -> str:
    # Remove caracteres inválidos no Windows
    nome_limpo = re.sub(r'[\\/*?:"<>|]', "", nome)
    # Limita o tamanho do nome
    if len(nome_limpo) > 100:
        nome_limpo = nome_limpo[:100]
    return nome_limpo.strip()

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

def baixar_video(url: str) -> str:
    """
    Baixa um vídeo a partir de um link (URL) de plataformas suportadas (YouTube, TikTok, Twitter, Twitch, etc.) e o salva localmente no PC.
    Se o vídeo tiver menos de 10MB, ele também será enviado em anexo no chat.
    """
    url_limpa = url.strip()

    # 1. Definir pasta de destino
    base_dir = Path(__file__).resolve().parents[2]
    pasta_saida = base_dir / "VideosBaixados"
    pasta_saida.mkdir(parents=True, exist_ok=True)

    # 2. Obter informações/título do vídeo para nomear o arquivo
    print(f"🎬 [Vídeo] Obtendo metadados para baixar o vídeo de {url_limpa}...")
    ydl_opts_info = {
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'socket_timeout': 30,
        'extractor_args': {'youtube': {'player_client': ['android']}}
    }

    video_id = obter_video_id(url_limpa)
    titulo = f"video_{video_id}" if video_id else "video"
    erro_metadados = None
    info = None

    try:
        _, info, metodo = executar_ytdl_com_fallback(ydl_opts_info, url_limpa, download=False)
        if info:
            titulo = info.get('title', titulo)
            if not video_id:
                video_id = info.get('id')
    except Exception as e:
        erro_metadados = e
        print(f"Aviso ao obter metadados: {e}")

    if not video_id:
        video_id = hashlib.md5(url_limpa.encode('utf-8')).hexdigest()[:8]

    titulo_limpo = limpar_nome_arquivo(titulo)
    outtmpl_path = pasta_saida / f"{titulo_limpo}_{video_id}.%(ext)s"

    # 3. Baixar o melhor formato pré-mesclado (para não precisar do ffmpeg)
    print(f"📥 [Vídeo] Baixando vídeo '{titulo}'...")
    ydl_dl_opts = {
        'format': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
        'merge_output_format': 'mp4',
        'outtmpl': str(outtmpl_path),
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'socket_timeout': 30,
        'progress_hooks': [progresso_hook],
        'extractor_args': {'youtube': {'player_client': ['android']}}
    }

    try:
        executar_ytdl_com_fallback(ydl_dl_opts, url_limpa, download=True)
    except Exception as e:
        if erro_metadados:
            return f"❌ Erro ao baixar o vídeo via yt-dlp: {e}\n\nNota: A obtenção de metadados também falhou com o seguinte erro:\n{erro_metadados}"
        return f"❌ Erro ao baixar o vídeo via yt-dlp: {e}"

    # 4. Encontrar o arquivo baixado
    arquivos = list(pasta_saida.glob(f"{titulo_limpo}_{video_id}.*"))
    if not arquivos:
        arquivos = list(pasta_saida.glob(f"*{video_id}.*"))
        if not arquivos:
            return "❌ O download concluiu, mas não consegui encontrar o arquivo na pasta de destino."

    caminho_video = arquivos[0]
    tamanho_bytes = caminho_video.stat().st_size
    tamanho_mb = tamanho_bytes / (1024 * 1024)

    # Limite do Discord para envio de arquivos é 10MB (padrão para bots sem Nitro)
    limite_discord_mb = 10.0

    if tamanho_mb <= limite_discord_mb:
        import ayla_state
        ayla_state.ULTIMA_IMAGEM_GERADA.set(str(caminho_video))
        
        return (
            f"🎥 **Vídeo baixado com sucesso!**\n"
            f"• **Título:** {titulo}\n"
            f"• **Tamanho:** {tamanho_mb:.2f} MB\n"
            f"• **Salvo em:** `{caminho_video}`\n\n"
            f"✨ Como ele tem menos de 10MB, estou enviando ele anexado aqui no chat para você!"
        )
    else:
        import ayla_state
        ayla_state.ULTIMA_IMAGEM_GERADA.set(None)
            
        return (
            f"🎥 **Vídeo baixado com sucesso!**\n"
            f"• **Título:** {titulo}\n"
            f"• **Tamanho:** {tamanho_mb:.2f} MB\n"
            f"• **Salvo em:** `{caminho_video}`\n\n"
            f"⚠️ O arquivo tem mais de 10MB (limite do Discord), por isso não consegui anexá-lo aqui no chat. Mas ele já está salvo no seu computador no caminho acima para você assistir! 🦎"
        )

TOOL_MAP["baixar_video"] = baixar_video
FUNCTION_DECLARATIONS.append({
    "name": "baixar_video",
    "description": (
        "Baixa um vídeo de plataformas suportadas (como YouTube, TikTok, Twitter/X, Twitch, etc.) "
        "a partir do link (URL) fornecido e salva no computador. "
        "Se o tamanho do vídeo for de até 10MB, ele também será enviado como anexo no Discord."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "O link completo do vídeo (deve começar com http ou https)."
            }
        },
        "required": ["url"]
    }
})
