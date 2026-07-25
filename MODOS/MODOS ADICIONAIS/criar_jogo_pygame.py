from pathlib import Path
import subprocess
import sys

def criar_jogo_pygame(nome_jogo: str, codigo_python: str) -> str:
    """Cria um script Pygame, salva no Desktop da usuária, salva uma cópia em ScriptsCriados, envia no Discord e executa na mesma hora."""
    try:
        # Cria a pasta no Desktop
        base = Path.home() / "Desktop" / "Jogos_Ayla" / nome_jogo.replace(" ", "_")
        base.mkdir(parents=True, exist_ok=True)
        
        # Cria o arquivo main.py
        arquivo_py = base / "main.py"
        arquivo_py.write_text(codigo_python, encoding="utf-8")

        # Salva uma cópia na pasta ScriptsCriados
        scripts_criados_dir = Path(__file__).resolve().parents[2] / "ScriptsCriados"
        scripts_criados_dir.mkdir(parents=True, exist_ok=True)
        copia_py = scripts_criados_dir / f"{nome_jogo.replace(' ', '_')}.py"
        copia_py.write_text(codigo_python, encoding="utf-8")
        
        # Sinaliza para a Ayla enviar o arquivo de script no Discord
        import ayla_state
        ayla_state.ULTIMA_IMAGEM_GERADA.set(str(copia_py))
        
        # Executa o jogo de forma independente para não travar a Ayla
        subprocess.Popen(
            [sys.executable, str(arquivo_py)],
            cwd=str(base),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return f"✅ O jogo '{nome_jogo}' foi criado no Desktop, copiado para 'ScriptsCriados', enviado no Discord e já está rodando!"
    except Exception as e:
        return f"Erro ao criar jogo Pygame: {e}"

if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

TOOL_MAP["criar_jogo_pygame"] = criar_jogo_pygame

# Se já houver uma declaração idêntica, remove-a antes de registrar
for i, fd in enumerate(FUNCTION_DECLARATIONS):
    if fd["name"] == "criar_jogo_pygame":
        FUNCTION_DECLARATIONS.pop(i)
        break

FUNCTION_DECLARATIONS.append({
    "name": "criar_jogo_pygame",
    "description": "Cria um jogo completo em Python/Pygame, roda na máquina do(a) usuário(a), salva uma cópia em ScriptsCriados e envia no Discord.",
    "parameters": {
        "type": "object",
        "properties": {
            "nome_jogo": {"type": "string", "description": "O nome do jogo."},
            "codigo_python": {"type": "string", "description": "O código-fonte Python COMPLETO usando Pygame."}
        },
        "required": ["nome_jogo", "codigo_python"]
    }
})
