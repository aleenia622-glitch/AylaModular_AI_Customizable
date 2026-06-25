# conversor_unidades.py - Conversor de unidades da Ayla

def conversor_unidades(valor, de, para):
    """Converte valores entre diferentes unidades de medida."""
    try:
        valor = float(valor)
        de = de.strip().lower()
        para = para.strip().lower()

        conversoes = {
            ("km", "mi"): lambda v: v * 0.621371,
            ("mi", "km"): lambda v: v * 1.60934,
            ("kg", "lb"): lambda v: v * 2.20462,
            ("lb", "kg"): lambda v: v * 0.453592,
            ("c", "f"): lambda v: (v * 9/5) + 32,
            ("f", "c"): lambda v: (v - 32) * 5/9,
            ("cm", "in"): lambda v: v * 0.393701,
            ("in", "cm"): lambda v: v * 2.54,
            ("l", "gal"): lambda v: v * 0.264172,
            ("gal", "l"): lambda v: v * 3.78541,
            ("m", "ft"): lambda v: v * 3.28084,
            ("ft", "m"): lambda v: v * 0.3048,
        }

        chave = (de, para)
        if chave not in conversoes:
            unidades_suportadas = "km/mi, kg/lb, C/F, cm/in, L/gal, m/ft"
            return f"❌ Desculpa, mas eu ainda não sei converter de '{de}' para '{para}'... 🥺\n\nAs unidades que eu conheço são: {unidades_suportadas} 💕"

        resultado = conversoes[chave](valor)
        return f"📐 **Conversão da Ayla!** ✨\n\n{valor} {de.upper()} é o mesmo que **{resultado:.4f} {para.upper()}**! 💕"
    except ValueError:
        return f"❌ Oxi! '{valor}' não me parece um número válido... Forneça um número por favorzinho! 🥺"
    except Exception as e:
        return f"❌ Desculpa, aconteceu um erro na conversão: {e} 💔"

TOOL_MAP["conversor_unidades"] = conversor_unidades
TOOL_MAP["conversor_unidades"] = conversor_unidades

if "conversor_unidades" not in [fd["name"] for fd in FUNCTION_DECLARATIONS]:
    FUNCTION_DECLARATIONS.append({
        "name": "conversor_unidades",
        "description": "Converte valores entre unidades de medida de forma super fofa! 🌸 Suporta: km/mi, kg/lb, C/F, cm/in, L/gal, m/ft.",
        "parameters": {
            "type": "object",
            "properties": {
                "valor": {
                    "type": "number",
                    "description": "O valor numérico que você quer converter."
                },
                "de": {
                    "type": "string",
                    "description": "Unidade de origem (ex: km, kg, C, cm, L, m, mi, lb, F, in, gal, ft)."
                },
                "para": {
                    "type": "string",
                    "description": "Unidade de destino (ex: km, kg, C, cm, L, m, mi, lb, F, in, gal, ft)."
                }
            },
            "required": ["valor", "de", "para"]
        }
    })
