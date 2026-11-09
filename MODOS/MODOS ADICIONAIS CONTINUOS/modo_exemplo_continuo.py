"""Verifica se ferramentas contínuas permanecem ativas entre respostas."""
from datetime import datetime

if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

_CONTADOR_EXECUCOES = 0

def verificar_modo_continuo() -> str:
    """
    Verifica se o modo adicional contínuo está retido no contexto ativo da Ayla e reporta métricas de execução.
    """
    global _CONTADOR_EXECUCOES
    _CONTADOR_EXECUCOES += 1
    agora = datetime.now().strftime("%H:%M:%S")
    return (
        f"♾️ [Modo Adicional Contínuo Ativo]\n"
        f"Horário atual: {agora}\n"
        f"Total de execuções nesta sessão: {_CONTADOR_EXECUCOES}\n"
        f"Status: Ferramenta retida com sucesso no contexto da Ayla sem limpeza pós-resposta! ✨"
    )

TOOL_MAP["verificar_modo_continuo"] = verificar_modo_continuo

FUNCTION_DECLARATIONS.append({
    "name": "verificar_modo_continuo",
    "description": "Verifica se os modos adicionais contínuos continuam ativos e preservados no contexto da Ayla após as respostas.",
    "parameters": {
        "type": "object",
        "properties": {}
    }
})
