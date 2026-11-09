"""Consulta e altera perfil, status e atividade do bot no Discord."""
from ayla_paths import resolve_path
import os
import sys
import json
import asyncio
import typing
import requests
import io
from pathlib import Path
import discord

try:
    import ayla_state
except ImportError:
    ayla_state = None



def _get_bot():
    bot = globals().get("bot")
    if not bot:
        ayla_mod = sys.modules.get("__main__")
        if ayla_mod and hasattr(ayla_mod, "bot"):
            bot = getattr(ayla_mod, "bot")
    return bot


def _run_async(coro, timeout: float = 30.0):
    bot = _get_bot()
    if not bot:
        return "❌ Erro: O objeto do bot do Discord não está disponível ou inicializado."
    
    loop = getattr(bot, "loop", None)
    if not loop or loop.is_closed():
        return "❌ Erro: O loop de eventos do Discord não está rodando."

    try:
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)
    except TimeoutError:
        return f"⏱️ A operação no Discord expirou após {timeout} segundos."
    except discord.Forbidden as e:
        return f"🚫 Permissão Negada pelo Discord! O bot não possui permissões suficientes para alterar esta propriedade. Detalhes: {e}"
    except discord.NotFound as e:
        return f"🔍 Objeto não encontrado no Discord. Detalhes: {e}"
    except discord.HTTPException as e:
        return f"❌ Erro HTTP do Discord (Status {e.status}): {e.text}"
    except Exception as e:
        return f"⚠️ Erro ao executar comando do bot: {e}"


def _get_guild(bot: discord.Client, guild_id_or_name: str = "") -> discord.Guild:
    if not bot or not hasattr(bot, "guilds"):
        return None
    
    if guild_id_or_name:
        target = str(guild_id_or_name).strip()
        # 1. Tenta por ID numérico
        if target.isdigit():
            g = bot.get_guild(int(target))
            if g:
                return g
        # 2. Tenta por nome exato ou parcial
        target_lower = target.lower()
        for g in bot.guilds:
            if g.name.lower() == target_lower:
                return g
        for g in bot.guilds:
            if target_lower in g.name.lower():
                return g

    # 3. Tenta contexto ativo se disponível
    if ayla_state and hasattr(ayla_state, "CONTEXTO_ATIVO"):
        try:
            ctx = ayla_state.CONTEXTO_ATIVO.get()
            if ctx and hasattr(ctx, "guild") and ctx.guild:
                return ctx.guild
        except Exception:
            pass

    # 4. Fallback: Primeiro servidor onde o bot está
    if bot.guilds:
        return bot.guilds[0]
    return None


def _load_image_bytes(url_or_path: str) -> bytes:
    """Carrega dados de imagem como bytes a partir de uma URL ou caminho de arquivo local."""
    if not url_or_path or str(url_or_path).strip().lower() in ("none", "remove", "null", "reset", "deletar"):
        return None
    
    val = str(url_or_path).strip()
    if val.lower().startswith(("http://", "https://")):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        resp = requests.get(val, headers=headers, timeout=20)
        resp.raise_for_status()
        return resp.content
    else:
        path = resolve_path(val)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Arquivo local de imagem não encontrado no caminho: '{val}'")
        return path.read_bytes()


# ══════════════════════════════════════════════════════════
#  FUNÇÕES ASÍNCRONAS INTERNAS
# ══════════════════════════════════════════════════════════

async def _async_get_profile(guild_id_or_name: str = ""):
    bot = _get_bot()
    if not bot or not bot.user:
        return "❌ Bot não está conectado ao Discord."
    
    user = bot.user
    info = {
        "perfil_global": {
            "id": str(user.id),
            "username": user.name,
            "discriminator": user.discriminator,
            "display_name": getattr(user, "display_name", user.name),
            "avatar_url": user.display_avatar.url if user.display_avatar else None,
            "banner_url": user.banner.url if getattr(user, "banner", None) else None,
            "bot": user.bot
        }
    }

    # Status & Presença do bot
    guild_sample = bot.guilds[0] if bot.guilds else None
    me_member = guild_sample.me if guild_sample else None
    
    status_str = "desconhecido"
    activity_str = "nenhuma"
    if me_member:
        status_str = str(me_member.status)
        if me_member.activity:
            act = me_member.activity
            act_type = str(act.type).replace("ActivityType.", "")
            act_name = getattr(act, "name", str(act))
            activity_str = f"{act_type}: {act_name}"
    
    info["perfil_global"]["status"] = status_str
    info["perfil_global"]["atividade"] = activity_str

    # Servidor específico ou detectado
    target_guild = _get_guild(bot, guild_id_or_name)
    if target_guild:
        me_in_guild = target_guild.me
        info["perfil_servidor"] = {
            "guild_id": str(target_guild.id),
            "guild_name": target_guild.name,
            "nickname": me_in_guild.nick,
            "display_name": me_in_guild.display_name,
            "guild_avatar_url": me_in_guild.guild_avatar.url if getattr(me_in_guild, "guild_avatar", None) else None,
            "display_avatar_url": me_in_guild.display_avatar.url if me_in_guild.display_avatar else None,
            "roles": [r.name for r in me_in_guild.roles if r.name != "@everyone"],
            "permissions_administrator": me_in_guild.guild_permissions.administrator
        }

    return f"🤖 **Perfil do Bot Discord:**\n```json\n{json.dumps(info, indent=2, ensure_ascii=False)}\n```"


async def _async_edit_global_profile(username: str = "", avatar_url_or_path: str = "", banner_url_or_path: str = ""):
    bot = _get_bot()
    if not bot or not bot.user:
        return "❌ Bot não está conectado ao Discord."
    
    kwargs = {}
    alteracoes = []

    if username and username.strip():
        kwargs["username"] = username.strip()
        alteracoes.append(f"Username global -> '{username.strip()}'")

    if avatar_url_or_path and avatar_url_or_path.strip():
        val = avatar_url_or_path.strip()
        if val.lower() in ("none", "remove", "null", "reset", "deletar"):
            kwargs["avatar"] = None
            alteracoes.append("Avatar global -> Removido")
        else:
            try:
                img_bytes = _load_image_bytes(val)
                kwargs["avatar"] = img_bytes
                alteracoes.append("Avatar global -> Atualizado com sucesso")
            except Exception as e:
                return f"❌ Erro ao carregar imagem para avatar global: {e}"

    if banner_url_or_path and banner_url_or_path.strip():
        val = banner_url_or_path.strip()
        if val.lower() in ("none", "remove", "null", "reset", "deletar"):
            kwargs["banner"] = None
            alteracoes.append("Banner global -> Removido")
        else:
            try:
                img_bytes = _load_image_bytes(val)
                kwargs["banner"] = img_bytes
                alteracoes.append("Banner global -> Atualizado com sucesso")
            except Exception as e:
                return f"❌ Erro ao carregar imagem para banner global: {e}"

    if not kwargs:
        return "⚠️ Nenhuma alteração foi especificada para o perfil global (passe username, avatar_url_or_path ou banner_url_or_path)."

    await bot.user.edit(**kwargs)
    return f"✅ **Perfil Global do Bot Atualizado com sucesso!**\n" + "\n".join(f"• {alt}" for alt in alteracoes)


async def _async_edit_server_profile(guild_id_or_name: str = "", nickname: str = None, avatar_url_or_path: str = None):
    bot = _get_bot()
    if not bot:
        return "❌ Bot não está conectado ao Discord."

    guild = _get_guild(bot, guild_id_or_name)
    if not guild:
        return f"❌ Servidor '{guild_id_or_name}' não foi encontrado ou o bot não pertence a ele."

    me = guild.me
    if not me:
        return f"❌ Não foi possível encontrar o perfil do membro do bot no servidor '{guild.name}'."

    kwargs = {}
    alteracoes = []

    if nickname is not None:
        nick_val = str(nickname).strip()
        if nick_val.lower() in ("reset", "remove", "none", "null", ""):
            kwargs["nick"] = None
            alteracoes.append("Apelido no servidor -> Removido (resetado para nome padrão)")
        else:
            kwargs["nick"] = nick_val
            alteracoes.append(f"Apelido no servidor -> '{nick_val}'")

    if avatar_url_or_path is not None:
        av_val = str(avatar_url_or_path).strip()
        if av_val.lower() in ("reset", "remove", "none", "null"):
            kwargs["avatar"] = None
            alteracoes.append("Avatar no servidor -> Removido (resetado para avatar global)")
        elif av_val:
            try:
                img_bytes = _load_image_bytes(av_val)
                kwargs["avatar"] = img_bytes
                alteracoes.append("Avatar no servidor -> Atualizado com sucesso")
            except Exception as e:
                return f"❌ Erro ao carregar imagem para avatar do servidor: {e}"

    if not kwargs:
        return "⚠️ Nenhuma alteração foi especificada para o perfil no servidor (passe nickname ou avatar_url_or_path)."

    await me.edit(**kwargs)
    return f"✅ **Perfil do Bot no Servidor '{guild.name}' (ID: {guild.id}) Atualizado!**\n" + "\n".join(f"• {alt}" for alt in alteracoes)


async def _async_set_presence(status: str = "", activity_type: str = "", activity_name: str = "", url: str = ""):
    bot = _get_bot()
    if not bot:
        return "❌ Bot não está conectado ao Discord."

    status_map = {
        "online": discord.Status.online,
        "idle": discord.Status.idle,
        "ausente": discord.Status.idle,
        "dnd": discord.Status.dnd,
        "do_not_disturb": discord.Status.dnd,
        "ocupado": discord.Status.dnd,
        "invisible": discord.Status.invisible,
        "invisivel": discord.Status.invisible,
        "offline": discord.Status.offline,
    }

    status_obj = status_map.get(status.lower().strip(), None) if status else None

    activity_obj = None
    act_clean = activity_type.lower().strip() if activity_type else ""

    if act_clean and act_clean not in ("none", "remove", "null", "reset"):
        name = activity_name.strip() if activity_name else "Ayla AI"
        
        if act_clean in ("playing", "jogando"):
            activity_obj = discord.Game(name=name)
        elif act_clean in ("streaming", "transmitindo", "live"):
            stream_url = url.strip() if url else "https://www.twitch.tv/discord"
            activity_obj = discord.Streaming(name=name, url=stream_url)
        elif act_clean in ("listening", "ouvindo"):
            activity_obj = discord.Activity(type=discord.ActivityType.listening, name=name)
        elif act_clean in ("watching", "assistindo"):
            activity_obj = discord.Activity(type=discord.ActivityType.watching, name=name)
        elif act_clean in ("competing", "competindo"):
            activity_obj = discord.Activity(type=discord.ActivityType.competing, name=name)
        elif act_clean in ("custom", "customizado"):
            activity_obj = discord.CustomActivity(name=name)
        else:
            activity_obj = discord.Game(name=name)

    await bot.change_presence(status=status_obj, activity=activity_obj)
    
    res = "✅ **Presença do Bot Atualizada!**\n"
    if status_obj:
        res += f"• Status: `{status_obj}`\n"
    if act_clean in ("none", "remove", "null", "reset"):
        res += f"• Atividade: Removida\n"
    elif activity_obj:
        res += f"• Atividade: `{activity_obj}`\n"

    return res


async def _async_list_guilds():
    bot = _get_bot()
    if not bot:
        return "❌ Bot não está conectado ao Discord."
    
    if not bot.guilds:
        return "ℹ️ O bot não está presente em nenhum servidor no momento."

    guilds_data = []
    for g in bot.guilds:
        me = g.me
        guilds_data.append({
            "id": str(g.id),
            "name": g.name,
            "member_count": g.member_count,
            "bot_nickname": me.nick if me else None,
            "icon_url": g.icon.url if g.icon else None,
            "owner_id": str(g.owner_id)
        })

    return f"🏰 **Servidores do Bot ({len(guilds_data)}):**\n```json\n{json.dumps(guilds_data, indent=2, ensure_ascii=False)}\n```"


# ══════════════════════════════════════════════════════════
#  FERRAMENTAS PÚBLICAS DO MÓDULO DISCORD_BOT
# ══════════════════════════════════════════════════════════

def discord_bot_get_profile(guild_id_or_name: str = "") -> str:
    """Obtém dados detalhados do perfil do bot no Discord (global e no servidor)."""
    return _run_async(_async_get_profile(guild_id_or_name))


def discord_bot_edit_global_profile(username: str = "", avatar_url_or_path: str = "", banner_url_or_path: str = "") -> str:
    """Altera o perfil geral/global do bot (Username, Avatar global, Banner global)."""
    return _run_async(_async_edit_global_profile(username, avatar_url_or_path, banner_url_or_path))


def discord_bot_edit_server_profile(guild_id_or_name: str = "", nickname: str = None, avatar_url_or_path: str = None) -> str:
    """Altera o perfil do bot em um servidor específico (Apelido/Nickname e Avatar no servidor)."""
    return _run_async(_async_edit_server_profile(guild_id_or_name, nickname, avatar_url_or_path))


def discord_bot_set_presence(status: str = "", activity_type: str = "", activity_name: str = "", url: str = "") -> str:
    """Altera o status e atividade do bot."""
    return _run_async(_async_set_presence(status, activity_type, activity_name, url))


def discord_bot_list_guilds() -> str:
    """Lista todos os servidores onde o bot está presente."""
    return _run_async(_async_list_guilds())


# ══════════════════════════════════════════════════════════
#  REGISTRO E COMPATIBILIDADE COM AYLA
# ══════════════════════════════════════════════════════════

FERRAMENTAS_DISCORD_BOT = {
    "discord_bot_get_profile": discord_bot_get_profile,
    "discord_bot_edit_global_profile": discord_bot_edit_global_profile,
    "discord_bot_edit_server_profile": discord_bot_edit_server_profile,
    "discord_bot_set_presence": discord_bot_set_presence,
    "discord_bot_list_guilds": discord_bot_list_guilds,
}

DECLARACOES_DISCORD_BOT = [
    {
        "name": "discord_bot_get_profile",
        "description": "Obtém dados completos do perfil do bot no Discord (global e servidor).",
        "parameters": {
            "type": "object",
            "properties": {
                "guild_id_or_name": {"type": "string", "description": "ID ou nome do servidor para consultar o perfil no servidor (opcional)."}
            }
        }
    },
    {
        "name": "discord_bot_edit_global_profile",
        "description": "Altera o perfil geral/global do bot no Discord (Username global, foto de perfil/Avatar global e Banner global).",
        "parameters": {
            "type": "object",
            "properties": {
                "username": {"type": "string", "description": "Novo nome de usuário global do bot."},
                "avatar_url_or_path": {"type": "string", "description": "URL de imagem ou caminho local para alterar o avatar global. Passe 'none' ou 'remove' para remover."},
                "banner_url_or_path": {"type": "string", "description": "URL de imagem ou caminho local para alterar o banner global. Passe 'none' ou 'remove' para remover."}
            }
        }
    },
    {
        "name": "discord_bot_edit_server_profile",
        "description": "Altera o perfil do bot em um servidor específico (Apelido/Nickname e Foto de Perfil/Avatar exclusivo no servidor).",
        "parameters": {
            "type": "object",
            "properties": {
                "guild_id_or_name": {"type": "string", "description": "ID ou nome do servidor onde o perfil será alterado (opcional; se omitido, usa o servidor ativo)."},
                "nickname": {"type": "string", "description": "Novo apelido (nickname) do bot no servidor. Passe string vazia ou 'reset' para remover o apelido."},
                "avatar_url_or_path": {"type": "string", "description": "URL de imagem ou caminho local para avatar exclusivo no servidor. Passe 'none' ou 'reset' para restaurar o avatar global."}
            }
        }
    },
    {
        "name": "discord_bot_set_presence",
        "description": "Altera o status (Online, Ausente, Ocupado/Não Perturbe, Invisível) e a atividade (Jogando, Transmitindo, Ouvindo, Assistindo, Competindo, Customizado) do bot.",
        "parameters": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Status do bot: 'online', 'idle' (ausente), 'dnd' (não perturbe/ocupado), 'invisible'."},
                "activity_type": {"type": "string", "description": "Tipo de atividade: 'playing' (jogando), 'streaming' (live), 'listening' (ouvindo), 'watching' (assistindo), 'competing' (competindo), 'custom' (customizado), 'none' (remover)."},
                "activity_name": {"type": "string", "description": "Nome da atividade, jogo, música, transmissão ou status customizado."},
                "url": {"type": "string", "description": "URL da transmissão (Twitch/YouTube) quando activity_type for 'streaming'."}
            }
        }
    },
    {
        "name": "discord_bot_list_guilds",
        "description": "Lista todos os servidores onde o bot está conectado com ID, nome, quantidade de membros, apelido do bot e ícone.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
]

if "TOOL_MAP" in globals():
    TOOL_MAP.update(FERRAMENTAS_DISCORD_BOT)

if "FUNCTION_DECLARATIONS" in globals():
    for dec in DECLARACOES_DISCORD_BOT:
        if not any(existing.get("name") == dec["name"] for existing in FUNCTION_DECLARATIONS):
            FUNCTION_DECLARATIONS.append(dec)

def register(tool_map, function_declarations):
    tool_map.update(FERRAMENTAS_DISCORD_BOT)
    for dec in DECLARACOES_DISCORD_BOT:
        if not any(existing.get("name") == dec["name"] for existing in function_declarations):
            function_declarations.append(dec)
