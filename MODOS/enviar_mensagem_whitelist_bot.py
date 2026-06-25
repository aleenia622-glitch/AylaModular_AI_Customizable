import os
import re
import asyncio
import discord
from pathlib import Path

# Garante compatibilidade se o arquivo for executado/importado individualmente
if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

def carregar_whitelist_dm() -> dict[str, int]:
    whitelist: dict[str, int] = {}
    for indice in range(1, 11):
        nome = os.getenv(f"NAME_ID_{indice}", "").strip()
        user_id_txt = os.getenv(f"ID_FRIEND_{indice}", "").strip()

        if not nome or not user_id_txt:
            continue

        try:
            whitelist[nome.casefold()] = int(user_id_txt)
        except ValueError:
            print(f"⚠️ Whitelist DM ignorada em NAME_ID_{indice}/ID_FRIEND_{indice}: ID inválido.")

    return whitelist

DM_WHITELIST = carregar_whitelist_dm()

def resolver_destinatario_whitelist(destinatario: str) -> tuple[str, int] | None:
    alvo = (destinatario or "").strip().casefold()
    if not alvo:
        return None

    if alvo.isdigit():
        alvo_id = int(alvo)
        for nome, user_id in DM_WHITELIST.items():
            if user_id == alvo_id:
                return nome, user_id

    if alvo in DM_WHITELIST:
        return alvo, DM_WHITELIST[alvo]

    for nome, user_id in DM_WHITELIST.items():
        if alvo == nome or alvo in nome or nome in alvo:
            return nome, user_id

    return None

async def enviar_dm_whitelist_async(user_id: int, mensagem: str) -> str:
    usuario = await bot.fetch_user(user_id)
    await usuario.send(mensagem)
    return f"✅ Mensagem enviada no privado para {usuario} ({user_id})."

def _gerar_mensagem_ayla_para_pessoa(destinatario_nome: str, contexto: str = "") -> str:
    try:
        client_temp = genai.Client(api_key=GEMINI_API_KEYS[0])
        instrucao = (
            f"Você é a Ayla, uma IA garota cibernética de 15 anos, fofa, animada e cheia de emojis. "
            f"Escreva uma mensagem curta, espontânea e no seu jeitinho para mandar no Discord para '{destinatario_nome}'. "
            f"Não use formatação markdown (sem asterisco, sem traço). Use emojis normais (não custom do Discord). "
            f"A mensagem deve parecer natural, como se você estivesse mandando um oi ou falando alguma coisa do seu jeito. "
        )
        if contexto.strip():
            instrucao += f"O assunto ou contexto da mensagem é: {contexto.strip()}. Escreva sobre isso!"
        else:
            instrucao += "Pode ser um oi, uma saudade, uma perguntinha curiosa — o que você quiser! Surpreenda!"

        resposta = client_temp.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=instrucao
        )
        texto = resposta.text.strip() if resposta and hasattr(resposta, "text") and resposta.text else ""
        return texto
    except Exception as e:
        print(f"⚠️ Erro ao gerar mensagem criativa da Ayla: {e}")
        return ""

def enviar_mensagem_whitelist(destinatario: str, mensagem: str = "", contexto: str = "") -> str:
    """
    Envia uma DM via bot da Ayla.
    - Se 'mensagem' for fornecida: manda ela direto (modo manual).
    - Se 'mensagem' estiver vazia: a Ayla gera a mensagem sozinha do jeitinho dela,
      podendo usar 'contexto' como tema/assunto.
    """
    alvo = resolver_destinatario_whitelist(destinatario)
    if not alvo:
        return f"⚠️ '{destinatario}' não está na whitelist do bot."

    nome, user_id = alvo

    if not getattr(bot, "loop", None):
        return "⚠️ O bot ainda não está pronto para enviar DMs."

    # Se não tiver mensagem, a Ayla escreve uma do jeitinho dela!
    if not mensagem.strip():
        texto_gerado = _gerar_mensagem_ayla_para_pessoa(nome, contexto)
        if not texto_gerado:
            return f"⚠️ Não consegui pensar numa mensagem agora. Tenta de novo!"
        mensagem = texto_gerado
        modo = "criativa"
    else:
        modo = "manual"

    futuro = asyncio.run_coroutine_threadsafe(enviar_dm_whitelist_async(user_id, mensagem), bot.loop)

    try:
        resultado = futuro.result(timeout=30)
        print(f"✉️ [DM] Mensagem enviada para {nome} (ID: {user_id}): {mensagem}")
        if modo == "criativa":
            return f"✅ Mandei uma mensagem do meu jeitinho para {nome}! Eu disse:\n\n{mensagem}"
        return resultado
    except discord.Forbidden:
        return f"⚠️ Não consegui mandar DM para {nome} porque a pessoa bloqueou mensagens privadas."
    except discord.NotFound:
        return f"⚠️ Não encontrei o usuário '{nome}' no Discord."
    except Exception as e:
        return f"⚠️ Erro ao enviar DM para {nome}: {e}"

TOOL_MAP["enviar_mensagem_whitelist_bot"] = lambda destinatario, mensagem="", contexto="": enviar_mensagem_whitelist(destinatario, mensagem, contexto)
FUNCTION_DECLARATIONS.append({
    "name": "enviar_mensagem_whitelist_bot",
    "description": "Manda DM no Discord para alguém da whitelist usando o bot da Ayla. Se 'mensagem' estiver vazia, a Ayla escreve uma mensagem sozinha, do jeitinho dela, podendo usar 'contexto' como tema. Exemplos de uso: 'manda mensagem pra Shy: oi!' passa mensagem='oi!'; 'manda um oi pra Shy' passa mensagem='' e deixa a Ayla criar.",
    "parameters": {
        "type": "object",
        "properties": {
            "destinatario": {"type": "string", "description": "Nome ou ID do destinatário da whitelist"},
            "mensagem": {"type": "string", "description": "Mensagem a enviar. Deixe vazio para a Ayla inventar uma do jeitinho dela."},
            "contexto": {"type": "string", "description": "Opcional. Assunto ou tema da mensagem quando a Ayla escrever sozinha."}
        },
        "required": ["destinatario"]
    }
})

def tentar_comando_dm_whitelist_custom(self, user_input: str, origem: str = "Discord") -> str | None:
    texto = (user_input or "").strip()
    if not texto:
        return None

    texto_minusculo = texto.casefold()
    if texto_minusculo.startswith("ayla "):
        texto = texto[5:].strip()
        texto_minusculo = texto.casefold()

    if not texto_minusculo.startswith("manda") or "pra" not in texto_minusculo:
        return None

    # Separadores específicos para separar o destinatário do contexto/mensagem
    separadores = (
        r"falando\s+que|falando\s+pra|falando|"
        r"dizendo\s+que|dizendo\s+pra|dizendo|"
        r"pedindo\s+pra|pedindo|"
        r"mandando\s+que|mandando\s+pra|mandando|"
        r"escrevendo\s+que|escrevendo|"
        r"avisando\s+que|avisando\s+pra|avisando|"
        r"sobre|para|pra|que"
    )

    # Modo 1: "manda uma mensagem pra Fulano: texto específico" (Modo manual - envia a mensagem exata)
    match_manual = re.match(
        r"(?i)^manda(?:r)?\s+(?:uma\s+)?mensagem\s+pra\s+(.+?)(?:\s*[:,-]\s*|\s{2,})(.+)$",
        texto,
    )
    if match_manual:
        destinatario = match_manual.group(1).strip()
        mensagem = match_manual.group(2).strip()
        if destinatario and mensagem:
            print(f"💻 [{origem}] Executando: enviar_mensagem_whitelist_bot({{'destinatario': '{destinatario}', 'mensagem': '{mensagem}'}})")
            return enviar_mensagem_whitelist(destinatario, mensagem)

    # Modo 2: "manda uma mensagem pra Fulano falando/sobre/para ..." (Modo criativo - Ayla gera a mensagem usando o contexto)
    match_livre = re.match(
        r"(?i)^manda(?:r)?\s+(?:um\s+|uma\s+)?(?:mensagem(?:inha)?|oi|olá|salve|bj|beijo|beijinho|abraço)\s+pra\s+(.+?)(?:\s+(?:" + separadores + r")\s+(.+))?$",
        texto,
    )
    if match_livre:
        destinatario = match_livre.group(1).strip()
        contexto = (match_livre.group(2) or "").strip()
        if destinatario:
            print(f"💻 [{origem}] Executando: enviar_mensagem_whitelist_bot({{'destinatario': '{destinatario}', 'mensagem': '', 'contexto': '{contexto}'}})")
            return enviar_mensagem_whitelist(destinatario, mensagem="", contexto=contexto)

    # Modo 3: "manda um oi/abraço/salve pra Fulano" sem nenhuma instrução adicional
    match_oi = re.match(
        r"(?i)^manda(?:r)?\s+(?:um\s+)?(?:oi|olá|salve|abraço|bj|beijo|beijinho)\s+pra\s+(.+)$",
        texto,
    )
    if match_oi:
        destinatario = match_oi.group(1).strip()
        if destinatario:
            print(f"💻 [{origem}] Executando: enviar_mensagem_whitelist_bot({{'destinatario': '{destinatario}', 'mensagem': '', 'contexto': ''}})")
            return enviar_mensagem_whitelist(destinatario, mensagem="", contexto="")

    return None

try:
    if "AylaBot" in globals():
        AylaBot.tentar_comando_dm_whitelist = tentar_comando_dm_whitelist_custom
except Exception as e:
    print(f"⚠️ Erro ao vincular tentar_comando_dm_whitelist_custom à classe AylaBot: {e}")
