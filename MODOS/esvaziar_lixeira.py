
def esvaziar_lixeira():
    """Esvazia a Lixeira do Windows."""
    try:
        resultado = subprocess.run(
            ['powershell', '-NoProfile', '-Command', 'Clear-RecycleBin -Force -ErrorAction Stop'],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30
        )

        if resultado.returncode == 0:
            return "🗑️ Lixeira esvaziada com sucesso! ✨"
        else:
            erro = resultado.stderr.strip()
            if "porque está vazi" in erro.lower() or "empty" in erro.lower() or "is empty" in erro.lower():
                return "🗑️ A Lixeira já estava vazia!"
            return f"❌ Erro ao esvaziar lixeira: {erro}"

    except subprocess.TimeoutExpired:
        return "❌ Tempo esgotado ao tentar esvaziar a lixeira."
    except Exception as e:
        return f"❌ Erro ao esvaziar lixeira: {e}"

TOOL_MAP["esvaziar_lixeira"] = esvaziar_lixeira

FUNCTION_DECLARATIONS.append({
    "name": "esvaziar_lixeira",
    "description": "Esvazia a Lixeira do Windows permanentemente.",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": []
    }
})
