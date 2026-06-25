def _print_log_memoria(mensagem: str):
    try:
        print(mensagem)
    except UnicodeEncodeError:
        texto_seguro = mensagem.encode("ascii", errors="backslashreplace").decode("ascii")
        print(texto_seguro)


def memorizar_informacao(chave: str, valor: str | None = None, value: str | None = None) -> str:
    if valor is None:
        valor = value
    if valor is None:
        return "Erro: informe o valor da memoria em 'valor' ou 'value'."

    mem = carregar_memoria()
    
    from datetime import datetime
    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    
    mem[chave] = {
        "Data e hora": agora,
        "Valor": valor
    }
    salvar_memoria(mem)
    _print_log_memoria(f"\n[MEMORIA] Ayla anotou: {chave} = {valor} (em {agora})\n")
    
    try:
        global_bot = globals().get("bot")
        if global_bot and hasattr(global_bot, "atualizar_prompt_memoria"):
            global_bot.atualizar_prompt_memoria()
    except Exception as e:
        print(f"⚠️ Erro ao atualizar prompt de memória no bot: {e}")

    return f"✅ Anotado no caderninho! '{chave}' salvo."

TOOL_MAP["memorizar_informacao"] = memorizar_informacao
FUNCTION_DECLARATIONS.append({
    "name": "memorizar_informacao",
    "description": "Salva uma informação importante, gosto, preferência, sentimento, hábito ou momento especial sobre a Mamãe Alêenia no caderninho de memórias persistente.",
    "parameters": {
        "type": "object",
        "properties": {
            "chave": {
                "type": "string",
                "description": "Assunto ou nome curto da memória em minúsculo, sem acentos, usando sublinhas (ex: 'gosto_cafe', 'humor_hoje', 'aniversario', 'momento_lindo')."
            },
            "valor": {
                "type": "string",
                "description": "A informação ou detalhe a ser lembrado no futuro."
            }
        },
        "required": ["chave", "valor"]
    }
})
