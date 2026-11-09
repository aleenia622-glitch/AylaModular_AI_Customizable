"""Faz a Ayla sair de um servidor do Discord indicado ou do servidor atual."""

import asyncio
from concurrent.futures import TimeoutError as FutureTimeoutError

import discord

try:
    import ayla_state
except ImportError:
    ayla_state = None


# Permite validar/importar este arquivo isoladamente, além do carregamento normal
# feito pelo gerenciador de modos da Ayla.
if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []


def _bot_ativo():
    """Retorna a conexão Discord injetada pelo carregador de modos."""
    return globals().get("bot")


def _loop_discord_ativo(bot):
    """Obtém o loop real do Discord sem depender do sentinel do discord.py."""
    for atributo in ("discord_loop", "loop"):
        try:
            loop = getattr(bot, atributo, None)
            if loop is not None and loop.is_running() and not loop.is_closed():
                return loop
        except (AttributeError, RuntimeError):
            continue
    return None


def _contexto_ativo():
    if ayla_state is None:
        return None
    contexto = getattr(ayla_state, "CONTEXTO_ATIVO", None)
    return contexto.get() if contexto is not None else None


def _normalizar_nome(valor: str) -> str:
    return " ".join(str(valor).casefold().split())


def _localizar_servidor(bot, servidor: str = ""):
    """Resolve o servidor citado sem escolher silenciosamente um alvo incerto."""
    servidores = list(getattr(bot, "guilds", ()) or ())
    if not servidores:
        return None, "Ayla não está conectada a nenhum servidor."

    alvo = str(servidor or "").strip()
    if alvo:
        if alvo.isdigit():
            guild = bot.get_guild(int(alvo))
            if guild is not None:
                return guild, None
            return None, f"Não encontrei um servidor com o ID {alvo}."

        nome_alvo = _normalizar_nome(alvo)
        exatos = [g for g in servidores if _normalizar_nome(g.name) == nome_alvo]
        if len(exatos) == 1:
            return exatos[0], None
        if len(exatos) > 1:
            opcoes = ", ".join(f"{g.name} ({g.id})" for g in exatos)
            return None, f"Há mais de um servidor com esse nome: {opcoes}. Informe o ID."

        parciais = [g for g in servidores if nome_alvo in _normalizar_nome(g.name)]
        if len(parciais) == 1:
            return parciais[0], None
        if len(parciais) > 1:
            opcoes = ", ".join(f"{g.name} ({g.id})" for g in parciais)
            return None, f"O nome informado combina com vários servidores: {opcoes}. Seja mais específica ou informe o ID."
        return None, f"Não encontrei o servidor chamado '{alvo}'."

    contexto = _contexto_ativo()
    guild = getattr(contexto, "guild", None)
    if guild is not None and any(g.id == guild.id for g in servidores):
        return guild, None

    return None, (
        "Não consegui identificar o servidor da conversa atual. "
        "Diga o nome ou o ID do servidor do qual devo sair."
    )


async def _sair(bot, servidor: str = "") -> str:
    guild, erro = _localizar_servidor(bot, servidor)
    if guild is None:
        return f"❌ {erro}"

    nome, guild_id = guild.name, guild.id
    await guild.leave()
    return f"✅ Saí do servidor **{nome}** (`{guild_id}`)."


def sair_do_servidor_atual(servidor: str = "") -> str:
    """Faz a Ayla sair do servidor citado ou daquele em que recebeu a mensagem."""
    bot = _bot_ativo()
    if bot is None or not getattr(bot, "user", None):
        return "❌ A Ayla não está conectada ao Discord."

    loop = _loop_discord_ativo(bot)
    if loop is None:
        return "❌ A conexão da Ayla com o Discord não está pronta."

    futuro = asyncio.run_coroutine_threadsafe(_sair(bot, servidor), loop)
    try:
        return futuro.result(timeout=30)
    except FutureTimeoutError:
        futuro.cancel()
        return "❌ O Discord demorou demais para responder; a saída foi cancelada."
    except discord.NotFound:
        return "❌ O servidor não existe mais ou a Ayla já saiu dele."
    except discord.HTTPException as erro:
        return f"❌ O Discord recusou a saída do servidor: {erro}"
    except Exception as erro:
        return f"❌ Não consegui sair do servidor: {erro}"


TOOL_MAP["sair_do_servidor_atual"] = sair_do_servidor_atual

_DECLARACAO = {
    "name": "sair_do_servidor_atual",
    "description": (
        "Faz a Ayla sair do servidor do Discord que a dona indicou. "
        "Se o pedido foi feito dentro de um servidor e o parâmetro for omitido, "
        "usa o servidor da conversa atual."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "servidor": {
                "type": "string",
                "description": (
                    "Nome ou ID do servidor citado pela dona. Omita somente quando "
                    "ela estiver falando no próprio servidor do qual deseja que a Ayla saia."
                ),
            }
        },
        "required": [],
    },
}

if not any(item.get("name") == _DECLARACAO["name"] for item in FUNCTION_DECLARATIONS):
    FUNCTION_DECLARATIONS.append(_DECLARACAO)


def register(tool_map, function_declarations):
    """Registro compatível com o ModuleManager da Ayla."""
    tool_map["sair_do_servidor_atual"] = sair_do_servidor_atual
    if not any(item.get("name") == _DECLARACAO["name"] for item in function_declarations):
        function_declarations.append(_DECLARACAO)
