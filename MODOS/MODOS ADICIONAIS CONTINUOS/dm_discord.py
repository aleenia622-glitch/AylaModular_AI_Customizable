"""Consulta as DMs acessíveis e envia mensagens diretas para usuários do Discord."""
import asyncio
import sys

import discord

if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

_LIMITE_DISCORD = 1990
_MAXIMO_LISTAGEM = 200
_MAXIMO_VERIFICACAO = 60
_PAUSA_VERIFICACAO = 0.35


def _get_bot():
    bot = globals().get("bot")
    if not bot:
        main = sys.modules.get("__main__")
        if main and hasattr(main, "bot"):
            bot = getattr(main, "bot")
    return bot


def _run_async(coro, timeout: float = 60.0):
    bot = _get_bot()
    if not bot:
        return "❌ O bot do Discord não está disponível ou ainda não inicializou."
    loop = getattr(bot, "loop", None)
    if not loop or loop.is_closed():
        return "❌ O loop de eventos do Discord não está em execução."
    try:
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=timeout)
    except TimeoutError:
        return f"⏱️ A operação no Discord passou de {timeout:.0f}s e foi cancelada."
    except discord.NotFound:
        return "🔍 Usuário não encontrado no Discord."
    except discord.Forbidden:
        return "🚫 O Discord bloqueou a ação: provavelmente esse usuário não aceita DM vinda do bot."
    except discord.HTTPException as exc:
        return f"❌ Erro HTTP do Discord ({exc.status}): {exc.text}"
    except Exception as exc:
        return f"⚠️ Erro ao executar a ação no Discord: {exc}"


def _dividir(texto: str):
    splitter = globals().get("dividir_mensagem_discord")
    if callable(splitter):
        try:
            partes = [p for p in splitter(texto) if p and p.strip()]
            if partes:
                return partes
        except Exception:
            pass
    return [texto[i:i + _LIMITE_DISCORD] for i in range(0, len(texto), _LIMITE_DISCORD)] or [""]


async def _coletar_dms(bot, incluir_membros: bool, verificar_dm: bool, limite: int):
    abertas = []
    grupos = []
    ids_em_dm = set()

    for canal in list(getattr(bot, "private_channels", []) or []):
        recipient = getattr(canal, "recipient", None)
        if recipient is not None:
            abertas.append((canal.id, recipient.id, str(recipient),
                            bool(getattr(recipient, "bot", False))))
            ids_em_dm.add(recipient.id)
        else:
            membros = ", ".join(str(u) for u in (getattr(canal, "recipients", []) or []))
            grupos.append((canal.id, membros or "sem nome"))

    linhas = []
    linhas.append(f"📬 **DMs já abertas com o bot (cache):** {len(abertas)}")
    for canal_id, usuario_id, nome, eh_bot in abertas[:_MAXIMO_LISTAGEM]:
        marca = " [bot]" if eh_bot else ""
        linhas.append(f"• {nome}{marca} — ID: {usuario_id} (canal {canal_id})")
    if not abertas:
        linhas.append("• nenhuma DM no cache — normal logo após iniciar o bot")

    if grupos:
        linhas.append("")
        linhas.append(f"👥 **Grupos (DM em grupo):** {len(grupos)}")
        for canal_id, membros in grupos[:_MAXIMO_LISTAGEM]:
            linhas.append(f"• {membros} — canal {canal_id}")

    if not incluir_membros:
        return "\n".join(linhas)

    intents = getattr(bot, "intents", None)
    tem_intent = bool(getattr(intents, "members", False))
    if not tem_intent:
        linhas.append("")
        linhas.append("⚠️ O intent GUILD_MEMBERS está desativado: só consigo ver membros em cache.")

    candidatos = {}
    for guild in list(getattr(bot, "guilds", []) or []):
        for membro in list(getattr(guild, "members", []) or []):
            if getattr(membro, "bot", False):
                continue
            if membro.id == getattr(bot.user, "id", None):
                continue
            candidatos.setdefault(membro.id, membro)

    ordenados = sorted(candidatos.values(), key=lambda u: str(u).lower())
    if limite and limite > 0:
        alvo = ordenados[:limite]
    else:
        alvo = ordenados[:_MAXIMO_LISTAGEM]

    linhas.append("")
    linhas.append(f"👤 **Membros de servidores (humanos):** {len(candidatos)}"
                  + (f" — mostrando {len(alvo)}" if len(alvo) < len(candidatos) else ""))

    if verificar_dm:
        if len(alvo) > _MAXIMO_VERIFICACAO:
            linhas.append(f"⚠️ Verificação limitada a {_MAXIMO_VERIFICACAO} usuários por chamada.")
            alvo = alvo[:_MAXIMO_VERIFICACAO]
        linhas.append("🔎 Abrindo canal de DM de cada um para confirmar (sem enviar mensagem)...")
        ok = bloqueados = erros = 0
        for usuario in alvo:
            if usuario.id in ids_em_dm:
                linhas.append(f"• ✅ {usuario} — ID: {usuario.id} — DM já aberta")
                ok += 1
                continue
            try:
                await usuario.create_dm()
                linhas.append(f"• ✅ {usuario} — ID: {usuario.id} — DM pode ser aberta")
                ok += 1
            except discord.Forbidden:
                linhas.append(f"• 🚫 {usuario} — ID: {usuario.id} — não aceita DM do bot")
                bloqueados += 1
            except discord.HTTPException as exc:
                linhas.append(f"• ❌ {usuario} — ID: {usuario.id} — erro HTTP {exc.status}")
                erros += 1
            except Exception as exc:
                linhas.append(f"• ❌ {usuario} — ID: {usuario.id} — erro: {exc}")
                erros += 1
            await asyncio.sleep(_PAUSA_VERIFICACAO)
        linhas.append("")
        linhas.append(f"**Resumo:** {ok} com DM disponível, {bloqueados} bloqueado(s), {erros} erro(s).")
    else:
        for usuario in alvo:
            estado = " (DM já aberta)" if usuario.id in ids_em_dm else ""
            linhas.append(f"• {usuario} — ID: {usuario.id}{estado}")
        if len(ordenados) > len(alvo):
            linhas.append(f"... e mais {len(ordenados) - len(alvo)} membros (aumente o limite ou use verificar_dm)")
        linhas.append("")
        linhas.append("ℹ️ Use `verificar_dm=true` para confirmar quem realmente aceita DM do bot.")

    return "\n".join(linhas)


def consultar_dms(incluir_membros: bool = True, verificar_dm: bool = False,
                  limite: int = 60) -> str:
    bot = _get_bot()
    if not bot:
        return "❌ O bot do Discord não está disponível ou ainda não inicializou."
    try:
        limite = int(limite)
    except (TypeError, ValueError):
        limite = 60
    return _run_async(_coletar_dms(bot, bool(incluir_membros), bool(verificar_dm), limite))


async def _enviar(bot, usuario_id: int, mensagem: str):
    if usuario_id == getattr(bot.user, "id", None):
        return "🤨 Esse ID é o meu próprio. Vou mandar mensagem pra mim mesma? Aí é demais."

    usuario = bot.get_user(usuario_id)
    if usuario is None:
        try:
            usuario = await bot.fetch_user(usuario_id)
        except discord.NotFound:
            return f"🔍 Não existe usuário com o ID {usuario_id}."
    if usuario is None:
        return f"🔍 Não consegui obter o usuário de ID {usuario_id}."

    partes = _dividir(mensagem)
    enviadas = []
    for parte in partes:
        try:
            msg = await usuario.send(parte)
            enviadas.append(msg.id)
        except discord.Forbidden:
            if enviadas:
                return (f"⚠️ Enviei {len(enviadas)} de {len(partes)} partes para {usuario} "
                        f"(ID {usuario_id}) e o Discord bloqueou o resto: as DMs desse usuário não aceitam o bot.")
            return (f"🚫 Não consegui enviar para {usuario} (ID {usuario_id}): "
                    f"esse usuário não aceita mensagem direta do bot.")
        except discord.HTTPException as exc:
            return f"❌ Falha HTTP do Discord ao enviar ({exc.status}): {exc.text}"

    total = sum(len(p) for p in partes)
    return (f"✅ Mensagem enviada para **{usuario}** (ID {usuario_id}) — "
            f"{len(enviadas)} mensagem(ns), {total} caracteres.\nIDs: {', '.join(str(i) for i in enviadas)}")


def enviar_dm(usuario_id: str, mensagem: str) -> str:
    bot = _get_bot()
    if not bot:
        return "❌ O bot do Discord não está disponível ou ainda não inicializou."

    alvo = str(usuario_id or "").strip().strip("<@!>")
    if not alvo.isdigit():
        return f"❌ ID inválido: '{usuario_id}'. Preciso do ID numérico do usuário, não do nome."
    if not mensagem or not str(mensagem).strip():
        return "❌ A mensagem está vazia."

    return _run_async(_enviar(bot, int(alvo), str(mensagem)))


TOOL_MAP["consultar_dms"] = consultar_dms
TOOL_MAP["enviar_dm"] = enviar_dm

FUNCTION_DECLARATIONS.append({
    "name": "consultar_dms",
    "description": (
        "Lista nome e ID de todos os destinatários possíveis de DM no Discord: DMs já abertas, "
        "grupos e membros dos servidores onde o bot está. Com verificar_dm=true, tenta abrir o "
        "canal de DM de cada um (sem enviar mensagem) para confirmar quem realmente aceita. "
        "Use antes de enviar_dm quando não souber o ID."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "incluir_membros": {
                "type": "boolean",
                "description": "Se true (padrão), inclui os membros dos servidores, não só DMs em cache."
            },
            "verificar_dm": {
                "type": "boolean",
                "description": "Se true, tenta abrir o canal de DM de cada usuário para confirmar quem aceita receber (mais lento, limitado a 60 por chamada)."
            },
            "limite": {
                "type": "integer",
                "description": "Quantos membros listar/verificar (padrão 60)."
            }
        },
        "required": []
    }
})

FUNCTION_DECLARATIONS.append({
    "name": "enviar_dm",
    "description": "Envia uma mensagem direta (DM) no Discord para um usuário pelo ID numérico.",
    "parameters": {
        "type": "object",
        "properties": {
            "usuario_id": {
                "type": "string",
                "description": "ID numérico do usuário que vai receber a DM (não use o nome)."
            },
            "mensagem": {
                "type": "string",
                "description": "Texto completo da mensagem a ser enviada."
            }
        },
        "required": ["usuario_id", "mensagem"]
    }
})
