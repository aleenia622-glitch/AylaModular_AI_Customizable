import contextvars
import threading
import time
import collections
from dataclasses import dataclass, field

# Variáveis de contexto para manter o estado thread-safe por requisição/interação
CONTEXTO_ATIVO = contextvars.ContextVar('CONTEXTO_ATIVO', default=None)
ULTIMA_IMAGEM_GERADA = contextvars.ContextVar('ULTIMA_IMAGEM_GERADA', default=None)
ULTIMO_ANEXO_IMAGEM = contextvars.ContextVar('ULTIMO_ANEXO_IMAGEM', default=None)
ULTIMO_ANEXO_VIDEO = contextvars.ContextVar('ULTIMO_ANEXO_VIDEO', default=None)
ULTIMO_ANEXO_AUDIO = contextvars.ContextVar('ULTIMO_ANEXO_AUDIO', default=None)
ULTIMO_ARQUIVO_MIDIA = contextvars.ContextVar('ULTIMO_ARQUIVO_MIDIA', default=None)
ULTIMAS_IMAGENS_MODULO = contextvars.ContextVar('ULTIMAS_IMAGENS_MODULO', default=None)
BOT_LAUNCH_ERROR = contextvars.ContextVar('BOT_LAUNCH_ERROR', default=None)
TAREFA_ATUAL = contextvars.ContextVar('TAREFA_ATUAL', default=None)


# ══════════════════════════════════════════════════════════
#  SISTEMA DE TAREFAS COM PRIORIDADE (U15)
# ══════════════════════════════════════════════════════════

# Prioridades: menor número = maior prioridade
PRIORIDADES = {
    "DM-Dona": 0,
    "GUI": 1,
    "Terminal": 1,
    "DM": 2,
    "Discord": 3,
}
@dataclass(order=True)
class Tarefa:
    prioridade: int
    timestamp: float = field(compare=False)
    task_id: str = field(compare=False)
    descricao: str = field(compare=False)
    origem: str = field(compare=False, default="Discord")
    status: str = field(compare=False, default="executando")
    sessao: str = field(compare=False, default="")
    ferramenta: str = field(compare=False, default="")
    titulo: str = field(compare=False, default="")

TAREFAS_ATIVAS = {}  # task_id -> Tarefa (mantém compatibilidade de lookup)
TAREFAS_LOCK = threading.Lock()
TAREFAS_RECENTES = collections.deque(maxlen=30)


def adicionar_tarefa(task_id: str, descricao: str, origem: str = "Discord", status: str = "executando", sessao: str = ""):
    with TAREFAS_LOCK:
        prioridade = PRIORIDADES.get(origem, 3)
        tarefa = Tarefa(
            prioridade=prioridade,
            timestamp=time.time(),
            task_id=task_id,
            descricao=descricao,
            origem=origem,
            status=status,
            sessao=sessao,
            titulo=descricao,
        )
        TAREFAS_ATIVAS[task_id] = tarefa

def remover_tarefa(task_id: str):
    with TAREFAS_LOCK:
        TAREFAS_ATIVAS.pop(task_id, None)

def listar_tarefas() -> list:
    """Retorna lista de descrições (compatível com código legado)."""
    with TAREFAS_LOCK:
        return [t.descricao for t in sorted(TAREFAS_ATIVAS.values())]

def listar_tarefas_detalhadas() -> list[dict]:
    """Retorna tarefas com metadados completos, ordenadas por prioridade."""
    with TAREFAS_LOCK:
        return [
            {
                "task_id": t.task_id,
                "descricao": t.descricao,
                "prioridade": t.prioridade,
                "origem": t.origem,
                "status": getattr(t, "status", "executando"),
                "timestamp": t.timestamp,
                "sessao": t.sessao,
                "ferramenta": t.ferramenta,
                "titulo": t.titulo,
            }
            for t in sorted(TAREFAS_ATIVAS.values())
        ]


def atualizar_tarefa(task_id, descricao=None, status=None, ferramenta=None):
    with TAREFAS_LOCK:
        tarefa = TAREFAS_ATIVAS.get(task_id)
        if tarefa:
            if descricao is not None: tarefa.descricao = descricao
            if status is not None: tarefa.status = status
            if ferramenta is not None: tarefa.ferramenta = ferramenta


def finalizar_tarefa(task_id, status="concluida"):
    with TAREFAS_LOCK:
        tarefa = TAREFAS_ATIVAS.pop(task_id, None)
        if tarefa:
            TAREFAS_RECENTES.append({"task_id":task_id,"descricao":tarefa.titulo or tarefa.descricao,
                                    "origem":tarefa.origem,"status":status,"timestamp":time.time(),
                                    "sessao":tarefa.sessao})


def listar_tarefas_recentes():
    with TAREFAS_LOCK:
        return [dict(t) for t in reversed(TAREFAS_RECENTES)]


def contexto_tarefas(sessao, incluir_todas=False):
    tarefas = listar_tarefas_detalhadas()
    tarefas = [t for t in tarefas if t['task_id'] != TAREFA_ATUAL.get()
               and (incluir_todas or t['sessao']==sessao)]
    if not tarefas: return ""
    return "[Estado atual de outras tarefas; continuam em paralelo]\n" + "\n".join(
        f"• {t['titulo']} — {t['descricao']} ({t['status']}, {t['origem']})" for t in tarefas[:15])


def resultado_sucesso(value):
    from ayla_verificacao import retorno_falhou
    return not retorno_falhou(value)


def __getattr__(name: str):
    if name == "LISTA_TAREFAS":
        return listar_tarefas_detalhadas()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# ══════════════════════════════════════════════════════════
#  MÉTRICAS DE USO DE FERRAMENTAS (U14)
# ══════════════════════════════════════════════════════════

METRICAS_FERRAMENTAS = {}  # nome_ferramenta -> {chamadas, erros, tempo_total_ms, ultimo_uso}
METRICAS_LOCK = threading.Lock()

def registrar_metrica(nome_ferramenta: str, duracao_ms: float, sucesso: bool):
    """Registra uma chamada de ferramenta nas métricas."""
    with METRICAS_LOCK:
        if nome_ferramenta not in METRICAS_FERRAMENTAS:
            METRICAS_FERRAMENTAS[nome_ferramenta] = {
                "chamadas": 0,
                "erros": 0,
                "tempo_total_ms": 0.0,
                "ultimo_uso": 0.0,
            }
        m = METRICAS_FERRAMENTAS[nome_ferramenta]
        m["chamadas"] += 1
        if not sucesso:
            m["erros"] += 1
        m["tempo_total_ms"] += duracao_ms
        m["ultimo_uso"] = time.time()

def obter_metricas() -> dict:
    """Retorna uma cópia das métricas de todas as ferramentas."""
    with METRICAS_LOCK:
        resultado = {}
        for nome, m in METRICAS_FERRAMENTAS.items():
            chamadas = m["chamadas"]
            resultado[nome] = {
                "chamadas": chamadas,
                "erros": m["erros"],
                "latencia_media_ms": round(m["tempo_total_ms"] / chamadas, 1) if chamadas > 0 else 0,
                "taxa_erro": round((m["erros"] / chamadas) * 100, 1) if chamadas > 0 else 0,
                "ultimo_uso": m["ultimo_uso"],
            }
        return resultado

