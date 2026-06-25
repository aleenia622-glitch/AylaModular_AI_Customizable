import os
import re
import sys
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

def baixar_video_youtube(url: str) -> str:
    """
    Baixa um vídeo do YouTube a partir de um link (URL) e o salva localmente no PC.
    Se o vídeo tiver menos de 10MB, ele também será enviado em anexo no chat.
    """
    url_limpa = url.strip()
    video_id = obter_video_id(url_limpa)
    if not video_id:
        return "⚠️ Não consegui extrair o ID do vídeo a partir deste link. Por favor, envie um link válido do YouTube!"

    # 1. Definir pasta de destino
    projeto_raiz = Path(__file__).resolve().parent.parent
    pasta_saida = projeto_raiz / "VideosBaixados"
    pasta_saida.mkdir(parents=True, exist_ok=True)

    # 2. Obter informações/título do vídeo para nomear o arquivo
    print(f"🎬 [YouTube] Obtendo metadados para baixar o vídeo ID {video_id}...")
    ydl_opts_info = {
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'socket_timeout': 30,
        'extractor_args': {'youtube': {'player_client': ['android']}}
    }

    titulo = f"video_{video_id}"
    try:
        with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
            info = ydl.extract_info(url_limpa, download=False)
            titulo = info.get('title', titulo)
    except Exception as e:
        print(f"Aviso ao obter metadados: {e}")

    titulo_limpo = limpar_nome_arquivo(titulo)
    outtmpl_path = pasta_saida / f"{titulo_limpo}_{video_id}.%(ext)s"

    # 3. Baixar o melhor formato pré-mesclado (para não precisar do ffmpeg)
    print(f"📥 [YouTube] Baixando vídeo '{titulo}'...")
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
        with yt_dlp.YoutubeDL(ydl_dl_opts) as ydl:
            ydl.download([url_limpa])
    except Exception as e:
        return f"❌ Erro ao baixar o vídeo via yt-dlp: {e}"

    # 4. Encontrar o arquivo baixado
    arquivos = list(pasta_saida.glob(f"{titulo_limpo}_{video_id}.*"))
    if not arquivos:
        return "❌ O download concluiu, mas não consegui encontrar o arquivo na pasta de destino."

    caminho_video = arquivos[0]
    tamanho_bytes = caminho_video.stat().st_size
    tamanho_mb = tamanho_bytes / (1024 * 1024)

    # Limite do Discord para envio de arquivos é 10MB (padrão para bots sem Nitro)
    limite_discord_mb = 10.0

    if tamanho_mb <= limite_discord_mb:
        # Define a variável global no Ayla.py para anexar e enviar
        global ULTIMA_IMAGEM_GERADA
        ULTIMA_IMAGEM_GERADA = str(caminho_video)
        globals()["ULTIMA_IMAGEM_GERADA"] = str(caminho_video)
        
        return (
            f"🎥 **Vídeo baixado com sucesso!**\n"
            f"• **Título:** {titulo}\n"
            f"• **Tamanho:** {tamanho_mb:.2f} MB\n"
            f"• **Salvo em:** `{caminho_video}`\n\n"
            f"✨ Como ele tem menos de 10MB, estou enviando ele anexado aqui no chat para você!"
        )
    else:
        # Se ultrapassa 10MB, não tenta enviar pelo Discord (daria erro), mas informa onde está salvo
        # Garante que não envie lixo de outra geração
        if "ULTIMA_IMAGEM_GERADA" in globals():
            globals()["ULTIMA_IMAGEM_GERADA"] = None
            
        return (
            f"🎥 **Vídeo baixado com sucesso!**\n"
            f"• **Título:** {titulo}\n"
            f"• **Tamanho:** {tamanho_mb:.2f} MB\n"
            f"• **Salvo em:** `{caminho_video}`\n\n"
            f"⚠️ O arquivo tem mais de 10MB (limite do Discord), por isso não consegui anexá-lo aqui no chat. Mas ele já está salvo no seu computador no caminho acima para você assistir! 🦎"
        )

TOOL_MAP["baixar_video_youtube"] = baixar_video_youtube
FUNCTION_DECLARATIONS.append({
    "name": "baixar_video_youtube",
    "description": (
        "Baixa um vídeo do YouTube a partir do link (URL) fornecido e salva no computador. "
        "Se o tamanho do vídeo for de até 10MB, ele também será enviado como anexo no Discord."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "O link completo do vídeo do YouTube (deve começar com http ou https)."
            }
        },
        "required": ["url"]
    }
})
