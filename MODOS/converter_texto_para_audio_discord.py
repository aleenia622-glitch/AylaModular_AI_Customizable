import sys
import discord
from pathlib import Path

# Adiciona o diretório da pasta 'voicevox' ao sys.path para importação
PASTA_RAIZ = Path(__file__).resolve().parent.parent
pasta_voicevox = str(PASTA_RAIZ / "voicevox")
if pasta_voicevox not in sys.path:
    sys.path.append(pasta_voicevox)

# Importa o gerador de áudio diretamente do voicevox.falar_texto
from falar_texto import gerar_audio_voicevox_bytes as vv_tts

# Mapeamento de tons (nome) para IDs de voz no Voicevox
# Suporta variantes em português e em inglês (conforme instruções da Ayla)
tons_map = {
    "normal": 3,
    "sweet": 1,
    "calmo": 1,
    "tsuntsun": 7,
    "bravo": 7,
    "sexy": 5,
    "whisper": 22,
    "sussurrando": 22,
    "whisper_mumble": 38,
    "murmurando": 38,
    "cansado": 75,
    "chorando": 76,
}

def converter_texto_para_audio_discord(texto: str, tom: str = "normal") -> str:
    """
    Gera um arquivo de áudio com Voicevox usando o tom de voz especificado e o envia no Discord.
    Se a Ayla estiver conectada em uma call na guilda atual, ela também falará ao vivo na call!
    """
    global ULTIMA_IMAGEM_GERADA, CONTEXTO_ATIVO
    try:
        # Resolve o tom usando o mapeamento (case-insensitive)
        tom_key = str(tom).lower().strip()
        voice_id = tons_map.get(tom_key, 3) # Se não encontrar, padrão é 3 (normal)
        
        # Filtra emojis usando a função global injetada pela Ayla
        if "filtrar_emojis_ayla" in globals():
            texto_limpo = filtrar_emojis_ayla(texto)
        else:
            # Fallback local simples para remover emojis/markdown básicos
            import re
            texto_limpo = re.sub(r'<a?:[a-zA-Z0-9_]+:[0-9]+>', '', texto)
            texto_limpo = re.sub(r'[*_`#~]', '', texto_limpo)
            texto_limpo = re.sub(r'\s+', ' ', texto_limpo).strip()

        if not texto_limpo.strip():
            return "🥺 Desculpinha! O texto enviado para o áudio ficou vazio."

        # Gera os bytes do áudio usando o Voicevox
        audio_bytes = vv_tts(texto_limpo, style_id=voice_id)
        if audio_bytes is None:
            return "🥺 Desculpinha! Tentei usar minha vozinha para falar com você, mas meu sintetizador de fala Voicevox deu um probleminha! Podemos conversar por texto por enquanto? 🩵"
            
        projeto_raiz = Path(__file__).resolve().parent.parent
        PASTA_AYLA = projeto_raiz / "Aylafotitos"
        PASTA_AYLA.mkdir(parents=True, exist_ok=True)
        from datetime import datetime as dt
        caminho = str(PASTA_AYLA / f"Ayla_audio_{dt.now().strftime('%Y%m%d_%H%M%S')}.wav")
        with open(caminho, "wb") as f:
            f.write(audio_bytes)
            
        # Sinaliza para o Discord enviar o arquivo
        ULTIMA_IMAGEM_GERADA = caminho
        
        retorno = f"🎙️ Áudio gerado e pronto pra mandar no Discord: {caminho}"
        return retorno
        
    except Exception as e:
        return f"❌ Erro ao converter texto em áudio: {e}"

TOOL_MAP["converter_texto_para_audio_discord"] = converter_texto_para_audio_discord

# Atualiza a declaração se já existir ou adiciona se for nova
for i, fd in enumerate(FUNCTION_DECLARATIONS):
    if fd["name"] == "converter_texto_para_audio_discord":
        FUNCTION_DECLARATIONS.pop(i)
        break

FUNCTION_DECLARATIONS.append({
    "name": "converter_texto_para_audio_discord",
    "description": "Gera um arquivo de áudio WAV com a voz da Ayla usando Voicevox e o envia no Discord (e fala na call se estiver conectada). Use isso sempre que te pedirem para falar, mandar áudio, ler em voz alta ou falar na call.",
    "parameters": {
        "type": "object",
        "properties": {
            "texto": {"type": "string", "description": "O texto que a Ayla irá falar."},
            "tom": {
                "type": "string",
                "enum": ["normal", "sweet", "calmo", "tsuntsun", "bravo", "sexy", "whisper", "sussurrando", "whisper_mumble", "murmurando", "cansado", "chorando"],
                "description": "O tom de voz com o qual você (Ayla) vai falar. Escolha o que combina melhor com seu sentimento atual (ex: 'sweet' se estiver muito feliz/fofa, 'tsuntsun' se estiver braba ou birrenta, 'whisper' para segredos, etc.). Padrão: 'normal'."
            }
        },
        "required": ["texto"]
    }
})
