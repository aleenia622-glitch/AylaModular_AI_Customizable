from .common import *

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

        kwargs = {"limit": min(limit, 30)}
        if action_enum is not None:
            kwargs["action"] = action_enum
        if user_obj is not None:
            kwargs["user"] = user_obj

        entries = []
        async for entry in guild.audit_logs(**kwargs):
            target_str = str(entry.target) if entry.target else "N/A"
            reason_str = f" | Motivo: {entry.reason}" if entry.reason else ""
            time_str = entry.created_at.strftime("%d/%m %H:%M")
            user_name = str(entry.user) if entry.user else "Desconhecido"
            entries.append(f"• `[{time_str}]` **{user_name}** fez `{entry.action.name}` em **{target_str}**{reason_str}")

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


def discord_adm_add_emoji(name: str = "", image_url_or_path: str = "", guild_id: str = "") -> str:
    """Cria um emoji personalizado no servidor Discord usando o anexo enviado pelo usuário, uma URL ou caminho de arquivo local."""
    async def _impl():
        bot = _get_bot()
        guild = _get_guild(bot, guild_id)
        if not guild:
            return "❌ Nenhuma guilda (servidor) encontrada."

        img_bytes, suggested_name = await _resolve_image_bytes(image_url_or_path)
        if not img_bytes:
            return "❌ Nenhuma imagem encontrada! Envie uma imagem em anexo junto com a mensagem ou forneça uma URL/caminho válido da imagem."

        final_name = _sanitize_emoji_name(name, suggested_name)
        opt_bytes = _optimize_emoji_image(img_bytes)

        emoji = await guild.create_custom_emoji(name=final_name, image=opt_bytes, reason="Emoji criado via Ayla ADM")
        return f"😀 Emoji criado com sucesso no servidor **{guild.name}**: <:{emoji.name}:{emoji.id}> (Nome: `:{emoji.name}:`, ID: `{emoji.id}`)"

    return _run_async(_impl())


def discord_adm_add_sticker(name: str = "", description: str = "", emoji: str = "😀", image_url_or_path: str = "", guild_id: str = "") -> str:
    """Cria um sticker (figurinha - NÃO É EMOJI) personalizado no servidor Discord usando a imagem em anexo enviada na mensagem, URL ou caminho de arquivo local."""
    async def _impl():
        bot = _get_bot()
        guild = _get_guild(bot, guild_id)
        if not guild:
            return "❌ Nenhuma guilda (servidor) encontrada."

        img_bytes, suggested_name = await _resolve_image_bytes(image_url_or_path)
        if not img_bytes:
            return "❌ Nenhuma imagem encontrada! Envie uma imagem em anexo junto com a mensagem ou forneça uma URL/caminho válido da imagem."

        sticker_name = name.strip() if name and name.strip() else suggested_name.strip()
        if not sticker_name:
            sticker_name = "sticker_custom"
        if len(sticker_name) < 2:
            sticker_name = f"sticker_{sticker_name}"
        if len(sticker_name) > 30:
            sticker_name = sticker_name[:30]

        sticker_desc = description.strip() if description and len(description.strip()) >= 2 else "Sticker criado via Ayla ADM"
        if len(sticker_desc) > 100:
            sticker_desc = sticker_desc[:100]

        # A API do Discord exige o NOME do emoji, não o caractere Unicode (HTTP 400 caso contrário)
        emoji_raw = emoji.strip() if emoji and emoji.strip() else "😀"
        emoji_name = _emoji_to_name(emoji_raw)

        opt_bytes, img_ext = _optimize_sticker_image(img_bytes, image_url_or_path or "")
        file_obj = discord.File(io.BytesIO(opt_bytes), filename=f"{sticker_name}.{img_ext}")

        sticker = await guild.create_sticker(
            name=sticker_name,
            description=sticker_desc,
            emoji=emoji_name,
            file=file_obj,
            reason="Sticker criado via Ayla ADM"
        )
        return f"🎨 Sticker (figurinha) **{sticker.name}** (ID: `{sticker.id}`) criado com sucesso no servidor **{guild.name}**!"

    return _run_async(_impl())


def discord_adm_manage_emojis_stickers(action: str = "create_emoji", name: str = "", image_url_or_path: str = "", target_id_or_name: str = "", guild_id: str = "") -> str:
    """Cria ou deleta emojis e stickers customizados na guilda a partir de anexo, URL ou arquivo local."""
    async def _impl():
        bot = _get_bot()
        guild = _get_guild(bot, guild_id)
        if not guild:
            return "❌ Nenhuma guilda encontrada."

        act = action.lower().strip()

        if act in ("create_emoji", "add_emoji", "criar_emoji", "emoji"):
            img_bytes, suggested_name = await _resolve_image_bytes(image_url_or_path)
            if not img_bytes:
                return "❌ Nenhuma imagem encontrada! Envie uma imagem em anexo junto com a mensagem ou forneça uma URL/caminho válido da imagem."

            final_name = _sanitize_emoji_name(name, suggested_name)
            opt_bytes = _optimize_emoji_image(img_bytes)

            emoji = await guild.create_custom_emoji(name=final_name, image=opt_bytes, reason="Criado via Ayla ADM")
            return f"😀 Emoji criado com sucesso no servidor **{guild.name}**: <:{emoji.name}:{emoji.id}> (Nome: `:{emoji.name}:`, ID: `{emoji.id}`)"

        elif act in ("create_sticker", "add_sticker", "criar_sticker", "sticker", "figurinha", "criar_figurinha"):
            img_bytes, suggested_name = await _resolve_image_bytes(image_url_or_path)
            if not img_bytes:
                return "❌ Nenhuma imagem encontrada! Envie uma imagem em anexo junto com a mensagem ou forneça uma URL/caminho válido da imagem."

            sticker_name = name.strip() if name and name.strip() else suggested_name.strip()
            if not sticker_name:
                sticker_name = "sticker_custom"
            if len(sticker_name) < 2:
                sticker_name = f"sticker_{sticker_name}"
            if len(sticker_name) > 30:
                sticker_name = sticker_name[:30]

            sticker_desc = "Sticker criado via Ayla ADM"
            # A API do Discord exige o NOME do emoji, não o caractere Unicode (HTTP 400 caso contrário)
            emoji_name = "grinning"

            opt_bytes, img_ext = _optimize_sticker_image(img_bytes, image_url_or_path or "")
            file_obj = discord.File(io.BytesIO(opt_bytes), filename=f"{sticker_name}.{img_ext}")

            sticker = await guild.create_sticker(
                name=sticker_name,
                description=sticker_desc,
                emoji=emoji_name,
                file=file_obj,
                reason="Sticker criado via Ayla ADM"
            )
            return f"🎨 Sticker (figurinha) **{sticker.name}** (ID: `{sticker.id}`) criado com sucesso no servidor **{guild.name}**!"

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

        return "⚠️ Ação inválida. Use 'create_emoji', 'delete_emoji', 'create_sticker' ou 'delete_sticker'."

    return _run_async(_impl())


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
