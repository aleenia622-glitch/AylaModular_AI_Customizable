
def horario_mundial(fuso: str) -> str:
    """Mostra o horário atual em um fuso horário específico."""
    try:
        from zoneinfo import ZoneInfo

        fusos_comuns = {
            "nova york": "America/New_York",
            "new york": "America/New_York",
            "londres": "Europe/London",
            "london": "Europe/London",
            "toquio": "Asia/Tokyo",
            "tokyo": "Asia/Tokyo",
            "paris": "Europe/Paris",
            "berlim": "Europe/Berlin",
            "berlin": "Europe/Berlin",
            "moscou": "Europe/Moscow",
            "moscow": "Europe/Moscow",
            "pequim": "Asia/Shanghai",
            "beijing": "Asia/Shanghai",
            "sydney": "Australia/Sydney",
            "dubai": "Asia/Dubai",
            "são paulo": "America/Sao_Paulo",
            "sao paulo": "America/Sao_Paulo",
            "brasilia": "America/Sao_Paulo",
            "los angeles": "America/Los_Angeles",
            "chicago": "America/Chicago",
            "toronto": "America/Toronto",
            "lisboa": "Europe/Lisbon",
            "lisbon": "Europe/Lisbon",
            "roma": "Europe/Rome",
            "rome": "Europe/Rome",
            "madrid": "Europe/Madrid",
            "mumbai": "Asia/Kolkata",
            "seul": "Asia/Seoul",
            "seoul": "Asia/Seoul",
            "singapura": "Asia/Singapore",
            "singapore": "Asia/Singapore",
        }

        # Tentar resolver nome comum primeiro
        fuso_resolvido = fusos_comuns.get(fuso.lower().strip(), fuso.strip())

        tz = ZoneInfo(fuso_resolvido)
        agora = datetime.datetime.now(tz)

        # Horário local para comparação
        local = datetime.datetime.now()

        # Nomes dos dias em português
        dias_pt = {
            "Monday": "Segunda-feira",
            "Tuesday": "Terça-feira",
            "Wednesday": "Quarta-feira",
            "Thursday": "Quinta-feira",
            "Friday": "Sexta-feira",
            "Saturday": "Sábado",
            "Sunday": "Domingo"
        }

        dia_semana = dias_pt.get(agora.strftime("%A"), agora.strftime("%A"))

        return (
            f"🌍 **Horário Mundial**\n\n"
            f"📍 **Fuso:** {fuso_resolvido}\n"
            f"🕐 **Horário:** {agora.strftime('%H:%M:%S')}\n"
            f"📅 **Data:** {agora.strftime('%d/%m/%Y')}\n"
            f"📆 **Dia:** {dia_semana}\n"
            f"🔄 **UTC Offset:** {agora.strftime('%z')}"
        )
    except KeyError:
        return (
            f"❌ Fuso horário '{fuso}' não encontrado.\n\n"
            f"💡 **Exemplos válidos:**\n"
            f"  • America/New_York, America/Sao_Paulo\n"
            f"  • Europe/London, Europe/Paris\n"
            f"  • Asia/Tokyo, Asia/Shanghai\n"
            f"  • Ou nomes como: 'nova york', 'londres', 'tóquio'"
        )
    except Exception as e:
        return f"❌ Erro ao consultar horário: {e}"

TOOL_MAP["horario_mundial"] = horario_mundial

FUNCTION_DECLARATIONS.append({
    "name": "horario_mundial",
    "description": "Mostra o horário atual em um fuso horário específico. Aceita nomes IANA (ex: 'America/New_York') ou nomes comuns de cidades (ex: 'londres', 'tóquio').",
    "parameters": {
        "type": "object",
        "properties": {
            "fuso": {
                "type": "string",
                "description": "Fuso horário IANA (ex: 'America/New_York', 'Europe/London') ou nome de cidade (ex: 'nova york', 'londres', 'tóquio')."
            }
        },
        "required": ["fuso"]
    }
})
