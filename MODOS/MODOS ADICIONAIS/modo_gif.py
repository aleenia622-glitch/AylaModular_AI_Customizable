import os
import sys
from pathlib import Path

base_dir = Path(__file__).resolve().parents[2]
if str(base_dir) not in sys.path:
    sys.path.append(str(base_dir))
import ayla_state
from moviepy import VideoFileClip
import uuid

# Garante compatibilidade se o arquivo for executado/importado individualmente
if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

def criar_gif_de_video():
    # Print seguro para evitar UnicodeEncodeError
    def safe_print(msg):
        print(msg.encode('utf-8', errors='replace').decode('utf-8'))

    pasta_destino = str(base_dir / "Aylafotitos")
    if not os.path.exists(pasta_destino):
        os.makedirs(pasta_destino)

    id_unico = str(uuid.uuid4())[:8]
    gif_final = os.path.join(pasta_destino, f'gif_{id_unico}.gif')

    try:
        anexo_video = ayla_state.ULTIMO_ANEXO_VIDEO.get()
        if not anexo_video:
            return "⚠️ Por favor, envie o vídeo em anexo na mensagem!"

        safe_print(f"Usando vídeo anexado: {anexo_video}")
        
        safe_print("Processando vídeo...")
        with VideoFileClip(anexo_video) as clip:
            duracao = min(10, clip.duration)
            gif_clip = clip.subclipped(0, duracao)
            gif_clip.write_gif(gif_final, fps=29, logger=None)

        return f"✨ GIF criado com sucesso: {gif_final}"

    except Exception as e:
        return f"❌ Erro ao criar GIF: {str(e)}"

TOOL_MAP["criar_gif_de_video"] = criar_gif_de_video
FUNCTION_DECLARATIONS.append({
    "name": "criar_gif_de_video",
    "description": "Cria um GIF de até 10s e 29fps a partir de um vídeo enviado em anexo na mensagem.",
    "parameters": {"type": "object", "properties": {}},
    "required": []
})
