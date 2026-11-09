"""Montagem do prompt da Ayla com identidade, contexto e regras separados."""
from functools import lru_cache

from ayla_regras import (
    REGRAS_FERRAMENTAS, REGRAS_MIDIAS, REGRAS_MEMORIA_E_COMPORTAMENTO,
    REGRA_HONESTIDADE,
)

IDENTIDADE_E_PERSONALIDADE = ""

CONTEXTO_usuario_E_MIDIAS = ""

DIRETRIZES_PESSOAIS = ""

def montar_prompt_base():
    """Preserva texto e ordem anteriores, acrescentando a regra de honestidade."""
    return (IDENTIDADE_E_PERSONALIDADE + REGRAS_FERRAMENTAS
            + CONTEXTO_usuario_E_MIDIAS + REGRAS_MIDIAS
            + REGRAS_MEMORIA_E_COMPORTAMENTO + DIRETRIZES_PESSOAIS
            + REGRA_HONESTIDADE)


@lru_cache(maxsize=16)
def compose_system_prompt(base, verification, authorship):
    return base + verification + authorship
