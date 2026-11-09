"""Gerencia ciclos Pomodoro e lembretes de água, postura e pausas."""
import time
import threading
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

# Estado global da sessão Pomodoro
_POMODORO_SESSION = {
    "ativo": False,
    "foco_minutos": 25,
    "descanso_minutos": 5,
    "ciclos_totais": 4,
    "ciclo_atual": 1,
    "estado": "parado",  # 'foco', 'descanso', 'parado'
    "inicio_fase": 0.0,
    "duracao_fase_segundos": 0,
    "tarefa": "Produtividade",
    "thread": None,
    "canal_id": None,
    "guild_id": None,
    "cancelar": False,
}

_LEMBRETE_AGUA = {
    "ativo": False,
    "intervalo_minutos": 45,
    "proximo_aviso": 0.0,
    "thread": None,
    "cancelar": False,
    "canal_id": None,
}

_LOCK = threading.Lock()


def _notificar_discord(mensagem: str, canal_id=None):
    """Envia notificação no Discord de forma assíncrona se o bot estiver disponível."""
    bot = globals().get("bot")
    if not bot:
        return
    discord_loop = getattr(bot, "discord_loop", None)
    if not discord_loop or not discord_loop.is_running():
        return

    async def _send():
        target_channel = None
        if canal_id:
            target_channel = bot.get_channel(int(canal_id))
            if not target_channel:
                try:
                    target_channel = await bot.fetch_channel(int(canal_id))
                except Exception:
                    target_channel = None

        if not target_channel and getattr(bot, "last_active_channel_id", None):
            try:
                target_channel = bot.get_channel(int(bot.last_active_channel_id))
            except Exception:
                pass

        if target_channel and hasattr(target_channel, "send"):
            try:
                await target_channel.send(mensagem)
            except Exception as e:
                print(f"⚠️ [Pomodoro] Erro ao enviar mensagem no canal: {e}")

    asyncio.run_coroutine_threadsafe(_send(), discord_loop)


def _executar_ciclo_pomodoro_impl():
    """Worker de execução do ciclo Pomodoro."""
    while True:
        with _LOCK:
            if _POMODORO_SESSION.get("cancelar", False) or not _POMODORO_SESSION.get("ativo", False):
                _POMODORO_SESSION["ativo"] = False
                _POMODORO_SESSION["estado"] = "parado"
                break
            ciclo = _POMODORO_SESSION["ciclo_atual"]
            totais = _POMODORO_SESSION["ciclos_totais"]
            foco_s = _POMODORO_SESSION["foco_minutos"] * 60
            descanso_s = _POMODORO_SESSION["descanso_minutos"] * 60
            tarefa = _POMODORO_SESSION["tarefa"]
            canal_id = _POMODORO_SESSION["canal_id"]

        # Fase de Foco
        with _LOCK:
            _POMODORO_SESSION["estado"] = "foco"
            _POMODORO_SESSION["inicio_fase"] = time.time()
            _POMODORO_SESSION["duracao_fase_segundos"] = foco_s

        _notificar_discord(
            f"🍅 **Pomodoro Iniciado — Ciclo {ciclo}/{totais}!**\n"
            f"🎯 Tarefa: **{tarefa}**\n"
            f"⏱️ Foco total pelos próximos **{_POMODORO_SESSION['foco_minutos']} minutos**! Mantenha a concentração, usuario/humano! 🩵",
            canal_id
        )

        # Espera foco com verificação de cancelamento
        tempo_decorrido = 0
        while tempo_decorrido < foco_s:
            time.sleep(2)
            tempo_decorrido += 2
            with _LOCK:
                if _POMODORO_SESSION.get("cancelar", False):
                    _POMODORO_SESSION["ativo"] = False
                    _POMODORO_SESSION["estado"] = "parado"
                    return

        # Fim do foco -> Descanso
        if ciclo >= totais:
            _notificar_discord(
                f"🎉 **Parabéns! Todos os {totais} ciclos de Pomodoro foram concluídos com sucesso!**\n"
                f"Você foi incrível e farmou muita aura de foco hoje! Agora tire um belo descanso prolongado! 🩵✨",
                canal_id
            )
            with _LOCK:
                _POMODORO_SESSION["ativo"] = False
                _POMODORO_SESSION["estado"] = "parado"
            break

        with _LOCK:
            _POMODORO_SESSION["estado"] = "descanso"
            _POMODORO_SESSION["inicio_fase"] = time.time()
            _POMODORO_SESSION["duracao_fase_segundos"] = descanso_s

        _notificar_discord(
            f"☕ **Hora do Descanso — Ciclo {ciclo}/{totais} Finalizado!**\n"
            f"🧘 Descanse a vista, beba água e alongue as costas por **{_POMODORO_SESSION['descanso_minutos']} minutos**! ✨",
            canal_id
        )

        tempo_decorrido = 0
        while tempo_decorrido < descanso_s:
            time.sleep(2)
            tempo_decorrido += 2
            with _LOCK:
                if _POMODORO_SESSION.get("cancelar", False):
                    _POMODORO_SESSION["ativo"] = False
                    _POMODORO_SESSION["estado"] = "parado"
                    return

        with _LOCK:
            _POMODORO_SESSION["ciclo_atual"] += 1


def _executar_ciclo_pomodoro():
    try:
        _executar_ciclo_pomodoro_impl()
    finally:
        with _LOCK:
            _POMODORO_SESSION["ativo"] = False
            _POMODORO_SESSION["estado"] = "parado"
        if "ayla_state" in globals():
            ayla_state.finalizar_tarefa("pomodoro_ativo", "cancelada" if _POMODORO_SESSION["cancelar"] else "concluida")


def shutdown():
    cancelar_pomodoro()
    with _LOCK:
        _LEMBRETE_AGUA["cancelar"] = True
        _LEMBRETE_AGUA["ativo"] = False


def iniciar_pomodoro(foco_minutos: int = 25, descanso_minutos: int = 5, ciclos: int = 4, tarefa: str = "Produtividade / Código") -> str:
    """Inicia um temporizador Pomodoro com fases de foco e descanso automáticas."""
    foco = max(1, min(120, int(foco_minutos or 25)))
    descanso = max(1, min(60, int(descanso_minutos or 5)))
    ciclos_qtd = max(1, min(12, int(ciclos or 4)))
    tarefa_str = str(tarefa or "Produtividade").strip()

    canal_id = None
    if "ayla_state" in globals():
        ctx = globals()["ayla_state"].CONTEXTO_ATIVO.get()
        if ctx and hasattr(ctx, "channel") and ctx.channel:
            canal_id = ctx.channel.id

    with _LOCK:
        if _POMODORO_SESSION.get("ativo", False) or (_POMODORO_SESSION.get("thread") and _POMODORO_SESSION["thread"].is_alive()):
            return f"⚠️ Já existe um Pomodoro ativo no momento ({_POMODORO_SESSION['estado']} - ciclo {_POMODORO_SESSION['ciclo_atual']}/{_POMODORO_SESSION['ciclos_totais']}). Use `cancelar_pomodoro` se desejar reiniciar."

        _POMODORO_SESSION["ativo"] = True
        _POMODORO_SESSION["foco_minutos"] = foco
        _POMODORO_SESSION["descanso_minutos"] = descanso
        _POMODORO_SESSION["ciclos_totais"] = ciclos_qtd
        _POMODORO_SESSION["ciclo_atual"] = 1
        _POMODORO_SESSION["tarefa"] = tarefa_str
        _POMODORO_SESSION["canal_id"] = canal_id
        _POMODORO_SESSION["cancelar"] = False

        t = threading.Thread(target=_executar_ciclo_pomodoro, daemon=True, name="PomodoroWorker")
        _POMODORO_SESSION["thread"] = t

    if "ayla_state" in globals():
        globals()["ayla_state"].adicionar_tarefa(
            "pomodoro_ativo",
            f"Pomodoro: {ciclos_qtd}x ({foco}min foco / {descanso}min descanso) - {tarefa_str}",
            origem="Discord"
        )

    t.start()

    return (
        f"🍅 **Ciclo Pomodoro Iniciado com Sucesso!**\n"
        f"• 🎯 Tarefa: `{tarefa_str}`\n"
        f"• ⏱️ Foco: `{foco} min` | Descanso: `{descanso} min`\n"
        f"• 🔁 Total de Ciclos: `{ciclos_qtd}`\n"
        f"Vou te avisar aqui no chat quando cada fase começar e terminar, nanodaze! 🩵"
    )


def status_pomodoro() -> str:
    """Consulta o status atual do ciclo Pomodoro."""
    with _LOCK:
        if not _POMODORO_SESSION.get("ativo", False):
            return "🍅 Nenhum ciclo Pomodoro está ativo no momento. Use `iniciar_pomodoro` para começar!"

        estado = _POMODORO_SESSION["estado"].upper()
        ciclo = _POMODORO_SESSION["ciclo_atual"]
        totais = _POMODORO_SESSION["ciclos_totais"]
        tarefa = _POMODORO_SESSION["tarefa"]
        inicio = _POMODORO_SESSION["inicio_fase"]
        duracao = _POMODORO_SESSION["duracao_fase_segundos"]
        decorrido = int(time.time() - inicio) if inicio > 0 else 0
        restante = max(0, duracao - decorrido)
        restante_min = restante // 60
        restante_seg = restante % 60

    return (
        f"📊 **Status do Pomodoro Atual:**\n"
        f"• 📌 Fase: **{estado}** ({ciclo}/{totais})\n"
        f"• 🎯 Tarefa: `{tarefa}`\n"
        f"• ⏳ Tempo restante na fase: `{restante_min:02d}:{restante_seg:02d}`\n"
        f"• ⚙️ Configuração: `{_POMODORO_SESSION['foco_minutos']}m foco` / `{_POMODORO_SESSION['descanso_minutos']}m descanso`"
    )


def cancelar_pomodoro() -> str:
    """Cancela e encerra a sessão de Pomodoro ativa."""
    with _LOCK:
        if not _POMODORO_SESSION.get("ativo", False):
            return "🍅 Não há nenhum Pomodoro em andamento para cancelar."
        _POMODORO_SESSION["cancelar"] = True
        _POMODORO_SESSION["ativo"] = False
        _POMODORO_SESSION["estado"] = "parado"

    if "ayla_state" in globals():
        globals()["ayla_state"].atualizar_tarefa("pomodoro_ativo", status="cancelando")

    return "🛑 **Pomodoro cancelado com sucesso!** Pode descansar ou reiniciar quando quiser."


def lembrete_agua_postura(intervalo_minutos: int = 45) -> str:
    """Configura um lembrete carinhoso recorrente para beber água e corrigir a postura."""
    minutos = max(10, min(180, int(intervalo_minutos or 45)))
    
    canal_id = None
    if "ayla_state" in globals():
        ctx = globals()["ayla_state"].CONTEXTO_ATIVO.get()
        if ctx and hasattr(ctx, "channel") and ctx.channel:
            canal_id = ctx.channel.id

    with _LOCK:
        _LEMBRETE_AGUA["ativo"] = True
        _LEMBRETE_AGUA["intervalo_minutos"] = minutos
        _LEMBRETE_AGUA["proximo_aviso"] = time.time() + (minutos * 60)
        _LEMBRETE_AGUA["canal_id"] = canal_id
        _LEMBRETE_AGUA["cancelar"] = False

        if not _LEMBRETE_AGUA["thread"] or not _LEMBRETE_AGUA["thread"].is_alive():
            def _worker():
                mensagens_fofas = [
                    "💧 **Lembrete de Hidratação & Postura da Ayla!**\nBeba um gole d'água e ajeite essa postura de neandertal curvado na cadeira, usuario/humano! 🩵",
                    "🌊 **Hora do Gole d'Água!**\nHidrate esse cérebro pra não virar um bebedor de água de ar-condicionado! Aproveita e estica os braços! ✨",
                    "🥤 **Pausa Rápida de Saúde!**\nOlhos longe da tela por 20 segundos, respira fundo e toma uma aguinha gelada! 🩵✨",
                ]
                import random
                while True:
                    with _LOCK:
                        if _LEMBRETE_AGUA.get("cancelar", False) or not _LEMBRETE_AGUA.get("ativo", False):
                            break
                        proximo = _LEMBRETE_AGUA["proximo_aviso"]
                        cid = _LEMBRETE_AGUA["canal_id"]
                        intervalo_s = _LEMBRETE_AGUA["intervalo_minutos"] * 60

                    if time.time() >= proximo:
                        msg = random.choice(mensagens_fofas)
                        _notificar_discord(msg, cid)
                        with _LOCK:
                            _LEMBRETE_AGUA["proximo_aviso"] = time.time() + intervalo_s

                    time.sleep(15)

            t = threading.Thread(target=_worker, daemon=True, name="AguaPosturaWorker")
            _LEMBRETE_AGUA["thread"] = t
            t.start()

    return f"💧 **Lembrete de Água & Postura ativado!** Vou te lembrar a cada **{minutos} minutos** de se hidratar e ajeitar as costas! 🩵"


def register(tool_map: dict, function_declarations: list):
    tool_map["iniciar_pomodoro"] = iniciar_pomodoro
    tool_map["status_pomodoro"] = status_pomodoro
    tool_map["cancelar_pomodoro"] = cancelar_pomodoro
    tool_map["lembrete_agua_postura"] = lembrete_agua_postura

    function_declarations.append({
        "name": "iniciar_pomodoro",
        "description": "Inicia uma sessão de Pomodoro com ciclos de foco e descanso e avisos no Discord.",
        "parameters": {
            "type": "object",
            "properties": {
                "foco_minutos": {"type": "integer", "description": "Duração da fase de foco em minutos (padrão: 25)."},
                "descanso_minutos": {"type": "integer", "description": "Duração da pausa de descanso em minutos (padrão: 5)."},
                "ciclos": {"type": "integer", "description": "Quantidade total de ciclos (padrão: 4)."},
                "tarefa": {"type": "string", "description": "Nome da tarefa ou atividade de foco."}
            },
            "required": []
        }
    })

    function_declarations.append({
        "name": "status_pomodoro",
        "description": "Consulta o status e tempo restante da sessão de Pomodoro ativa.",
        "parameters": {"type": "object", "properties": {}}
    })

    function_declarations.append({
        "name": "cancelar_pomodoro",
        "description": "Cancela e encerra a sessão de Pomodoro ativa.",
        "parameters": {"type": "object", "properties": {}}
    })

    function_declarations.append({
        "name": "lembrete_agua_postura",
        "description": "Ativa lembretes periódicos para beber água e arrumar a postura.",
        "parameters": {
            "type": "object",
            "properties": {
                "intervalo_minutos": {"type": "integer", "description": "Intervalo em minutos entre cada lembrete (padrão: 45)."}
            }
        }
    })


if "TOOL_MAP" in globals() and "FUNCTION_DECLARATIONS" in globals():
    register(TOOL_MAP, FUNCTION_DECLARATIONS)
