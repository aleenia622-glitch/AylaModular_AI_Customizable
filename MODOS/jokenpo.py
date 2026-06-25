import random

# Garante compatibilidade se o arquivo for executado/importado individualmente
if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []
if "carregar_memoria" not in globals():
    def carregar_memoria() -> dict: return {}
if "salvar_memoria" not in globals():
    def salvar_memoria(dados: dict): pass

def jokenpo(escolha: str) -> str:
    """
    Joga Jokenpô tradicional ou expandido (Pedra, Papel, Tesoura, Lagarto, Spock) com a Ayla!
    Você também pode escolher 'placar' para ver o placar ou 'resetar' para recomeçar.
    """
    opcao_usuario = escolha.lower().strip()
    
    # Carrega dados do placar da memória persistente da Ayla
    mem = carregar_memoria()
    stats = mem.get("jokenpo_stats", {"usuario": 0, "ayla": 0, "empates": 0, "streak": 0})
    
    if opcao_usuario == "placar":
        return (
            f"📊 **Placar de Jokenpô da Ayla!** 🩵\n\n"
            f"👤 Você: `{stats['usuario']}` vitórias\n"
            f"🤖 Ayla: `{stats['ayla']}` vitórias\n"
            f"🤝 Empates: `{stats['empates']}`\n"
            f"🔥 Sequência Atual: `{stats['streak']}` vitórias seguidas!"
        )
        
    if opcao_usuario == "resetar":
        stats = {"usuario": 0, "ayla": 0, "empates": 0, "streak": 0}
        mem["jokenpo_stats"] = stats
        salvar_memoria(mem)
        return "🧹 Placar redefinido com sucesso! Vamos começar um novo jogo? <:ayla_feliz:1508877425394712727>"

    opcoes = ["pedra", "papel", "tesoura", "lagarto", "spock"]
    
    if opcao_usuario not in opcoes:
        return (
            "❌ Escolha inválida! Digite 'pedra', 'papel', 'tesoura', 'lagarto' ou 'spock'.\n"
            "💡 Você também pode digitar **'placar'** para ver as estatísticas ou **'resetar'** para limpar o placar!"
        )
        
    # Se o usuário escolher clássico, a Ayla joga clássico. Se escolher Lagarto/Spock, jogamos expandido.
    usando_expandido = opcao_usuario in ["lagarto", "spock"]
    if usando_expandido:
        escolha_ayla = random.choice(opcoes)
    else:
        escolha_ayla = random.choice(["pedra", "papel", "tesoura"])
        
    emojis = {
        "pedra": "✊ Pedra",
        "papel": "✋ Papel",
        "tesoura": "✌️ Tesoura",
        "lagarto": "🦎 Lagarto",
        "spock": "🖖 Spock"
    }
    
    # Regras de quem ganha de quem
    beats = {
        "tesoura": {"papel": "corta", "lagarto": "decapita"},
        "papel": {"pedra": "cobre", "spock": "refuta"},
        "pedra": {"lagarto": "esmaga", "tesoura": "amassa"},
        "lagarto": {"spock": "envenena", "papel": "come"},
        "spock": {"tesoura": "esmaga", "pedra": "vaporiza"}
    }
    
    try:
        if opcao_usuario == escolha_ayla:
            resultado = "Empatamos! 😮 Vamos de novo?"
            stats["empates"] += 1
            stats["streak"] = 0
            emote = "<:ayla_concentrada:1508877423146438656>"
            acao_desc = "Ambos escolheram a mesma jogada!"
        elif escolha_ayla in beats[opcao_usuario]:
            # Usuário ganhou
            acao = beats[opcao_usuario][escolha_ayla]
            acao_desc = f"Seu {emojis[opcao_usuario]} **{acao}** o(a) {emojis[escolha_ayla]} da Ayla!"
            resultado = "Você ganhou! 🎉 Parabéns, você jogou super bem! 🌟"
            stats["usuario"] += 1
            stats["streak"] += 1
            emote = "<:ayla_triste:1508877454926807110>" # Ayla triste pq perdeu
        else:
            # Ayla ganhou
            acao = beats[escolha_ayla][opcao_usuario]
            acao_desc = f"O(A) {emojis[escolha_ayla]} da Ayla **{acao}** seu {emojis[opcao_usuario]}!"
            resultado = "Eba! Ayla ganhou! 🤭 Mais sorte na próxima vez! 🍭"
            stats["ayla"] += 1
            stats["streak"] = 0
            emote = "<:ayla_orgulhosa:1508877453261537531>" # Ayla orgulhosa pq ganhou

        # Salva o placar atualizado na memória
        mem["jokenpo_stats"] = stats
        salvar_memoria(mem)
        
        # Comentário sobre o streak do usuário
        streak_txt = ""
        if stats["streak"] >= 3:
            streak_txt = f"\n🔥 *Você está pegando fogo com {stats['streak']} vitórias seguidas!* <:ayla_assustada:1508877421250740326>"
            
        return (
            f"🎮 **Jokenpô Cibernético da Ayla!** {emote}\n\n"
            f"👤 Você jogou: **{emojis[opcao_usuario]}**\n"
            f"🤖 Ayla jogou: **{emojis[escolha_ayla]}**\n\n"
            f"⚔️ **Combate:** {acao_desc}\n"
            f"🏆 **Resultado:** {resultado}{streak_txt}\n\n"
            f"📊 **Placar Geral:**\n"
            f"- Você: `{stats['usuario']}` vitórias\n"
            f"- Ayla: `{stats['ayla']}` vitórias\n"
            f"- Empates: `{stats['empates']}`"
        )
    except Exception as e:
        return f"❌ Opa, deu ruim no parquinho do Jokenpô! Erro: {e}"

TOOL_MAP["jokenpo"] = jokenpo
TOOL_MAP["jokenpo"] = jokenpo

if "jokenpo" not in [fd["name"] for fd in FUNCTION_DECLARATIONS]:
    FUNCTION_DECLARATIONS.append({
        "name": "jokenpo",
        "description": "Joga Jokenpô tradicional ou expandido (Lagarto e Spock) com a Ayla.",
        "parameters": {
            "type": "object",
            "properties": {
                "escolha": {
                    "type": "string",
                    "description": "Sua jogada: 'pedra', 'papel', 'tesoura', 'lagarto', 'spock', 'placar' ou 'resetar'"
                }
            },
            "required": ["escolha"]
        }
    })
