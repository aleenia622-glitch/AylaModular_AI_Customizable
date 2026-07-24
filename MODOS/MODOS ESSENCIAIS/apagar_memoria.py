def apagar_memoria(chave: str) -> str:
    mem = carregar_memoria()
    if chave not in mem:
        return f"Erro: A memória '{chave}' não foi encontrada no caderninho."

    del mem[chave]
    salvar_memoria(mem)
    
    try:
        print(f"\n[MEMORIA] Ayla apagou a memória: {chave}\n")
    except Exception:
        pass
        
    try:
        global_bot = globals().get("bot")
        if global_bot and hasattr(global_bot, "atualizar_prompt_memoria"):
            global_bot.atualizar_prompt_memoria()
    except Exception as e:
        print(f"⚠️ Erro ao atualizar prompt de memória no bot: {e}")

    return f"🗑️ Memória '{chave}' foi apagada com sucesso do caderninho!"

TOOL_MAP["apagar_memoria"] = apagar_memoria
FUNCTION_DECLARATIONS.append({
    "name": "apagar_memoria",
    "description": "Apaga ou remove permanentemente uma memória do caderninho de memórias usando a chave correspondente.",
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
