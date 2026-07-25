def _print_log_memoria(mensagem: str):
    try:
        print(mensagem)
    except UnicodeEncodeError:
        texto_seguro = mensagem.encode("ascii", errors="backslashreplace").decode("ascii")
        print(texto_seguro)


def memorizar_informacao(chave: str, valor: str | None = None, value: str | None = None, sobrescrever: bool | None = None, overwrite: bool | None = None) -> str:
    if valor is None:
        valor = value
    if valor is None:
        return "Erro: informe o valor da memoria em 'valor' ou 'value'."

    pode_sobrescrever = False
    if sobrescrever is not None:
        pode_sobrescrever = sobrescrever
    elif overwrite is not None:
        pode_sobrescrever = overwrite

    mem = carregar_memoria()
    
    if chave in mem and not pode_sobrescrever:
        valor_atual = mem[chave].get("Valor")
        if valor_atual == valor:
            return f"ℹ️ A chave '{chave}' já existe com exatamente o mesmo valor no caderninho. Nenhuma alteração feita."
        return (
            f"⚠️ Aviso: A chave '{chave}' já existe no caderninho de memórias com o valor: '{valor_atual}'. "
            f"Se você deseja atualizar esse valor especificamente, chame esta ferramenta novamente com o parâmetro 'sobrescrever=True'. "
            f"Caso contrário, use uma chave mais específica (ex: '{chave}_2', '{chave}_novo') para não perder a informação anterior."
        )
    
    from datetime import datetime
    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    
    mem[chave] = {
        "Data e hora": agora,
        "Valor": valor,
        "acessos": 0
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
    "description": "Salva uma informação importante, gosto, preferência, sentimento, hábito ou momento especial sobre o(a) usuário(a) no caderninho de memórias persistente.",
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
            },
            "sobrescrever": {
                "type": "boolean",
                "description": "Defina como True apenas se você realmente deseja substituir o valor de uma chave existente por uma informação atualizada."
            }
        },
        "required": ["chave", "valor"]
    }
})
