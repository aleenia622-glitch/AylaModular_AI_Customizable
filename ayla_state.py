import contextvars
import threading

# Variáveis de contexto para manter o estado thread-safe por requisição/interação
CONTEXTO_ATIVO = contextvars.ContextVar('CONTEXTO_ATIVO', default=None)
ULTIMA_IMAGEM_GERADA = contextvars.ContextVar('ULTIMA_IMAGEM_GERADA', default=None)
ULTIMO_ANEXO_IMAGEM = contextvars.ContextVar('ULTIMO_ANEXO_IMAGEM', default=None)
ULTIMO_ANEXO_VIDEO = contextvars.ContextVar('ULTIMO_ANEXO_VIDEO', default=None)
ULTIMAS_IMAGENS_MODULO = contextvars.ContextVar('ULTIMAS_IMAGENS_MODULO', default=None)
BOT_LAUNCH_ERROR = contextvars.ContextVar('BOT_LAUNCH_ERROR', default=None)

# Dicionário global para rastrear as tarefas ativas da Ayla e um lock para acessá-lo
TAREFAS_ATIVAS = {}
TAREFAS_LOCK = threading.Lock()

# Estado Global do Modo Socializar (Chat Livre em Lotes de 5 em 5)
MODO_SOCIALIZAR_CANAIS = set()
MODO_SOCIALIZAR_BUFFERS = {}
MODO_SOCIALIZAR_LOCK = threading.Lock()

def adicionar_tarefa(task_id: str, descricao: str):
    with TAREFAS_LOCK:
        TAREFAS_ATIVAS[task_id] = descricao

def remover_tarefa(task_id: str):
    with TAREFAS_LOCK:
        TAREFAS_ATIVAS.pop(task_id, None)

def listar_tarefas() -> list:
    with TAREFAS_LOCK:
        return list(TAREFAS_ATIVAS.values())

def ativar_modo_socializar(channel_id: int | str = "GLOBAL") -> str:
    key = str(channel_id) if channel_id else "GLOBAL"
    with MODO_SOCIALIZAR_LOCK:
        MODO_SOCIALIZAR_CANAIS.add(key)
        if key not in MODO_SOCIALIZAR_BUFFERS:
            MODO_SOCIALIZAR_BUFFERS[key] = []
    return f"💬 Modo Socializar ATIVADO no canal {key}! Lendo mensagens em lotes de 5 em 5 até você fechar."

def desativar_modo_socializar(channel_id: int | str = None) -> str:
    with MODO_SOCIALIZAR_LOCK:
        if channel_id:
            key = str(channel_id)
            MODO_SOCIALIZAR_CANAIS.discard(key)
            MODO_SOCIALIZAR_BUFFERS.pop(key, None)
        else:
            MODO_SOCIALIZAR_CANAIS.clear()
            MODO_SOCIALIZAR_BUFFERS.clear()
    return "🛑 Modo Socializar FOI FECHADO/DESATIVADO! Ayla voltou ao modo normal."

def is_modo_socializar_ativo(channel_id: int | str = None) -> bool:
    with MODO_SOCIALIZAR_LOCK:
        if not MODO_SOCIALIZAR_CANAIS:
            return False
        if channel_id is None:
            return len(MODO_SOCIALIZAR_CANAIS) > 0
        key = str(channel_id)
        return (key in MODO_SOCIALIZAR_CANAIS) or ("GLOBAL" in MODO_SOCIALIZAR_CANAIS)

def adicionar_mensagem_socializar(channel_id: int | str, msg_info: dict) -> list | None:
    key = str(channel_id)
    with MODO_SOCIALIZAR_LOCK:
        if key not in MODO_SOCIALIZAR_BUFFERS:
            MODO_SOCIALIZAR_BUFFERS[key] = []
        MODO_SOCIALIZAR_BUFFERS[key].append(msg_info)
        if len(MODO_SOCIALIZAR_BUFFERS[key]) >= 5:
            lote = MODO_SOCIALIZAR_BUFFERS[key][:5]
            MODO_SOCIALIZAR_BUFFERS[key] = MODO_SOCIALIZAR_BUFFERS[key][5:]
            return lote
    return None

