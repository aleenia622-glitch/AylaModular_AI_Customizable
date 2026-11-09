"""Move memórias para a lixeira, permitindo restaurá-las depois."""
def apagar_memoria(chave: str) -> str:
    resultado = enviar_memoria_para_lixeira(chave, "Removida pela Ayla a pedido da dona")
    if not resultado.get("ok"):
        return f"Erro: {resultado.get('mensagem', 'a memória não foi encontrada no caderninho.')}"
    
    try:
        print(f"\n[MEMORIA] Ayla moveu a memória para a lixeira: {chave}\n")
    except Exception:
        pass
        
    try:
        global_bot = globals().get("bot")
        if global_bot and hasattr(global_bot, "atualizar_prompt_memoria"):
            global_bot.atualizar_prompt_memoria()
    except Exception as e:
        print(f"⚠️ Erro ao atualizar prompt de memória no bot: {e}")

    return f"🗑️ {resultado.get('mensagem')}"

TOOL_MAP["apagar_memoria"] = apagar_memoria
FUNCTION_DECLARATIONS.append({
    "name": "apagar_memoria",
    "description": "Move uma memória para a lixeira usando a chave correspondente. A memória pode ser restaurada depois.",
    "parameters": {
        "type": "object",
        "properties": {
            "chave": {
                "type": "string",
                "description": "A chave da memória que você deseja apagar permanentemente (ex: 'gosto_cafe', 'meu_aniversario')."
            }
        },
        "required": ["chave"]
    }
})
