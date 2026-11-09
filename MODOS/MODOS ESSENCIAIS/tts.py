"""Converte texto na voz da Ayla e envia o áudio no Discord."""
import sys
import discord
from pathlib import Path

PASTA_RAIZ = Path(__file__).resolve().parents[2]
if str(PASTA_RAIZ) not in sys.path:
    sys.path.append(str(PASTA_RAIZ))

def converter_texto_para_audio_discord(texto: str, tom: str = "normal") -> str:
    """
    Gera um arquivo de áudio WAV usando Fish Audio e o envia no Discord.
    O parâmetro tom é mantido por compatibilidade; a voz vem das configurações.
    Se a Ayla estiver conectada em uma call na guilda atual, ela também falará ao vivo na call!
    """
    try:
        import json

        # Filtra emojis usando a função global injetada pela Ayla
        if "filtrar_emojis_ayla" in globals():
            texto_limpo = filtrar_emojis_ayla(texto)
        else:
            # Fallback local com remoção de emojis Unicode, Discord e Markdown
            import re
            texto_limpo = re.sub(r'<a?:[a-zA-Z0-9_]+:[0-9]+>', '', texto)
            texto_filtrado = re.sub(r'[%&][^%&\n]+[%&]', '', texto_limpo)
            texto_limpo = re.sub(r'[*_`#~>|]', '', texto_filtrado)
            texto_limpo = re.sub(
                r'[\U00010000-\U0010ffff]|[\u2600-\u27bf]|[\u2300-\u23ff]|[\u2b50-\u2b55]|[\ufe00-\ufe0f]|[\u200d]',
                '',
                texto_limpo
            )
            texto_limpo = re.sub(r'\s+', ' ', texto_limpo).strip()

        if not texto_limpo.strip():
            return "🥺 Desculpinha! O texto enviado para o áudio ficou vazio."

        audio_bytes = None

        # Carrega as configurações da Ayla para obter chaves e motores TTS
        settings = {}
        try:
            settings_path = PASTA_RAIZ / "ayla_settings.json"
            if settings_path.exists():
                with open(settings_path, "r", encoding="utf-8") as sf:
                    settings = json.load(sf)
        except Exception as se:
            print(f"[Fish Audio] Erro ao carregar ayla_settings.json: {se}")

        # Se estiver em uma chamada de voz (Discord-Call), bloqueia o TTS duplicado
        import ayla_state
        try:
            if hasattr(ayla_state, "listar_tarefas_detalhadas"):
                tarefas = ayla_state.listar_tarefas_detalhadas()
            elif hasattr(ayla_state, "LISTA_TAREFAS"):
                tarefas = ayla_state.LISTA_TAREFAS
            else:
                tarefas = []
            is_call = any(
                (t.get("origem") if isinstance(t, dict) else getattr(t, "origem", "")) == "Discord-Call"
                and (t.get("status") if isinstance(t, dict) else getattr(t, "status", "executando")) == "executando"
                for t in (tarefas or [])
            )
            if is_call:
                return "🎙️ [AVISO DO SISTEMA: Você já está em uma chamada de voz ao vivo! Não use a ferramenta 'tts' aqui, pois o que você responder no texto normal já será falado automaticamente na call.]"
        except Exception as e_chk:
            print(f"[TTS] Aviso ao verificar tarefas ativas: {e_chk}")

        # Usa o mesmo gerador Fish Audio das chamadas de voz.
        try:
            from ayla_live import generate_tts_audio
            audio_bytes = generate_tts_audio(texto_limpo, settings)
        except Exception as ge:
            print(f"[TTS Discord] Erro ao usar generate_tts_audio: {ge}")

        if audio_bytes is None:
            return "🥺 Desculpinha! Tentei usar minha vozinha para falar com você, mas meu sintetizador de fala deu um probleminha! Podemos conversar por texto por enquanto? 🩵"
            
        PASTA_AYLA = PASTA_RAIZ / "audio_output"
        PASTA_AYLA.mkdir(parents=True, exist_ok=True)
        from datetime import datetime as dt
        caminho = str(PASTA_AYLA / f"Ayla_audio_{dt.now().strftime('%Y%m%d_%H%M%S')}.wav")
        with open(caminho, "wb") as f:
            f.write(audio_bytes)
            
        # Sinaliza para o Discord enviar o arquivo
        ayla_state.ULTIMA_IMAGEM_GERADA.set(str(caminho))

        # Se a Ayla estiver conectada em uma call no servidor atual, reproduz o áudio na chamada
        tocado_na_call = False
        ctx = ayla_state.CONTEXTO_ATIVO.get() if "ayla_state" in globals() else None
        if ctx:
            guild_obj = getattr(ctx, "guild", None)
            if guild_obj and "tocar_audio_na_call" in globals():
                try:
                    tocado_na_call = tocar_audio_na_call(guild_obj.id, caminho)
                except Exception as e_call:
                    print(f"⚠️ Erro ao tentar tocar áudio na call: {e_call}")

        if tocado_na_call:
            retorno = f"🎙️ Áudio gerado e reproduzido ao vivo na chamada de voz do Discord: {caminho}"
        else:
            retorno = f"🎙️ Áudio gerado e pronto pra mandar no Discord: {caminho}"
        return retorno
        
    except Exception as e:
        return f"❌ Erro ao converter texto em áudio: {e}"

def register(tool_map: dict, function_declarations: list):
    tool_map["tts"] = converter_texto_para_audio_discord
    tool_map["converter_texto_para_audio_discord"] = converter_texto_para_audio_discord
    
    for i in range(len(function_declarations) - 1, -1, -1):
        if function_declarations[i].get("name") in ("converter_texto_para_audio_discord", "tts"):
            function_declarations.pop(i)

    function_declarations.append({
        "name": "tts",
        "description": "Gera áudio WAV com a voz da Ayla a partir de um texto e envia no Discord.",
        "parameters": {
            "type": "object",
            "properties": {
                "texto": {"type": "string", "description": "O texto que a Ayla irá falar."},
                "tom": {
                    "type": "string",
                    "enum": ["normal", "sweet", "calmo", "tsuntsun", "bravo", "sexy", "whisper", "sussurrando", "whisper_mumble", "murmurando", "cansado", "chorando"],
                    "description": "Parâmetro legado de compatibilidade. A voz utilizada é a configurada no Fish Audio."
                }
            },
            "required": ["texto"]
        }
    })

# Execução no carregamento
if "TOOL_MAP" in globals() and "FUNCTION_DECLARATIONS" in globals():
    register(TOOL_MAP, FUNCTION_DECLARATIONS)
