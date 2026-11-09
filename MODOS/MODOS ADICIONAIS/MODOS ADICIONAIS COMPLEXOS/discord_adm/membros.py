from .common import *
from ayla_verificacao import ResultadoFerramenta

def discord_adm_ban_member(user_id: str, reason: str = "Banido via Ayla ADM", delete_message_days: int = 0, guild_id: str = "") -> str:
    """Bane diretamente pelo ID ou menção; não precisa consultar o membro antes. O sucesso já confirma a operação, sem listar banidos."""
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
        return ResultadoFerramenta(
            f"🔨 **{user_to_ban}** (ID: `{user_to_ban.id}`) foi BANIDO com sucesso do servidor!\nMotivo: {reason}",
            'verificado',
            [f'Discord confirmou a conclusão de guild.ban para o usuário {user_to_ban.id} no servidor {guild.id}.'],
            'Confirma a operação neste momento; não é necessário listar banidos para reconfirmar.',
        )

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
