"""Converte um vídeo anexado em GIF animado."""
from ayla_paths import project_path
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import ayla_state
import uuid

# Import de alta compatibilidade para MoviePy v1.x e v2.x
try:
    from moviepy import VideoFileClip
except (ImportError, AttributeError):
    try:
        from moviepy.editor import VideoFileClip
    except (ImportError, AttributeError):
        try:
            from moviepy.video.io.VideoFileClip import VideoFileClip
        except ImportError:
            VideoFileClip = None

# Garante compatibilidade se o arquivo for executado/importado individualmente
if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

def criar_gif_de_video():
    if VideoFileClip is None:
        return 'Conversão de GIF requer moviepy. Instale as dependências com ./install_linux.sh.'
    # Print seguro para evitar UnicodeEncodeError
    def safe_print(msg):
        print(msg.encode('utf-8', errors='replace').decode('utf-8'))

    pasta_destino = str(project_path('Aylafotitos'))
    if not os.path.exists(pasta_destino):
        os.makedirs(pasta_destino)

    id_unico = str(uuid.uuid4())[:8]
    gif_final = os.path.join(pasta_destino, f'gif_{id_unico}.gif')

    try:
        anexo_video = ayla_state.ULTIMO_ANEXO_VIDEO.get()
        if not anexo_video:
            return "⚠️ Por favor, envie o vídeo em anexo na mensagem!"

        safe_print(f"Usando vídeo anexado: {anexo_video}")
        
        safe_print("Processando vídeo e otimizando tamanho do GIF...")
        with VideoFileClip(anexo_video) as clip:
            # Limita duração a 10 segundos conforme pedido da usuario Usuario
            duracao = min(10, clip.duration)
            gif_clip = clip.subclipped(0, duracao) if hasattr(clip, "subclipped") else clip.subclip(0, duracao)
            
            # Redimensiona para no máximo 480px de largura mantendo a proporção (garante que fique leve mesmo a 24 FPS)
            largura_atual = getattr(gif_clip, "w", None) or (gif_clip.size[0] if hasattr(gif_clip, "size") else 1080)
            if largura_atual > 480:
                if hasattr(gif_clip, "resized"):
                    gif_clip = gif_clip.resized(width=480)
                elif hasattr(gif_clip, "resize"):
                    gif_clip = gif_clip.resize(width=480)

            # 24 FPS para máxima fluidez mantendo o redimensionamento a 480px
            gif_clip.write_gif(gif_final, fps=24, logger=None)

        # Checa o tamanho do GIF gerado
        tamanho_bytes = os.path.getsize(gif_final)
        tamanho_mb = tamanho_bytes / (1024 * 1024)
        limite_discord_mb = 10.0

        if tamanho_mb <= limite_discord_mb:
            ayla_state.ULTIMA_IMAGEM_GERADA.set(str(gif_final))
            return (
                f"✨ **GIF criado e otimizado com sucesso!**\n"
                f"• **Tamanho:** {tamanho_mb:.2f} MB\n"
                f"• **Salvo em:** `{gif_final}`\n\n"
                f"🖼️ O GIF gerado foi anexado e enviado aqui no chat!"
            )
        else:
            ayla_state.ULTIMA_IMAGEM_GERADA.set(None)
            return (
                f"✨ **GIF criado com sucesso!**\n"
                f"• **Tamanho:** {tamanho_mb:.2f} MB\n"
                f"• **Salvo em:** `{gif_final}`\n\n"
                f"⚠️ O arquivo do GIF ainda ultrapassa 10MB, por isso não pôde ser enviado no chat, mas já está salvo no seu computador no caminho acima."
            )

    except Exception as e:
        return f"❌ Erro ao criar GIF: {str(e)}"

# Aliases diretos expostos no escopo global do módulo
modo_gif = criar_gif_de_video
criar_gif = criar_gif_de_video
gerar_gif_de_video = criar_gif_de_video

# ── Registro das ferramentas e suporte a recarregamento dinâmico ──
FERRAMENTAS_GIF = {
    "modo_gif": criar_gif_de_video,
    "criar_gif_de_video": criar_gif_de_video,
    "gerar_gif_de_video": criar_gif_de_video,
    "criar_gif": criar_gif_de_video,
}

DECLARACOES_GIF = [
    {
        "name": "modo_gif",
        "description": "Cria um GIF animado otimizado (até 10s, 24fps e max 480px de largura) a partir de um vídeo enviado em anexo na mensagem e envia o arquivo no Discord.",
        "parameters": {"type": "object", "properties": {}},
        "required": []
    },
    {
        "name": "criar_gif_de_video",
        "description": "Cria um GIF animado otimizado (até 10s, 24fps e max 480px de largura) a partir de um vídeo enviado em anexo na mensagem e envia o arquivo no Discord.",
        "parameters": {"type": "object", "properties": {}},
        "required": []
    }
]

if "TOOL_MAP" in globals():
    TOOL_MAP.update(FERRAMENTAS_GIF)

if "FUNCTION_DECLARATIONS" in globals():
    for dec in DECLARACOES_GIF:
        if not any(existing.get("name") == dec["name"] for existing in FUNCTION_DECLARATIONS):
            FUNCTION_DECLARATIONS.append(dec)

def register(tool_map, function_declarations):
    """Função invocada pelo carregador dinâmico do bot principal (Ayla.py)."""
    tool_map.update(FERRAMENTAS_GIF)
    for dec in DECLARACOES_GIF:
        if not any(existing.get("name") == dec["name"] for existing in function_declarations):
            function_declarations.append(dec)
