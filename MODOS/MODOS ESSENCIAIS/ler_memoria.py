def ler_memoria(chave=None, chaves=None) -> str:
    lista_chaves = []

    if chaves is not None:
        if isinstance(chaves, list):
            lista_chaves.extend([str(k).strip() for k in chaves if str(k).strip()])
        elif isinstance(chaves, str):
            lista_chaves.extend([k.strip() for k in chaves.split(",") if k.strip()])

    if chave is not None:
        if isinstance(chave, list):
            lista_chaves.extend([str(k).strip() for k in chave if str(k).strip()])
        elif isinstance(chave, str):
            lista_chaves.extend([k.strip() for k in chave.split(",") if k.strip()])

    # Remover duplicatas preservando a ordem
    lista_chaves = list(dict.fromkeys(lista_chaves))

    if not lista_chaves:
        return "Erro: Nenhuma chave válida foi informada para leitura de memória."

    mem = carregar_memoria()
    resultados = []
    atualizou_alguma = False

    for k in lista_chaves:
        if k not in mem:
            resultados.append(f"❌ Chave '{k}': Não encontrada no caderninho.")
            continue

        registro = mem[k]
        if not isinstance(registro, dict):
            registro = {
                "Valor": registro,
                "acessos": 0
            }

        acessos = registro.get("acessos", 0) + 1
        registro["acessos"] = acessos
        mem[k] = registro
        atualizou_alguma = True

        valor = registro.get("Valor", registro.get("valor", registro))
        data_hora = registro.get("Data e hora", registro.get("data_hora", "desconhecida"))
        resultados.append(
            f"🧠 **'{k}'** (Acessos: {acessos})\n"
            f"   - Valor: {valor}\n"
            f"   - Salvo em: {data_hora}"
        )

    if atualizou_alguma:
        salvar_memoria(mem)
        try:
            global_bot = globals().get("bot")
            if global_bot and hasattr(global_bot, "atualizar_prompt_memoria"):
                global_bot.atualizar_prompt_memoria()
        except Exception as e:
            print(f"⚠️ Erro ao atualizar prompt de memória no bot após leitura: {e}")

    return "🧠 Memórias carregadas com sucesso!\n\n" + "\n\n".join(resultados)

TOOL_MAP["ler_memoria"] = ler_memoria
FUNCTION_DECLARATIONS.append({
    "name": "ler_memoria",
    "description": "Lê o conteúdo de uma ou mais memórias do caderninho a partir de suas chaves. Selecione e leia várias chaves de uma só vez informando uma lista no parâmetro 'chaves'.",
    "parameters": {
        "type": "object",
        "properties": {
            "chaves": {
                "type": "array",
                "items": { "type": "string" },
                "description": "Lista com as chaves das memórias que você deseja selecionar e ler em lote (ex: ['gosto_cafe', 'meu_aniversario'])."
            },
            "chave": {
                "type": "string",
                "description": "Uma única chave ou chaves separadas por vírgula caso vá ler apenas uma chave (ex: 'gosto_cafe')."
            }
        }
    }
})
