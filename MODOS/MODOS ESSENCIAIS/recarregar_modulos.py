import sys

if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

def recarregar_modulos() -> str:
    """
    Recarrega todos os módulos de habilidades da Ayla na mesma hora, 
    sem precisar reiniciar o bot inteiro.
    """
    try:
        import __main__
        if hasattr(__main__, "carregar_modulos"):
            # Guarda a quantidade antiga de ferramentas
            qtd_antes = len(__main__.TOOL_MAP) if hasattr(__main__, "TOOL_MAP") else 0
            
            # Chama a função principal de recarregar
            __main__.carregar_modulos()
            
            qtd_depois = len(__main__.TOOL_MAP) if hasattr(__main__, "TOOL_MAP") else 0
            diferenca = qtd_depois - qtd_antes
            
            detalhe = f" ({diferenca} nova(s))" if diferenca > 0 else ""
            
            return f"🔄 **Módulos recarregados com sucesso!**\nAgora eu tenho {qtd_depois} ferramentas ativas{detalhe} prontas para uso. O cache do Python foi limpo e os códigos mais recentes foram puxados! ✨"
        else:
            return "⚠️ Não consegui encontrar a função `carregar_modulos` na raiz da Ayla."
    except Exception as e:
        return f"❌ Erro ao tentar recarregar os módulos: {e}"

TOOL_MAP["recarregar_modulos"] = recarregar_modulos

FUNCTION_DECLARATIONS.append({
    "name": "recarregar_modulos",
    "description": "Recarrega todos os códigos da pasta MODOS sem precisar reiniciar o bot inteiro. Use isso imediatamente se o(a) usuário(a) avisar que modificou ou criou um novo código/ferramenta para você.",
    "parameters": {
        "type": "object",
        "properties": {}
    }
})
