"""
🐍 Módulo: Criação de Scripts Python
Permite que a Ayla escreva códigos Python (.py) e os salve em uma pasta específica.
"""

import os
from pathlib import Path

def criar_python(nome_arquivo: str, codigo: str) -> str:
    """
    Cria um arquivo Python (.py) com o código fornecido.
    
    Args:
        nome_arquivo (str): Nome do arquivo (ex: 'meu_script.py'). Se não terminar em .py, será adicionado.
        codigo (str): O código fonte Python a ser escrito no arquivo.
    """
    try:
        nome_original = (nome_arquivo or "").strip()
        if (
            not nome_original
            or Path(nome_original).is_absolute()
            or any(parte == ".." for parte in Path(nome_original).parts)
            or "/" in nome_original
            or "\\" in nome_original
        ):
            return "⚠️ Use apenas o nome do arquivo, sem caminho, subpastas ou '..'."

        # Garante que o nome do arquivo termine com .py
        nome_arquivo = nome_original
        if not nome_arquivo.lower().endswith(".py"):
            nome_arquivo += ".py"

        # Define a pasta de saída (mesma lógica de organização da Ayla)
        # Salva em uma pasta chamada 'ScriptsCriados' para não bagunçar a raiz
        projeto_raiz = Path(__file__).resolve().parent.parent
        pasta_scripts = projeto_raiz / "ScriptsCriados"
        pasta_scripts.mkdir(parents=True, exist_ok=True)
        
        caminho_final = pasta_scripts / nome_arquivo

        # Escreve o código no arquivo com encoding UTF-8
        with open(caminho_final, "w", encoding="utf-8") as f:
            f.write(codigo)

        return (
            f"✅ Código Python criado com sucesso!\n"
            f"📁 Arquivo: {nome_arquivo}\n"
            f"📍 Salvo em: {caminho_final}\n"
            f"🚀 Agora é só rodar o script!"
        )

    except Exception as e:
        return f"❌ Erro ao criar o arquivo Python: {e}"

# ── Registro da ferramenta ──
TOOL_MAP["criar_python"] = criar_python
FUNCTION_DECLARATIONS.append({
    "name": "criar_python",
    "description": (
        "Cria um arquivo de script Python (.py) com o código fornecido. "
        "Use isso para escrever automações, scripts de utilidade ou qualquer código Python para a Alêenia."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "nome_arquivo": {
                "type": "string",
                "description": "O nome do arquivo a ser criado (ex: 'calculadora.py')."
            },
            "codigo": {
                "type": "string",
                "description": "O código Python completo que deve ser escrito no arquivo."
            }
        },
        "required": ["nome_arquivo", "codigo"]
    }
})
