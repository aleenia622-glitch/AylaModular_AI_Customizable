"""Gera imagens com IA; imagens anexadas servem de referência para editar ou combinar."""
from ayla_platform import open_path
import sys
import os
import uuid
import json
import base64
import requests
from pathlib import Path
from datetime import datetime as _dt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import ayla_state

"""
🎨 Módulo Unificado: Geração e Edição de Imagens em 4K com ByteDance Seed (Seedream 4.5)
Suporte a Múltiplas Imagens de Referência e Proporções de Aspecto Flexíveis (1:1, 16:9, 9:16, 4:3, 3:4, 21:9, 3:2, 2:3)!
"""

# Mapeamento de proporções de aspecto para resoluções em 4K (máximo do modelo: 4096px)
PROPORCOES_4K = {
    "1:1": {"size": "4096x4096", "width": 4096, "height": 4096, "ratio": "1:1"},
    "16:9": {"size": "4096x2304", "width": 4096, "height": 2304, "ratio": "16:9"},
    "9:16": {"size": "2304x4096", "width": 2304, "height": 4096, "ratio": "9:16"},
    "4:3": {"size": "4096x3072", "width": 4096, "height": 3072, "ratio": "4:3"},
    "3:4": {"size": "3072x4096", "width": 3072, "height": 4096, "ratio": "3:4"},
    "21:9": {"size": "4096x1755", "width": 4096, "height": 1755, "ratio": "21:9"},
    "3:2": {"size": "4096x2730", "width": 4096, "height": 2730, "ratio": "3:2"},
    "2:3": {"size": "2730x4096", "width": 2730, "height": 4096, "ratio": "2:3"},
}


def _chamar_bytedance_seed(model_name: str, api_key: str, prompt: str, size_info: dict, image_inputs: list = None) -> tuple:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # ModelArk BytePlus e Volcengine têm catálogos/identificadores distintos.
    endpoints = [
        "https://ark.cn-beijing.volces.com/api/v3/images/generations"
        if model_name.startswith("doubao-")
        else "https://ark.ap-southeast.bytepluses.com/api/v3/images/generations"
    ]

    payload = {
        "model": model_name,
        "prompt": prompt,
        "response_format": "url",
        "size": size_info.get("size", "4096x4096"),
        "width": size_info.get("width", 4096),
        "height": size_info.get("height", 4096),
        "aspect_ratio": size_info.get("ratio", "1:1")
    }

    # Suporta de 1 a múltiplas imagens de referência (Seedream 4.5 aceita até 10 imagens)
    if image_inputs:
        urls_list = []
        for item in image_inputs:
            if isinstance(item, tuple) and len(item) == 2:
                img_b, mime = item
                b64_img = base64.b64encode(img_b).decode("utf-8")
                urls_list.append(f"data:{mime};base64,{b64_img}")
            elif isinstance(item, str):
                urls_list.append(item)
        if urls_list:
            payload["image_urls"] = urls_list

    ultimo_erro = None

    for endpoint in endpoints:
        # Tenta primeiro formato 'url' (payload leve de ~200 bytes) e depois 'b64_json' se necessário
        for fmt in ["url", "b64_json"]:
            payload["response_format"] = fmt
            try:
                resp = requests.post(endpoint, headers=headers, json=payload, timeout=90)
                if resp.status_code != 200:
                    ultimo_erro = f"HTTP {resp.status_code} em {endpoint}: {resp.text}"
                    continue
                
                res_json = resp.json()
                if "data" in res_json and len(res_json["data"]) > 0:
                    first_item = res_json["data"][0]
                    if "url" in first_item and first_item["url"]:
                        img_resp = requests.get(first_item["url"], timeout=60)
                        if img_resp.status_code == 200:
                            return img_resp.content, model_name
                    if "b64_json" in first_item and first_item["b64_json"]:
                        return base64.b64decode(first_item["b64_json"]), model_name
                
                if "result" in res_json and res_json["result"].get("image"):
                    return base64.b64decode(res_json["result"]["image"]), model_name
            except Exception as e:
                ultimo_erro = f"Erro em {endpoint} ({fmt}): {str(e)}"

    raise RuntimeError(ultimo_erro or f"Nenhuma imagem válida retornada pelo modelo {model_name}")


def _obter_imagens_anexadas() -> list:
    """
    Coleta todas as imagens fornecidas no contexto (suporta 1 ou múltiplas imagens).
    """
    imagens = []
    
    # 1. Tenta obter do anexo único
    anexo_unico = ayla_state.ULTIMO_ANEXO_IMAGEM.get()
    if anexo_unico:
        if isinstance(anexo_unico, list):
            imagens.extend(anexo_unico)
        else:
            imagens.append(anexo_unico)
            
    # 2. Tenta obter do anexo múltiplo se houver
    anexos_multiplos = ayla_state.ULTIMAS_IMAGENS_MODULO.get()
    if anexos_multiplos and isinstance(anexos_multiplos, list):
        for item in anexos_multiplos:
            if item not in imagens:
                imagens.append(item)
                
    return imagens


def gerar_imagem(prompt: str, proporcao: str = "1:1") -> str:
    """
    Gera uma nova imagem em resolução 4K (máximo 4096px) ou edita/combina imagens anexadas no chat a partir de um prompt em inglês.
    Permite escolher a proporção de aspecto (ex: '1:1', '16:9', '9:16', '4:3', '3:4', '21:9', '3:2', '2:3').
    """
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=env_path, override=True)
    except Exception:
        pass

    api_token = os.getenv("ARK_API_KEY", "").strip() or os.getenv("BYTEDANCE_SEED_API_KEY", "").strip() or os.getenv("SEED_API_KEY", "").strip()

    if not api_token:
        return (
            "⚠️ A chave `ARK_API_KEY` não está configurada no arquivo `.env`!\n"
            "Por favor, configure `ARK_API_KEY=ark-1c87b...` no `.env` para usar esta função."
        )

    # Normaliza a proporção de aspecto solicitada
    prop_clean = str(proporcao or "1:1").strip().replace(" ", "")
    size_info = PROPORCOES_4K.get(prop_clean, PROPORCOES_4K["1:1"])

    # Coleta todas as imagens anexadas (suporta 1 ou várias)
    imagens_anexadas = _obter_imagens_anexadas()

    qtd_imagens = len(imagens_anexadas)
    if qtd_imagens > 1:
        modo_operacao = f"Edição / Composição com {qtd_imagens} Imagens (4K Max 4096px - {size_info['ratio']})"
    elif qtd_imagens == 1:
        modo_operacao = f"Edição / Img2Img (4K Max 4096px - {size_info['ratio']})"
    else:
        modo_operacao = f"Geração do Zero (4K Max 4096px - {size_info['ratio']})"

    prompt_final = prompt.strip()

    model_name = os.getenv("ARK_IMAGE_MODEL", "").strip() or "CONFIGURE_LOCALMENTE"
    img_data = None
    modelo_sucesso = None
    erros = []

    try:
        img_data, modelo_sucesso = _chamar_bytedance_seed(
            model_name=model_name,
            api_key=api_token,
            prompt=prompt_final,
            size_info=size_info,
            image_inputs=imagens_anexadas if imagens_anexadas else None
        )
    except Exception as e:
        erros.append(f"{model_name}: {e}")

    if not img_data:
        return (
            f"⚠️ Erro ao processar imagem via ByteDance Seed (Volcengine Ark)!\n"
            f"Erros encontrados:\n" + "\n".join(erros)
        )

    # Pasta de saída da Ayla
    pasta_saida = Path(__file__).resolve().parent.parent.parent / "Aylafotitos"
    pasta_saida.mkdir(parents=True, exist_ok=True)

    prefixo = "editada" if imagens_anexadas else "gerada"
    data_hora = _dt.now().strftime("%Y%m%d_%H%M%S")
    nome_arquivo = f"{prefixo}_4k_{data_hora}_{uuid.uuid4().hex[:6]}.png"
    caminho_final = pasta_saida / nome_arquivo

    with open(caminho_final, "wb") as f:
        f.write(img_data)

    # Abre a imagem no aplicativo padrão de Galeria/Fotos do Windows
    try:
        open_path(caminho_final)
    except Exception as exc:
        print(f'Imagem salva; visualizador indisponível: {exc}')

    # Atualiza a variável global para que o bot envie a imagem em anexo
    ayla_state.ULTIMA_IMAGEM_GERADA.set(str(caminho_final))

    return (
        f"🎨 Imagem 4K processada com sucesso ({modo_operacao}) via ByteDance Seed (Seedream 4.5)!\n"
        f"🤖 Modelo: {modelo_sucesso}\n"
        f"📐 Resolução Máxima: {size_info['size']} ({size_info['ratio']})\n"
        f"🖼️ Imagens de referência utilizadas: {qtd_imagens}\n"
        f"📁 Salva em: {caminho_final}\n"
        f"🖼️ A imagem será enviada junto com a resposta!"
    )


# ── Registro das ferramentas ──
if "TOOL_MAP" in globals():
    TOOL_MAP["gerar_imagem"] = gerar_imagem

if "FUNCTION_DECLARATIONS" in globals():
    FUNCTION_DECLARATIONS.append({
        "name": "gerar_imagem",
        "description": "Gera uma nova imagem em resolução 4K (máximo de 4096px) do zero ou edita/modifica/combina de 1 a 10 imagens anexadas no chat, permitindo escolher a proporção de aspecto.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "A descrição detalhada em INGLÊS do que desenhar ou das modificações/mesclas a fazer nas imagens anexadas."
                },
                "proporcao": {
                    "type": "string",
                    "description": "A proporção de aspecto (Aspect Ratio) da imagem. Opções (máximo 4096px): '1:1' (quadrada 4096x4096), '16:9' (widescreen 4096x2304), '9:16' (vertical/stories 2304x4096), '4:3' (4096x3072), '3:4' (3072x4096), '21:9' (ultrawide 4096x1755), '3:2' (4096x2730), '2:3' (2730x4096). Padrão: '1:1'."
                }
            },
            "required": ["prompt"]
        }
    })
