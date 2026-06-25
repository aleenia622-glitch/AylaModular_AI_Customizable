import random
import re

def dado_rpg(notacao):
    """Rola dados RPG com notação como 2d20+5, 4d6, 1d100."""
    try:
        notacao = str(notacao).strip().lower()
        if not notacao:
            return "❌ Oxi, você precisa fornecer uma notação de dados (como '2d20+5', '4d6' ou '1d100') para eu rolar! 🥺"

        # Parse notação: [N]d[F][+/-M] ou múltiplos separados por +
        # Suporta: 2d20+5, 4d6, 1d100, 2d6+1d8+3
        partes = re.split(r'\s*\+\s*', notacao)

        todos_resultados = []
        total_geral = 0
        descricao_partes = []

        for parte in partes:
            parte = parte.strip()

            # Verificar se é um dado (contém 'd')
            match_dado = re.match(r'^(\d+)?d(\d+)(?:([+-])(\d+))?$', parte)

            if match_dado:
                qtd = int(match_dado.group(1)) if match_dado.group(1) else 1
                faces = int(match_dado.group(2))
                sinal_mod = match_dado.group(3)
                mod = int(match_dado.group(4)) if match_dado.group(4) else 0
                if sinal_mod == '-':
                    mod = -mod

                if qtd < 1 or qtd > 100:
                    return "❌ Desculpa, mas eu só consigo rolar de 1 a 100 dados por vez! 🥺"
                if faces < 2 or faces > 10000:
                    return "❌ Nhaw, o dado precisa ter entre 2 e 10000 faces! 🥺"

                resultados = [random.randint(1, faces) for _ in range(qtd)]
                subtotal = sum(resultados) + mod

                dados_str = ', '.join(str(r) for r in resultados)
                parte_desc = f"🎲 {qtd}d{faces}: [{dados_str}]"
                if mod != 0:
                    parte_desc += f" {'+' if mod > 0 else ''}{mod}"
                parte_desc += f" = **{subtotal}**"

                descricao_partes.append(parte_desc)
                todos_resultados.extend(resultados)
                total_geral += subtotal

            elif re.match(r'^-?\d+$', parte):
                # É um modificador numérico simples
                val = int(parte)
                total_geral += val
                descricao_partes.append(f"➕ Modificador: {'+' if val >= 0 else ''}{val}")

            else:
                # Tentar parse com subtração: 2d20-5
                match_sub = re.match(r'^(\d+)?d(\d+)-(\d+)$', parte)
                if match_sub:
                    qtd = int(match_sub.group(1)) if match_sub.group(1) else 1
                    faces = int(match_sub.group(2))
                    mod = -int(match_sub.group(3))

                    if qtd < 1 or qtd > 100:
                        return "❌ Desculpa, mas eu só consigo rolar de 1 a 100 dados por vez! 🥺"
                    if faces < 2 or faces > 10000:
                        return "❌ Nhaw, o dado precisa ter entre 2 e 10000 faces! 🥺"

                    resultados = [random.randint(1, faces) for _ in range(qtd)]
                    subtotal = sum(resultados) + mod
                    dados_str = ', '.join(str(r) for r in resultados)
                    descricao_partes.append(f"🎲 {qtd}d{faces}: [{dados_str}] {mod} = **{subtotal}**")
                    todos_resultados.extend(resultados)
                    total_geral += subtotal
                else:
                    return f"❌ Eita, não entendi essa parte: '{parte}'. Usa um formato como '2d20+5' para eu entender, por favorzinho! 🥺"

        # Estatísticas adicionais para múltiplos dados
        extras = ""
        if len(todos_resultados) > 1:
            maior = max(todos_resultados)
            menor = min(todos_resultados)
            media = sum(todos_resultados) / len(todos_resultados)
            extras = (
                f"\n\n📊 **Estatísticas fofas dos dados:**\n"
                f"⬆️ Maior: {maior}\n"
                f"⬇️ Menor: {menor}\n"
                f"📈 Média: {media:.1f}"
            )

        resultado_text = '\n'.join(descricao_partes)
        return (
            f"🎲 **Rolagem de Dados da Ayla!** 🌸\n\n"
            f"Fórmula: `{notacao}`\n\n"
            f"{resultado_text}\n\n"
            f"🎯 **Total Geral: {total_geral}**{extras} 🎉"
        )

    except Exception as e:
        return f"❌ Desculpa, aconteceu um erro ao rolar os dados: {e} 💔"

TOOL_MAP["dado_rpg"] = dado_rpg
TOOL_MAP["dado_rpg"] = dado_rpg

if "dado_rpg" not in [fd["name"] for fd in FUNCTION_DECLARATIONS]:
    FUNCTION_DECLARATIONS.append({
        "name": "dado_rpg",
        "description": "Rola dados de RPG de forma divertida! 🎲🌸 Suporta formatos como '2d20+5', '4d6', '1d100', '2d6+1d8+3'.",
        "parameters": {
            "type": "object",
            "properties": {
                "notacao": {
                    "type": "string",
                    "description": "A notação dos dados de RPG (ex: '2d20+5', '4d6', '1d100')"
                }
            },
            "required": ["notacao"]
        }
    })
