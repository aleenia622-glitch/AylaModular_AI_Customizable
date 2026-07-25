import sys
import os
import uuid
import json
import base64
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime as _dt

sys.path.append(r"C:\Users\Aleenia\Documents\AI")
import ayla_state

"""
🎨 Módulo: Edição de Imagens com Cloudflare Workers AI
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

def editar_imagem(prompt: str) -> str:
    """
    Edita uma imagem existente usando Cloudflare Workers AI.
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

    # Verifica se há um anexo de imagem no contexto
    exemplo = ayla_state.ULTIMO_ANEXO_IMAGEM.get()
    if not exemplo:
        return (
            "⚠️ Você precisa enviar uma imagem em anexo para eu conseguir editá-la, Mamãe! "
            "Envie a imagem junto com a sua mensagem."
        )

    img_bytes, mime_type = exemplo

    # Modelos verificados na Cloudflare que aceitam envio de imagem (Img2Img / Referência)
    models_img2img = [
        "@cf/runwayml/stable-diffusion-v1-5-img2img",
        "@cf/leonardo/phoenix-1.0",
        "@cf/leonardo/lucid-origin"
    ]
    img_data = None
    modelo_sucesso = None
    erros = []

    # Tenta primeiro os modelos nativos de Img2Img
    for model_name in models_img2img:
        try:
            img_data, modelo_sucesso = _chamar_cloudflare_ai(
                model_name=model_name,
                api_key=api_token,
                account_id=account_id,
                prompt=prompt,
                image_bytes=img_bytes
            )
            if img_data:
                break
        except Exception as e:
            erros.append(f"{model_name}: {e}")

    # Fallback para modelos Text-To-Image se os modelos de imagem pura falharem
    if not img_data:
        fallback_txt2img = [
            "@cf/black-forest-labs/flux-1-schnell",
            "@cf/bytedance/stable-diffusion-xl-lightning"
        ]
        for model_name in fallback_txt2img:
            try:
                img_data, modelo_sucesso = _chamar_cloudflare_ai(
                    model_name=model_name,
                    api_key=api_token,
                    account_id=account_id,
                    prompt=prompt,
                    image_bytes=None  # Remove o campo image para não dar 400 Bad Request nos modelos Txt2Img
                )
                if img_data:
                    break
            except Exception as e:
                erros.append(f"{model_name} (sem anexo): {e}")

    if not img_data:
        return (
            f"⚠️ Erro ao editar imagem via Cloudflare Workers AI!\n"
            f"Erros encontrados:\n" + "\n".join(erros)
        )

    # Pasta de saída da Ayla
    pasta_saida = Path(r"C:\Users\Aleenia\Documents\AI\Aylafotitos")
    pasta_saida.mkdir(parents=True, exist_ok=True)

    data_hora = _dt.now().strftime("%Y%m%d_%H%M%S")
    nome_arquivo = f"editada_{data_hora}_{uuid.uuid4().hex[:6]}.png"
    caminho_final = pasta_saida / nome_arquivo

    with open(caminho_final, "wb") as f:
        f.write(img_data)

    # Abre a pasta da galeria automaticamente no Windows
    os.startfile(pasta_saida)

    # Atualiza a variável global para que o bot envie a imagem em anexo
    ayla_state.ULTIMA_IMAGEM_GERADA.set(str(caminho_final))
    ayla_state.ULTIMA_IMAGEM_GERADA.set(str(caminho_final))

    return (
        f"🎨 Imagem editada com sucesso via Cloudflare Workers AI!\n"
        f"🤖 Modelo: {modelo_sucesso}\n"
        f"📁 Salva em: {caminho_final}\n"
        f"🖼️ A imagem editada será enviada junto com a resposta!"
    )


# ── Registro da ferramenta ──
if "TOOL_MAP" in globals():
    TOOL_MAP["editar_imagem"] = editar_imagem

if "FUNCTION_DECLARATIONS" in globals():
    FUNCTION_DECLARATIONS.append({
        "name": "editar_imagem",
        "description": (
            "Edita uma imagem existente enviada no chat usando modelos de Image-to-Image da Cloudflare Workers AI (SD v1.5 Img2Img, Leonardo Phoenix e Leonardo Lucid Origin). "
            "Você DEVE fornecer o prompt com as alterações desejadas em INGLÊS. "
            "Esta ferramenta requer obrigatoriamente uma imagem em anexo."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Instruções detalhadas em INGLÊS sobre as modificações a serem feitas na imagem."
                }
            },
            "required": ["prompt"]
        }
    })
