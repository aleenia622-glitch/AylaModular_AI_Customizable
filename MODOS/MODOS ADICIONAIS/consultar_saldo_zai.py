"""Consulta o saldo pré-pago da API Z.AI."""

from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation
from typing import Any

import requests


ENDPOINTS_SALDO_ZAI = (
    "https://api.z.ai/api/biz/account/query-customer-account-report",
    "https://api.z.ai/api/paas/v4/balance",
)


def _obter_chaves_zai() -> list[str]:
    """Obtém as chaves já carregadas pela Ayla, sem expô-las em logs ou respostas."""
    chaves = []

    for chave in globals().get("ZAI_API_KEYS", []) or []:
        if isinstance(chave, str) and chave.strip():
            chaves.append(chave.strip())

    if not chaves:
        nomes = [f"ZAI_API_KEY_{i}" for i in range(1, 7)] + ["ZAI_API_KEY"]
        for nome in nomes:
            chave = os.environ.get(nome, "").strip()
            if chave:
                chaves.append(chave)

    return list(dict.fromkeys(chaves))


def _numero(valor: Any) -> Decimal | None:
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = Decimal(str(valor).replace(",", "."))
        return numero if numero.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def _formatar_usd(valor: Any) -> str | None:
    numero = _numero(valor)
    if numero is None:
        return None
    return f"US$ {numero:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _localizar_relatorio(payload: Any) -> dict[str, Any] | None:
    """Localiza o objeto financeiro mesmo se o envelope da API mudar levemente."""
    campos = {
        "balance", "availableBalance", "rechargeAmount", "giveAmount",
        "totalSpendAmount", "frozenBalance",
    }
    fila = [payload]
    while fila:
        atual = fila.pop(0)
        if isinstance(atual, dict):
            if campos.intersection(atual):
                return atual
            fila.extend(atual.values())
        elif isinstance(atual, list):
            fila.extend(atual)
    return None


def _mensagem_erro_api(payload: Any) -> str:
    if not isinstance(payload, dict):
        return "resposta inesperada"
    erro = payload.get("error")
    erro_msg = erro.get("message") if isinstance(erro, dict) else erro
    return str(
        payload.get("msg")
        or payload.get("message")
        or erro_msg
        or "resposta recusada pela Z.AI"
    )


def consultar_relatorio_zai(chave_numero: int = 1) -> tuple[dict, int, int]:
    """Retorna os valores originais, sem arredondamento nem formatação de moeda."""
    chaves = _obter_chaves_zai()
    if not chaves:
        raise ValueError("Nenhuma chave Z.AI foi encontrada nas configurações da Ayla.")

    try:
        indice = int(chave_numero) - 1
    except (TypeError, ValueError):
        indice = 0

    if indice < 0 or indice >= len(chaves):
        raise ValueError(f"A chave {chave_numero} não existe. Há {len(chaves)} chave(s) Z.AI configurada(s).")

    chave = chaves[indice]
    ultimo_erro = "endpoint indisponível"

    for endpoint in ENDPOINTS_SALDO_ZAI:
        for autorizacao in (f"Bearer {chave}", chave):
            try:
                resposta = requests.get(
                    endpoint,
                    headers={
                        "Authorization": autorizacao,
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "Accept-Encoding": "identity",
                    },
                    timeout=15,
                )

                try:
                    payload = resposta.json()
                except ValueError:
                    ultimo_erro = f"HTTP {resposta.status_code} com resposta inválida"
                    break

                relatorio = _localizar_relatorio(payload)
                if resposta.ok and relatorio:
                    if any(_numero(relatorio.get(campo)) is not None for campo in ("availableBalance", "balance")):
                        return relatorio, indice + 1, len(chaves)
                    ultimo_erro = "resposta sem saldo monetário válido"
                    break

                ultimo_erro = _mensagem_erro_api(payload)
                if resposta.status_code not in (401, 403):
                    break
            except requests.Timeout:
                ultimo_erro = "tempo limite excedido"
                break
            except requests.RequestException as exc:
                ultimo_erro = f"falha de conexão ({type(exc).__name__})"
                break

    raise RuntimeError(
        "Não consegui consultar o saldo Pay-as-you-go da Z.AI. "
        f"Motivo: {ultimo_erro}. O endpoint financeiro não é oficial e pode ter mudado."
    )


def consultar_saldo_disponivel_zai(chave_numero: int = 1) -> Decimal:
    relatorio, _, _ = consultar_relatorio_zai(chave_numero)
    disponivel = _numero(relatorio.get("availableBalance"))
    return disponivel if disponivel is not None else _numero(relatorio.get("balance"))


def consultar_saldo_zai(chave_numero: int = 1) -> str:
    """Consulta e apresenta o saldo monetário Pay-as-you-go da Z.AI."""
    try:
        relatorio, numero, quantidade = consultar_relatorio_zai(chave_numero)
    except (ValueError, RuntimeError) as exc:
        return f"⚠️ {exc}"
    saldo = _formatar_usd(relatorio.get("balance"))
    principal = _formatar_usd(relatorio.get("availableBalance")) or saldo
    linhas = [f"💰 **Saldo Pay-as-you-go da Z.AI:** {principal}"]
    if saldo and saldo != principal:
        linhas.append(f"• Saldo total: {saldo}")
    for campo, titulo in (("frozenBalance", "Saldo congelado"), ("rechargeAmount", "Total recarregado"),
                           ("giveAmount", "Créditos promocionais"), ("totalSpendAmount", "Consumo acumulado")):
        valor = _formatar_usd(relatorio.get(campo))
        if valor:
            linhas.append(f"• {titulo}: {valor}")
    linhas.append(f"• Chave consultada: {numero} de {quantidade}")
    return "\n".join(linhas)


if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

TOOL_MAP["consultar_saldo_zai"] = consultar_saldo_zai
FUNCTION_DECLARATIONS.append({
    "name": "consultar_saldo_zai",
    "description": (
        "Consulta o saldo financeiro pré-pago Pay-as-you-go da conta Z.AI. "
        "Use quando o usuário perguntar pelo saldo, créditos ou dinheiro restante da API Z.AI; "
        "não consulta a cota do Coding Plan."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "chave_numero": {
                "type": "integer",
                "description": "Número da chave Z.AI configurada que deve ser consultada. O padrão é 1.",
                "minimum": 1,
            }
        },
    },
})
