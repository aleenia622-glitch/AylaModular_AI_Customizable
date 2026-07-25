import os
import sys
import uuid
import subprocess
from pathlib import Path

base_dir = Path(__file__).resolve().parents[2]
if str(base_dir) not in sys.path:
    sys.path.append(str(base_dir))
import ayla_state

# Garante compatibilidade se o arquivo for executado/importado individualmente
if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

def comprimir_video(
    caminho_video: str = "",
    qualidade: str = "media",
    crf: int = 28
) -> str:
    """
    Comprime um vídeo (do anexo recebido no Discord ou de um caminho especificado) reduzindo seu tamanho com FFmpeg.
    """
    try:
        if crf is not None:
            crf = int(crf)
        else:
            crf = 28
    except (ValueError, TypeError):
        crf = 28

    qualidade_clean = str(qualidade).strip().lower() if qualidade else "media"
    if qualidade_clean in ["baixa", "baixa qualidade", "low"]:
        crf = max(crf, 32)
    elif qualidade_clean in ["alta", "alta qualidade", "high"]:
        crf = min(crf, 23)

    crf = max(18, min(40, crf))

    video_origem = None
    if caminho_video and os.path.exists(caminho_video):
        video_origem = caminho_video
    else:
        anexo_video = ayla_state.ULTIMO_ANEXO_VIDEO.get()
        if anexo_video and os.path.exists(anexo_video):
            video_origem = anexo_video

    if not video_origem or not os.path.exists(video_origem):
        return (
            "⚠️ Você precisa enviar um vídeo em anexo na mensagem ou fornecer um caminho válido para eu conseguir comprimi-lo, Mamãe! "
            "Envie o vídeo junto com a mensagem pedindo para comprimir."
        )

    pasta_saida = base_dir / "Buffer de video"
    pasta_saida.mkdir(parents=True, exist_ok=True)

    id_unico = uuid.uuid4().hex[:8]
    caminho_saida = pasta_saida / f"comprimido_{id_unico}.mp4"

    sucesso = False
    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_origem),
            "-c:v", "libx264",
            "-crf", str(crf),
            "-preset", "medium",
            "-c:a", "aac",
            "-b:a", "128k",
            str(caminho_saida)
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300)
        if res.returncode == 0 and caminho_saida.exists() and caminho_saida.stat().st_size > 0:
            sucesso = True
        else:
            print(f"Aviso: FFmpeg stderr: {res.stderr[:200]}")
    except Exception as e:
        print(f"Aviso: FFmpeg falhou: {e}")

    if not sucesso:
        try:
            from moviepy import VideoFileClip
            with VideoFileClip(str(video_origem)) as clip:
                clip.write_videofile(
                    str(caminho_saida),
                    codec="libx264",
                    audio_codec="aac",
                    bitrate="1000k",
                    logger=None
                )
            if caminho_saida.exists() and caminho_saida.stat().st_size > 0:
                sucesso = True
        except Exception as e:
            return f"❌ Ocorreu um erro ao comprimir o vídeo com FFmpeg e MoviePy: {e}"

    if not sucesso or not caminho_saida.exists():
        return "❌ Não foi possível gerar o vídeo comprimido."

    tamanho_orig_mb = os.path.getsize(video_origem) / (1024 * 1024)
    tamanho_novo_mb = caminho_saida.stat().st_size / (1024 * 1024)
    reducao = ((tamanho_orig_mb - tamanho_novo_mb) / tamanho_orig_mb * 100) if tamanho_orig_mb > 0 else 0

    if tamanho_novo_mb <= 25.0:
        ayla_state.ULTIMA_IMAGEM_GERADA.set(str(caminho_saida))
        return (
            f"🗜️ **Vídeo comprimido com sucesso!** 🎬\n"
            f"📁 **Tamanho original:** `{tamanho_orig_mb:.2f} MB`\n"
            f"📉 **Novo tamanho:** `{tamanho_novo_mb:.2f} MB` ({reducao:.1f}% de redução)\n"
            f"⚙️ **CRF utilizado:** `{crf}`\n\n"
            f"✨ Aqui está o seu vídeo comprimido, Mamãe!"
        )
    else:
        ayla_state.ULTIMA_IMAGEM_GERADA.set(None)
        return (
            f"🗜️ **Vídeo comprimido com sucesso!** 🎬\n"
            f"📁 **Tamanho original:** `{tamanho_orig_mb:.2f} MB`\n"
            f"📉 **Novo tamanho:** `{tamanho_novo_mb:.2f} MB` ({reducao:.1f}% de redução)\n"
            f"⚠️ Ultrapassou o limite de 25 MB do Discord.\n\n"
            f"💾 Salvo no computador em: `{caminho_saida}`"
        )

TOOL_MAP["comprimir_video"] = comprimir_video
TOOL_MAP["compressor_video"] = comprimir_video

if "comprimir_video" not in [fd["name"] for fd in FUNCTION_DECLARATIONS]:
    FUNCTION_DECLARATIONS.append({
        "name": "comprimir_video",
        "description": (
            "Comprime um vídeo enviado em anexo na mensagem do Discord ou através de um caminho de arquivo, reduzindo o seu tamanho sem perder muita qualidade. "
            "Exemplo: Passe qualidade='media' ou 'baixa' para comprimir mais, ou ajuste o parâmetro 'crf'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "caminho_video": {
                    "type": "string",
                    "description": "Caminho opcional do arquivo de vídeo no computador. Se não informado, usará o vídeo enviado em anexo no Discord."
                },
                "qualidade": {
                    "type": "string",
                    "description": "Nível de qualidade do vídeo comprimido ('alta', 'media', 'baixa'). O padrão é 'media'."
                },
                "crf": {
                    "type": "integer",
                    "description": "Fator de taxa constante (CRF) do FFmpeg. Valores típicos: 23 (alta qualidade), 28 (padrão equilibrado), 32 (mais leve). Padrão: 28."
                }
            },
            "required": []
        }
    })

if "compressor_video" not in [fd["name"] for fd in FUNCTION_DECLARATIONS]:
    FUNCTION_DECLARATIONS.append({
        "name": "compressor_video",
        "description": (
            "Comprime um vídeo enviado em anexo na mensagem do Discord ou através de um caminho de arquivo, reduzindo o seu tamanho sem perder muita qualidade. "
            "Exemplo: Passe qualidade='media' ou 'baixa' para comprimir mais, ou ajuste o parâmetro 'crf'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "caminho_video": {
                    "type": "string",
                    "description": "Caminho opcional do arquivo de vídeo no computador. Se não informado, usará o vídeo enviado em anexo no Discord."
                },
                "qualidade": {
                    "type": "string",
                    "description": "Nível de qualidade do vídeo comprimido ('alta', 'media', 'baixa'). O padrão é 'media'."
                },
                "crf": {
                    "type": "integer",
                    "description": "Fator de taxa constante (CRF) do FFmpeg. Valores típicos: 23 (alta qualidade), 28 (padrão equilibrado), 32 (mais leve). Padrão: 28."
                }
            },
            "required": []
        }
    })
