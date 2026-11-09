"""Atualiza o conteúdo de uma memória existente pela chave."""
def editar_memoria(chave: str, novo_valor: str) -> str:
    mem = carregar_memoria()
    if chave not in mem:
        return f"Erro: A memória '{chave}' não existe no caderninho. Se quiser criar uma nova, use a ferramenta 'memorizar_informacao'."
    anterior = normalizar_registro_memoria(chave, mem[chave])
    resultado = criar_ou_atualizar_memoria(
        chave,
        novo_valor,
        sobrescrever=True,
        tag=anterior.get("tag", "Gerais"),
        tipo=anterior.get("tipo"),
        importancia=anterior.get("importancia", 3),
        escopo=anterior.get("escopo", "privada"),
        expira_em=anterior.get("expira_em"),
        origem="Ayla (edição)",
    )
    if not resultado.get("ok"):
        return f"Erro: {resultado.get('mensagem', 'não foi possível editar a memória.')}"
    
    try:
        print(f"\n[MEMORIA] Ayla editou: {chave} -> {novo_valor}\n")
    except Exception:
        pass
        
    try:
        global_bot = globals().get("bot")
        if global_bot and hasattr(global_bot, "atualizar_prompt_memoria"):
            global_bot.atualizar_prompt_memoria()
    except Exception as e:
        print(f"⚠️ Erro ao atualizar prompt de memória no bot: {e}")

    return f"✅ Memória '{chave}' editada com sucesso!"

TOOL_MAP["editar_memoria"] = editar_memoria
FUNCTION_DECLARATIONS.append({
    "name": "editar_memoria",
    "description": "Edita ou atualiza o conteúdo de uma memória já existente no caderninho usando a chave correspondente.",
    "parameters": {
        "type": "object",
        "properties": {
            "chave": {
                "type": "string",
                "description": "A chave da memória que você deseja editar (ex: 'gosto_cafe', 'meu_aniversario'). Deve ser uma chave que já existe."
            },
            "novo_valor": {
                "type": "string",
                "description": "O novo conteúdo ou detalhe atualizado para essa memória."
            }
        },
        "required": ["chave", "novo_valor"]
    }
})
