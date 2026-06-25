def resumir_historico_conversa() -> str:
    """Retorna um resumo do histórico atual da conversa com o Gemini"""
    try:
        historico = bot.chat_session.get_history() if bot.chat_session and hasattr(bot.chat_session, "get_history") else []
        if not historico:
            return "Ainda não temos histórico de conversa nessa sessão!"
        total = len(historico)
        return f"📜 Sessão atual: {total} mensagens trocadas com a Alêenia."
    except Exception as e:
        return f"Erro ao ler histórico: {e}"

TOOL_MAP["resumir_historico_conversa"] = resumir_historico_conversa
FUNCTION_DECLARATIONS.append({"name": "resumir_historico_conversa", "description": "Mostra quantas mensagens foram trocadas na sessão atual.", "parameters": {"type": "object", "properties": {}}})
