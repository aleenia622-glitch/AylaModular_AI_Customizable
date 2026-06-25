def consultar_memorias() -> str:
    mem = carregar_memoria()
    if not mem: return "Caderninho vazio."
    pedacos = []
    for k, v in mem.items():
        if isinstance(v, dict) and "Data e hora" in v and "Valor" in v:
            pedacos.append(f"- {k}: {v.get('Valor')} (Salvo em: {v.get('Data e hora')})")
        elif isinstance(v, dict) and "valor" in v and "data_hora" in v:
            pedacos.append(f"- {k}: {v.get('valor')} (Salvo em: {v.get('data_hora')})")
        else:
            pedacos.append(f"- {k}: {v}")
    return "🧠 Meu caderninho:\n" + "\n".join(pedacos)

TOOL_MAP["consultar_memorias"] = consultar_memorias
FUNCTION_DECLARATIONS.append({
    "name": "consultar_memorias",
    "description": "Consulta todas as memórias, preferências e momentos especiais sobre a Mamãe Alêenia guardados no caderninho de memórias persistente.",
    "parameters": {"type": "object", "properties": {}}
})
