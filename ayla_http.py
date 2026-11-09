"""Limites do transporte persistente, sem alterar timeouts de requisição."""
import httpx


def connection_limits():
    # Mantém a capacidade padrão do HTTPX e tolera pausas entre mensagens.
    # O servidor ainda pode encerrar uma conexão antes deste prazo.
    return httpx.Limits(max_connections=100, max_keepalive_connections=20,
                        keepalive_expiry=60.0)
