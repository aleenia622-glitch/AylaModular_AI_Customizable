"""Busca memórias por assunto, categoria ou tipo."""


def buscar_memorias(consulta: str, limite: int = 10, tipo: str | None = None, tag: str | None = None) -> str:
    tipos = [tipo] if tipo else None
    tags = [tag] if tag else None
    resultados = buscar_memorias_estruturadas(
        consulta=consulta,
        limite=limite,
        escopos_permitidos={"privada", "publica"},
        tipos=tipos,
        tags=tags,
    )
    if not resultados:
        return "🧠 Não encontrei nenhuma memória ativa relacionada a isso."
    registrar_acessos_memoria([item["chave"] for item in resultados])
    return "🧠 Memórias mais relevantes:\n" + formatar_memorias_encontradas(resultados)


TOOL_MAP["buscar_memorias"] = buscar_memorias
FUNCTION_DECLARATIONS.append({
    "name": "buscar_memorias",
    "description": "Busca memórias relevantes por assunto antes de responder sobre preferências, pessoas, projetos ou detalhes pessoais. Use esta ferramenta em vez de consultar o caderninho inteiro.",
    "parameters": {
        "type": "object",
        "properties": {
            "consulta": {"type": "string", "description": "Assunto ou pergunta curta, por exemplo 'jogos que a usuario gosta'."},
            "limite": {"type": "integer", "description": "De 1 a 20 resultados; use poucos resultados quando possível."},
            "tipo": {"type": "string", "description": "Filtro opcional: preferencia, pessoa, projeto, regra, momento, contexto, lore ou outro."},
            "tag": {"type": "string", "description": "Filtro opcional por categoria/tag."}
        },
        "required": ["consulta"]
    }
})
