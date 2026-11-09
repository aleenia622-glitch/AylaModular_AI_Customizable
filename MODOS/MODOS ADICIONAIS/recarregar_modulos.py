"""Recarrega os módulos da Ayla sem reiniciar o bot."""
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
        from pathlib import Path
        import runpy
        root = Path(__file__).resolve().parent.parent.parent
        # A view identifica a instância real, mesmo com Ayla.py antigo na RAM.
        manager = getattr(TOOL_MAP, 'manager', None)
        if manager is None:
            return "⚠️ Não consegui encontrar o gerenciador de módulos ativo da Ayla."
        namespace = runpy.run_path(str(root / 'ayla_module_reload.py'))
        count = namespace['reload_active_manager'](manager)
        return (f"🔄 Recarga concluída: {count} ferramentas ativas. "
                "Gerenciador, funções da interação atual e .env atualizados do disco. "
                "Serviços contínuos em execução foram preservados.")
    except Exception as e:
        return f"❌ Erro ao tentar recarregar os módulos: {e}"

TOOL_MAP["recarregar_modulos"] = recarregar_modulos

FUNCTION_DECLARATIONS.append({
    "name": "recarregar_modulos",
    "description": "Recarrega dinamicamente todos os módulos Python da pasta MODOS.",
    "parameters": {
        "type": "object",
        "properties": {}
    }
})
