import sys
import os
from pathlib import Path

base_dir = Path(__file__).resolve().parents[2]
if str(base_dir) not in sys.path:
    sys.path.append(str(base_dir))
import ayla_state

if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

def modo_socializar(acao: str = "ativar", canal_id: str = None) -> str:
    """
    Ativa, desativa ou verifica o status do Modo Socializar da Ayla.
    No Modo Socializar, a Ayla lê as mensagens do chat temporariamente em lotes de 5 em 5
    sem precisar de gatilhos como /ayla ou @ayla, respondendo a quem quiser até ser fechado.
    """
    acao_clean = (acao or "ativar").strip().lower()
    
    # Tenta obter o canal ativo do contexto se canal_id não foi informado
    if not canal_id and hasattr(ayla_state, "CONTEXTO_ATIVO"):
        ctx = ayla_state.CONTEXTO_ATIVO.get()
        if ctx and hasattr(ctx, "channel") and ctx.channel:
            canal_id = str(ctx.channel.id)

    target_channel = canal_id or "GLOBAL"

    if acao_clean in ["ativar", "iniciar", "on", "ligar"]:
        res = ayla_state.ativar_modo_socializar(target_channel)
        return f"✨ {res}\n(Agora você pode conversar no chat! A cada 5 mensagens enviadas pela galera, a Ayla lerá o lote e responderá!)"

    elif acao_clean in ["desativar", "parar", "fechar", "off", "desligar"]:
        res = ayla_state.desativar_modo_socializar(target_channel if canal_id else None)
        return f"🛑 {res}"

    elif acao_clean in ["status", "ver", "checar"]:
        ativo = ayla_state.is_modo_socializar_ativo(target_channel)
        if ativo:
            return f"💬 O Modo Socializar está ATIVO no momento (Canal: {target_channel}). Lendo em lotes de 5 em 5."
        else:
            return "💬 O Modo Socializar está DESATIVADO no momento. A Ayla só responde com menções ou /ayla."

    else:
        return f"⚠️ Ação inválida '{acao}'. Use 'ativar', 'desativar' ou 'status'."

TOOL_MAP["modo_socializar"] = modo_socializar
FUNCTION_DECLARATIONS.append({
    "name": "modo_socializar",
    "description": "Ativa ou fecha o Modo Socializar temporário no chat. No Modo Socializar, a Ayla lê o chat sem menções ou /ayla, em lotes de 5 em 5 mensagens, respondendo livremente até você mandar fechar.",
    "parameters": {
        "type": "object",
        "properties": {
            "acao": {
                "type": "string",
                "description": "Ação a ser executada: 'ativar' (ou 'iniciar'), 'desativar' (ou 'fechar'), ou 'status'."
            },
            "canal_id": {
                "type": "string",
                "description": "Opcional: ID do canal do Discord onde ativar/desativar o modo."
            }
        },
        "required": ["acao"]
    }
})
