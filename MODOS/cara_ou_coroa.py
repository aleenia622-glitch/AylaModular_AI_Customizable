import random

# Garante compatibilidade se o arquivo for executado/importado individualmente
if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

def cara_ou_coroa() -> str:
    """
    Realiza um sorteio clássico de moeda (Cara ou Coroa) e retorna o resultado.
    """
    resultado = random.choice(["Cara", "Coroa"])
    return f"🪙 O resultado do sorteio foi: **{resultado}**!"

TOOL_MAP["cara_ou_coroa"] = cara_ou_coroa
FUNCTION_DECLARATIONS.append({
    "name": "cara_ou_coroa",
    "description": "Realiza um sorteio clássico de cara ou coroa (moeda) e retorna o resultado.",
    "parameters": {
        "type": "object",
        "properties": {}
    }
})
