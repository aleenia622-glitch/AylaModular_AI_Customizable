import os
import sys
import uuid
import subprocess
from pathlib import Path

sys.path.append(r"C:\Users\Aleenia\Documents\AI")
import ayla_state

# Garante compatibilidade se o arquivo for executado/importado individualmente
if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

def cortar_video(
    minuto_inicio: int = 0,
    segundo_inicio: float = 0,
    minuto_fim: int = 0,
    segundo_fim: float = 0
) -> str:
    """
    Corta um vídeo enviado em anexo na mensagem do Discord com base no minuto e segundo inicial e final.
    """
    try:
        minuto_inicio = int(minuto_inicio)
        segundo_inicio = float(segundo_inicio)
        minuto_fim = int(minuto_fim)
        segundo_fim = float(segundo_fim)
    except (ValueError, TypeError):
        return "⚠️ Os minutos e segundos fornecidos devem ser números válidos!"

    anexo_video = ayla_state.ULTIMO_ANEXO_VIDEO.get()
    if not anexo_video or not os.path.exists(anexo_video):
        return (
            "⚠️ Você precisa enviar um vídeo em anexo na mensagem para eu conseguir cortá-lo, Mamãe! "
            "Envie o vídeo junto com a mensagem indicando o tempo de início e fim."
        )

    inicio_total = (minuto_inicio * 60) + segundo_inicio
    fim_total = (minuto_fim * 60) + segundo_fim

    if inicio_total < 0:
        inicio_total = 0.0

    if fim_total <= inicio_total:
        return (
            f"⚠️ O tempo final ({minuto_fim}m {segundo_fim:g}s) precisa ser maior "
            f"que o tempo inicial ({minuto_inicio}m {segundo_inicio:g}s)!"
        )

    duracao_corte = fim_total - inicio_total

    pasta_saida = Path(r"C:\Users\Aleenia\Documents\AI\Buffer de video")
    pasta_saida.mkdir(parents=True, exist_ok=True)

    id_unico = uuid.uuid4().hex[:8]
    caminho_saida = pasta_saida / f"corte_{id_unico}.mp4"

    # Tentativa 1: FFmpeg via subprocess (ultra rápido e eficiente)
    sucesso = False
    try:
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(inicio_total),
            "-to", str(fim_total),
            "-i", str(anexo_video),
            "-c:v", "libx264",
            "-c:a", "aac",
            "-preset", "ultrafast",
            str(caminho_saida)
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0 and caminho_saida.exists() and caminho_saida.stat().st_size > 0:
            sucesso = True
        else:
            print(f"Aviso: FFmpeg stderr: {res.stderr[:200]}")
    except Exception as e:
        print(f"Aviso: FFmpeg falhou: {e}")

    # Tentativa 2: MoviePy (fallback se o FFmpeg via CLI direta falhar)
    if not sucesso:
        try:
            from moviepy import VideoFileClip
            with VideoFileClip(str(anexo_video)) as clip:
                if hasattr(clip, "subclipped"):
                    clip_cortado = clip.subclipped(inicio_total, fim_total)
                else:
                    clip_cortado = clip.subclip(inicio_total, fim_total)
                clip_cortado.write_videofile(
                    str(caminho_saida),
                    codec="libx264",
                    audio_codec="aac",
                    logger=None
                )
            if caminho_saida.exists() and caminho_saida.stat().st_size > 0:
                sucesso = True
        except Exception as e:
            return f"❌ Ocorreu um erro ao cortar o vídeo com FFmpeg e MoviePy: {e}"

    if not sucesso or not caminho_saida.exists():
        return "❌ Não foi possível gerar o vídeo cortado."

    tamanho_bytes = caminho_saida.stat().st_size
    tamanho_mb = tamanho_bytes / (1024 * 1024)

    # limite para anexo de envio do Discord
    if tamanho_mb <= 25.0:
        ayla_state.ULTIMA_IMAGEM_GERADA.set(str(caminho_saida))
        return (
            f"✂️ **Vídeo cortado com sucesso!** 🎬\n"
            f"⏱️ **Intervalo:** `{minuto_inicio:02d}:{int(segundo_inicio):02d}` até `{minuto_fim:02d}:{int(segundo_fim):02d}` ({duracao_corte:.1f}s de duração)\n"
            f"📁 **Tamanho:** `{tamanho_mb:.2f} MB`\n\n"
            f"✨ Aqui está o seu vídeo cortado, Mamãe!"
        )
    else:
        ayla_state.ULTIMA_IMAGEM_GERADA.set(None)
        return (
            f"✂️ **Vídeo cortado com sucesso!** 🎬\n"
            f"⏱️ **Intervalo:** `{minuto_inicio:02d}:{int(segundo_inicio):02d}` até `{minuto_fim:02d}:{int(segundo_fim):02d}`\n"
            f"📁 **Tamanho:** `{tamanho_mb:.2f} MB` (ultrapassou o limite do Discord)\n\n"
            f"⚠️ Salvo no computador em: `{caminho_saida}`"
        )

TOOL_MAP["cortar_video"] = cortar_video

if "cortar_video" not in [fd["name"] for fd in FUNCTION_DECLARATIONS]:
    FUNCTION_DECLARATIONS.append({
        "name": "cortar_video",
        "description": (
            "Corta um vídeo enviado em anexo na mensagem do Discord indicando o minuto e segundo inicial e final. "
            "Exemplo: Para cortar do segundo 10 do minuto 0 até 1 minuto e 30 segundos, passe minuto_inicio=0, segundo_inicio=10, minuto_fim=1, segundo_fim=30. "
            "O vídeo cortado é retornado em anexo no chat do Discord."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "minuto_inicio": {
                    "type": "integer",
                    "description": "Minuto inicial do trecho a cortar (ex: 0)."
                },
                "segundo_inicio": {
                    "type": "number",
                    "description": "Segundo inicial do trecho a cortar (ex: 15)."
                },
                "minuto_fim": {
                    "type": "integer",
                    "description": "Minuto final do trecho a cortar (ex: 1)."
                },
                "segundo_fim": {
                    "type": "number",
                    "description": "Segundo final do trecho a cortar (ex: 30)."
                }
            },
            "required": ["minuto_inicio", "segundo_inicio", "minuto_fim", "segundo_fim"]
        }
    })
