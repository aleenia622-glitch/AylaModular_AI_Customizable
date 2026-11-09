"""Salva informações e preferências na memória persistente."""
def _print_log_memoria(mensagem: str):
    try:
        print(mensagem)
    except UnicodeEncodeError:
        texto_seguro = mensagem.encode("ascii", errors="backslashreplace").decode("ascii")
        print(texto_seguro)


def memorizar_informacao(
    chave: str,
    valor: str | None = None,
    value: str | None = None,
    sobrescrever: bool | None = None,
    overwrite: bool | None = None,
    tag: str = "Gerais",
    tipo: str | None = None,
    importancia: int | None = None,
    escopo: str = "privada",
    expira_em: str | None = None,
    confirmada: bool | None = True,
) -> str:
    if valor is None:
        valor = value
    if valor is None:
        return "Erro: informe o valor da memoria em 'valor' ou 'value'."

    pode_sobrescrever = False
    if sobrescrever is not None:
        pode_sobrescrever = sobrescrever
    elif overwrite is not None:
        pode_sobrescrever = overwrite

    resultado = criar_ou_atualizar_memoria(
        chave,
        valor,
        sobrescrever=pode_sobrescrever,
        tag=tag,
        tipo=tipo,
        importancia=importancia,
        escopo=escopo,
        expira_em=expira_em,
        confirmada=confirmada,
        origem="Ayla",
    )
    if not resultado.get("ok"):
        atual = resultado.get("valor_atual")
        detalhe = f" Valor atual: '{atual}'." if atual else ""
        return f"⚠️ {resultado.get('mensagem', 'Não foi possível salvar a memória.')}{detalhe}"
    if not resultado.get("alterada", False):
        return f"ℹ️ {resultado.get('mensagem')}"
    _print_log_memoria(f"\n[MEMORIA] Ayla {resultado.get('acao', 'salvou')}: {resultado.get('chave')}\n")
    
    try:
        global_bot = globals().get("bot")
        if global_bot and hasattr(global_bot, "atualizar_prompt_memoria"):
            global_bot.atualizar_prompt_memoria()
    except Exception as e:
        print(f"⚠️ Erro ao atualizar prompt de memória no bot: {e}")

    similares = resultado.get("similares") or []
    aviso = f" Possíveis memórias relacionadas: {', '.join(similares)}." if similares else ""
    return f"✅ {resultado.get('mensagem')}{aviso}"

TOOL_MAP["memorizar_informacao"] = memorizar_informacao
FUNCTION_DECLARATIONS.append({
    "name": "memorizar_informacao",
    "description": "Salva uma informação importante, gosto, preferência, sentimento, hábito ou momento especial sobre a usuario Usuario no caderninho de memórias persistente.",
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
            },
            "tag": {
                "type": "string",
                "description": "Categoria curta, como 'Jogos', 'Projetos', 'Saúde' ou 'Gerais'."
            },
            "tipo": {
                "type": "string",
                "enum": ["preferencia", "pessoa", "projeto", "regra", "momento", "contexto", "lore", "outro"],
                "description": "Tipo da memória; use preferencia para gostos e regra para instruções duradouras."
            },
            "importancia": {
                "type": "integer",
                "minimum": 1,
                "maximum": 5,
                "description": "De 1 (detalhe pequeno) a 5 (informação essencial)."
            },
            "escopo": {
                "type": "string",
                "enum": ["privada", "publica"],
                "description": "Privada por padrão. Só use publica se a usuario autorizar que a informação possa orientar conversas públicas."
            },
            "expira_em": {
                "type": "string",
                "description": "Opcional: data/hora ISO de validade para contexto temporário, ex.: 2026-08-10T18:00:00."
            },
            "confirmada": {
                "type": "boolean",
                "description": "False se for uma hipótese ou algo ainda não confirmado; True para um fato confirmado pela usuario."
            }
        },
        "required": ["chave", "valor"]
    }
})
