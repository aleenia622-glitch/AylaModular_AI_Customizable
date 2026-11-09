"""Pesquisa e abre vídeos no YouTube, lê transcrições e gerencia favoritos."""
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ayla_youtube import (
    pesquisar_youtube,
    lancar_video,
    obter_transcricao,
    salvar_video_na_biblioteca,
    carregar_biblioteca,
    remover_video_da_biblioteca,
    extrair_video_id
)

if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []


def tool_pesquisar_youtube(busca: str, limite: int = 5) -> str:
    """Pesquisa vídeos no YouTube por nome ou assunto e retorna uma lista formatada."""
    resultados = pesquisar_youtube(query=busca, limite=limite)
    if not resultados:
        return f"ℹ️ Nenhum vídeo encontrado no YouTube para '{busca}'."
    
    linhas = [f"▶️ **Resultados da pesquisa no YouTube por:** \"{busca}\"\n"]
    for idx, v in enumerate(resultados, 1):
        dur = f" (`{v['duration']}`)" if v.get('duration') else ""
        views = f" • {v['views']}" if v.get('views') else ""
        linhas.append(
            f"{idx}. **[{v['title']}]({v['url']})**\n"
            f"   👤 Canal: {v['channel']}{dur}{views}\n"
            f"   🔗 Link: {v['url']} (ID: `{v['id']}`)"
        )
    
    return "\n\n".join(linhas)


def tool_lancar_video_youtube(nome_ou_link: str) -> str:
    """
    Lança um vídeo no YouTube: Encontra o link/vídeo pelo nome ou URL, coloca o link no chat e ABRE NA HORA no navegador do PC.
    """
    resultado = lancar_video(nome_ou_link, abrir_no_pc=True)
    if not resultado.get("sucesso"):
        return f"⚠️ Erro ao lançar vídeo: {resultado.get('erro')}"

    v = resultado["video"]
    dur = f" (`{v.get('duration')}`)" if v.get('duration') and v.get('duration') != "N/A" else ""
    channel = v.get("channel", "YouTube")

    return (
        f"🚀 **Lançado no seu navegador, usuario!** ▶️\n\n"
        f"📌 **[{v.get('title')}]({resultado['url']})**{dur}\n"
        f"👤 Canal: `{channel}`\n"
        f"🔗 Link: {resultado['url']}\n\n"
        f"*(Já abri no seu navegador do computador pra você assistir na hora! 🎬)*"
    )


def tool_obter_transcricao_youtube(video_id_ou_url: str) -> str:
    """Obtém a legenda/transcrição em texto do vídeo."""
    res = obter_transcricao(video_id_ou_url)
    if not res.get("sucesso"):
        return f"⚠️ Não foi possível obter as legendas do vídeo (`{res.get('video_id')}`): {res.get('erro')}"
    
    return (
        f"📜 **Transcrição do vídeo (`{res['video_id']}`):**\n\n"
        f"{res['texto']}\n\n"
        f"*(Total de {res['total_linhas']} linhas capturadas)*"
    )


def tool_salvar_video_youtube(video_id_ou_url: str, nota: str = "Salvo pela Ayla 🐾") -> str:
    """Salva um vídeo na biblioteca de favoritos da Ayla."""
    v_id = extrair_video_id(video_id_ou_url)
    if not v_id:
        return "Erro: informe um ID ou link válido de vídeo do YouTube."
    res = pesquisar_youtube(v_id, limite=1)
    v_info = res[0] if res else {"id": v_id, "title": f"Vídeo {v_id}", "url": f"https://www.youtube.com/watch?v={v_id}"}
    
    r = salvar_video_na_biblioteca(v_info, nota=nota)
    if r.get("sucesso"):
        return f"📌 **Vídeo salvo na Biblioteca da Ayla!**\n🎬 Título: {v_info.get('title')}\n🔗 Link: {v_info.get('url')}"
    return f"⚠️ Erro ao salvar vídeo: {r.get('erro')}"


def tool_listar_biblioteca_youtube() -> str:
    """Lista todos os vídeos salvos na biblioteca da Ayla."""
    lib = carregar_biblioteca()
    if not lib:
        return "📚 A biblioteca de vídeos do YouTube da Ayla está vazia no momento!"
    
    linhas = ["📚 **Vídeos na Biblioteca da Ayla:**\n"]
    for idx, v in enumerate(lib, 1):
        linhas.append(
            f"{idx}. **[{v.get('title')}]({v.get('url')})**\n"
            f"   👤 {v.get('channel')} • ⏱️ {v.get('duration')}\n"
            f"   💬 Nota: *{v.get('note')}*\n"
            f"   🔗 {v.get('url')}"
        )
    return "\n\n".join(linhas)


# ══════════════════════════════════════════════════════════
#  REGISTRO DAS FERRAMENTAS PARA O MODELO Z.AI / BOT AYLA
# ══════════════════════════════════════════════════════════
TOOL_MAP["pesquisar_youtube"] = tool_pesquisar_youtube
FUNCTION_DECLARATIONS.append({
    "name": "pesquisar_youtube",
    "description": "Pesquisa vídeos no YouTube por palavra-chave ou título e retorna resultados com links e detalhes.",
    "parameters": {
        "type": "object",
        "properties": {
            "busca": {"type": "string", "description": "Termo ou título a pesquisar no YouTube"},
            "limite": {"type": "integer", "description": "Quantidade máxima de vídeos (1 a 15). Padrão: 5"}
        },
        "required": ["busca"]
    }
})

TOOL_MAP["lancar_video_youtube"] = tool_lancar_video_youtube
FUNCTION_DECLARATIONS.append({
    "name": "lancar_video_youtube",
    "description": "Busca um vídeo pelo nome ou URL, envia o link no chat e ABRE NA HORA no navegador do PC para assistir.",
    "parameters": {
        "type": "object",
        "properties": {
            "nome_ou_link": {"type": "string", "description": "Nome do vídeo, assunto ou URL/ID para lançar no PC"}
        },
        "required": ["nome_ou_link"]
    }
})

TOOL_MAP["obter_transcricao_youtube"] = tool_obter_transcricao_youtube
FUNCTION_DECLARATIONS.append({
    "name": "obter_transcricao_youtube",
    "description": "Lê as legendas/transcrição em texto de um vídeo do YouTube para entender ou resumir o conteúdo.",
    "parameters": {
        "type": "object",
        "properties": {
            "video_id_ou_url": {"type": "string", "description": "ID ou URL do vídeo"}
        },
        "required": ["video_id_ou_url"]
    }
})

TOOL_MAP["salvar_video_youtube"] = tool_salvar_video_youtube
FUNCTION_DECLARATIONS.append({
    "name": "salvar_video_youtube",
    "description": "Salva um vídeo do YouTube na biblioteca de favoritos da Ayla.",
    "parameters": {
        "type": "object",
        "properties": {
            "video_id_ou_url": {"type": "string", "description": "ID ou URL do vídeo"},
            "nota": {"type": "string", "description": "Nota ou comentário sobre o vídeo"}
        },
        "required": ["video_id_ou_url"]
    }
})

TOOL_MAP["listar_biblioteca_youtube"] = tool_listar_biblioteca_youtube
FUNCTION_DECLARATIONS.append({
    "name": "listar_biblioteca_youtube",
    "description": "Lista todos os vídeos salvos na biblioteca do YouTube da Ayla.",
    "parameters": {
        "type": "object",
        "properties": {}
    }
})
