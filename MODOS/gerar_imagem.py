"""
🎨 Módulo: Geração de Imagens com SiliconFlow e Qwen/Qwen-Image-Edit
Exclusivo para a dona!
Usa o modelo Qwen/Qwen-Image-Edit via SiliconFlow.
"""

def gerar_imagem(prompt: str) -> str:
    """
    Gera uma imagem usando o modelo Qwen/Qwen-Image-Edit da SiliconFlow.
    Se houver um anexo de imagem (máximo 1) no contexto da Ayla, ele será usado
    como exemplo (reference image) para orientar a geração. Caso contrário, a
    imagem será criada do zero a partir do *prompt*.
    """
    import requests, os, uuid, io, base64
    from pathlib import Path
    from datetime import datetime as _dt

    api_token = os.getenv("SILICONFLOW_API_KEY", "").strip()
    if not api_token:
        return (
            "⚠️ A chave `SILICONFLOW_API_KEY` não está configurada no arquivo `.env`!\n"
            "Por favor, adicione `SILICONFLOW_API_KEY=seu_token_aqui` no arquivo `.env` para usar esta função."
        )

    url = "https://api.siliconflow.com/v1/images/generations"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }

    # Garante o foco no estilo anime adicionando tags de estilo
    prompt_anime = prompt.strip()
    suffix_anime = ", anime key visual, anime style, highly detailed 2d illustration, vibrant colors, masterpiece, anime aesthetic"
    if not any(tag in prompt_anime.lower() for tag in ["anime", "manga", "illustration", "drawing", "2d"]):
        prompt_anime += suffix_anime
    else:
        # Se já tiver alguma palavra-chave de estilo, apenas reforça a qualidade e o estilo
        prompt_anime += ", anime style, masterpiece, highly detailed"

    # Monta o payload. Se houver imagem de exemplo, inclui‑a como base64 data URL.
    payload = {
        "model": "Qwen/Qwen-Image-Edit",
        "prompt": prompt_anime,
        "image_size": "1024x1024",
    }

    # Verifica se há um anexo de imagem armazenado globalmente (exemplo).
    exemplo = globals().get("ULTIMO_ANEXO_IMAGEM")
    if exemplo:
        img_bytes, mime_type = exemplo
        # Converte para data URL base64 conforme esperado pela API.
        base64_str = base64.b64encode(img_bytes).decode("utf-8")
        data_url = f"data:{mime_type};base64,{base64_str}"
        payload["image"] = data_url

    try:
        # Envia a requisição para a API do SiliconFlow
        resp = requests.post(url, json=payload, headers=headers, timeout=120)
        resp.raise_for_status()

        dados = resp.json()
        if "error" in dados:
            return f"⚠️ Erro retornado pelo SiliconFlow: {dados['error'].get('message', 'Erro desconhecido')}"

        images = dados.get("images", [])
        if not images:
            return f"⚠️ O SiliconFlow não retornou nenhuma imagem. Resposta: {dados}"

        image_url = images[0].get("url", "")
        if not image_url:
            return "⚠️ Não foi possível obter o link da imagem gerada."

        # Baixa os bytes da imagem (suporta base64 Data URI e URL HTTP)
        if image_url.startswith("data:") and ";base64," in image_url:
            header, base64_data = image_url.split(";base64,", 1)
            img_data = base64.b64decode(base64_data)
        elif image_url.startswith("http://") or image_url.startswith("https://"):
            img_resp = requests.get(image_url, timeout=60)
            img_resp.raise_for_status()
            img_data = img_resp.content
        else:
            img_data = base64.b64decode(image_url)

        # Pasta de saída da Ayla
        projeto_raiz = Path(__file__).resolve().parent.parent
        pasta_saida = projeto_raiz / "Aylafotitos"
        pasta_saida.mkdir(parents=True, exist_ok=True)

        data_hora = _dt.now().strftime("%Y%m%d_%H%M%S")
        nome_arquivo = f"flux_{data_hora}_{uuid.uuid4().hex[:6]}.png"
        caminho_final = pasta_saida / nome_arquivo

        with open(caminho_final, "wb") as f:
            f.write(img_data)

        # Abre a pasta da galeria automaticamente no Windows
        os.startfile(pasta_saida)

        # Atualiza a variável global para que o bot envie a imagem em anexo
        global ULTIMA_IMAGEM_GERADA
        ULTIMA_IMAGEM_GERADA = str(caminho_final)
        globals()["ULTIMA_IMAGEM_GERADA"] = str(caminho_final)

        return (
            f"🎨 Imagem gerada com sucesso via SiliconFlow!\n"
            f"🤖 Modelo: Qwen/Qwen-Image-Edit\n"
            f"📁 Salva em: {caminho_final}\n"
            f"🖼️ A imagem gerada será enviada junto com a resposta!"
        )

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response else "?"
        corpo = ""
        try:
            corpo = e.response.json()
        except Exception:
            try:
                corpo = e.response.text[:500]
            except Exception:
                pass

        if isinstance(corpo, dict) and "error" in corpo:
            err_msg = corpo["error"].get("message", "")
            return f"⚠️ Erro HTTP {status} no SiliconFlow: {err_msg}"
        return f"⚠️ Erro HTTP {status} ao se comunicar com o SiliconFlow: {corpo}"
    except requests.exceptions.Timeout:
        return "⚠️ A API do SiliconFlow demorou demais para responder (timeout)!"
    except Exception as e:
        return f"⚠️ Erro ao processar imagem: {e}"


# ── Registro da ferramenta ──
TOOL_MAP["gerar_imagem"] = gerar_imagem
# Alias para usar a mesma função como "editar imagem"
TOOL_MAP["editar_imagem"] = gerar_imagem

FUNCTION_DECLARATIONS.append({
    "name": "gerar_imagem",
    "description": (
        "Gera uma imagem usando o modelo Qwen/Qwen-Image-Edit da SiliconFlow. "
        "Se houver um anexo de imagem (máximo 1) no contexto, ele será usado como exemplo. "
        "O prompt deve ser detalhado e em INGLÊS."
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

# Declaração adicional para a mesma funcionalidade como "editar imagem"
FUNCTION_DECLARATIONS.append({
    "name": "editar_imagem",
    "description": (
        "Edita ou gera uma imagem usando o modelo Qwen/Qwen-Image-Edit da SiliconFlow. "
        "Se houver um anexo de imagem (máximo 1) no contexto, ele será usado como referência; "
        "caso contrário, a imagem será criada do zero."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "Prompt detalhado em INGLÊS para gerar ou editar a imagem."
            }
        },
        "required": ["prompt"]
    }
})
