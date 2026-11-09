"""Consulta preços, descontos e detalhes de jogos na Steam."""
from ayla_paths import project_path
import sys
import os
import json
import requests
from urllib.parse import quote_plus
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import ayla_state

if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
}

def pesquisar_jogo_steam(nome_jogo: str) -> str:
    """
    Pesquisa um jogo na loja da Steam, trazendo preço atual, desconto, avaliação,
    descrição e baixando a capa oficial do jogo.
    """
    nome_limpo = nome_jogo.strip()
    if not nome_limpo:
        return "⚠️ Informe o nome de um jogo para pesquisar na Steam!"

    try:
        url_busca = f"https://store.steampowered.com/api/storesearch/?term={quote_plus(nome_limpo)}&l=portuguese&cc=BR"
        res_busca = requests.get(url_busca, headers=_HEADERS, timeout=8)
        if res_busca.status_code != 200:
            return f"❌ Erro ao consultar a loja da Steam (HTTP {res_busca.status_code})."

        dados_busca = res_busca.json()
        itens = dados_busca.get("items", [])
        if not itens:
            return f"ℹ️ Nenhum jogo encontrado na Steam para '{nome_limpo}'."

        # Prefere o título exato para evitar escolher outro jogo da busca.
        normalizar = lambda nome: " ".join(str(nome).casefold().split())
        primeiro = next(
            (item for item in itens
             if normalizar(item.get("name", "")) == normalizar(nome_limpo)),
            itens[0],
        )
        appid = primeiro.get("id")

        # A busca também retorna pacotes (sub), com endpoint e link próprios.
        pacote = primeiro.get("type") == "sub"
        endpoint = "packagedetails" if pacote else "appdetails"
        parametro = "packageids" if pacote else "appids"
        url_detalhes = f"https://store.steampowered.com/api/{endpoint}?{parametro}={appid}&cc=BR&l=portuguese"
        res_detalhes = requests.get(url_detalhes, headers=_HEADERS, timeout=8)

        titulo = primeiro.get("name", nome_limpo)
        url_loja = f"https://store.steampowered.com/{'sub' if pacote else 'app'}/{appid}"
        preco_formatado = "Preço indisponível no momento; consulte a página da Steam."
        # Preserva o preço confirmado pela busca mesmo se os detalhes falharem.
        preco_busca = primeiro.get("price") or {}
        if preco_busca.get("currency") == "BRL" and isinstance(preco_busca.get("final"), (int, float)):
            valor = f"{preco_busca['final'] / 100:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
            preco_formatado = f"R$ {valor}"
        desconto_str = ""
        descricao = ""
        header_image = primeiro.get("tiny_image", "")

        if res_detalhes.status_code == 200:
            detalhes_json = res_detalhes.json().get(str(appid), {})
            if detalhes_json.get("success"):
                data = detalhes_json.get("data", {})
                titulo = data.get("name", titulo)
                descricao = data.get("short_description", "")
                header_image = data.get("header_image", header_image)

                price_overview = data.get("price") if pacote else data.get("price_overview")
                if price_overview and price_overview.get("final_formatted"):
                    final_price = price_overview["final_formatted"]
                    initial_price = price_overview.get("initial_formatted", "")
                    discount = price_overview.get("discount_percent", 0)
                    if discount > 0:
                        preco_formatado = f"~~{initial_price}~~ ➡️ **{final_price}**"
                        desconto_str = f" 🔥 **-{discount}% DE DESCONTO!**"
                    else:
                        preco_formatado = final_price
                elif data.get("is_free") is True:
                    preco_formatado = "Gratuito para Jogar"

        # Tenta baixar a capa do jogo
        if header_image:
            try:
                res_img = requests.get(header_image, headers=_HEADERS, timeout=5)
                if res_img.status_code == 200:
                    pasta = project_path('Aylafotitos')
                    pasta.mkdir(parents=True, exist_ok=True)
                    arq_img = pasta / f"steam_{appid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                    arq_img.write_bytes(res_img.content)
                    ayla_state.ULTIMA_IMAGEM_GERADA.set(str(arq_img))
            except Exception:
                pass

        resposta = (
            f"🎮 **Steam — {titulo}**{desconto_str}\n\n"
            f"💰 **Preço:** {preco_formatado}\n"
            f"📝 **Descrição:** {descricao[:300]}...\n\n"
            f"🔗 **Página na Steam:** {url_loja}"
        )
        return resposta

    except Exception as e:
        return f"⚠️ Erro ao pesquisar jogo na Steam: {e}"

TOOL_MAP["pesquisar_jogo_steam"] = pesquisar_jogo_steam
FUNCTION_DECLARATIONS.append({
    "name": "pesquisar_jogo_steam",
    "description": "Pesquisa um jogo na loja da Steam. Retorna preço atual, descontos, descrição e capa oficial do jogo.",
    "parameters": {
        "type": "object",
        "properties": {
            "nome_jogo": {"type": "string", "description": "Nome do jogo a pesquisar na Steam"}
        },
        "required": ["nome_jogo"]
    }
})
