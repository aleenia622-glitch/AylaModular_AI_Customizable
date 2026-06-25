def criar_jogo_pygame(nome_jogo: str, codigo_python: str) -> str:
    """Cria um script Pygame, salva no Desktop da usuária e executa na mesma hora."""
    try:
        # Cria a pasta no Desktop
        base = Path.home() / "Desktop" / "Jogos_Ayla" / nome_jogo.replace(" ", "_")
        base.mkdir(parents=True, exist_ok=True)
        
        # Cria o arquivo main.py
        arquivo_py = base / "main.py"
        arquivo_py.write_text(codigo_python, encoding="utf-8")
        
        # Executa o jogo de forma independente para não travar a Ayla
        subprocess.Popen(
            [sys.executable, str(arquivo_py)],
            cwd=str(base),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return f"✅ O jogo '{nome_jogo}' foi criado com sucesso, salvo em '{base}' e já está rodando!"
    except Exception as e:
        return f"Erro ao criar jogo Pygame: {e}"

TOOL_MAP["criar_jogo_pygame"] = criar_jogo_pygame
FUNCTION_DECLARATIONS.append({"name": "criar_jogo_pygame", "description": "Cria um jogo completo em Python/Pygame e roda na máquina da Alêenia.", "parameters": {"type": "object", "properties": {"nome_jogo": {"type": "string", "description": "O nome do jogo."}, "codigo_python": {"type": "string", "description": "O código-fonte Python COMPLETO usando Pygame."}}, "required": ["nome_jogo", "codigo_python"]}})
