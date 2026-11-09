"""Identifica memórias expiradas, duplicadas ou conflitantes e pode arquivar as vencidas."""


def revisar_memorias(arquivar_expiradas: bool = False, limite: int = 12) -> str:
    relatorio = revisar_memorias_estruturadas(arquivar_expiradas=arquivar_expiradas, limite=limite)
    linhas = [
        f"- Memórias ativas: {relatorio['total_ativas']}",
        f"- Itens na lixeira: {relatorio['lixeira']}",
        f"- Expiradas: {', '.join(relatorio['expiradas']) or 'nenhuma'}",
        f"- Possíveis duplicatas: {', '.join(f'{a} ↔ {b}' for a, b, _ in relatorio['duplicatas']) or 'nenhuma'}",
        f"- Possíveis conflitos: {', '.join(f'{a} ↔ {b}' for a, b in relatorio['possiveis_conflitos']) or 'nenhum'}",
    ]
    if relatorio['arquivadas_agora']:
        linhas.append("- As memórias expiradas foram arquivadas.")
    return "🧹 Revisão do caderninho:\n" + "\n".join(linhas)


TOOL_MAP["revisar_memorias"] = revisar_memorias
FUNCTION_DECLARATIONS.append({
    "name": "revisar_memorias",
    "description": "Revisa o caderninho e aponta memórias expiradas, possíveis duplicatas e possíveis conflitos. Só arquive expiradas se a dona pedir ou se for claramente seguro.",
    "parameters": {
        "type": "object",
        "properties": {
            "arquivar_expiradas": {"type": "boolean", "description": "Move automaticamente memórias vencidas para arquivo, sem apagá-las."},
            "limite": {"type": "integer", "description": "Máximo de alertas de cada tipo (1 a 50)."}
        }
    }
})
