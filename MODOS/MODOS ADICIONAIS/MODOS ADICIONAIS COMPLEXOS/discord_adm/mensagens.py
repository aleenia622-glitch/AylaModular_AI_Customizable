from .common import *

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
