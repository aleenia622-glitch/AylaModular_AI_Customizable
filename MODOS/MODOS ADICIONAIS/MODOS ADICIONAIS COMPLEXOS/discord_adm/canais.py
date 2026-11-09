from .common import *

def discord_adm_list_channels(channel_type: str = "", category_id_or_name: str = "", include_threads: bool = False, group_by_category: bool = True, guild_id: str = "") -> str:
    """Lista todos os canais do servidor Discord (Guild) detalhadamente com seus nomes, IDs, tipos, categorias e propriedades."""
    async def _impl():
        bot = _get_bot()
        guild = _get_guild(bot, guild_id)
        if not guild:
            return "❌ Nenhuma guilda (servidor) encontrada."

        def _type_info(chan):
            if isinstance(chan, discord.CategoryChannel):
                return "📂 Categoria", "category"
            elif isinstance(chan, discord.TextChannel):
                if getattr(chan, "is_news", lambda: False)():
                    return "📢 Anúncio", "news"
                return "💬 Texto", "text"
            elif isinstance(chan, discord.VoiceChannel):
                return "🔊 Voz", "voice"
            elif isinstance(chan, discord.StageChannel):
                return "🎙️ Palco (Stage)", "stage"
            elif isinstance(chan, discord.ForumChannel):
                return "📋 Fórum", "forum"
            elif isinstance(chan, discord.Thread):
                return "🧵 Thread", "thread"
            elif hasattr(discord, "MediaChannel") and isinstance(chan, discord.MediaChannel):
                return "🖼️ Mídia", "media"
            return f"📁 {type(chan).__name__}", "other"

        filter_type = channel_type.lower().strip()
        category_filter = _resolve_channel(guild, category_id_or_name) if category_id_or_name else None

        all_channels = list(guild.channels)

        if category_filter:
            if isinstance(category_filter, discord.CategoryChannel):
                all_channels = [c for c in all_channels if getattr(c, "category_id", None) == category_filter.id or c.id == category_filter.id]
            else:
                return f"❌ A categoria `{category_id_or_name}` não é uma categoria válida."

        if filter_type:
            def _matches_type(c):
                lbl, key = _type_info(c)
                if filter_type in (key, lbl.lower()):
                    return True
                if filter_type in ("text", "texto") and key == "text":
                    return True
                if filter_type in ("voice", "voz") and key == "voice":
                    return True
                if filter_type in ("category", "categoria") and key == "category":
                    return True
                if filter_type in ("news", "announcement", "anuncio") and key == "news":
                    return True
                if filter_type in ("forum", "forum") and key == "forum":
                    return True
                if filter_type in ("stage", "palco") and key == "stage":
                    return True
                if filter_type in ("thread", "threads") and key == "thread":
                    return True
                return False
            all_channels = [c for c in all_channels if _matches_type(c)]

        if not all_channels:
            return "📁 Nenhum canal encontrado para os filtros fornecidos."

        lines = []

        if group_by_category and not filter_type:
            categories_and_channels = guild.by_category()
            for cat, chans in categories_and_channels:
                if category_filter and cat != category_filter:
                    continue

                if cat:
                    lines.append(f"\n📂 **[CATEGORIA] {cat.name.upper()}** (ID: `{cat.id}`)")
                else:
                    lines.append("\n📁 **[SEM CATEGORIA]**")

                target_chans = chans if not filter_type else [c for c in chans if c in all_channels]
                if not target_chans:
                    lines.append("  *(Nenhum canal)*")
                    continue

                for c in target_chans:
                    lbl, key = _type_info(c)
                    details = []
                    if hasattr(c, "topic") and c.topic:
                        topic_short = c.topic.replace("\n", " ")
                        if len(topic_short) > 60:
                            topic_short = topic_short[:57] + "..."
                        details.append(f"Tópico: \"{topic_short}\"")
                    if getattr(c, "nsfw", False):
                        details.append("🔞 NSFW")
                    if getattr(c, "slowmode_delay", 0) > 0:
                        details.append(f"⏳ Slowmode: {c.slowmode_delay}s")
                    if isinstance(c, discord.VoiceChannel):
                        bitrate_kbps = c.bitrate // 1000
                        details.append(f"🎧 Bitrate: {bitrate_kbps}kbps")
                        if c.user_limit:
                            details.append(f"👥 Limite: {c.user_limit}")
                        if len(c.members) > 0:
                            details.append(f"🎙️ {len(c.members)} conectados")

                    det_str = f" | {' • '.join(details)}" if details else ""
                    lines.append(f"  • {lbl} **#{c.name}** — ID: `{c.id}` (Tipo: `{key}`){det_str}")

                    if include_threads and hasattr(c, "threads") and c.threads:
                        for th in c.threads:
                            lines.append(f"    └─ 🧵 **Thread:** `{th.name}` — ID: `{th.id}`")

        else:
            for c in all_channels:
                lbl, key = _type_info(c)
                cat_str = f" | Categoria: **{c.category.name}** (`{c.category_id}`)" if getattr(c, "category", None) else ""
                details = []
                if hasattr(c, "topic") and c.topic:
                    topic_short = c.topic.replace("\n", " ")
                    if len(topic_short) > 50:
                        topic_short = topic_short[:47] + "..."
                    details.append(f"Tópico: \"{topic_short}\"")
                if getattr(c, "nsfw", False):
                    details.append("🔞 NSFW")
                if getattr(c, "slowmode_delay", 0) > 0:
                    details.append(f"⏳ Slowmode: {c.slowmode_delay}s")
                if isinstance(c, discord.VoiceChannel):
                    if len(c.members) > 0:
                        details.append(f"🎙️ {len(c.members)} em call")

                det_str = f" | {' • '.join(details)}" if details else ""
                lines.append(f"• {lbl} **#{c.name}** — ID: `{c.id}` (Tipo: `{key}`){cat_str}{det_str}")

                if include_threads and hasattr(c, "threads") and c.threads:
                    for th in c.threads:
                        lines.append(f"  └─ 🧵 **Thread:** `{th.name}` — ID: `{th.id}`")

        total_text = len(guild.text_channels)
        total_voice = len(guild.voice_channels)
        total_cats = len(guild.categories)
        total_forums = len(getattr(guild, "forum_channels", []))
        total_threads = len(guild.threads)

        resumo = (
            f"📊 **Canais do Servidor {guild.name}**\n"
            f"Total: **{len(guild.channels)}** canais ({total_cats} categorias, {total_text} texto, {total_voice} voz, {total_forums} fóruns, {total_threads} threads)\n"
            f"──────────────────────────────────────────"
        )
        return f"{resumo}\n" + "\n".join(lines)

    return _run_async(_impl())


def discord_adm_get_channel_info(channel_id_or_name: str, guild_id: str = "") -> str:
    """Exibe informações detalhadas, permissões e status de um canal específico no Discord."""
    async def _impl():
        bot = _get_bot()
        guild = _get_guild(bot, guild_id)
        if not guild:
            return "❌ Nenhuma guilda (servidor) encontrada."

        channel = _resolve_channel(guild, channel_id_or_name)
        if not channel:
            return f"❌ Canal `{channel_id_or_name}` não encontrado."

        def _type_str(chan):
            if isinstance(chan, discord.CategoryChannel):
                return "Categoria (Category)"
            elif isinstance(chan, discord.TextChannel):
                return "Canal de Texto (TextChannel)" if not getattr(chan, "is_news", lambda: False)() else "Canal de Anúncio (NewsChannel)"
            elif isinstance(chan, discord.VoiceChannel):
                return "Canal de Voz (VoiceChannel)"
            elif isinstance(chan, discord.StageChannel):
                return "Canal de Palco (StageChannel)"
            elif isinstance(chan, discord.ForumChannel):
                return "Canal de Fórum (ForumChannel)"
            elif isinstance(chan, discord.Thread):
                return "Thread / Tópico"
            return type(chan).__name__

        created = channel.created_at.strftime("%d/%m/%Y %H:%M:%S") if hasattr(channel, "created_at") and channel.created_at else "N/A"
        category_name = channel.category.name if getattr(channel, "category", None) else "Nenhuma (Raiz)"
        category_id = channel.category_id if getattr(channel, "category_id", None) else "N/A"

        info_lines = [
            f"📺 **Informações Detalhadas do Canal: #{channel.name}**",
            f"🆔 **ID:** `{channel.id}`",
            f"🏷️ **Tipo:** {_type_str(channel)}",
            f"📂 **Categoria:** {category_name} (`{category_id}`)",
            f"📍 **Posição:** {getattr(channel, 'position', 'N/A')}",
            f"📅 **Criado em:** {created} UTC",
        ]

        if hasattr(channel, "topic") and channel.topic:
            info_lines.append(f"📝 **Tópico:** {channel.topic}")
        if hasattr(channel, "nsfw"):
            info_lines.append(f"🔞 **NSFW:** {'Sim' if channel.nsfw else 'Não'}")
        if hasattr(channel, "slowmode_delay"):
            info_lines.append(f"⏳ **Modo Lento (Slowmode):** {channel.slowmode_delay} segundos")
        if isinstance(channel, discord.VoiceChannel):
            info_lines.append(f"🎧 **Bitrate:** {channel.bitrate // 1000} kbps")
            info_lines.append(f"👥 **Limite de Usuários:** {channel.user_limit if channel.user_limit else 'Ilimitado'}")
            info_lines.append(f"🎙️ **Membros Conectados ({len(channel.members)}):** {', '.join([m.display_name for m in channel.members[:10]]) or 'Nenhum'}")
            if len(channel.members) > 10:
                info_lines[-1] += f" (+{len(channel.members)-10})"

        if hasattr(channel, "threads") and channel.threads:
            info_lines.append(f"🧵 **Threads Ativas ({len(channel.threads)}):** {', '.join([f'`{t.name}`' for t in channel.threads[:5]])}")

        if hasattr(channel, "overwrites") and channel.overwrites:
            overwrites_str = []
            for target, overwrite in list(channel.overwrites.items())[:10]:
                target_name = target.name if hasattr(target, "name") else str(target)
                target_type = "Cargo" if isinstance(target, discord.Role) else "Membro"
                allow_list, deny_list = [], []
                for perm, val in overwrite:
                    if val is True:
                        allow_list.append(perm)
                    elif val is False:
                        deny_list.append(perm)
                
                status_parts = []
                if allow_list:
                    status_parts.append(f"Permitidos: [{', '.join(allow_list[:3])}]")
                if deny_list:
                    status_parts.append(f"Negados: [{', '.join(deny_list[:3])}]")
                
                overwrites_str.append(f"  • **{target_type} {target_name}:** {' | '.join(status_parts) if status_parts else 'Padrão'}")

            info_lines.append(f"🔐 **Sobrescritas de Permissão ({len(channel.overwrites)} alvos):**\n" + "\n".join(overwrites_str))

        return "\n".join(info_lines)

    return _run_async(_impl())


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
