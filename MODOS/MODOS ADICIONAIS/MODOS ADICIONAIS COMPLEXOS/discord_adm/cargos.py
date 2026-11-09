from .common import *

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
