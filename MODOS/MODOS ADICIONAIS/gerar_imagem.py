import sys
import os
import uuid
import json
import base64
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime as _dt

base_dir = Path(__file__).resolve().parents[2]
if str(base_dir) not in sys.path:
    sys.path.append(str(base_dir))
import ayla_state

"""
🎨 Módulo: Geração de Imagens com Cloudflare Workers AI
Exclusivo para o(a) usuário(a)!
"""

def _chamar_cloudflare_ai(model_name: str, api_key: str, account_id: str, prompt: str, image_bytes: bytes = None) -> tuple:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    m = model_name if model_name.startswith("@cf/") else f"@cf/{model_name}"
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{m}"
    payload = {"prompt": prompt}
    if image_bytes:
        payload["image"] = list(image_bytes)

    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=req_data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            content_type = resp.headers.get("Content-Type", "").lower()
            data = resp.read()
            
            # Resposta direta em imagem binária (PNG/JPEG/GIF)
            if "image/" in content_type or data[:4] in (b"\x89PNG", b"\xff\xd8\xff", b"GIF8"):
                return data, m

            # Resposta em JSON (ex: base64 no payload)
            res_json = json.loads(data.decode("utf-8"))
            if res_json.get("result", {}).get("image"):
                return base64.b64decode(res_json["result"]["image"]), m
            elif res_json.get("result", {}).get("response"):
                return base64.b64decode(res_json["result"]["response"]), m
    except urllib.error.HTTPError as he:
        err_body = he.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {he.code}: {err_body}")
    except Exception as e:
        raise RuntimeError(str(e))

    raise RuntimeError(f"Nenhuma imagem válida retornada pelo modelo {m}")


def gerar_imagem(prompt: str) -> str:
    """
    Gera uma imagem do zero a partir do prompt usando Cloudflare Workers AI.
    """
    api_token = os.getenv("CLOUDFLAREKEY", "").strip() or os.getenv("CLOUDFLARE_API_KEY", "").strip() or os.getenv("CLOUDFLARE_KEY", "").strip()
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip() or os.getenv("CLOUDFLARE_ACCOUNT", "").strip()

    if not api_token:
        return (
            "⚠️ A chave `CLOUDFLAREKEY` não está configurada no arquivo `.env`!\n"
            "Por favor, configure `CLOUDFLAREKEY=seu_token_api` no `.env` para usar esta função."
        )

    if not account_id:
        return (
            "⚠️ O `CLOUDFLARE_ACCOUNT_ID` não está configurado no arquivo `.env`!\n"
            "A API da Cloudflare requer o ID da sua conta na URL.\n"
            "Por favor, adicione `CLOUDFLARE_ACCOUNT_ID=seu_account_id` no arquivo `.env`."
        )

    # Garante o estilo anime adicionando tags se necessário
    prompt_anime = prompt.strip()
    suffix_anime = ", anime key visual, anime style, highly detailed 2d illustration, vibrant colors, masterpiece, anime aesthetic"
    if not any(tag in prompt_anime.lower() for tag in ["anime", "manga", "illustration", "drawing", "2d"]):
        prompt_anime += suffix_anime
    else:
        prompt_anime += ", anime style, masterpiece, highly detailed"

    models_order = [
        "@cf/black-forest-labs/flux-2-dev",
        "@cf/leonardo/phoenix-1.0",
        "@cf/black-forest-labs/flux-2-klein-9b",
        "@cf/leonardo/lucid-origin",
        "@cf/black-forest-labs/flux-2-klein-4b",
        "@cf/black-forest-labs/flux-1-schnell",
        "@cf/lykon/dreamshaper-8-lcm",
        "@cf/stabilityai/stable-diffusion-xl-base-1.0",
        "@cf/bytedance/stable-diffusion-xl-lightning"
    ]

    img_data = None
    modelo_sucesso = None
    erros = []

    for model_name in models_order:
        try:
            img_data, modelo_sucesso = _chamar_cloudflare_ai(
                model_name=model_name,
                api_key=api_token,
                account_id=account_id,
                prompt=prompt_anime
            )
            if img_data:
                break
        except Exception as e:
            erros.append(f"{model_name}: {e}")

    if not img_data:
        return (
            f"⚠️ Erro ao gerar imagem via Cloudflare Workers AI!\n"
            f"Erros encontrados:\n" + "\n".join(erros)
        )

    # Pasta de saída da Ayla
    pasta_saida = base_dir / "Aylafotitos"
    pasta_saida.mkdir(parents=True, exist_ok=True)

    data_hora = _dt.now().strftime("%Y%m%d_%H%M%S")
    nome_arquivo = f"gerada_{data_hora}_{uuid.uuid4().hex[:6]}.png"
    caminho_final = pasta_saida / nome_arquivo

    with open(caminho_final, "wb") as f:
        f.write(img_data)

    # Abre a pasta da galeria automaticamente no Windows
    os.startfile(pasta_saida)

    # Atualiza a variável global para que o bot envie a imagem em anexo
    ayla_state.ULTIMA_IMAGEM_GERADA.set(str(caminho_final))
    ayla_state.ULTIMA_IMAGEM_GERADA.set(str(caminho_final))

    return (
        f"🎨 Imagem gerada com sucesso via Cloudflare Workers AI!\n"
        f"🤖 Modelo: {modelo_sucesso}\n"
        f"📁 Salva em: {caminho_final}\n"
        f"🖼️ A imagem gerada será enviada junto com a resposta!"
    )


# ── Registro da ferramenta ──
if "TOOL_MAP" in globals():
    TOOL_MAP["gerar_imagem"] = gerar_imagem

if "FUNCTION_DECLARATIONS" in globals():
    FUNCTION_DECLARATIONS.append({
        "name": "gerar_imagem",
        "description": (
            "Gera uma imagem do zero a partir do prompt de texto usando a ordem priorizada de modelos Cloudflare Workers AI (FLUX.2 Dev, Leonardo Phoenix, FLUX.2 Klein, Leonardo Lucid Origin, FLUX.1 Schnell, Dreamshaper 8, SDXL Base e SDXL Lightning). "
            "O prompt deve ser detalhado e em INGLÊS. Esta ferramenta serve apenas para criar novas imagens."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "A descrição detalhada do que desenhar, em INGLÊS."
                }
            },
            "required": ["prompt"]
        }
    })
