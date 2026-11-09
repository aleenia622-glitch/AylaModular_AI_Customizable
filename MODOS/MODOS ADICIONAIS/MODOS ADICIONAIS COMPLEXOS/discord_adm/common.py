"""
🛡️ Administração do Discord: ban, kick, timeout, cargos, canais, threads e apagar mensagens.
"""
from ayla_paths import resolve_path
import os
import sys
import re
import json
import asyncio
import typing
import requests
import io
from datetime import datetime as dt_class, timezone as dt_timezone, timedelta as dt_timedelta
from pathlib import Path
import discord

try:
    import ayla_state
except ImportError:
    ayla_state = None




def _get_bot():
    import Ayla
    return Ayla.bot


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
        return f"🚫 Permissão Negada pelo Discord! O bot não possui permissão suficiente para esta ação. Detalhes: {e}"
    except discord.NotFound as e:
        return f"🔍 Objeto não encontrado no Discord (canal, cargo, membro ou id inválido). Detalhes: {e}"
    except discord.HTTPException as e:
        return f"❌ Erro HTTP do Discord (Status {e.status}): {e.text}"
    except Exception as e:
        return f"⚠️ Erro ao executar comando administrativo: {e}"


def _get_guild(bot: discord.Client, guild_id_str: str = "") -> discord.Guild:
    # 1. Se um ID de guilda foi passado explicitamente na chamada
    if guild_id_str and str(guild_id_str).isdigit():
        g = bot.get_guild(int(guild_id_str))
        if g:
            return g

    # 2. Tenta detectar a guilda ativa através do contexto da mensagem/interação atual da Ayla
    if ayla_state and hasattr(ayla_state, "CONTEXTO_ATIVO"):
        ctx = ayla_state.CONTEXTO_ATIVO.get()
        if ctx and hasattr(ctx, "guild") and ctx.guild:
            return ctx.guild

    # 3. Fallback: Pega o primeiro servidor onde o bot está conectado
    if bot.guilds:
        return bot.guilds[0]
    return None


async def _resolve_member(guild: discord.Guild, identifier: str) -> discord.Member:
    if not identifier:
        return None
    identifier = str(identifier).strip()
    clean_id = identifier
    if identifier.startswith("<@") and identifier.endswith(">"):
        clean_id = identifier.replace("<@", "").replace("!", "").replace(">", "")

    # 1. Tenta por ID numérico via cache local
    if clean_id.isdigit():
        m = guild.get_member(int(clean_id))
        if m:
            return m
        # 2. Se não estiver no cache local, busca diretamente via API do Discord (fetch_member)
        try:
            return await guild.fetch_member(int(clean_id))
        except Exception:
            pass

    # 3. Tenta por nome ou apelido no cache local
    ident_lower = identifier.lower()
    for m in guild.members:
        if m.name.lower() == ident_lower or m.display_name.lower() == ident_lower:
            return m
    for m in guild.members:
        if ident_lower in m.name.lower() or ident_lower in m.display_name.lower():
            return m

    # 4. Tenta consultar a API de membros da guilda por nome/query
    try:
        members = await guild.query_members(query=identifier, limit=5)
        if members:
            return members[0]
    except Exception:
        pass

    return None


def _check_hierarchy(guild: discord.Guild, member: discord.Member) -> str | None:
    if not guild or not member or not isinstance(member, discord.Member):
        return None
    if member.id == guild.owner_id:
        return f"👑 Não é possível moderar o(a) Dono(a) do servidor ({member.display_name})."
    bot_member = guild.me
    if bot_member and bot_member.top_role.position <= member.top_role.position:
        return (
            f"🚫 **Erro de Hierarquia de Cargos do Discord!**\n"
            f"O cargo mais alto da Ayla (**{bot_member.top_role.name}** - posição `{bot_member.top_role.position}`) "
            f"está **IGUAL ou ABAIXO** do cargo mais alto de **{member.display_name}** (**{member.top_role.name}** - posição `{member.top_role.position}`).\n\n"
            f"💡 **Como resolver:** No Discord, vá em *Configurações do Servidor > Cargos* e **arraste o cargo da Ayla_IA para CIMA do cargo dessa pessoa** na lista!"
        )
    return None


def _resolve_channel(guild: discord.Guild, identifier: str) -> discord.abc.GuildChannel:
    if not identifier:
        return None
    identifier = str(identifier).strip()
    if identifier.isdigit():
        c = guild.get_channel(int(identifier))
        if c:
            return c
    if identifier.startswith("<#") and identifier.endswith(">"):
        clean_id = identifier.replace("<#", "").replace(">", "")
        if clean_id.isdigit():
            c = guild.get_channel(int(clean_id))
            if c:
                return c
    ident_lower = identifier.lower().replace("#", "")
    for c in guild.channels:
        if c.name.lower() == ident_lower:
            return c
    for c in guild.channels:
        if ident_lower in c.name.lower():
            return c
    return None


def _resolve_role(guild: discord.Guild, identifier: str) -> discord.Role:
    if not identifier:
        return None
    identifier = str(identifier).strip()
    if identifier.isdigit():
        r = guild.get_role(int(identifier))
        if r:
            return r
    if identifier.startswith("<@&") and identifier.endswith(">"):
        clean_id = identifier.replace("<@&", "").replace(">", "")
        if clean_id.isdigit():
            r = guild.get_role(int(clean_id))
            if r:
                return r
    ident_lower = identifier.lower().replace("@", "")
    for r in guild.roles:
        if r.name.lower() == ident_lower:
            return r
    for r in guild.roles:
        if ident_lower in r.name.lower():
            return r
    return None


def _sanitize_emoji_name(raw_name: str = "", fallback_name: str = "") -> str:
    """Sanitiza o nome do emoji para atender aos requisitos estritos do Discord (alphanumeric + underscore, 2-32 chars)."""
    name_to_use = raw_name.strip() if raw_name and raw_name.strip() else fallback_name.strip()
    if not name_to_use:
        name_to_use = "emoji_custom"

    # Substitui espaços e hífens por underline
    clean = re.sub(r'[\s\-]+', '_', name_to_use)
    # Remove qualquer caractere que não seja letras, números ou underline
    clean = re.sub(r'[^a-zA-Z0-9_]', '', clean)

    if len(clean) < 2:
        clean = f"emoji_{clean}" if clean else "emoji_custom"
    if len(clean) > 32:
        clean = clean[:32]
    return clean


def _emoji_to_name(emoji_char: str) -> str:
    """
    Converte um caractere de emoji Unicode para o nome de texto compatível com a API do Discord.
    A API do create_sticker rejeita o caractere emoji diretamente (gera HTTP 400);
    ela exige o nome do emoji (ex: '😀' -> 'grinning').
    """
    import unicodedata

    # Se já é um nome de texto sem emoji (ex: "grinning", "wave"), retorna direto
    # Heurística: se não contiver caracteres acima do ASCII básico, já é nome
    if emoji_char and all(ord(c) < 128 for c in emoji_char.strip()):
        clean = emoji_char.strip().lower().replace(' ', '_').replace('-', '_')
        return clean if clean else "grinning"

    if not emoji_char or not emoji_char.strip():
        return "grinning"

    try:
        # Pega o nome Unicode do primeiro caractere do emoji
        raw = unicodedata.name(emoji_char.strip()[0], "").lower()
        # Converte "smiling face with open mouth" -> "smiling_face_with_open_mouth"
        name = re.sub(r'[^a-z0-9]+', '_', raw).strip('_')
        return name if name else "grinning"
    except Exception:
        return "grinning"


def _optimize_emoji_image(img_bytes: bytes) -> bytes:
    """Garante que a imagem do emoji esteja dentro do limite de 256KB do Discord."""
    if not img_bytes or len(img_bytes) <= 256 * 1024:
        return img_bytes

    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(img_bytes))

        # Redimensiona para máximo 128x128 (tamanho ideal de emoji no Discord)
        img.thumbnail((128, 128))

        output = io.BytesIO()
        if getattr(img, "is_animated", False):
            img.save(output, format="GIF", save_all=True)
        else:
            img.save(output, format="PNG", optimize=True)

        res = output.getvalue()
        if len(res) < len(img_bytes):
            return res
    except Exception:
        pass
    return img_bytes


def _optimize_sticker_image(img_bytes: bytes, filename_hint: str = "sticker") -> tuple:
    """
    Garante que a imagem do sticker esteja dentro do limite de 512KB do Discord e ajustada para até 320x320.
    Retorna (bytes, extensao) onde extensao é 'gif' para animados ou 'png' para estáticos.
    IMPORTANTE: A extensão do arquivo DEVE bater com o conteúdo real da imagem,
    caso contrário a API do Discord retorna HTTP 400.
    """
    # Detecta extensão original
    ext = "png"
    if filename_hint:
        low = filename_hint.lower()
        if low.endswith(".gif") or low == "gif":
            ext = "gif"
        elif low.endswith(".apng") or low == "apng":
            ext = "apng"

    if not img_bytes:
        return img_bytes, ext

    # Detecta se é GIF pelos magic bytes
    if img_bytes[:6] in (b"GIF87a", b"GIF89a"):
        ext = "gif"

    if len(img_bytes) <= 512 * 1024:
        return img_bytes, ext

    try:
        from PIL import Image
        img = Image.open(io.BytesIO(img_bytes))

        # Redimensiona para máximo 320x320 (tamanho padrão de sticker no Discord)
        img.thumbnail((320, 320))

        output = io.BytesIO()
        is_anim = getattr(img, "is_animated", False)
        if is_anim:
            img.save(output, format="GIF", save_all=True)
            ext = "gif"
        else:
            img.save(output, format="PNG", optimize=True)
            ext = "png"

        res = output.getvalue()
        if len(res) < len(img_bytes):
            return res, ext
    except Exception:
        pass
    return img_bytes, ext


async def _resolve_image_bytes(image_url_or_path: str = "") -> tuple[bytes | None, str]:
    """
    Obtém os bytes da imagem e o nome sugerido a partir de:
    1. image_url_or_path (URL ou arquivo local)
    2. ayla_state.ULTIMO_ANEXO_IMAGEM
    3. ayla_state.CONTEXTO_ATIVO (anexo da mensagem do Discord)
    4. ayla_state.ULTIMA_IMAGEM_GERADA / ULTIMAS_IMAGENS_MODULO
    """
    img_bytes = None
    suggested_name = ""

    # 1. Tenta carregar de URL ou caminho local
    if image_url_or_path and str(image_url_or_path).strip():
        target = str(image_url_or_path).strip()
        if target.startswith("http://") or target.startswith("https://"):
            try:
                resp = requests.get(target, timeout=15)
                if resp.status_code == 200:
                    img_bytes = resp.content
                    suggested_name = Path(target.split("?")[0]).stem
            except Exception:
                pass
        else:
            p = resolve_path(target)
            if p.exists() and p.is_file():
                try:
                    img_bytes = p.read_bytes()
                    suggested_name = p.stem
                except Exception:
                    pass

    # 2. Tenta obter de ayla_state.ULTIMO_ANEXO_IMAGEM
    if not img_bytes and ayla_state:
        try:
            ultimo = ayla_state.ULTIMO_ANEXO_IMAGEM.get() if hasattr(ayla_state, "ULTIMO_ANEXO_IMAGEM") else None
            if ultimo:
                if isinstance(ultimo, tuple):
                    img_bytes = ultimo[0]
                elif isinstance(ultimo, bytes):
                    img_bytes = ultimo
                elif isinstance(ultimo, (str, Path)):
                    p = Path(ultimo)
                    if p.exists() and p.is_file():
                        img_bytes = p.read_bytes()
                        suggested_name = p.stem
        except Exception:
            pass

    # 3. Tenta obter de ayla_state.CONTEXTO_ATIVO (anexo do Discord)
    if not img_bytes and ayla_state:
        try:
            ctx = ayla_state.CONTEXTO_ATIVO.get() if hasattr(ayla_state, "CONTEXTO_ATIVO") else None
            if ctx:
                attachments = []
                if hasattr(ctx, "message") and ctx.message and ctx.message.attachments:
                    attachments = ctx.message.attachments
                elif hasattr(ctx, "attachments") and ctx.attachments:
                    attachments = ctx.attachments

                for att in attachments:
                    is_img = False
                    if hasattr(att, "content_type") and att.content_type and att.content_type.startswith("image/"):
                        is_img = True
                    elif hasattr(att, "filename") and att.filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                        is_img = True

                    if is_img:
                        try:
                            img_bytes = await att.read()
                            if hasattr(att, "filename") and att.filename:
                                suggested_name = Path(att.filename).stem
                            break
                        except Exception:
                            if hasattr(att, "url") and att.url:
                                resp = requests.get(att.url, timeout=15)
                                if resp.status_code == 200:
                                    img_bytes = resp.content
                                    if hasattr(att, "filename") and att.filename:
                                        suggested_name = Path(att.filename).stem
                                    break
        except Exception:
            pass

    # 4. Fallback: ULTIMA_IMAGEM_GERADA ou ULTIMAS_IMAGENS_MODULO
    if not img_bytes and ayla_state:
        try:
            gerada = ayla_state.ULTIMA_IMAGEM_GERADA.get() if hasattr(ayla_state, "ULTIMA_IMAGEM_GERADA") else None
            if gerada:
                if isinstance(gerada, bytes):
                    img_bytes = gerada
                elif isinstance(gerada, (str, Path)):
                    p = Path(gerada)
                    if p.exists() and p.is_file():
                        img_bytes = p.read_bytes()
                        suggested_name = p.stem
        except Exception:
            pass

    return img_bytes, suggested_name


__all__ = [name for name in globals() if not name.startswith("__")]
