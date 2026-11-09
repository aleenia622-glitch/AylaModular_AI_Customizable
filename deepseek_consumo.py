"""Gastos estimados DeepSeek da sessão e histórico persistente separado da Z.ai."""
import math
from pathlib import Path
from threading import RLock

from ayla_consumo import RegistroConsumo

_LOCK = RLock()
_TOTAL_SESSAO = 0.0
_REGISTRO = RegistroConsumo(
    Path(__file__).resolve().with_name('ayla_consumo_deepseek.json'),
    tipo='estimativa_deepseek',
)


def salvar_consumo_deepseek():
    """Snapshot idempotente: salvar novamente não duplica a sessão."""
    with _LOCK:
        _REGISTRO.salvar(_TOTAL_SESSAO)


def obter_gasto_total_sessao_deepseek():
    with _LOCK:
        return _TOTAL_SESSAO


def obter_gasto_total_acumulado_deepseek():
    with _LOCK:
        return _REGISTRO.total(_TOTAL_SESSAO)


def somar_gasto_deepseek(cost):
    if cost is None or not math.isfinite(cost) or cost < 0:
        return
    global _TOTAL_SESSAO
    with _LOCK:
        _TOTAL_SESSAO += cost
        try:
            _REGISTRO.salvar(_TOTAL_SESSAO)
        except Exception as exc:
            print(f'⚠️ Não foi possível salvar o consumo DeepSeek ({type(exc).__name__}); '
                  'valor mantido nesta sessão.')
