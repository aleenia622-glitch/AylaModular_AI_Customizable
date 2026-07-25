import os
import sys
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

"""
🛡️ Módulo Unificado de Administração do Discord (Discord_ADM)
Oferece controle administrativo completo sobre servidores (guildas) no Discord:
- Informações do servidor, auditoria, configurações e templates.
- Moderação de membros (Ban, Unban, Kick, Timeout/Castigo, Nickname, Prune).
- Moderação de voz individual e em massa (Mute, Deafen, Mover, Desconectar).
- Gestão total de Cargos (Criar, Editar, Excluir, Atribuir/Remover) e Permissões.
- Gestão de Canais (Criar, Editar, Excluir, Purge de Mensagens, Permissões/Overwrites).
- Gestão de Tópicos/Threads (Criar, Trancar, Destrancar, Arquivar, Excluir).
- Emojis e Stickers personalizados (Criar e Excluir via URL/Path).
- Convites e Webhooks.
- Eventos Agendados do Servidor.
"""

def _get_bot():
    bot = globals().get("bot")
    if not bot:
        # Tenta buscar do sys.modules se injetado em Ayla
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


# ══════════════════════════════════════════════════════════
# 1. INFORMAÇÕES DA GUILDA & AUDIT LOGS & CONFIGURAÇÕES
# ══════════════════════════════════════════════════════════

def discord_adm_guild_info(guild_id: str = "") -> str:
    """Retorna detalhes completos e estatísticas do servidor atual no Discord."""
    async def _impl():
        bot = _get_bot()
        guild = _get_guild(bot, guild_id)
        if not guild:
            return "❌ Nenhuma guilda (servidor) encontrada."

        owner = guild.owner or await bot.fetch_user(guild.owner_id)
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        categories = len(guild.categories)
        threads = len(guild.threads)
        roles = len(guild.roles)
        emojis = len(guild.emojis)
        stickers = len(guild.stickers)

        info = (
            f"🏰 **Informações da Guilda: {guild.name}**\n"
            f"🆔 **ID:** `{guild.id}`\n"
            f"👑 **Dono(a):** {owner} (`{guild.owner_id}`)\n"
            f"📅 **Criado em:** {guild.created_at.strftime('%d/%m/%Y %H:%M:%S')} UTC\n"
            f"👥 **Membros:** {guild.member_count} (Bots: {sum(1 for m in guild.members if m.bot)})\n"
            f"🚀 **Nível de Boost:** {guild.premium_tier} ({guild.premium_subscription_count} impulsionadores)\n"
            f"🔒 **Nível de Verificação:** {guild.verification_level}\n"
            f"🔞 **Filtro de Conteúdo:** {guild.explicit_content_filter}\n"
            f"📊 **Canais:** {len(guild.channels)} Total ({text_channels} Texto, {voice_channels} Voz, {categories} Categorias, {threads} Threads)\n"
            f"🎭 **Cargos:** {roles} | 😀 **Emojis:** {emojis} | 🎨 **Stickers:** {stickers}\n"
        )
        if guild.description:
            info += f"📝 **Descrição:** {guild.description}\n"
        if guild.afk_channel:
            info += f"💤 **Canal AFK:** {guild.afk_channel.name} (Timeout: {guild.afk_timeout // 60} min)\n"
        if guild.system_channel:
            info += f"🔔 **Canal do Sistema:** {guild.system_channel.name}\n"
        if guild.features:
            info += f"✨ **Recursos:** {', '.join(guild.features[:8])}"
            if len(guild.features) > 8:
                info += f" (+{len(guild.features)-8})"
            info += "\n"

        return info

    return _run_async(_impl())


def discord_adm_get_audit_logs(guild_id: str = "", limit: int = 10, action_type: str = "", user_id: str = "") -> str:
    """Busca e resume entradas recentes do registro de auditoria (Audit Log) do servidor."""
    async def _impl():
        bot = _get_bot()
        guild = _get_guild(bot, guild_id)
        if not guild:
            return "❌ Nenhuma guilda encontrada."

        action_enum = None
        if action_type:
            action_name = action_type.lower().strip()
            for a in discord.AuditLogAction:
                if a.name.lower() == action_name or action_name in a.name.lower():
                    action_enum = a
                    break

        user_obj = None
        if user_id:
            user_obj = (await _resolve_member(guild, user_id)) or (await bot.fetch_user(int(user_id)) if user_id.isdigit() else None)

        entries = []
        async for entry in guild.audit_logs(limit=min(limit, 30), action=action_enum, user=user_obj):
            target_str = str(entry.target) if entry.target else "N/A"
            reason_str = f" | Motivo: {entry.reason}" if entry.reason else ""
            time_str = entry.created_at.strftime("%d/%m %H:%M")
            entries.append(f"• `[{time_str}]` **{entry.user}** fez `{entry.action.name}` em **{target_str}**{reason_str}")

        if not entries:
            return "📜 Nenhuma entrada encontrada no Audit Log para os filtros especificados."

        return f"📜 **Audit Log Recente ({len(entries)} registros):**\n" + "\n".join(entries)

    return _run_async(_impl())


def discord_adm_edit_guild(name: str = "", description: str = "", verification_level: str = "", explicit_content_filter: str = "", afk_timeout: int = 0, guild_id: str = "") -> str:
    """Modifica as configurações principais da guilda (nome, descrição, verificação, filtro e AFK)."""
    async def _impl():
        bot = _get_bot()
        guild = _get_guild(bot, guild_id)
        if not guild:
            return "❌ Nenhuma guilda encontrada."

        kwargs = {}
        if name.strip():
            kwargs["name"] = name.strip()
        if description:
            kwargs["description"] = description.strip()
        if afk_timeout in (60, 300, 900, 1800, 3600):
            kwargs["afk_timeout"] = afk_timeout

        if verification_level:
            vl = verification_level.lower()
            v_map = {
                "none": discord.VerificationLevel.none,
                "low": discord.VerificationLevel.low,
                "medium": discord.VerificationLevel.medium,
                "high": discord.VerificationLevel.high,
                "highest": discord.VerificationLevel.highest,
                "extreme": discord.VerificationLevel.highest,
            }
            if vl in v_map:
                kwargs["verification_level"] = v_map[vl]

        if explicit_content_filter:
            ec = explicit_content_filter.lower()
            ec_map = {
                "disabled": discord.ContentFilter.disabled,
                "no_role": discord.ContentFilter.no_role,
                "all_members": discord.ContentFilter.all_members,
            }
            if ec in ec_map:
                kwargs["explicit_content_filter"] = ec_map[ec]

        if not kwargs:
            return "⚠️ Nenhum parâmetro de alteração válido especificado."

        await guild.edit(**kwargs)
        alterados = ", ".join(kwargs.keys())
        return f"✅ Configurações da guilda **{guild.name}** atualizadas com sucesso! (Campos alterados: {alterados})"

    return _run_async(_impl())


# ══════════════════════════════════════════════════════════
# 2. MODERAÇÃO DE MEMBROS (BAN, UNBAN, KICK, TIMEOUT, PRUNE)
# ══════════════════════════════════════════════════════════

def discord_adm_ban_member(user_id: str, reason: str = "Banido via Ayla ADM", delete_message_days: int = 0, guild_id: str = "") -> str:
    """Bane um usuário do servidor pelo ID ou menção, com opção de apagar mensagens de N dias."""
    async def _impl():
        bot = _get_bot()
        guild = _get_guild(bot, guild_id)
        if not guild:
            return "❌ Nenhuma guilda encontrada."

        member = await _resolve_member(guild, user_id)
        user_to_ban = member
        if not user_to_ban and user_id.isdigit():
            user_to_ban = await bot.fetch_user(int(user_id))

        if not user_to_ban:
            return f"❌ Usuário `{user_id}` não encontrado no Discord."

        days = max(0, min(delete_message_days, 7))
        seconds = days * 86400

        await guild.ban(user_to_ban, reason=reason, delete_message_seconds=seconds)
        return f"🔨 **{user_to_ban}** (ID: `{user_to_ban.id}`) foi BANIDO com sucesso do servidor!\nMotivo: {reason}"

    return _run_async(_impl())


def discord_adm_unban_member(user_id: str, reason: str = "Desbanido via Ayla ADM", guild_id: str = "") -> str:
    """Remove o banimento de um usuário pelo ID."""
    async def _impl():
        bot = _get_bot()
        guild = _get_guild(bot, guild_id)
        if not guild:
            return "❌ Nenhuma guilda encontrada."

        if not user_id.isdigit():
            return "❌ O ID do usuário para desbanir deve ser numérico."

        user_obj = await bot.fetch_user(int(user_id))
        await guild.unban(user_obj, reason=reason)
        return f"🕊️ **{user_obj}** (ID: `{user_id}`) foi DESBANIDO com sucesso!"

    return _run_async(_impl())


def discord_adm_list_bans(guild_id: str = "") -> str:
    """Lista todos os banimentos ativos no servidor."""
    async def _impl():
        bot = _get_bot()
        guild = _get_guild(bot, guild_id)
        if not guild:
            return "❌ Nenhuma guilda encontrada."

        bans = []
        async for ban_entry in guild.bans(limit=50):
            reason_str = f" | Motivo: {ban_entry.reason}" if ban_entry.reason else ""
            bans.append(f"• **{ban_entry.user}** (`{ban_entry.user.id}`){reason_str}")

        if not bans:
            return "🕊️ Não há nenhum banimento ativo neste servidor."

        return f"🔨 **Lista de Banidos ({len(bans)}):**\n" + "\n".join(bans)

    return _run_async(_impl())


def discord_adm_kick_member(user_id: str, reason: str = "Expulso via Ayla ADM", guild_id: str = "") -> str:
    """Expulsa (Kick) um membro do servidor."""
    async def _impl():
        bot = _get_bot()
        guild = _get_guild(bot, guild_id)
        if not guild:
            return "❌ Nenhuma guilda encontrada."

        member = await _resolve_member(guild, user_id)
        if not member:
            return f"❌ Membro `{user_id}` não encontrado no servidor."

        err_h = _check_hierarchy(guild, member)
        if err_h:
            return err_h

        await member.kick(reason=reason)
        return f"🥾 **{member}** (ID: `{member.id}`) foi EXPULSO com sucesso!\nMotivo: {reason}"

    return _run_async(_impl())


def discord_adm_timeout_member(user_id: str, duration_minutes: int = 10, remove_timeout: bool = False, reason: str = "Timeout via Ayla ADM", guild_id: str = "") -> str:
    """Aplica ou remove castigo (Timeout / Mute temporário) de um membro no servidor."""
    async def _impl():
        bot = _get_bot()
        guild = _get_guild(bot, guild_id)
        if not guild:
            return "❌ Nenhuma guilda encontrada."

        member = await _resolve_member(guild, user_id)
        if not member:
            return f"❌ Membro `{user_id}` não encontrado no servidor."

        err_h = _check_hierarchy(guild, member)
        if err_h:
            return err_h

        if remove_timeout:
            await member.timeout(None, reason=reason)
            return f"🔊 Castigo de **{member}** foi REMOVIDO com sucesso!"

        duration = max(1, min(duration_minutes, 40320))  # Max 28 dias
        until = dt_class.now(dt_timezone.utc) + dt_timedelta(minutes=duration)
        await member.timeout(until, reason=reason)
        return f"🔇 **{member}** recebeu um castigo de **{duration} minutos**!\nMotivo: {reason}"

    return _run_async(_impl())


def discord_adm_edit_member(user_id: str, nickname: str = None, mute: bool = None, deafen: bool = None, voice_channel_id: str = None, disconnect_voice: bool = False, guild_id: str = "") -> str:
    """Altera apelido ou modera voz individualmente (mute, deafen, mover de canal ou desconectar)."""
    async def _impl():
        bot = _get_bot()
        guild = _get_guild(bot, guild_id)
        if not guild:
            return "❌ Nenhuma guilda encontrada."

        member = await _resolve_member(guild, user_id)
        if not member:
            return f"❌ Membro `{user_id}` não encontrado no servidor."

        kwargs = {}
        if nickname is not None:
            kwargs["nick"] = nickname if nickname.strip() else None

        if mute is not None:
            kwargs["mute"] = bool(mute)
        if deafen is not None:
            kwargs["deafen"] = bool(deafen)

        if disconnect_voice:
            kwargs["voice_channel"] = None
        elif voice_channel_id:
            vc = _resolve_channel(guild, voice_channel_id)
            if isinstance(vc, discord.VoiceChannel) or isinstance(vc, discord.StageChannel):
                kwargs["voice_channel"] = vc

        if not kwargs:
            return "⚠️ Nenhuma alteração de membro especificada."

        await member.edit(**kwargs)
        res = f"✅ Membro **{member}** modificado com sucesso!"
        if "nick" in kwargs:
            res += f" Novo Nick: `{kwargs['nick']}`"
        return res

    return _run_async(_impl())


def discord_adm_prune_members(days: int = 7, simulate_only: bool = True, guild_id: str = "") -> str:
    """Simula ou executa a limpeza/expurgo (Prune) de membros inativos sem cargos."""
    async def _impl():
        bot = _get_bot()
        guild = _get_guild(bot, guild_id)
        if not guild:
            return "❌ Nenhuma guilda encontrada."

        days = max(1, min(days, 30))
        if simulate_only:
            count = await guild.estimate_pruned_members(days=days)
            return f"📊 **Estimativa de Prune:** Excluiria **{count} membros** inativos há mais de {days} dias."
        else:
            pruned = await guild.prune_members(days=days, reason="Prune administrativo via Ayla")
            return f"🧹 **Prune Concluído!** **{pruned} membros** inativos foram removidos da guilda."

    return _run_async(_impl())


def discord_adm_list_members(role_id_or_name: str = "", name_filter: str = "", limit: int = 50, include_bots: bool = True, guild_id: str = "") -> str:
    """Consulta e lista os membros/integrantes do servidor com suporte a filtros por cargo e nome."""
    async def _impl():
        bot = _get_bot()
        guild = _get_guild(bot, guild_id)
        if not guild:
            return "❌ Nenhuma guilda encontrada."

        role = _resolve_role(guild, role_id_or_name) if role_id_or_name else None
        
        membros = []
        name_sub = name_filter.lower().strip()

        for m in guild.members:
            if not include_bots and m.bot:
                continue
            if role and role not in m.roles:
                continue
            if name_sub and name_sub not in m.name.lower() and name_sub not in m.display_name.lower():
                continue
            membros.append(m)

        if not membros:
            return "👥 Nenhum membro encontrado para os filtros especificados."

        limite_real = min(max(1, limit), 100)
        exibicao = membros[:limite_real]

        linhas = []
        for m in exibicao:
            bot_tag = " 🤖" if m.bot else ""
            roles_str = ", ".join([r.name for r in m.roles if r.name != "@everyone"][:3])
            roles_txt = f" | Cargos: [{roles_str}]" if roles_str else ""
            status_txt = f" ({m.status.name})" if hasattr(m, "status") and m.status else ""
            linhas.append(f"• **{m.display_name}** (@{m.name}){bot_tag} — ID: `{m.id}`{status_txt}{roles_txt}")

        resultado = f"👥 **Integrantes do Servidor ({len(membros)} encontrados, exibindo {len(exibicao)}):**\n" + "\n".join(linhas)
        if len(membros) > limite_real:
            resultado += f"\n\n*... e mais {len(membros) - limite_real} membros.*"
        return resultado

    return _run_async(_impl())


def discord_adm_read_channel_messages(channel_id_or_name: str, limit: int = 20, before_message_id: str = "", guild_id: str = "") -> str:
    """Lê em lote as mensagens recentes de um canal de texto ou thread do Discord."""
    async def _impl():
        bot = _get_bot()
        guild = _get_guild(bot, guild_id)
        if not guild:
            return "❌ Nenhuma guilda encontrada."

        channel = _resolve_channel(guild, channel_id_or_name)
        if not isinstance(channel, discord.TextChannel) and not isinstance(channel, discord.Thread):
            return f"❌ Canal de texto ou thread `{channel_id_or_name}` não encontrado."

        before_obj = None
        if before_message_id and before_message_id.isdigit():
            try:
                before_obj = await channel.fetch_message(int(before_message_id))
            except Exception:
                pass

        max_lim = min(max(1, limit), 100)
        mensagens = []
        async for msg in channel.history(limit=max_lim, before=before_obj):
            mensagens.append(msg)

        if not mensagens:
            return f"📜 Nenhuma mensagem encontrada no canal **#{channel.name}**."

        mensagens.reverse()  # Ordena da mais antiga para a mais recente

        linhas = []
        for m in mensagens:
            time_str = m.created_at.strftime("%d/%m %H:%M:%S")
            bot_tag = " [BOT]" if m.author.bot else ""
            anexos = f" 📎[{len(m.attachments)} anexos]" if m.attachments else ""
            reacoes = f" ❤️[{sum(r.count for r in m.reactions)} reações]" if m.reactions else ""
            conteudo = m.clean_content or "(Sem conteúdo de texto)"
            if len(conteudo) > 300:
                conteudo = conteudo[:300] + "..."
            linhas.append(f"• `[{time_str}]` **{m.author.display_name}**{bot_tag} (`{m.author.id}`): {conteudo}{anexos}{reacoes}")

        return f"📖 **Histórico de mensagens em #{channel.name} ({len(mensagens)} lidas):**\n" + "\n".join(linhas)

    return _run_async(_impl())


# ══════════════════════════════════════════════════════════
# 3. GESTÃO DE CARGOS (ROLES) E PERMISSÕES
# ══════════════════════════════════════════════════════════

def discord_adm_create_role(name: str, color_hex: str = "#99AAB5", permissions_int: int = None, hoist: bool = False, mentionable: bool = False, guild_id: str = "") -> str:
    """Cria um novo cargo com cor, destaque e permissões customizadas."""
    async def _impl():
        bot = _get_bot()
        guild = _get_guild(bot, guild_id)
        if not guild:
            return "❌ Nenhuma guilda encontrada."

        # Parse de cor
        color = discord.Color.default()
        if color_hex.startswith("#"):
            try:
                color = discord.Color(int(color_hex.lstrip("#"), 16))
            except ValueError:
                pass

        perms = discord.Permissions.none()
        if permissions_int is not None:
            perms = discord.Permissions(permissions_int)

        role = await guild.create_role(
            name=name,
            color=color,
            permissions=perms,
            hoist=hoist,
            mentionable=mentionable,
            reason="Cargo criado via Ayla ADM"
        )
        return f"🎨 Cargo **{role.name}** (ID: `{role.id}`) criado com sucesso!"

    return _run_async(_impl())


def discord_adm_edit_role(role_id_or_name: str, name: str = None, color_hex: str = None, hoist: bool = None, mentionable: bool = None, position: int = None, guild_id: str = "") -> str:
    """Edita propriedades de um cargo existente (nome, cor, hoist, mencionável, posição)."""
    async def _impl():
        bot = _get_bot()
        guild = _get_guild(bot, guild_id)
        if not guild:
            return "❌ Nenhuma guilda encontrada."

        role = _resolve_role(guild, role_id_or_name)
        if not role:
            return f"❌ Cargo `{role_id_or_name}` não encontrado."

        kwargs = {}
        if name and name.strip():
            kwargs["name"] = name.strip()
        if color_hex and color_hex.startswith("#"):
            try:
                kwargs["color"] = discord.Color(int(color_hex.lstrip("#"), 16))
            except ValueError:
                pass
        if hoist is not None:
            kwargs["hoist"] = bool(hoist)
        if mentionable is not None:
            kwargs["mentionable"] = bool(mentionable)
        if position is not None and position > 0:
            kwargs["position"] = position

        if not kwargs:
            return "⚠️ Nenhuma propriedade para editar especificada."

        await role.edit(**kwargs)
        return f"✏️ Cargo **{role.name}** atualizado com sucesso!"

    return _run_async(_impl())


def discord_adm_delete_role(role_id_or_name: str, guild_id: str = "") -> str:
    """Exclui um cargo do servidor."""
    async def _impl():
        bot = _get_bot()
        guild = _get_guild(bot, guild_id)
        if not guild:
            return "❌ Nenhuma guilda encontrada."

        role = _resolve_role(guild, role_id_or_name)
        if not role:
            return f"❌ Cargo `{role_id_or_name}` não encontrado."

        nome_salvo = role.name
        await role.delete(reason="Excluído via Ayla ADM")
        return f"🗑️ Cargo **{nome_salvo}** foi EXCLUÍDO do servidor."

    return _run_async(_impl())


def discord_adm_manage_member_roles(user_id: str, role_id_or_name: str, action: str = "add", guild_id: str = "") -> str:
    """Adiciona ou remove um cargo de um ou múltiplos membros (IDs ou nomes separados por vírgula)."""
    async def _impl():
        bot = _get_bot()
        guild = _get_guild(bot, guild_id)
        if not guild:
            return "❌ Nenhuma guilda encontrada."

        role = _resolve_role(guild, role_id_or_name)
        if not role:
            return f"❌ Cargo `{role_id_or_name}` não encontrado."

        raw_ids = [uid.strip() for uid in re.split(r"[\n,;]+", str(user_id or "")) if uid.strip()]
        if not raw_ids:
            return "❌ Nenhum ID ou nome de membro fornecido."

        act = action.lower().strip()
        sucessos = []
        erros = []

        for uid in raw_ids:
            member = await _resolve_member(guild, uid)
            if not member:
                erros.append(f"Membro `{uid}` não encontrado")
                continue

            try:
                if act in ("add", "adicionar", "+"):
                    await member.add_roles(role, reason="Atribuído via Ayla ADM em Lote")
                    sucessos.append(member.display_name)
                elif act in ("remove", "remover", "-"):
                    await member.remove_roles(role, reason="Removido via Ayla ADM em Lote")
                    sucessos.append(member.display_name)
                else:
                    return "⚠️ Ação inválida. Use 'add' ou 'remove'."
            except Exception as e_m:
                erros.append(f"{member.display_name}: {e_m}")

        acao_str = "ADICIONADO a" if act in ("add", "adicionar", "+") else "REMOVIDO de"
        res_partes = []
        if sucessos:
            nomes_str = ", ".join(sucessos)
            res_partes.append(f"✅ Cargo **{role.name}** {acao_str} **{len(sucessos)}** membro(s): [{nomes_str}]")
        if erros:
            erros_str = "; ".join(erros)
            res_partes.append(f"⚠️ Falhas ({len(erros)}): {erros_str}")

        return "\n".join(res_partes) if res_partes else "Nenhum membro afetado."

    return _run_async(_impl())


# ══════════════════════════════════════════════════════════
# 4. GESTÃO DE CANAIS E PURGE DE MENSAGENS
# ══════════════════════════════════════════════════════════

def discord_adm_create_channel(name: str, channel_type: str = "text", topic: str = "", category_id_or_name: str = "", slowmode_seconds: int = 0, nsfw: bool = False, guild_id: str = "") -> str:
    """Cria um novo canal (texto, voz, categoria, anúncio ou fórum) no servidor."""
    async def _impl():
        bot = _get_bot()
        guild = _get_guild(bot, guild_id)
        if not guild:
            return "❌ Nenhuma guilda encontrada."

        category = _resolve_channel(guild, category_id_or_name) if category_id_or_name else None
        if category and not isinstance(category, discord.CategoryChannel):
            category = None

        ctype = channel_type.lower().strip()
        if ctype in ("text", "texto"):
            c = await guild.create_text_channel(name=name, topic=topic, category=category, slowmode_delay=slowmode_seconds, nsfw=nsfw)
        elif ctype in ("voice", "voz"):
            c = await guild.create_voice_channel(name=name, category=category)
        elif ctype in ("category", "categoria"):
            c = await guild.create_category(name=name)
        elif ctype in ("news", "announcement", "anuncio"):
            c = await guild.create_text_channel(name=name, topic=topic, category=category, news=True)
        elif ctype in ("forum", "forum"):
            c = await guild.create_forum_channel(name=name, topic=topic, category=category)
        else:
            return f"❌ Tipo de canal `{channel_type}` inválido (use text, voice, category, news ou forum)."

        return f"📁 Canal **{c.name}** (ID: `{c.id}`) criado com sucesso!"

    return _run_async(_impl())


def discord_adm_edit_channel(channel_id_or_name: str, name: str = None, topic: str = None, slowmode_seconds: int = None, nsfw: bool = None, category_id_or_name: str = None, bitrate: int = None, user_limit: int = None, guild_id: str = "") -> str:
    """Edita configurações de um canal (nome, tópico, slowmode, nsfw, bitrate, limite)."""
    async def _impl():
        bot = _get_bot()
        guild = _get_guild(bot, guild_id)
        if not guild:
            return "❌ Nenhuma guilda encontrada."

        channel = _resolve_channel(guild, channel_id_or_name)
        if not channel:
            return f"❌ Canal `{channel_id_or_name}` não encontrado."

        kwargs = {}
        if name and name.strip():
            kwargs["name"] = name.strip()
        if topic is not None and hasattr(channel, "topic"):
            kwargs["topic"] = topic
        if slowmode_seconds is not None and hasattr(channel, "slowmode_delay"):
            kwargs["slowmode_delay"] = slowmode_seconds
        if nsfw is not None and hasattr(channel, "nsfw"):
            kwargs["nsfw"] = bool(nsfw)
        if bitrate is not None and hasattr(channel, "bitrate"):
            kwargs["bitrate"] = min(max(8000, bitrate), guild.bitrate_limit)
        if user_limit is not None and hasattr(channel, "user_limit"):
            kwargs["user_limit"] = max(0, min(user_limit, 99))

        if category_id_or_name is not None:
            cat = _resolve_channel(guild, category_id_or_name)
            if isinstance(cat, discord.CategoryChannel):
                kwargs["category"] = cat

        if not kwargs:
            return "⚠️ Nenhuma configuração para alterar foi fornecida."

        await channel.edit(**kwargs)
        return f"✏️ Canal **{channel.name}** atualizado com sucesso!"

    return _run_async(_impl())


def discord_adm_delete_channel(channel_id_or_name: str, guild_id: str = "") -> str:
    """Exclui um canal do servidor."""
    async def _impl():
        bot = _get_bot()
        guild = _get_guild(bot, guild_id)
        if not guild:
            return "❌ Nenhuma guilda encontrada."

        channel = _resolve_channel(guild, channel_id_or_name)
        if not channel:
            return f"❌ Canal `{channel_id_or_name}` não encontrado."

        nome_salvo = channel.name
        await channel.delete(reason="Excluído via Ayla ADM")
        return f"🗑️ Canal **#{nome_salvo}** foi EXCLUÍDO do servidor."

    return _run_async(_impl())


def discord_adm_purge_messages(channel_id_or_name: str, limit: int = 50, user_id_filter: str = "", guild_id: str = "") -> str:
    """Apaga em massa N mensagens de um canal (com suporte a filtro por usuário)."""
    async def _impl():
        bot = _get_bot()
        guild = _get_guild(bot, guild_id)
        if not guild:
            return "❌ Nenhuma guilda encontrada."

        channel = _resolve_channel(guild, channel_id_or_name)
        if not isinstance(channel, discord.TextChannel) and not isinstance(channel, discord.Thread):
            return f"❌ Canal de texto `{channel_id_or_name}` inválido."

        filter_user = (await _resolve_member(guild, user_id_filter)) if user_id_filter else None

        def check_fn(m):
            if filter_user:
                return m.author.id == filter_user.id
            return True

        deleted = await channel.purge(limit=min(limit, 1000), check=check_fn)
        user_str = f" do usuário **{filter_user}**" if filter_user else ""
        return f"🧹 Limpeza realizada! **{len(deleted)} mensagens** foram apagadas em **#{channel.name}**{user_str}."

    return _run_async(_impl())


def discord_adm_set_channel_permissions(channel_id_or_name: str, target_id_or_name: str, target_type: str = "role", allow_permissions: str = "", deny_permissions: str = "", reset_permissions: bool = False, guild_id: str = "") -> str:
    """Configura sobrescritas de permissão (Permission Overwrites) em um canal para um cargo ou membro."""
    async def _impl():
        bot = _get_bot()
        guild = _get_guild(bot, guild_id)
        if not guild:
            return "❌ Nenhuma guilda encontrada."

        channel = _resolve_channel(guild, channel_id_or_name)
        if not channel:
            return f"❌ Canal `{channel_id_or_name}` não encontrado."

        target = None
        if target_type.lower() == "role":
            target = _resolve_role(guild, target_id_or_name)
        else:
            target = await _resolve_member(guild, target_id_or_name)

        if not target:
            return f"❌ Alvo `{target_id_or_name}` ({target_type}) não encontrado."

        if reset_permissions:
            await channel.set_permissions(target, overwrite=None, reason="Reset de permissões via Ayla ADM")
            return f"🔄 Permissões de **{target.name}** em **#{channel.name}** foram resetadas para o padrão."

        # Parse de permissões permitidas/negadas por texto (ex: "send_messages,view_channel")
        allow_kwargs = {p.strip(): True for p in allow_permissions.split(",") if p.strip()}
        deny_kwargs = {p.strip(): False for p in deny_permissions.split(",") if p.strip()}

        overwrite = channel.overwrites_for(target)
        for perm, val in allow_kwargs.items():
            if hasattr(overwrite, perm):
                setattr(overwrite, perm, True)
        for perm, val in deny_kwargs.items():
            if hasattr(overwrite, perm):
                setattr(overwrite, perm, False)

        await channel.set_permissions(target, overwrite=overwrite, reason="Permissões alteradas via Ayla ADM")
        return f"🔐 Sobrescrita de permissões de **{target.name}** em **#{channel.name}** configurada com sucesso!"

    return _run_async(_impl())


# ══════════════════════════════════════════════════════════
# 5. GESTÃO DE TÓPICOS (THREADS)
# ══════════════════════════════════════════════════════════

def discord_adm_manage_thread(channel_id_or_name: str, action: str = "create", name: str = "Thread", thread_id: str = "", archive: bool = None, lock: bool = None, guild_id: str = "") -> str:
    """Cria, tranca, destranca, arquiva ou exclui threads em canais de texto."""
    async def _impl():
        bot = _get_bot()
        guild = _get_guild(bot, guild_id)
        if not guild:
            return "❌ Nenhuma guilda encontrada."

        act = action.lower().strip()
        if act == "create":
            channel = _resolve_channel(guild, channel_id_or_name)
            if not isinstance(channel, discord.TextChannel):
                return f"❌ Canal de texto `{channel_id_or_name}` inválido."
            thread = await channel.create_thread(name=name, auto_archive_duration=1440)
            return f"🧵 Thread **{thread.name}** (ID: `{thread.id}`) criada com sucesso!"

        thread_obj = None
        if thread_id and thread_id.isdigit():
            thread_obj = guild.get_thread(int(thread_id))

        if not thread_obj and channel_id_or_name:
            t_cand = _resolve_channel(guild, channel_id_or_name)
            if isinstance(t_cand, discord.Thread):
                thread_obj = t_cand

        if not thread_obj:
            return f"❌ Thread `{thread_id or channel_id_or_name}` não encontrada."

        if act == "delete":
            nome = thread_obj.name
            await thread_obj.delete()
            return f"🗑️ Thread **{nome}** excluída com sucesso!"
        elif act in ("edit", "update"):
            kwargs = {}
            if archive is not None:
                kwargs["archived"] = bool(archive)
            if lock is not None:
                kwargs["locked"] = bool(lock)
            if name:
                kwargs["name"] = name
            await thread_obj.edit(**kwargs)
            return f"✏️ Thread **{thread_obj.name}** atualizada com sucesso!"

        return "⚠️ Ação inválida. Use 'create', 'edit' ou 'delete'."

    return _run_async(_impl())


# ══════════════════════════════════════════════════════════
# 6. EMOJIS E STICKERS PERSONALIZADOS
# ══════════════════════════════════════════════════════════

def discord_adm_manage_emojis_stickers(action: str = "create_emoji", name: str = "", image_url_or_path: str = "", target_id_or_name: str = "", guild_id: str = "") -> str:
    """Cria ou deleta emojis e stickers customizados na guilda a partir de URL ou arquivo local."""
    async def _impl():
        bot = _get_bot()
        guild = _get_guild(bot, guild_id)
        if not guild:
            return "❌ Nenhuma guilda encontrada."

        act = action.lower().strip()

        if act == "create_emoji":
            if not name or not image_url_or_path:
                return "❌ Nome e URL/Caminho da imagem são obrigatórios para criar emoji."

            img_bytes = None
            if image_url_or_path.startswith("http://") or image_url_or_path.startswith("https://"):
                resp = requests.get(image_url_or_path, timeout=15)
                if resp.status_code == 200:
                    img_bytes = resp.content
            else:
                p = Path(image_url_or_path)
                if p.exists():
                    img_bytes = p.read_bytes()

            if not img_bytes:
                return "❌ Não foi possível carregar os bytes da imagem fornecida."

            emoji = await guild.create_custom_emoji(name=name, image=img_bytes, reason="Criado via Ayla ADM")
            return f"😀 Emoji criado com sucesso: <:{emoji.name}:{emoji.id}> (ID: `{emoji.id}`)"

        elif act == "delete_emoji":
            target_emoji = None
            for e in guild.emojis:
                if str(e.id) == target_id_or_name or e.name == target_id_or_name:
                    target_emoji = e
                    break
            if not target_emoji:
                return f"❌ Emoji `{target_id_or_name}` não encontrado na guilda."

            nome = target_emoji.name
            await target_emoji.delete(reason="Deletado via Ayla ADM")
            return f"🗑️ Emoji **:{nome}:** deletado com sucesso!"

        elif act == "delete_sticker":
            target_sticker = None
            for s in guild.stickers:
                if str(s.id) == target_id_or_name or s.name == target_id_or_name:
                    target_sticker = s
                    break
            if not target_sticker:
                return f"❌ Sticker `{target_id_or_name}` não encontrado."

            nome = target_sticker.name
            await target_sticker.delete(reason="Deletado via Ayla ADM")
            return f"🎨 Sticker **{nome}** deletado com sucesso!"

        return "⚠️ Ação inválida. Use 'create_emoji', 'delete_emoji' ou 'delete_sticker'."

    return _run_async(_impl())


# ══════════════════════════════════════════════════════════
# 7. CONVITES E WEBHOOKS
# ══════════════════════════════════════════════════════════

def discord_adm_manage_invites(action: str = "list", channel_id_or_name: str = "", invite_code: str = "", max_age_seconds: int = 86400, max_uses: int = 0, unique: bool = True, guild_id: str = "") -> str:
    """Lista, cria ou revoga convites (Invites) do servidor."""
    async def _impl():
        bot = _get_bot()
        guild = _get_guild(bot, guild_id)
        if not guild:
            return "❌ Nenhuma guilda encontrada."

        act = action.lower().strip()

        if act == "list":
            invites = await guild.invites()
            if not invites:
                return "🔗 Nenhum convite ativo encontrado na guilda."
            lines = [f"• Code: `{inv.code}` | Canal: #{inv.channel.name} | Usos: {inv.uses}/{inv.max_uses or '∞'} | Criador: {inv.inviter}" for inv in invites[:20]]
            return f"🔗 **Convites Ativos ({len(invites)}):**\n" + "\n".join(lines)

        elif act == "create":
            channel = _resolve_channel(guild, channel_id_or_name)
            if not isinstance(channel, discord.TextChannel) and not isinstance(channel, discord.VoiceChannel):
                return f"❌ Canal `{channel_id_or_name}` inválido para criar convite."

            invite = await channel.create_invite(max_age=max_age_seconds, max_uses=max_uses, unique=unique, reason="Criado via Ayla ADM")
            return f"🔗 **Convite criado com sucesso!**\nURL: {invite.url}\nCódigo: `{invite.code}`"

        elif act == "delete":
            invites = await guild.invites()
            for inv in invites:
                if inv.code == invite_code or invite_code in inv.url:
                    await inv.delete(reason="Deletado via Ayla ADM")
                    return f"🗑️ Convite `{inv.code}` deletado com sucesso!"
            return f"❌ Convite com código `{invite_code}` não encontrado."

        return "⚠️ Ação inválida. Use 'list', 'create' ou 'delete'."

    return _run_async(_impl())


def discord_adm_manage_webhooks(action: str = "list", channel_id_or_name: str = "", webhook_id_or_name: str = "", name: str = "Ayla Webhook", guild_id: str = "") -> str:
    """Lista, cria ou deleta webhooks em canais do servidor."""
    async def _impl():
        bot = _get_bot()
        guild = _get_guild(bot, guild_id)
        if not guild:
            return "❌ Nenhuma guilda encontrada."

        act = action.lower().strip()

        if act == "list":
            webhooks = await guild.webhooks()
            if not webhooks:
                return "🪝 Nenhum webhook encontrado na guilda."
            lines = [f"• **{wh.name}** (ID: `{wh.id}`) em #{wh.channel.name}" for wh in webhooks]
            return f"🪝 **Webhooks da Guilda ({len(webhooks)}):**\n" + "\n".join(lines)

        elif act == "create":
            channel = _resolve_channel(guild, channel_id_or_name)
            if not isinstance(channel, discord.TextChannel):
                return f"❌ Canal de texto `{channel_id_or_name}` inválido."
            wh = await channel.create_webhook(name=name, reason="Criado via Ayla ADM")
            return f"🪝 Webhook **{wh.name}** criado com sucesso!\nURL: `{wh.url}`"

        elif act == "delete":
            webhooks = await guild.webhooks()
            for wh in webhooks:
                if str(wh.id) == webhook_id_or_name or wh.name == webhook_id_or_name:
                    await wh.delete(reason="Deletado via Ayla ADM")
                    return f"🗑️ Webhook **{wh.name}** deletado com sucesso!"
            return f"❌ Webhook `{webhook_id_or_name}` não encontrado."

        return "⚠️ Ação inválida. Use 'list', 'create' ou 'delete'."

    return _run_async(_impl())


# ══════════════════════════════════════════════════════════
# 8. EVENTOS AGENDADOS E MODERAÇÃO DE VOZ EM MASSA
# ══════════════════════════════════════════════════════════

def discord_adm_manage_scheduled_events(action: str = "list", name: str = "", description: str = "", start_time_iso: str = "", end_time_iso: str = "", channel_id_or_name: str = "", location: str = "", event_id: str = "", guild_id: str = "") -> str:
    """Lista, cria ou cancela eventos agendados no servidor."""
    async def _impl():
        bot = _get_bot()
        guild = _get_guild(bot, guild_id)
        if not guild:
            return "❌ Nenhuma guilda encontrada."

        act = action.lower().strip()

        if act == "list":
            events = guild.scheduled_events
            if not events:
                return "📅 Nenhum evento agendado ativo no servidor."
            lines = [f"• **{ev.name}** (ID: `{ev.id}`) | Início: {ev.start_time.strftime('%d/%m %H:%M')} | Status: {ev.status.name}" for ev in events]
            return f"📅 **Eventos Agendados ({len(events)}):**\n" + "\n".join(lines)

        elif act == "cancel" or act == "delete":
            event = None
            if event_id.isdigit():
                event = guild.get_scheduled_event(int(event_id))
            if not event:
                for ev in guild.scheduled_events:
                    if ev.name == name or str(ev.id) == event_id:
                        event = ev
                        break
            if not event:
                return f"❌ Evento agendado `{event_id or name}` não encontrado."

            await event.cancel()
            return f"🗑️ Evento agendado **{event.name}** foi cancelado com sucesso."

        return "⚠️ Ação inválida. Use 'list' ou 'cancel'."

    return _run_async(_impl())


def discord_adm_manage_voice(action: str = "mute_all", channel_id_or_name: str = "", target_channel_id_or_name: str = "", guild_id: str = "") -> str:
    """Realiza ações de moderação de voz em massa em um canal (mute_all, unmute_all, move_all, disconnect_all)."""
    async def _impl():
        bot = _get_bot()
        guild = _get_guild(bot, guild_id)
        if not guild:
            return "❌ Nenhuma guilda encontrada."

        channel = _resolve_channel(guild, channel_id_or_name)
        if not isinstance(channel, discord.VoiceChannel) and not isinstance(channel, discord.StageChannel):
            return f"❌ Canal de voz `{channel_id_or_name}` inválido."

        members = channel.members
        if not members:
            return f"🔊 Não há membros no canal de voz **{channel.name}**."

        act = action.lower().strip()
        count = 0

        if act == "mute_all":
            for m in members:
                await m.edit(mute=True)
                count += 1
            return f"🔇 **{count} membros** no canal **{channel.name}** foram SILENCIADOS no servidor."

        elif act == "unmute_all":
            for m in members:
                await m.edit(mute=False)
                count += 1
            return f"🔊 **{count} membros** no canal **{channel.name}** tiveram o silêncio REMOVIDO."

        elif act == "deafen_all":
            for m in members:
                await m.edit(deafen=True)
                count += 1
            return f"🙉 **{count} membros** no canal **{channel.name}** foram ENSURDECIDOS no servidor."

        elif act == "move_all":
            target_vc = _resolve_channel(guild, target_channel_id_or_name)
            if not isinstance(target_vc, discord.VoiceChannel) and not isinstance(target_vc, discord.StageChannel):
                return f"❌ Canal de voz de destino `{target_channel_id_or_name}` inválido."
            for m in members:
                await m.move_to(target_vc)
                count += 1
            return f"🚚 **{count} membros** foram MOVIDOS de **{channel.name}** para **{target_vc.name}**."

        elif act == "disconnect_all":
            for m in members:
                await m.move_to(None)
                count += 1
            return f"🔌 **{count} membros** foram DESCONECTADOS do canal **{channel.name}**."

        return "⚠️ Ação inválida. Use 'mute_all', 'unmute_all', 'deafen_all', 'move_all' ou 'disconnect_all'."

    return _run_async(_impl())


def discord_adm_manage_templates_integrations(action: str = "list_integrations", name: str = "Template Servidor", description: str = "", guild_id: str = "") -> str:
    """Gerencia templates de servidor e lista integrações ativas."""
    async def _impl():
        bot = _get_bot()
        guild = _get_guild(bot, guild_id)
        if not guild:
            return "❌ Nenhuma guilda encontrada."

        act = action.lower().strip()

        if act == "list_integrations":
            integrations = await guild.integrations()
            if not integrations:
                return "🔌 Nenhuma integração ativa encontrada na guilda."
            lines = [f"• **{integ.name}** (Tipo: `{integ.type}`, ID: `{integ.id}`)" for integ in integrations]
            return f"🔌 **Integrações da Guilda ({len(integrations)}):**\n" + "\n".join(lines)

        elif act == "create_template":
            tmpl = await guild.create_template(name=name, description=description)
            return f"📋 **Template de servidor criado com sucesso!**\nCódigo: `{tmpl.code}`\nURL: {tmpl.url}"

        return "⚠️ Ação inválida. Use 'list_integrations' ou 'create_template'."

    return _run_async(_impl())


# ══════════════════════════════════════════════════════════
# REGISTRO NO TOOL_MAP E FUNCTION_DECLARATIONS DA AYLA
# ══════════════════════════════════════════════════════════

FERRAMENTAS_DISCORD_ADM = {
    "discord_adm_guild_info": discord_adm_guild_info,
    "discord_adm_get_audit_logs": discord_adm_get_audit_logs,
    "discord_adm_edit_guild": discord_adm_edit_guild,
    "discord_adm_ban_member": discord_adm_ban_member,
    "discord_adm_unban_member": discord_adm_unban_member,
    "discord_adm_list_bans": discord_adm_list_bans,
    "discord_adm_kick_member": discord_adm_kick_member,
    "discord_adm_timeout_member": discord_adm_timeout_member,
    "discord_adm_edit_member": discord_adm_edit_member,
    "discord_adm_prune_members": discord_adm_prune_members,
    "discord_adm_create_role": discord_adm_create_role,
    "discord_adm_edit_role": discord_adm_edit_role,
    "discord_adm_delete_role": discord_adm_delete_role,
    "discord_adm_manage_member_roles": discord_adm_manage_member_roles,
    "discord_adm_create_channel": discord_adm_create_channel,
    "discord_adm_edit_channel": discord_adm_edit_channel,
    "discord_adm_delete_channel": discord_adm_delete_channel,
    "discord_adm_purge_messages": discord_adm_purge_messages,
    "discord_adm_set_channel_permissions": discord_adm_set_channel_permissions,
    "discord_adm_manage_thread": discord_adm_manage_thread,
    "discord_adm_list_members": discord_adm_list_members,
    "discord_adm_read_channel_messages": discord_adm_read_channel_messages,
    "discord_adm_manage_emojis_stickers": discord_adm_manage_emojis_stickers,
    "discord_adm_manage_invites": discord_adm_manage_invites,
    "discord_adm_manage_webhooks": discord_adm_manage_webhooks,
    "discord_adm_manage_scheduled_events": discord_adm_manage_scheduled_events,
    "discord_adm_manage_voice": discord_adm_manage_voice,
    "discord_adm_manage_templates_integrations": discord_adm_manage_templates_integrations,
}

DECLARACOES_DISCORD_ADM = [
    {
        "name": "discord_adm_guild_info",
        "description": "Retorna informações detalhadas do servidor atual (dono, contagem de membros, cargos, canais, nível de impulso, verificação, etc.).",
        "parameters": {
            "type": "object",
            "properties": {
                "guild_id": {"type": "string", "description": "ID opcional da guilda."}
            }
        }
    },
    {
        "name": "discord_adm_get_audit_logs",
        "description": "Busca registros recentes do registro de auditoria (Audit Log) do servidor com filtros opcionais.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Quantidade de registros (max 30)."},
                "action_type": {"type": "string", "description": "Tipo de ação (ex: ban, kick, channel_create, role_update)."},
                "user_id": {"type": "string", "description": "ID ou nome do usuário autor da ação."}
            }
        }
    },
    {
        "name": "discord_adm_edit_guild",
        "description": "Altera configurações principais do servidor (nome, descrição, nível de verificação, filtro explícito, timeout AFK).",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Novo nome da guilda."},
                "description": {"type": "string", "description": "Nova descrição da guilda."},
                "verification_level": {"type": "string", "description": "Nível de verificação (none, low, medium, high, extreme)."},
                "explicit_content_filter": {"type": "string", "description": "Filtro explícito (disabled, no_role, all_members)."},
                "afk_timeout": {"type": "integer", "description": "Timeout AFK em segundos (60, 300, 900, 1800, 3600)."}
            }
        }
    },
    {
        "name": "discord_adm_ban_member",
        "description": "Bane um usuário do servidor pelo ID ou menção, com motivo e opção de expurgar mensagens de até 7 dias.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "ID ou menção do usuário a banir."},
                "reason": {"type": "string", "description": "Motivo do banimento."},
                "delete_message_days": {"type": "integer", "description": "Dias de mensagens a apagar (0 a 7)."}
            },
            "required": ["user_id"]
        }
    },
    {
        "name": "discord_adm_unban_member",
        "description": "Desbane um usuário previamente banido do servidor pelo ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "ID numérico do usuário a desbanir."},
                "reason": {"type": "string", "description": "Motivo do desbanimento."}
            },
            "required": ["user_id"]
        }
    },
    {
        "name": "discord_adm_list_bans",
        "description": "Lista todos os banimentos ativos no servidor.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "discord_adm_kick_member",
        "description": "Expulsa (Kick) um membro do servidor.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "ID, menção ou nome do membro a expulsar."},
                "reason": {"type": "string", "description": "Motivo da expulsão."}
            },
            "required": ["user_id"]
        }
    },
    {
        "name": "discord_adm_timeout_member",
        "description": "Aplica ou remove castigo (Timeout / Mute temporário) de um membro no servidor.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "ID, menção ou nome do membro."},
                "duration_minutes": {"type": "integer", "description": "Duração do castigo em minutos."},
                "remove_timeout": {"type": "boolean", "description": "Se true, remove o castigo ativo."},
                "reason": {"type": "string", "description": "Motivo do castigo."}
            },
            "required": ["user_id"]
        }
    },
    {
        "name": "discord_adm_edit_member",
        "description": "Altera apelido ou estado de voz individual (mute, deafen, mover de canal ou desconectar) de um membro.",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "ID ou nome do membro."},
                "nickname": {"type": "string", "description": "Novo apelido."},
                "mute": {"type": "boolean", "description": "Silenciar no servidor (voice)."},
                "deafen": {"type": "boolean", "description": "Ensurdecer no servidor (voice)."},
                "voice_channel_id": {"type": "string", "description": "ID/Nome do canal de voz para mover."},
                "disconnect_voice": {"type": "boolean", "description": "Se true, desconecta da call de voz."}
            },
            "required": ["user_id"]
        }
    },
    {
        "name": "discord_adm_prune_members",
        "description": "Simula ou executa o expulso em massa (Prune) de membros inativos sem cargo no servidor.",
        "parameters": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Dias de inatividade (1 a 30)."},
                "simulate_only": {"type": "boolean", "description": "Se true, apenas estima sem expulsar."}
            }
        }
    },
    {
        "name": "discord_adm_list_members",
        "description": "Consulta e lista os integrantes/membros do servidor com suporte a filtros por cargo e busca de nome.",
        "parameters": {
            "type": "object",
            "properties": {
                "role_id_or_name": {"type": "string", "description": "ID ou nome de cargo para filtrar membros."},
                "name_filter": {"type": "string", "description": "Busca textual por parte do nome ou apelido."},
                "limit": {"type": "integer", "description": "Quantidade máxima de membros a exibir (max 100)."},
                "include_bots": {"type": "boolean", "description": "Se true, inclui contas de bots na lista."}
            }
        }
    },
    {
        "name": "discord_adm_read_channel_messages",
        "description": "Lê em lote a quantidade exata de mensagens recente que você especificar de um canal de texto ou thread do Discord (ex: 5, 10, 20, 50 até 100 mensagens).",
        "parameters": {
            "type": "object",
            "properties": {
                "channel_id_or_name": {"type": "string", "description": "ID ou nome do canal de texto ou thread."},
                "limit": {"type": "integer", "description": "A quantidade exata de mensagens que você quer ler no lote (ex: 5, 10, 20, 50, até 100)."},
                "before_message_id": {"type": "string", "description": "ID opcional de mensagem para ler o histórico anterior a ela."}
            },
            "required": ["channel_id_or_name", "limit"]
        }
    },
    {
        "name": "discord_adm_create_role",
        "description": "Cria um novo cargo no servidor com nome, cor HEX, permissões e propriedades de destaque.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nome do cargo."},
                "color_hex": {"type": "string", "description": "Código de cor HEX (ex: #FF0000)."},
                "hoist": {"type": "boolean", "description": "Exibir separadamente na lista de membros."},
                "mentionable": {"type": "boolean", "description": "Se pode ser mencionado por todos."}
            },
            "required": ["name"]
        }
    },
    {
        "name": "discord_adm_edit_role",
        "description": "Edita propriedades e permissões de um cargo existente.",
        "parameters": {
            "type": "object",
            "properties": {
                "role_id_or_name": {"type": "string", "description": "ID ou nome do cargo."},
                "name": {"type": "string", "description": "Novo nome."},
                "color_hex": {"type": "string", "description": "Nova cor HEX."},
                "hoist": {"type": "boolean", "description": "Alterar hoist."},
                "mentionable": {"type": "boolean", "description": "Alterar mencionável."}
            },
            "required": ["role_id_or_name"]
        }
    },
    {
        "name": "discord_adm_delete_role",
        "description": "Exclui um cargo do servidor.",
        "parameters": {
            "type": "object",
            "properties": {
                "role_id_or_name": {"type": "string", "description": "ID ou nome do cargo a deletar."}
            },
            "required": ["role_id_or_name"]
        }
    },
    {
        "name": "discord_adm_manage_member_roles",
        "description": "Adiciona ou remove um cargo de um ou MÚLTIPLOS membros de uma só vez (em lote). Suporta um ID/nome único ou múltiplos IDs/nomes separados por vírgula (ex: '12345, 67890, 11223'). Use esta função com múltiplos IDs quando precisar alterar cargos de vários membros/bots de uma só vez!",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "ID(s) ou nome(s) do(s) membro(s). Pode enviar múltiplos IDs separados por vírgula para processamento em lote!"},
                "role_id_or_name": {"type": "string", "description": "ID ou nome do cargo."},
                "action": {"type": "string", "description": "'add' para adicionar ou 'remove' para remover."}
            },
            "required": ["user_id", "role_id_or_name"]
        }
    },
    {
        "name": "discord_adm_create_channel",
        "description": "Cria um novo canal (texto, voz, categoria, anúncio ou fórum) no servidor.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nome do canal."},
                "channel_type": {"type": "string", "description": "text, voice, category, news ou forum."},
                "topic": {"type": "string", "description": "Tópico do canal."},
                "category_id_or_name": {"type": "string", "description": "ID ou nome da categoria pai."},
                "slowmode_seconds": {"type": "integer", "description": "Modo lento em segundos."},
                "nsfw": {"type": "boolean", "description": "Canal NSFW."}
            },
            "required": ["name"]
        }
    },
    {
        "name": "discord_adm_edit_channel",
        "description": "Modifica configurações de um canal (nome, tópico, slowmode, nsfw, bitrate, limite de usuários).",
        "parameters": {
            "type": "object",
            "properties": {
                "channel_id_or_name": {"type": "string", "description": "ID ou nome do canal."},
                "name": {"type": "string", "description": "Novo nome."},
                "topic": {"type": "string", "description": "Novo tópico."},
                "slowmode_seconds": {"type": "integer", "description": "Modo lento em segundos."},
                "nsfw": {"type": "boolean", "description": "Flag NSFW."}
            },
            "required": ["channel_id_or_name"]
        }
    },
    {
        "name": "discord_adm_delete_channel",
        "description": "Exclui um canal do servidor.",
        "parameters": {
            "type": "object",
            "properties": {
                "channel_id_or_name": {"type": "string", "description": "ID ou nome do canal a excluir."}
            },
            "required": ["channel_id_or_name"]
        }
    },
    {
        "name": "discord_adm_purge_messages",
        "description": "Apaga em massa N mensagens de um canal de texto (com filtro opcional por usuário).",
        "parameters": {
            "type": "object",
            "properties": {
                "channel_id_or_name": {"type": "string", "description": "ID ou nome do canal."},
                "limit": {"type": "integer", "description": "Quantidade de mensagens a apagar (max 1000)."},
                "user_id_filter": {"type": "string", "description": "ID ou nome de usuário opcional para apagar apenas mensagens dele."}
            },
            "required": ["channel_id_or_name"]
        }
    },
    {
        "name": "discord_adm_set_channel_permissions",
        "description": "Configura sobrescritas de permissão (Permission Overwrites) em um canal para um cargo ou membro.",
        "parameters": {
            "type": "object",
            "properties": {
                "channel_id_or_name": {"type": "string", "description": "ID ou nome do canal."},
                "target_id_or_name": {"type": "string", "description": "ID ou nome do cargo ou membro."},
                "target_type": {"type": "string", "description": "'role' ou 'member'."},
                "allow_permissions": {"type": "string", "description": "Permissões separadas por vírgula para permitir (ex: send_messages,view_channel)."},
                "deny_permissions": {"type": "string", "description": "Permissões separadas por vírgula para negar."},
                "reset_permissions": {"type": "boolean", "description": "Se true, remove sobrescritas e reseta para o padrão."}
            },
            "required": ["channel_id_or_name", "target_id_or_name"]
        }
    },
    {
        "name": "discord_adm_manage_thread",
        "description": "Cria, tranca, destranca, arquiva ou exclui threads em canais de texto.",
        "parameters": {
            "type": "object",
            "properties": {
                "channel_id_or_name": {"type": "string", "description": "Canal de texto ou thread."},
                "action": {"type": "string", "description": "'create', 'edit' ou 'delete'."},
                "name": {"type": "string", "description": "Nome da thread."},
                "archive": {"type": "boolean", "description": "Arquivar thread."},
                "lock": {"type": "boolean", "description": "Trancar thread."}
            }
        }
    },
    {
        "name": "discord_adm_manage_emojis_stickers",
        "description": "Cria ou deleta emojis e stickers customizados na guilda a partir de URL ou arquivo.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "'create_emoji', 'delete_emoji' ou 'delete_sticker'."},
                "name": {"type": "string", "description": "Nome do emoji/sticker a criar."},
                "image_url_or_path": {"type": "string", "description": "URL ou caminho local da imagem."},
                "target_id_or_name": {"type": "string", "description": "Nome ou ID para deletar."}
            }
        }
    },
    {
        "name": "discord_adm_manage_invites",
        "description": "Lista, cria ou revoga links de convite (Invites) do servidor.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "'list', 'create' ou 'delete'."},
                "channel_id_or_name": {"type": "string", "description": "Canal para criar convite."},
                "invite_code": {"type": "string", "description": "Código do convite para deletar."},
                "max_age_seconds": {"type": "integer", "description": "Validade em segundos (default 86400)."}
            }
        }
    },
    {
        "name": "discord_adm_manage_webhooks",
        "description": "Lista, cria ou deleta webhooks em canais do servidor.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "'list', 'create' ou 'delete'."},
                "channel_id_or_name": {"type": "string", "description": "Canal do webhook."},
                "name": {"type": "string", "description": "Nome do webhook a criar."},
                "webhook_id_or_name": {"type": "string", "description": "ID ou nome do webhook a deletar."}
            }
        }
    },
    {
        "name": "discord_adm_manage_scheduled_events",
        "description": "Lista, cria ou cancela eventos agendados no servidor.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "'list' ou 'cancel'."},
                "event_id": {"type": "string", "description": "ID ou nome do evento a cancelar."}
            }
        }
    },
    {
        "name": "discord_adm_manage_voice",
        "description": "Realiza ações de moderação de voz em massa em um canal (mute_all, unmute_all, deafen_all, move_all, disconnect_all).",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "'mute_all', 'unmute_all', 'deafen_all', 'move_all' ou 'disconnect_all'."},
                "channel_id_or_name": {"type": "string", "description": "Canal de voz de origem."},
                "target_channel_id_or_name": {"type": "string", "description": "Canal de voz de destino (para move_all)."}
            },
            "required": ["action", "channel_id_or_name"]
        }
    },
    {
        "name": "discord_adm_manage_templates_integrations",
        "description": "Gerencia templates de servidor e lista integrações ativas.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "'list_integrations' ou 'create_template'."},
                "name": {"type": "string", "description": "Nome do template a criar."}
            }
        }
    }
]

if "TOOL_MAP" in globals():
    TOOL_MAP.update(FERRAMENTAS_DISCORD_ADM)

if "FUNCTION_DECLARATIONS" in globals():
    for dec in DECLARACOES_DISCORD_ADM:
        if not any(existing.get("name") == dec["name"] for existing in FUNCTION_DECLARATIONS):
            FUNCTION_DECLARATIONS.append(dec)

def register(tool_map, function_declarations):
    tool_map.update(FERRAMENTAS_DISCORD_ADM)
    for dec in DECLARACOES_DISCORD_ADM:
        if not any(existing.get("name") == dec["name"] for existing in function_declarations):
            function_declarations.append(dec)
