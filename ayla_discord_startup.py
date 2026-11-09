"""Recuperação de falhas temporárias durante o login e registro de comandos."""
from __future__ import annotations

import asyncio
import random

import aiohttp
import discord


def is_temporary_discord_error(error):
    if isinstance(error, discord.HTTPException):
        return 500 <= error.status < 600 or error.status == 429
    if isinstance(error, (aiohttp.ClientSSLError, aiohttp.ServerFingerprintMismatch)):
        return False
    return isinstance(error, (asyncio.TimeoutError, aiohttp.ClientConnectionError,
                              discord.GatewayNotFound, discord.RateLimited))


def describe_discord_error(error):
    """Não imprime HTML de proxy/Cloudflare, URLs com tokens ou credenciais."""
    if isinstance(error, discord.LoginFailure):
        return "Token do bot recusado. Confira DISCORD_TOKEN no .env."
    if isinstance(error, discord.PrivilegedIntentsRequired):
        return "O Discord recusou os intents privilegiados configurados para o bot."
    if isinstance(error, discord.HTTPException):
        suffix = f", código Discord {error.code}" if error.code else ""
        return f"Discord respondeu HTTP {error.status}{suffix}."
    if isinstance(error, discord.RateLimited):
        return "Discord pediu uma pausa por limite de requisições."
    if isinstance(error, asyncio.TimeoutError):
        return "A conexão com o Discord excedeu o tempo de espera."
    if isinstance(error, aiohttp.ClientConnectionError):
        return f"Falha de conexão com o Discord ({type(error).__name__})."
    return f"Falha ao iniciar o Discord ({type(error).__name__})."


async def wait_for_retry(delay, stopped):
    """A espera para prontamente quando a aplicação está encerrando."""
    deadline = asyncio.get_running_loop().time() + delay
    while not stopped():
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            return
        await asyncio.sleep(min(0.25, remaining))


async def retry_discord_operation(operation, stage, *, stopped=lambda: False,
                                  report=print, wait=wait_for_retry):
    attempt = 0
    while not stopped():
        try:
            await operation()
            return True
        except Exception as error:
            if not is_temporary_discord_error(error):
                raise
            if stopped():
                return False
            attempt += 1
            delay = min(60.0, 5.0 * 2 ** min(attempt - 1, 4) + random.uniform(0, 2))
            retry_after = getattr(error, "retry_after", None)
            if retry_after is None and isinstance(error, discord.HTTPException):
                retry_after = getattr(error.response, "headers", {}).get("Retry-After")
            if retry_after is not None:
                try:
                    delay = max(delay, float(retry_after))
                except (TypeError, ValueError):
                    pass
            report(f"⚠️ {stage}: {describe_discord_error(error)} "
                   f"Nova tentativa automática em {delay:.0f}s (tentativa {attempt + 1}).")
            await wait(delay, stopped)
    return False


async def sync_discord_commands(client, *, stop_requested=lambda: False, report=print,
                                wait=wait_for_retry):
    """A falha no registro dos comandos não desconecta o bot já autenticado."""
    try:
        synced = await retry_discord_operation(
            client.tree.sync, "Sincronização dos comandos", report=report, wait=wait,
            stopped=lambda: stop_requested() or client.is_closed(),
        )
        if synced:
            report("✅ Comandos de barra sincronizados.")
    except Exception as error:
        if stop_requested() or client.is_closed():
            return
        report(f"⚠️ Comandos não sincronizados: {describe_discord_error(error)} "
               "Comandos novos podem ficar indisponíveis até corrigir a configuração e reiniciar.")


async def run_discord_client(client, token, *, stop_requested=lambda: False,
                             report=print, wait=wait_for_retry):
    # A previously failed run may have closed the client. Only call this runner
    # when no other runner is active for the same client.
    if client.is_closed():
        client.clear()
    client.discord_loop = asyncio.get_running_loop()
    async def login():
        # discord.py 2.7 creates a fresh HTTP session on every login call, but
        # retains its connector. Close the old session and renew a closed
        # default connector before retrying, without closing the bot itself.
        await client.http.close()
        client.http.clear()
        connector = client.http.connector
        if connector is not discord.utils.MISSING and connector.closed:
            client.http.connector = discord.utils.MISSING
        await client.login(token)
    try:
        async with client:
            logged_in = await retry_discord_operation(
                login, "Login do bot", report=report, wait=wait,
                stopped=lambda: stop_requested() or client.is_closed(),
            )
            if logged_in and not stop_requested() and not client.is_closed():
                # Gateway reconnection is owned by discord.py once login succeeds.
                await client.connect(reconnect=True)
    finally:
        task = getattr(client, "_command_sync_task", None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            client._command_sync_task = None
        client.discord_loop = None
