CONFIRMACAO_DESLIGAR = "SIM, tenho certeza"

def desligar_pc(tempo_segundos: int = 0, confirmar: str = "") -> str:
    try:
        if (confirmar or "").strip() != CONFIRMACAO_DESLIGAR:
            return (
                "⚠️ Desligar o computador é uma ação sensível. "
                f"Para continuar, chame a ferramenta com confirmar='{CONFIRMACAO_DESLIGAR}'."
            )
        subprocess.run(["shutdown", "/s", "/t", str(tempo_segundos) if tempo_segundos > 0 else "0"])
        return f"✅ Agendado para desligar em {tempo_segundos}s."
    except Exception as e: return f"Erro: {e}"

TOOL_MAP["desligar_pc"] = desligar_pc
FUNCTION_DECLARATIONS.append({
    "name": "desligar_pc",
    "description": "Desliga o computador. Ação sensível: só executa com confirmação literal.",
    "parameters": {
        "type": "object",
        "properties": {
            "tempo_segundos": {"type": "integer"},
            "confirmar": {
                "type": "string",
                "description": "Obrigatório para executar: SIM, tenho certeza"
            }
        },
        "required": ["confirmar"]
    }
})
