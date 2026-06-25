# cronometro.py - Cronômetro com persistência em arquivo temporário

def cronometro(acao):
    """Cronômetro: iniciar, parar ou ver o tempo decorrido."""
    try:
        import tempfile
        acao = acao.strip().lower()
        arquivo_temp = os.path.join(tempfile.gettempdir(), "ayla_cronometro.json")

        if acao == "iniciar":
            dados = {"inicio": datetime.datetime.now().isoformat(), "rodando": True}
            with open(arquivo_temp, "w", encoding="utf-8") as f:
                json.dump(dados, f)
            return "⏱️ Cronômetro iniciado!"

        elif acao == "parar":
            if not os.path.exists(arquivo_temp):
                return "❌ Nenhum cronômetro em andamento."
            with open(arquivo_temp, "r", encoding="utf-8") as f:
                dados = json.load(f)
            if not dados.get("rodando", False):
                return "❌ O cronômetro já está parado."
            inicio = datetime.datetime.fromisoformat(dados["inicio"])
            fim = datetime.datetime.now()
            elapsed = fim - inicio
            total_seconds = int(elapsed.total_seconds())
            horas = total_seconds // 3600
            minutos = (total_seconds % 3600) // 60
            segundos = total_seconds % 60
            milissegundos = elapsed.microseconds // 1000
            dados["rodando"] = False
            dados["fim"] = fim.isoformat()
            dados["elapsed"] = str(elapsed)
            with open(arquivo_temp, "w", encoding="utf-8") as f:
                json.dump(dados, f)
            return f"⏱️ Cronômetro parado!\n\nTempo decorrido: {horas:02d}:{minutos:02d}:{segundos:02d}.{milissegundos:03d}"

        elif acao == "ver":
            if not os.path.exists(arquivo_temp):
                return "❌ Nenhum cronômetro em andamento."
            with open(arquivo_temp, "r", encoding="utf-8") as f:
                dados = json.load(f)
            if not dados.get("rodando", False):
                if "elapsed" in dados:
                    return f"⏱️ Cronômetro parado. Último tempo: {dados['elapsed']}"
                return "❌ O cronômetro não está rodando."
            inicio = datetime.datetime.fromisoformat(dados["inicio"])
            agora = datetime.datetime.now()
            elapsed = agora - inicio
            total_seconds = int(elapsed.total_seconds())
            horas = total_seconds // 3600
            minutos = (total_seconds % 3600) // 60
            segundos = total_seconds % 60
            return f"⏱️ Cronômetro rodando...\n\nTempo atual: {horas:02d}:{minutos:02d}:{segundos:02d}"

        else:
            return f"❌ Ação desconhecida: '{acao}'. Use: iniciar, parar ou ver."
    except Exception as e:
        return f"❌ Erro no cronômetro: {e}"

TOOL_MAP["cronometro"] = cronometro

FUNCTION_DECLARATIONS.append({
    "name": "cronometro",
    "description": "Cronômetro: iniciar, parar ou ver o tempo decorrido.",
    "parameters": {
        "type": "object",
        "properties": {
            "acao": {
                "type": "string",
                "description": "Ação do cronômetro: 'iniciar', 'parar' ou 'ver'.",
                "enum": ["iniciar", "parar", "ver"]
            }
        },
        "required": ["acao"]
    }
})
