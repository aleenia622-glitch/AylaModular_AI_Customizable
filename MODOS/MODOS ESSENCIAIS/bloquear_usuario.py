import os
from pathlib import Path
from datetime import datetime

ARQUIVO_BLOQUEIO = Path(__file__).resolve().parent.parent / "ayla_block.json"


def _carregar_bloqueios() -> list:
    try:
        data = json.loads(ARQUIVO_BLOQUEIO.read_text(encoding="utf-8"))
        return data.get("blocked_users", [])
    except Exception:
        return []


def _salvar_bloqueios(lista: list):
    tmp = ARQUIVO_BLOQUEIO.with_suffix(".tmp")
    tmp.write_text(json.dumps({"blocked_users": lista}, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(str(tmp), str(ARQUIVO_BLOQUEIO))


def _usuario_bloqueado(user_id: int) -> bool:
    return any(str(u.get("id")) == str(user_id) for u in _carregar_bloqueios())


def _notificar_dona(user_id_int, nome, motivo):
    display = f"**{nome}** ({user_id_int})" if nome else f"**{user_id_int}**"
    async def _dm():
        try:
            global_bot = globals().get("bot")
            if not global_bot:
                return
            owner = await global_bot.fetch_user(DISCORD_OWNER_ID)
            if owner:
                await owner.send(
                    f"🚫 **Bloqueio automático!**\n\n"
                    f"Eu bloqueei o usuário {display} do modo público.\n"
                    f"**Motivo:** {motivo}"
                )
        except Exception as e:
            print(f"⚠️ Erro ao notificar dona sobre bloqueio: {e}")

    try:
        global_bot = globals().get("bot")
        if global_bot and hasattr(global_bot, "loop"):
            asyncio.run_coroutine_threadsafe(_dm(), global_bot.loop)
        else:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(_dm(), loop)
    except Exception as e:
        print(f"⚠️ Erro ao agendar DM de bloqueio: {e}")


def bloquear_usuario(user_id: str, motivo: str) -> str:
    try:
        user_id_int = int(user_id)
    except ValueError:
        return "❌ ID de usuário inválido."

    if user_id_int == DISCORD_OWNER_ID:
        return "❌ A dona (Aleenia) é imune e não pode ser bloqueada."

    bloqueios = _carregar_bloqueios()
    if any(u["id"] == user_id_int for u in bloqueios):
        return f"⚠️ Usuário {user_id_int} já está bloqueado."

    # Tenta resolver nome via Discord
    nome_discord = ""
    try:
        global_bot = globals().get("bot")
        if global_bot:
            import asyncio
            future = asyncio.run_coroutine_threadsafe(global_bot.fetch_user(user_id_int), global_bot.loop)
            user_obj = future.result(timeout=5)
            if user_obj:
                nome_discord = str(user_obj.display_name)
    except Exception:
        pass

    bloqueios.append({
        "id": user_id_int,
        "name": nome_discord,
        "reason": motivo,
        "blocked_at": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "blocked_by": "ayla",
    })
    _salvar_bloqueios(bloqueios)
    _notificar_dona(user_id_int, nome_discord, motivo)
    display = nome_discord or str(user_id_int)
    return f"✅ Usuário {display} ({user_id_int}) bloqueado com sucesso. Motivo: {motivo}"


def desbloquear_usuario(user_id: str) -> str:
    try:
        user_id_int = int(user_id)
    except ValueError:
        return "❌ ID de usuário inválido."

    bloqueios = _carregar_bloqueios()
    nova_lista = [u for u in bloqueios if u["id"] != user_id_int]

    if len(nova_lista) == len(bloqueios):
        return f"⚠️ Usuário {user_id_int} não está na lista de bloqueios."

    _salvar_bloqueios(nova_lista)
    return f"✅ Usuário {user_id_int} desbloqueado com sucesso."


TOOL_MAP["bloquear_usuario"] = bloquear_usuario
FUNCTION_DECLARATIONS.append({
    "name": "bloquear_usuario",
    "description": "Bloqueia um usuario do modo publico quando a conversa fica estranha, inapropriada ou o usuario quebra regras. A dona (Aleenia) eh imune.",
    "parameters": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "ID do usuario no Discord"},
            "motivo": {"type": "string", "description": "Motivo do bloqueio"},
        },
        "required": ["user_id", "motivo"],
    },
})

TOOL_MAP["desbloquear_usuario"] = desbloquear_usuario
FUNCTION_DECLARATIONS.append({
    "name": "desbloquear_usuario",
    "description": "Desbloqueia um usuario que foi bloqueado do modo publico",
    "parameters": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "ID do usuario no Discord"},
        },
        "required": ["user_id"],
    },
})
