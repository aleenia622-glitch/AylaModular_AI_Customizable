import random
import re

def sortear(tipo="numero", minimo=None, maximo=None, opcoes=None, dados=None):
    """Sorteia valores aleatórios de vários tipos."""
    try:
        tipo = str(tipo).lower().strip()

        if tipo == "numero":
            mi = int(minimo) if minimo is not None else 1
            ma = int(maximo) if maximo is not None else 100
            if mi > ma:
                mi, ma = ma, mi
            resultado = random.randint(mi, ma)
            return (
                f"🎲 **Sorteio de Número da Ayla!** 🌸\n"
                f"Intervalo: {mi} a {ma}\n"
                f"🎯 Resultado: **{resultado}**"
            )

        elif tipo == "moeda":
            resultado = random.choice(["Cara 🪙", "Coroa 👑"])
            return f"🪙 **Cara ou Coroa da Ayla!** 🌸\n🎯 Resultado: **{resultado}**"

        elif tipo == "dado":
            if dados:
                # Parse notação como '2d20', '3d6'
                match = re.match(r'^(\d+)?d(\d+)$', str(dados).strip().lower())
                if not match:
                    return "❌ Oxi, essa notação parece inválida... Use formatos como '2d20', '3d6' ou '1d100', por favorzinho! 🥺"
                qtd = int(match.group(1)) if match.group(1) else 1
                faces = int(match.group(2))
                if qtd < 1 or qtd > 100:
                    return "❌ Nhaw, a quantidade de dados deve ser entre 1 e 100! 🥺"
                if faces < 2 or faces > 1000:
                    return "❌ Desculpa, mas o dado precisa ter entre 2 e 1000 faces! 🥺"
                resultados = [random.randint(1, faces) for _ in range(qtd)]
                total = sum(resultados)
                dados_str = ', '.join(str(r) for r in resultados)
                return (
                    f"🎲 **Rolagem da Ayla: {qtd}d{faces}!** 🌸\n"
                    f"🎯 Resultados: [{dados_str}]\n"
                    f"📊 Total: **{total}**"
                )
            else:
                faces = int(maximo) if maximo else 6
                resultado = random.randint(1, faces)
                return f"🎲 **Dado de {faces} faces da Ayla!** 🌸\n🎯 Resultado: **{resultado}**"

        elif tipo == "lista":
            if not opcoes:
                return "❌ Você precisa me dar as opções separadas por vírgula no parâmetro 'opcoes' para eu escolher! 🥺"
            lista = [op.strip() for op in str(opcoes).split(',') if op.strip()]
            if len(lista) < 2:
                return "❌ Forneça pelo menos 2 opções separadas por vírgula, senão não tem graça sortear! 🥺"
            escolhido = random.choice(lista)
            return (
                f"🎰 **Sorteio de Lista da Ayla!** 🌸\n"
                f"📋 Opções: {', '.join(lista)}\n"
                f"🎯 Escolhido: **{escolhido}**"
            )

        else:
            return f"❌ Oxi! O tipo '{tipo}' não foi reconhecido. Use 'numero', 'moeda', 'dado' ou 'lista', tá bom? 💕"

    except Exception as e:
        return f"❌ Desculpa, aconteceu um erro no sorteio: {e} 💔"

TOOL_MAP["sortear"] = sortear
TOOL_MAP["sortear"] = sortear

if "sortear" not in [fd["name"] for fd in FUNCTION_DECLARATIONS]:
    FUNCTION_DECLARATIONS.append({
        "name": "sortear",
        "description": "Sorteia valores aleatórios de um jeito super fofo! 🎲🌸 Tipos: 'numero', 'moeda' (cara ou coroa), 'dado' (rola dados) ou 'lista' (escolhe item de uma lista).",
        "parameters": {
            "type": "object",
            "properties": {
                "tipo": {
                    "type": "string",
                    "description": "Tipo de sorteio: 'numero', 'moeda', 'dado' ou 'lista'",
                    "enum": ["numero", "moeda", "dado", "lista"]
                },
                "minimo": {
                    "type": "integer",
                    "description": "Valor mínimo (para tipo 'numero')"
                },
                "maximo": {
                    "type": "integer",
                    "description": "Valor máximo (para tipo 'numero') ou faces do dado (para tipo 'dado')"
                },
                "opcoes": {
                    "type": "string",
                    "description": "Opções separadas por vírgula (para tipo 'lista')"
                },
                "dados": {
                    "type": "string",
                    "description": "Notação de dados como '2d20', '3d6' (para tipo 'dado')"
                }
            }
        }
    })
