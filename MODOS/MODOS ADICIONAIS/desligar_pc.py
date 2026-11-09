"""Desliga o computador imediatamente ou após um prazo, mediante confirmação."""
import math
from ayla_platform import IS_WINDOWS, run_command
CONFIRMACAO_DESLIGAR = "SIM, tenho certeza"

def desligar_pc(tempo_segundos: int = 0, confirmar: str = "") -> str:
    try:
        if (confirmar or "").strip() != CONFIRMACAO_DESLIGAR:
            return (
                "⚠️ Desligar o computador é uma ação sensível. "
                f"Para continuar, chame a ferramenta com confirmar='{CONFIRMACAO_DESLIGAR}'."
            )
        seconds = max(0, int(tempo_segundos))
        if IS_WINDOWS:
            run_command(['shutdown', '/s', '/t', str(seconds)])
        elif seconds == 0:
            run_command(['systemctl', 'poweroff'])
        else:
            minutes = math.ceil(seconds / 60)
            run_command(['shutdown', '-h', f'+{minutes}'])
            return f'✅ Desligamento agendado para {minutes} minuto(s) (resolução do shutdown no Linux).'
        return f'✅ Comando de desligamento aceito; espera: {seconds}s.' 
    except Exception as e: return f"Erro: {e}"

TOOL_MAP["desligar_pc"] = desligar_pc
FUNCTION_DECLARATIONS.append({
    "name": "desligar_pc",
    "description": "Desliga o computador. Ação sensível: só executa com confirmação literal.",
    "parameters": {
        "type": "object",
        "properties": {
            "tempo_segundos": {"type": "integer",
                    "description": "Tempo de espera em segundos antes de desligar o PC (padrão: 0 para imediato)."},
            "confirmar": {
                "type": "string",
                "description": "Obrigatório para executar: SIM, tenho certeza"
            }
        },
        "required": ["confirmar"]
    }
})
