import requests

def conversor_moeda(de: str, para: str, valor: float) -> str:
    """
    Converte um valor de uma moeda para outra usando a cotação em tempo real!
    """
    moeda_origem = de.upper().strip()
    moeda_destino = para.upper().strip()
    try:
        url = f"https://open.er-api.com/v6/latest/{moeda_origem}"
        resp = requests.get(url, timeout=10)
        
        if resp.status_code != 200:
            return f"❌ Ih, não consegui obter a cotação da moeda '{moeda_origem}'. Ela existe mesmo? 🥺"
            
        data = resp.json()
        if data.get("result") != "success":
            return f"❌ Houve um problema na consulta de moedas para '{moeda_origem}'."
            
        taxas = data.get("rates", {})
        if moeda_destino not in taxas:
            return f"❌ Desculpe, não encontrei a moeda de destino '{moeda_destino}' na lista de cotações! 🥺"
            
        taxa = taxas[moeda_destino]
        convertido = valor * taxa
        
        return (
            f"💰 **Conversor de Moedas da Ayla!**\\n\\n"
            f"• Origem: {valor:,.2f} **{moeda_origem}**\\n"
            f"• Destino: {convertido:,.2f} **{moeda_destino}**\\n"
            f"• Taxa de câmbio: 1 {moeda_origem} = {taxa:.4f} {moeda_destino}\\n\\n"
            f"Prontinho! Negócios fechados com muito brilho! 🪙✨"
        )
    except Exception as e:
        return f"❌ O cofrinho da Ayla quebrou! Erro na conversão: {e}"

TOOL_MAP["conversor_moeda"] = conversor_moeda
TOOL_MAP["conversor_moeda"] = conversor_moeda

if "conversor_moeda" not in [fd["name"] for fd in FUNCTION_DECLARATIONS]:
    FUNCTION_DECLARATIONS.append({
        "name": "conversor_moeda",
        "description": "Converte valores monetários entre moedas diferentes com taxas de câmbio atuais.",
        "parameters": {
            "type": "object",
            "properties": {
                "de": {"type": "string", "description": "Código da moeda de origem (ex: USD, BRL, EUR)"},
                "para": {"type": "string", "description": "Código da moeda de destino (ex: BRL, USD, EUR)"},
                "valor": {"type": "number", "description": "O valor numérico a ser convertido"}
            },
            "required": ["de", "para", "valor"]
        }
    })
