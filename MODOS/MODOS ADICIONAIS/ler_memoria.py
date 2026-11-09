"""Lê memórias específicas pelas suas chaves."""
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
    encontradas = []

    for k in lista_chaves:
        if k not in mem:
            resultados.append(f"❌ Chave '{k}': Não encontrada no caderninho.")
            continue

        registro = normalizar_registro_memoria(k, mem[k])
        encontradas.append(k)
        valor = registro.get("Valor", "")
        data_hora = registro.get("Data e hora", "desconhecida")
        resultados.append(
            f"🧠 **'{k}'** ({registro.get('tipo', 'outro')} | {registro.get('tag', 'Gerais')} | importância {registro.get('importancia', 3)})\n"
            f"   - Valor: {valor}\n"
            f"   - Salvo em: {data_hora}\n"
            f"   - Escopo: {registro.get('escopo', 'privada')} | Status: {registro.get('status', 'ativa')}"
        )

    registrar_acessos_memoria(encontradas)

    return "🧠 Memórias carregadas com sucesso!\n\n" + "\n\n".join(resultados)

TOOL_MAP["ler_memoria"] = ler_memoria
FUNCTION_DECLARATIONS.append({
    "name": "ler_memoria",
    "description": "Lê uma ou mais memórias salvas no caderninho por suas chaves.",
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
