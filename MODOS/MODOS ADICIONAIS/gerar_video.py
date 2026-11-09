"""Gera vídeos com IA a partir de texto ou mídias anexadas."""
from ayla_platform import open_path
import sys
import os
import time
import uuid
import json
import base64
import requests
from pathlib import Path
from datetime import datetime as _dt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import ayla_state

# Mapeamento de proporções de aspecto para resoluções de vídeo
PROPORCOES_VIDEO = {
    "16:9": {"ratio": "16:9", "width": 1280, "height": 720, "desc": "Widescreen / YouTube (16:9)"},
    "9:16": {"ratio": "9:16", "width": 720, "height": 1280, "desc": "Vertical / Reels / TikTok (9:16)"},
    "1:1":  {"ratio": "1:1",  "width": 1024, "height": 1024, "desc": "Quadrado / Feed (1:1)"},
    "4:3":  {"ratio": "4:3",  "width": 1024, "height": 768,  "desc": "Padrão 4:3"},
    "3:4":  {"ratio": "3:4",  "width": 768,  "height": 1024, "desc": "Vertical 3:4"},
    "21:9": {"ratio": "21:9", "width": 1280, "height": 548,  "desc": "Ultrawide Cinema (21:9)"},
}

def _obter_anexos_midia() -> list:
    """
    Coleta todas as imagens e vídeos fornecidos no contexto.
    """
    midias = []
    
    # 1. Imagem única
    anexo_img = ayla_state.ULTIMO_ANEXO_IMAGEM.get()
    if anexo_img:
        if isinstance(anexo_img, list):
            midias.extend(anexo_img)
        else:
            midias.append(anexo_img)
            
    # 2. Imagens múltiplas
    anexos_multiplos = ayla_state.ULTIMAS_IMAGENS_MODULO.get()
    if anexos_multiplos and isinstance(anexos_multiplos, list):
        for item in anexos_multiplos:
            if item not in midias:
                midias.append(item)

    # 3. Vídeo anexado
    anexo_vid = ayla_state.ULTIMO_ANEXO_VIDEO.get()
    if anexo_vid:
        if isinstance(anexo_vid, list):
            for v in anexo_vid:
                if v not in midias:
                    midias.append(v)
        elif anexo_vid not in midias:
            midias.append(anexo_vid)

    return midias


def _chamar_bytedance_seedance_video(model_name: str, api_key: str, prompt: str, size_info: dict, duracao: int = 5, media_inputs: list = None) -> tuple:
    """
    Realiza a chamada para a API da Volcengine Ark (ByteDance Seed) para geração de vídeo.
    Suporta criação de tarefas assíncronas com polling e endpoints diretos.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    base_urls = [
        "https://ark.cn-beijing.volces.com/api/v3",
        "https://ark.ap-southeast.bytepluses.com/api/v3"
    ]

    # Prepara lista de imagens/vídeos de entrada se fornecidos (Image-to-Video)
    image_urls = []
    if media_inputs:
        for item in media_inputs:
            if isinstance(item, tuple) and len(item) == 2:
                img_b, mime = item
                b64_img = base64.b64encode(img_b).decode("utf-8")
                image_urls.append(f"data:{mime};base64,{b64_img}")
            elif isinstance(item, str):
                if item.startswith("http://") or item.startswith("https://") or item.startswith("data:"):
                    image_urls.append(item)
                elif os.path.exists(item):
                    try:
                        ext = os.path.splitext(item)[1].lower().strip(".")
                        mime = f"image/{ext}" if ext in ["png", "jpg", "jpeg", "webp"] else "application/octet-stream"
                        with open(item, "rb") as f:
                            b64_img = base64.b64encode(f.read()).decode("utf-8")
                        image_urls.append(f"data:{mime};base64,{b64_img}")
                    except Exception:
                        pass

    ultimo_erro = None

    for base_url in base_urls:
        # Formatos de payload para criação de tarefas (Task API OpenAPI v3)
        task_endpoints = [
            f"{base_url}/contents/generations/tasks",
            f"{base_url}/video/generations/tasks",
            f"{base_url}/video/generations"
        ]

        # Constrói o payload adaptativo
        content_items = [{"type": "text", "text": prompt}]
        for url in image_urls:
            content_items.append({
                "type": "image_url",
                "image_url": {"url": url}
            })

        payload_variants = [
            # Formato 1: Content array com tarefas
            {
                "model": model_name,
                "content": content_items,
                "duration": duracao,
                "ratio": size_info.get("ratio", "16:9"),
                "aspect_ratio": size_info.get("ratio", "16:9"),
                "fps": 24
            },
            # Formato 2: Prompt topo com image_urls
            {
                "model": model_name,
                "prompt": prompt,
                "image_urls": image_urls if image_urls else None,
                "duration": duracao,
                "ratio": size_info.get("ratio", "16:9"),
                "width": size_info.get("width", 1280),
                "height": size_info.get("height", 720)
            }
        ]

        for endpoint in task_endpoints:
            for payload in payload_variants:
                # Remove chaves com None
                clean_payload = {k: v for k, v in payload.items() if v is not None}
                try:
                    resp = requests.post(endpoint, headers=headers, json=clean_payload, timeout=60)
                    if resp.status_code not in (200, 201, 202):
                        ultimo_erro = f"HTTP {resp.status_code} em {endpoint}: {resp.text}"
                        continue

                    try:
                        res_json = resp.json()
                    except Exception:
                        ultimo_erro = f"HTTP {resp.status_code} em {endpoint}: resposta não é JSON ({resp.text[:150]})"
                        continue

                    # 1. Se a API retornou direto o vídeo em 'data' ou 'result'
                    video_url = None
                    if "data" in res_json and len(res_json["data"]) > 0:
                        first = res_json["data"][0]
                        video_url = first.get("url") or first.get("video_url")
                        if not video_url and "b64_json" in first:
                            return base64.b64decode(first["b64_json"]), model_name

                    if not video_url and "result" in res_json:
                        video_url = res_json["result"].get("video_url") or res_json["result"].get("url")
                        if not video_url and res_json["result"].get("video"):
                            return base64.b64decode(res_json["result"]["video"]), model_name

                    if video_url:
                        vid_resp = requests.get(video_url, timeout=120)
                        if vid_resp.status_code == 200:
                            return vid_resp.content, model_name

                    # 2. Se a API retornou um ID de Tarefa Assíncrona (Task ID)
                    task_id = res_json.get("id") or res_json.get("task_id") or (res_json.get("data", {}).get("id") if isinstance(res_json.get("data"), dict) else None)

                    if task_id:
                        print(f"🎬 Tarefa de vídeo iniciada na Ark ({task_id}). Aguardando processamento...")
                        # Loop de Polling (até 300 segundos = 5 minutos)
                        tempo_inicio = time.time()
                        status_url = f"{endpoint.rstrip('/')}/{task_id}"

                        while time.time() - tempo_inicio < 300:
                            time.sleep(5)
                            try:
                                poll_resp = requests.get(status_url, headers=headers, timeout=30)
                                if poll_resp.status_code != 200:
                                    # Tenta URL genérica de task se a específica falhar
                                    poll_resp = requests.get(f"{base_url}/contents/generations/tasks/{task_id}", headers=headers, timeout=30)

                                if poll_resp.status_code == 200:
                                    p_json = poll_resp.json()
                                    status = str(p_json.get("status") or p_json.get("task_status", "")).lower()

                                    if status in ["succeeded", "success", "completed", "done"]:
                                        # Extrai URL do vídeo
                                        v_url = (
                                            p_json.get("content", {}).get("video_url") if isinstance(p_json.get("content"), dict) else None
                                        ) or (
                                            p_json.get("data", {}).get("video_url") if isinstance(p_json.get("data"), dict) else None
                                        ) or (
                                            p_json.get("result", {}).get("video_url") if isinstance(p_json.get("result"), dict) else None
                                        )
                                        
                                        if not v_url and "data" in p_json and isinstance(p_json["data"], list) and len(p_json["data"]) > 0:
                                            v_url = p_json["data"][0].get("url") or p_json["data"][0].get("video_url")

                                        if v_url:
                                            v_resp = requests.get(v_url, timeout=120)
                                            if v_resp.status_code == 200:
                                                return v_resp.content, model_name

                                    elif status in ["failed", "error", "cancelled"]:
                                        err_msg = p_json.get("error") or p_json.get("message") or status
                                        raise RuntimeError(f"Geração de vídeo falhou no servidor: {err_msg}")
                            except RuntimeError:
                                raise
                            except Exception as poll_e:
                                print(f"⚠️ Aguardando vídeo ({task_id}): {poll_e}")
                except Exception as e:
                    ultimo_erro = f"Erro em {endpoint}: {str(e)}"

    raise RuntimeError(ultimo_erro or f"Nenhum vídeo válido retornado pelo modelo {model_name}")


def gerar_video(prompt: str, proporcao: str = "16:9", duracao: int = 5) -> str:
    """
    Gera um novo vídeo animado a partir de um prompt em inglês usando o modelo 'seedance-1-5-pro-251215' via ByteDance Seed (Volcengine Ark).
    Suporta Text-to-Video e Image-to-Video (a partir de imagens ou vídeos anexados no chat).
    Permite escolher a proporção de aspecto ('16:9', '9:16', '1:1', '4:3', '3:4', '21:9') e duração em segundos (5 ou 10).
    """
    api_token = os.getenv("ARK_API_KEY", "").strip() or os.getenv("BYTEDANCE_SEED_API_KEY", "").strip() or os.getenv("SEED_API_KEY", "").strip()

    if not api_token:
        return (
            "⚠️ A chave `ARK_API_KEY` não está configurada no arquivo `.env`!\n"
            "Por favor, configure `ARK_API_KEY=ark-1c87b...` no `.env` para usar a geração de vídeo."
        )

    # Normaliza a proporção de aspecto solicitada
    prop_clean = str(proporcao or "16:9").strip().replace(" ", "")
    size_info = PROPORCOES_VIDEO.get(prop_clean, PROPORCOES_VIDEO["16:9"])

    # Normaliza a duração
    try:
        dur_val = int(duracao)
        if dur_val not in [5, 10]:
            dur_val = 5
    except Exception:
        dur_val = 5

    # Coleta todas as mídias anexadas
    anexos_midia = _obter_anexos_midia()
    qtd_anexos = len(anexos_midia)

    if qtd_anexos > 0:
        modo_operacao = f"Image-to-Video com {qtd_anexos} anexo(s) ({size_info['ratio']}, {dur_val}s)"
        prompt_final = prompt.strip()
    else:
        modo_operacao = f"Text-to-Video do zero ({size_info['ratio']}, {dur_val}s)"
        prompt_final = prompt.strip()
        suffix_anime = ", high quality 3d animation, smooth motion, detailed, 4k resolution, cinematic lighting, masterpiece"
        if not any(tag in prompt_final.lower() for tag in ["anime", "animation", "cinematic", "3d", "render"]):
            prompt_final += suffix_anime

    model_name = "seedance-1-5-pro-251215"
    video_data = None
    modelo_sucesso = None
    erros = []

    try:
        video_data, modelo_sucesso = _chamar_bytedance_seedance_video(
            model_name=model_name,
            api_key=api_token,
            prompt=prompt_final,
            size_info=size_info,
            duracao=dur_val,
            media_inputs=anexos_midia if anexos_midia else None
        )
    except Exception as e:
        erros.append(f"{model_name}: {e}")

    if not video_data:
        return (
            f"⚠️ Erro ao processar vídeo via ByteDance Seed (Volcengine Ark)!\n"
            f"Erros encontrados:\n" + "\n".join(erros)
        )

    # Pasta de saída da Ayla
    pasta_saida = Path(__file__).resolve().parent.parent.parent / "Aylafotitos"
    pasta_saida.mkdir(parents=True, exist_ok=True)

    prefixo = "video_img2vid" if anexos_midia else "video_text2vid"
    data_hora = _dt.now().strftime("%Y%m%d_%H%M%S")
    nome_arquivo = f"{prefixo}_{data_hora}_{uuid.uuid4().hex[:6]}.mp4"
    caminho_final = pasta_saida / nome_arquivo

    with open(caminho_final, "wb") as f:
        f.write(video_data)

    # Abre o vídeo no aplicativo padrão do sistema
    try:
        open_path(caminho_final)
    except Exception:
        pass

    # Atualiza a variável global para que o bot envie o vídeo gerado
    ayla_state.ULTIMA_IMAGEM_GERADA.set(str(caminho_final))

    return (
        f"🎬 Video gerado com sucesso ({modo_operacao}) via ByteDance Seedance!\n"
        f"🤖 Modelo: {modelo_sucesso}\n"
        f"📐 Proporção: {size_info['ratio']} ({size_info['width']}x{size_info['height']})\n"
        f"⏱️ Duração: {dur_val} segundos\n"
        f"🖼️ Mídias de referência: {qtd_anexos}\n"
        f"📁 Salvo em: {caminho_final}\n"
        f"🎥 O vídeo será enviado junto com a resposta!"
    )


# Aliases para exportação
gerar_video_seedance = gerar_video
criar_video = gerar_video

# ── Registro das ferramentas e suporte a recarregamento dinâmico ──
FERRAMENTAS_VIDEO = {
    "gerar_video": gerar_video,
    "gerar_video_seedance": gerar_video,
    "criar_video": gerar_video,
}

DECLARACOES_VIDEO = [
    {
        "name": "gerar_video",
        "description": "Gera um novo vídeo animado usando o modelo 'seedance-1-5-pro-251215' via ByteDance Seed (Volcengine Ark). Suporta Text-to-Video e Image-to-Video a partir de imagens/vídeos anexados.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "A descrição detalhada em INGLÊS da cena, movimentos de câmera e ações para gerar o vídeo."
                },
                "proporcao": {
                    "type": "string",
                    "description": "A proporção de aspecto (Aspect Ratio) do vídeo. Opções: '16:9' (widescreen YouTube/PC), '9:16' (vertical Reels/TikTok/Stories), '1:1' (quadrado), '4:3', '3:4', '21:9' (cinema ultrawide). Padrão: '16:9'."
                },
                "duracao": {
                    "type": "integer",
                    "description": "Duração do vídeo em segundos (ex: 5 ou 10). Padrão: 5."
                }
            },
            "required": ["prompt"]
        }
    }
]

if "TOOL_MAP" in globals():
    TOOL_MAP.update(FERRAMENTAS_VIDEO)

if "FUNCTION_DECLARATIONS" in globals():
    for dec in DECLARACOES_VIDEO:
        if not any(existing.get("name") == dec["name"] for existing in FUNCTION_DECLARATIONS):
            FUNCTION_DECLARATIONS.append(dec)

def register(tool_map, function_declarations):
    """Função invocada pelo carregador dinâmico do bot principal (Ayla.py)."""
    tool_map.update(FERRAMENTAS_VIDEO)
    for dec in DECLARACOES_VIDEO:
        if not any(existing.get("name") == dec["name"] for existing in function_declarations):
            function_declarations.append(dec)
