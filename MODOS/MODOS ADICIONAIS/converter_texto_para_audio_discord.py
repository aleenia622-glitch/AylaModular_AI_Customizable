import sys
import discord
from pathlib import Path

# Adiciona o diretório da pasta 'voicevox' ao sys.path para importação
ARQUIVO_ATUAL = Path(__file__).resolve()
PASTA_RAIZ = ARQUIVO_ATUAL.parents[2] if len(ARQUIVO_ATUAL.parents) > 2 else ARQUIVO_ATUAL.parent
pasta_voicevox = PASTA_RAIZ / "voicevox"
if not pasta_voicevox.exists():
    for parent in ARQUIVO_ATUAL.parents:
        if (parent / "voicevox").exists():
            pasta_voicevox = parent / "voicevox"
            PASTA_RAIZ = parent
            break

if str(pasta_voicevox) not in sys.path:
    sys.path.append(str(pasta_voicevox))

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
    Gera um arquivo de áudio WAV usando Fish Audio (ou Voicevox como fallback)
    com o tom de voz especificado e o envia no Discord.
    Se a Ayla estiver conectada em uma call na guilda atual, ela também falará ao vivo na call!
    """
    try:
        import os
        import json
        import requests

        # Resolve o tom usando o mapeamento (case-insensitive) para o Voicevox fallback
        tom_key = str(tom).lower().strip()
        voice_id_voicevox = tons_map.get(tom_key, 3) # Se não encontrar, padrão é 3 (normal)
        
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

        audio_bytes = None

        # Carrega as configurações da Ayla para obter chaves do Fish Audio
        settings = {}
        try:
            settings_path = PASTA_RAIZ / "ayla_settings.json"
            if settings_path.exists():
                with open(settings_path, "r", encoding="utf-8") as sf:
                    settings = json.load(sf)
        except Exception as se:
            print(f"[Fish Audio] Erro ao carregar ayla_settings.json: {se}")

        # Pega a chave e voz do json, com fallback ao env
        fish_key = settings.get("fish_audio_api_key", "").strip()
        if not fish_key:
            try:
                from dotenv import load_dotenv
                load_dotenv(PASTA_RAIZ / ".env", override=True)
            except Exception:
                pass
            fish_key = os.getenv("FISH_AUDIO_API_KEY", "").strip()

        fish_voice_id = settings.get("fish_audio_voice_id", "").strip()
        if not fish_voice_id:
            try:
                from dotenv import load_dotenv
                load_dotenv(PASTA_RAIZ / ".env", override=True)
            except Exception:
                pass
            fish_voice_id = os.getenv("FISH_AUDIO_VOICE_ID", "").strip()

        # Tenta usar o Fish Audio se a chave estiver configurada
        if fish_key:
            try:
                url = "https://api.fish.audio/v1/tts"
                headers = {
                    "Authorization": f"Bearer {fish_key}",
                    "Content-Type": "application/json",
                    "model": "s2.1-pro-free"
                }
                payload = {
                    "text": texto_limpo,
                    "format": "wav",
                    "model": "s2.1-pro-free"
                }
                if fish_voice_id:
                    payload["reference_id"] = fish_voice_id

                print(f"[Fish Audio] Enviando requisicao para Fish Audio TTS...")
                response = requests.post(url, headers=headers, json=payload, timeout=20)
                if response.status_code == 200:
                    audio_bytes = response.content
                    print("[Fish Audio] Audio gerado com sucesso via Fish Audio!")
                else:
                    print(f"[Fish Audio] Erro na API do Fish Audio (Status {response.status_code}): {response.text}")
            except Exception as exc:
                print(f"[Fish Audio] Excecao na chamada do Fish Audio: {exc}")

        # Fallback para Voicevox se a geração do Fish Audio falhar ou não estiver configurada
        if audio_bytes is None:
            print("[Fish Audio] Fallback: Gerando audio via Voicevox local...")
            audio_bytes = vv_tts(texto_limpo, style_id=voice_id_voicevox)

        if audio_bytes is None:
            return "🥺 Desculpinha! Tentei usar minha vozinha para falar com você, mas meu sintetizador de fala deu um probleminha! Podemos conversar por texto por enquanto? 🩵"
            
        PASTA_AYLA = Path(r"C:\Users\Aleenia\Documents\AI\Aylafotitos")
        PASTA_AYLA.mkdir(parents=True, exist_ok=True)
        from datetime import datetime as dt
        caminho = str(PASTA_AYLA / f"Ayla_audio_{dt.now().strftime('%Y%m%d_%H%M%S')}.wav")
        with open(caminho, "wb") as f:
            f.write(audio_bytes)
            
        # Sinaliza para o Discord enviar o arquivo
        import ayla_state
        ayla_state.ULTIMA_IMAGEM_GERADA.set(str(caminho))
        
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
    "description": "Gera um arquivo de áudio WAV com a voz da Ayla usando Fish Audio (ou Voicevox como fallback) e o envia no Discord (e fala na call se estiver conectada). Use isso sempre que te pedirem para falar, mandar áudio, ler em voz alta ou falar na call.",
    "parameters": {
        "type": "object",
        "properties": {
            "texto": {"type": "string", "description": "O texto que a Ayla irá falar."},
            "tom": {
                "type": "string",
                "enum": ["normal", "sweet", "calmo", "tsuntsun", "bravo", "sexy", "whisper", "sussurrando", "whisper_mumble", "murmurando", "cansado", "chorando"],
                "description": "O tom de voz com o qual você (Ayla) vai falar (aplicável principalmente no fallback do Voicevox). Escolha o que combina melhor com seu sentimento atual (ex: 'sweet' se estiver muito feliz/fofa, 'tsuntsun' se estiver braba ou birrenta, 'whisper' para segredos, etc.). Padrão: 'normal'."
            }
        },
        "required": ["texto"]
    }
})
