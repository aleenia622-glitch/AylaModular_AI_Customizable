import requests

def informacao_astronautas() -> str:
    """
    Descobre quantas pessoas estão no espaço agora mesmo e quem são elas! 🚀
    """
    try:
        url = "http://api.open-notify.org/astros.json"
        resp = requests.get(url, timeout=10)
        
        if resp.status_code != 200:
            return "❌ Houston, temos um problema! Não consegui contato com a estação espacial... 🧑‍🚀"
            
        data = resp.json()
        numero = data.get("number", 0)
        pessoas = data.get("people", [])
        
        if numero == 0:
            return "🚀 Ué! Parece que não tem ninguém no espaço agora... Estão todos aqui na Terra? 🌍"
            
        lista_astronautas = []
        for p in pessoas:
            nome = p.get("name")
            nave = p.get("craft")
            lista_astronautas.append(f"• **{nome}** (na nave *{nave}*)")
            
        lista_str = "\\n".join(lista_astronautas)
        
        return (
            f"🌌 **Viagem Espacial da Ayla!** 🚀\\n\\n"
            f"Atualmente, existem **{numero}** pessoas corajosas flutuando no espaço! ✨\\n\\n"
            f"Olha só a lista de quem está lá:\\n"
            f"{lista_str}\\n\\n"
            f"Que incrível, né? Que vontade de flutuar também! 🛸🌠"
        )
    except Exception as e:
        return f"❌ Faltou combustível para subir ao espaço! Erro: {e}"

TOOL_MAP["informacao_astronautas"] = informacao_astronautas
TOOL_MAP["informacao_astronautas"] = informacao_astronautas

if "informacao_astronautas" not in [fd["name"] for fd in FUNCTION_DECLARATIONS]:
    FUNCTION_DECLARATIONS.append({
        "name": "informacao_astronautas",
        "description": "Retorna o número de pessoas que estão atualmente no espaço e seus nomes.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    })
