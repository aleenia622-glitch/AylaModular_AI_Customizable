"""Explica como entrar na call com visão opcional e acompanhar a dona."""
import asyncio
from concurrent.futures import TimeoutError as FutureTimeoutError

import ayla_state


class SeguirDonaNaCall:
    def __init__(self, bot, owner_id):
        self.bot = bot
        self.owner_id = owner_id
        self._lock = asyncio.Lock()
        self.ativo = False
        self.visao_bionica = False

    async def sincronizar(self, preferred=None, *, solicitado=False, visao_bionica=None):
        async with self._lock:
            if not solicitado and not self.ativo:
                return 'O acompanhamento está desativado. Aguardo um pedido para entrar.'
            if solicitado and visao_bionica is not None:
                self.visao_bionica = bool(visao_bionica)
            manager = self.bot.voice_manager
            if not manager or not self.owner_id:
                return 'Não foi possível iniciar a call: voz ou dona não configurada.'
            channels = []
            for guild in self.bot.guilds:
                member = guild.get_member(self.owner_id)
                channel = getattr(getattr(member, 'voice', None), 'channel', None)
                if channel:
                    channels.append(channel)
            target = next((c for c in channels if c.id == preferred), None)
            target = target or next(iter(channels), None)
            self.ativo = target is not None
            for guild_id in list(manager._voice_clients):
                if target is None or guild_id != target.guild.id:
                    await manager.desconectar_canal_voz(guild_id)
            if target:
                vc = manager.get_voice_client(target.guild.id)
                bridge = manager._voice_bridges.get(target.guild.id)
                if (vc and vc.is_connected() and vc.channel.id == target.id
                        and bridge and not bridge.stop_event.is_set()
                        and getattr(bridge, "visao_bionica", False) == self.visao_bionica):
                    return 'Já estou na sua call e acompanhando suas trocas de canal.'
                try:
                    ok, message = await manager.conectar_canal_voz(target, visao_bionica=self.visao_bionica)
                except BaseException:
                    self.ativo = False
                    raise
                if not ok:
                    self.ativo = False
                    print(f'[Seguir call] {message}')
                return message
            return 'Você não está numa call em um servidor em comum. Peça para eu entrar quando estiver.'

    async def sair(self):
        async with self._lock:
            self.ativo = False
            manager = self.bot.voice_manager
            if not manager:
                return 'O modo call está indisponível.'
            for guild_id in list(manager._voice_clients):
                await manager.desconectar_canal_voz(guild_id)
            return 'Saí da call. Só volto a entrar quando você pedir.'

    async def on_voice_state_update(self, member, before, after):
        if not self.ativo or member.id != self.owner_id or before.channel == after.channel:
            return
        # Consulta o cache dentro do lock: trocas rápidas não deixam a Ayla
        # presa a um evento antigo enquanto a conexão anterior terminava.
        await self.sincronizar(getattr(after.channel, 'id', None))


def consultar_seguimento_call():
    return 'Posso entrar na call da dona usando entrar_na_call e escolher visao_bionica para ver a tela ou apenas ouvir. Depois acompanho suas trocas de canal até ela sair. Não entro automaticamente ao iniciar o bot.'


def _executar_pedido(entrar, visao_bionica=False):
    bot_instance = globals().get('bot')
    follower = getattr(bot_instance, '_seguir_call', None)
    loop = getattr(bot_instance, 'discord_loop', None)
    if not follower or not loop or not loop.is_running():
        return 'A conexão de voz com o Discord ainda não está pronta.'
    contexto = ayla_state.CONTEXTO_ATIVO.get()
    autor = getattr(contexto, 'author', None) or getattr(contexto, 'user', None)
    if (contexto is not None and getattr(contexto, 'origem', None) != 'Discord-Call'
            and getattr(autor, 'id', None) != follower.owner_id):
        return 'Somente a dona pode pedir para eu entrar ou sair da call.'
    try:
        if asyncio.get_running_loop() is loop:
            return 'A ferramenta de call deve ser executada pelo worker da conversa.'
    except RuntimeError:
        pass
    coroutine = follower.sincronizar(solicitado=True, visao_bionica=visao_bionica) if entrar else follower.sair()
    future = asyncio.run_coroutine_threadsafe(coroutine, loop)
    try:
        return future.result(timeout=60)
    except FutureTimeoutError:
        future.cancel()
        return 'A operação de voz demorou demais; não consegui confirmar a conclusão.'
    except Exception as exc:
        return f'Não consegui concluir a operação de voz: {exc}'


def entrar_na_call(visao_bionica: bool):
    return _executar_pedido(True, visao_bionica=visao_bionica)


def sair_da_call():
    return _executar_pedido(False)


def register(tools, declarations):
    tools['consultar_seguimento_call'] = consultar_seguimento_call
    declarations.append({
        'name': 'consultar_seguimento_call',
        'description': 'Explica a entrada na call com visão opcional e o acompanhamento durante a chamada.',
        'parameters': {'type': 'object', 'properties': {}},
    })
    for name, function, description in (
        ('entrar_na_call', entrar_na_call,
         'Entra na call atual da dona em qualquer servidor em comum. Escolha visao_bionica=true para ver a tela do computador da dona, ou false para apenas voz. Depois acompanha trocas de canal até ela sair.'),
        ('sair_da_call', sair_da_call,
         'Sai da call e desativa o acompanhamento. Use quando a dona pedir para sair da chamada; só entra novamente mediante novo pedido.'),
    ):
        tools[name] = function
        declarations.append({'name': name, 'description': description,
                             'parameters': ({'type': 'object', 'properties': {
                                 'visao_bionica': {'type': 'boolean', 'description':
                                     'Ver a tela do computador da dona durante a call?'}},
                                 'required': ['visao_bionica']} if name == 'entrar_na_call'
                                 else {'type': 'object', 'properties': {}})})
