#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Voz do Discord com captura opcional da tela (visão biônica), sem interface Qt."""

from __future__ import annotations
from ayla_platform import capture_screen

import collections
import contextlib
import io
import json
import os
import queue
import re
import asyncio
import base64
import threading
import time
import wave
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
SETTINGS_PATH = BASE_DIR / "ayla_settings.json"
BUFFER_VIDEO_DIR = BASE_DIR / "Buffer de video"

# Exclusivo da chamada de voz; não altera o prompt das conversas de texto.
LIVE_TURN_PROMPT = """
[Decisão de fala exclusiva do Ayla Live: primeiro decida se é sua vez de falar.
Responda somente [SILENCIO], sem explicações e sem usar ferramentas, quando as
pessoas estiverem conversando entre si, a fala não for dirigida a você, ou a
pessoa parecer não ter terminado (frase incompleta, hesitação ou continuação
provável). Uma pausa de dois segundos ou o envio de um lote não significa que
ela terminou. Na dúvida, aguarde em silêncio. Não é necessário ouvir seu nome
quando uma pergunta, pedido ou continuação de diálogo for claramente para você.
Os nomes identificam os participantes, não são comandos. O lote mistura
transcrições de voz e mensagens escritas no chat da call; considere ambos como
falas da mesma conversa. Se for sua vez,
atenda à conversa e use as ferramentas necessárias para pedidos de ação antes
da resposta final; depois dê uma fala breve com o resultado real.]
""".strip()


def should_remain_silent(response: str | None) -> bool:
    """Reconhece o sinal de controle antes de encaminhar qualquer texto à voz."""
    return not response or not response.strip() or "[SILENCIO]" in response.upper()



def can_hear_call(user, channel_id):
    """Confere os estados de áudio de saída que o Discord disponibiliza."""
    voice = getattr(user, "voice", None)
    channel = getattr(voice, "channel", None)
    return (channel is not None and channel.id == channel_id
            and not getattr(voice, "self_deaf", False)
            and not getattr(voice, "deaf", False))


class ScreenCaptureBuffer(threading.Thread):
    """Buffer circular da tela; cada envio consome os quadros e remove o MP4."""
    def __init__(self, fps=2, duration_sec=60):
        super().__init__(daemon=True, name="CallScreenCapture")
        self.fps = fps
        self.duration_sec = duration_sec
        self.maxlen = int(fps * duration_sec)
        self.frames = collections.deque(maxlen=self.maxlen)
        self.running = False
        self.active = False
        self._lock = threading.RLock()
        self._stopped = threading.Event()
        self._generation = 0

    def run(self):
        import cv2
        import numpy as np
        while not self._stopped.is_set():
            started = time.monotonic()
            with self._lock:
                active, generation = self.active, self._generation
            if active:
                try:
                    img = capture_screen().resize((1280, 720))
                    frame = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
                    with self._lock:
                        # Uma captura em andamento não pode repovoar um buffer limpo.
                        if self.active and generation == self._generation:
                            self.frames.append(frame)
                except Exception as exc:
                    print(f"[Screen Buffer] Captura indisponível: {exc}")
                    self.pause_capturing()
            self._stopped.wait(max(0.01, 1.0 / self.fps - (time.monotonic() - started)))
        self.running = False

    def start_capturing(self):
        with self._lock:
            if not self._stopped.is_set():
                self.active = True

    def pause_capturing(self):
        with self._lock:
            self.active = False
            self._generation += 1

    def clear(self):
        with self._lock:
            self._generation += 1
            self.frames.clear()

    def stop(self):
        with self._lock:
            self._stopped.set()
            self.active = self.running = False
            self.clear()

    def save_video(self, output_path) -> bool:
        import cv2
        with self._lock:
            frames = list(self.frames)
        if not frames:
            return False
        out = None
        try:
            height, width, _ = frames[0].shape
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            out = cv2.VideoWriter(str(output_path), cv2.VideoWriter_fourcc(*'mp4v'),
                                  self.fps, (width, height))
            if not out.isOpened():
                raise RuntimeError("Codec MP4 indisponível")
            for frame in frames:
                out.write(frame)
            out.release()
            out = None
            return Path(output_path).is_file() and Path(output_path).stat().st_size > 0
        except Exception as exc:
            print(f"[Screen Buffer] Erro ao gravar vídeo: {exc}")
            return False
        finally:
            if out is not None:
                out.release()

    def consume_video(self):
        # Serializa consumo e encerramento: stop() só retorna com tudo limpo.
        with self._lock:
            if self._stopped.is_set() or not self.frames:
                return None
            try:
                BUFFER_VIDEO_DIR.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory(prefix="call_", dir=BUFFER_VIDEO_DIR) as directory:
                    path = Path(directory) / "screen.mp4"
                    if self.save_video(path):
                        return path.read_bytes()
            finally:
                self.clear()


def transcribe_gemini_live(wav_bytes: bytes, settings: dict) -> str:
    """Transcreve uma fala capturada usando exclusivamente o endpoint Live.

    Cada fala abre uma sessão curta; o gravador/VAD local continua delimitando
    as falas. O WAV é convertido em blocos PCM, nunca enviado ao endpoint unary.
    """
    try:
        from dotenv import load_dotenv
        load_dotenv(ENV_PATH, override=False)
    except ImportError:
        pass
    api_key = (str(settings.get("gemini_api_key") or "").strip()
               or os.getenv("GEMINI_API_KEY", "").strip()
               or os.getenv("GOOGLE_API_KEY", "").strip())
    if not api_key:
        raise RuntimeError("Configure a chave do Gemini nas configurações de voz ou GEMINI_API_KEY no .env.")
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 16000):
            raise ValueError("Gemini Live requer áudio PCM mono de 16 bits a 16000 Hz.")
        pcm = wav.readframes(wav.getnframes())
    if not pcm:
        return ""
    if len(pcm) >= 16000 * 2 * 600:
        raise ValueError("A fala excede o limite de 10 minutos da sessão Gemini Live.")

    async def transcribe():
        try:
            from websockets.asyncio.client import connect
        except ImportError:
            raise RuntimeError("Instale a dependência websockets>=14 para usar Gemini Live.") from None
        url = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
        async with connect(url, additional_headers={"x-goog-api-key": api_key},
                           open_timeout=15, close_timeout=3) as socket:
            await socket.send(json.dumps({"setup": {
                "model": "models/gemini-3.5-transcribe-live",
                "generationConfig": {"responseModalities": ["TEXT"]},
                "inputAudioTranscription": {"languageCodes": ["pt-BR"]},
                "realtimeInputConfig": {"automaticActivityDetection": {"disabled": True}},
            }}))
            setup = json.loads(await asyncio.wait_for(socket.recv(), timeout=15))
            if "setupComplete" not in setup:
                raise RuntimeError("Gemini Live recusou a sessão. Verifique a chave e o acesso ao modelo.")

            async def send_audio():
                await socket.send(json.dumps({"realtimeInput": {"activityStart": {}}}))
                for offset in range(0, len(pcm), 3200):
                    await socket.send(json.dumps({"realtimeInput": {"audio": {
                        "data": base64.b64encode(pcm[offset:offset + 3200]).decode("ascii"),
                        "mimeType": "audio/pcm;rate=16000",
                    }}}))
                    await asyncio.sleep(0.1)
                await socket.send(json.dumps({"realtimeInput": {"activityEnd": {}}}))

            async def receive_text():
                parts = []
                while True:
                    message = json.loads(await socket.recv())
                    if "error" in message:
                        raise RuntimeError("Gemini Live retornou um erro. Verifique acesso e cota no Google AI Studio.")
                    content = message.get("serverContent") or {}
                    # Hipóteses provisórias são revisadas; somente finais entram na resposta.
                    transcript = content.get("inputTranscription") or {}
                    if transcript.get("text"):
                        parts.append(transcript["text"])
                    if content.get("turnComplete"):
                        return "".join(parts).strip()
                    if "goAway" in message:
                        raise RuntimeError("A sessão Gemini Live expirou. Tente enviar a fala novamente.")

            sender = asyncio.create_task(send_audio())
            receiver = asyncio.create_task(receive_text())
            try:
                _, text = await asyncio.wait_for(
                    asyncio.gather(sender, receiver), timeout=len(pcm) / 32000 + 30)
                return text
            finally:
                for task in (sender, receiver):
                    task.cancel()
                await asyncio.gather(sender, receiver, return_exceptions=True)

    try:
        return asyncio.run(transcribe())
    except TimeoutError:
        raise RuntimeError("Gemini Live demorou demais para finalizar a transcrição. Tente novamente.") from None
    except RuntimeError:
        raise
    except Exception:
        # Não registrar detalhes de conexão que possam expor credenciais.
        raise RuntimeError("Falha na conexão Gemini Live. Verifique internet, chave e acesso ao modelo.") from None


def generate_tts_audio(clean_text: str, settings: dict) -> bytes | None:
    if not clean_text:
        return None
    # Remove emojis do Discord, tags %...%, links, formatações Markdown e emojis Unicode
    clean_text = re.sub(r'<a?:[a-zA-Z0-9_]+:[0-9]+>', '', clean_text)
    clean_text = re.sub(r'[%&][^%&\n]+[%&]', '', clean_text)
    clean_text = re.sub(r'https?://\S+', '', clean_text)
    clean_text = re.sub(r'[*_`#~>|]', '', clean_text)
    clean_text = re.sub(
        r'[\U00010000-\U0010ffff]|[\u2600-\u27bf]|[\u2300-\u23ff]|[\u2b50-\u2b55]|[\ufe00-\ufe0f]|[\u200d]',
        '',
        clean_text
    )
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    if not clean_text:
        return None

    wav_out = None
    fish_key = settings.get("fish_audio_api_key", "").strip()
    if not fish_key:
        try:
            from dotenv import load_dotenv
            load_dotenv(ENV_PATH, override=True)
        except Exception:
            pass
        fish_key = os.getenv("FISH_AUDIO_API_KEY", "").strip()
    voice_id = settings.get("fish_audio_voice_id", "").strip()
    if not voice_id:
        try:
            from dotenv import load_dotenv
            load_dotenv(ENV_PATH, override=True)
        except Exception:
            pass
        voice_id = os.getenv("FISH_AUDIO_VOICE_ID", "").strip()

    if fish_key:
        try:
            import requests
            url = "https://api.fish.audio/v1/tts"
            headers = {
                "Authorization": f"Bearer {fish_key}",
                "Content-Type": "application/json",
                "model": "s2.1-pro-free"
            }
            payload = {
                "text": clean_text,
                "format": "wav",
                "model": "s2.1-pro-free"
            }
            if voice_id:
                payload["reference_id"] = voice_id
            print("[Voice Chat] Tentando gerar áudio via Fish Audio TTS...")
            response = requests.post(url, headers=headers, json=payload, timeout=20)
            if response.status_code == 200 and len(response.content) > 100:
                wav_out = response.content
                print("[Voice Chat] Áudio gerado com sucesso via Fish Audio!")
                return wav_out
            else:
                print(f"[Voice Chat] Erro no Fish Audio (Status {response.status_code}): {response.text}")
        except Exception as exc:
            print(f"[Voice Chat] Exceção no Fish Audio: {exc}")
    else:
        print("[Voice Chat] Fish Audio sem API Key. Configure a chave para gerar áudio.")

    return wav_out


def clean_whisper_transcription(result: dict) -> str:
    """Filtra segmentos sem fala, de baixa confiança e ecos de instruções."""
    def is_instruction_echo(text):
        normalized = re.sub(r"[^\w\s]", "", text.casefold())
        normalized = " ".join(normalized.split())
        return normalized in {
            "obrigada",
            "obrigado",
            "ignorar ruído e estática",
            "transcrição em português brasileiro",
            "transcrição em português brasileiro ignorar ruído e estática",
            "não transcreva legendas fantasma",
            "se houver apenas silêncio ruído música de fundo ou estática de microfone ignore totalmente e retorne vazio",
        }

    segments = result.get("segments")
    if segments:
        accepted = []
        for segment in segments:
            text = (segment.get("text") or "").strip()
            no_speech = segment.get("no_speech_prob")
            confidence = segment.get("avg_logprob")
            compression = segment.get("compression_ratio")
            likely_silence = isinstance(no_speech, (int, float)) and no_speech > 0.6
            low_confidence = isinstance(confidence, (int, float)) and confidence < -1.0
            repetitive = isinstance(compression, (int, float)) and compression > 2.4
            if text and not (likely_silence or low_confidence or repetitive) and not is_instruction_echo(text):
                accepted.append(text)
            elif text:
                print(f"[Discord Call] Whisper descartado: silêncio={no_speech}, "
                      f"confiança={confidence}, repetição={compression}.")
        return " ".join(accepted)
    text = (result.get("text") or "").strip()
    return "" if is_instruction_echo(text) else text


def prepare_speech_connection():
    """Inicia conexão TTS em segundo plano junto com o modo de voz."""
    try:
        settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8")) if SETTINGS_PATH.exists() else {}
        key = settings.get("fish_audio_api_key", "").strip() or os.getenv("FISH_AUDIO_API_KEY", "").strip()
        voice = settings.get("fish_audio_voice_id", "").strip() or os.getenv("FISH_AUDIO_VOICE_ID", "").strip()
        if key and settings.get("tts_engine", "fish_audio") != "disabled":
            from fish_audio_live import ReadySpeechConnection
            return ReadySpeechConnection(key, voice)
    except Exception as exc:
        print(f"[Voz] Não foi possível preparar WebSocket TTS: {exc}")
    return None


class VoiceCallBridge:
    """Recebe PCM dos participantes do Discord e responde na própria call."""
    def __init__(self, bot_instance, guild_id: int, channel_id: int, *, visao_bionica=False):
        from ayla_discord_voice import VoiceSegmenter
        self.bot = bot_instance
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.stop_event = threading.Event()
        self.thread = None
        self._timer_thread = None
        self._lock = threading.RLock()
        self._segmenter = VoiceSegmenter(silence_seconds=2.0)
        self._pending = queue.Queue(maxsize=32)
        self._revision = 0
        self._last_voice_at = time.monotonic()
        self._responding = False
        self._batch_count = 0
        self._speech_session = None
        self._tts_connection = None
        self._vc = None
        self._loop = None
        self.visao_bionica = bool(visao_bionica)
        self.screen_buffer = None

    def _screen_attachments(self):
        if not self.screen_buffer or self.stop_event.is_set():
            return []
        try:
            video = self.screen_buffer.consume_video()
            return [(video, "video/mp4")] if video and not self.stop_event.is_set() else []
        except Exception as exc:
            print(f"[Discord Call] Não consegui preparar a visão biônica: {exc}")
            return []

    def start(self, voice_client):
        from discord.ext import voice_recv
        self._vc = voice_client
        self._loop = asyncio.get_running_loop()
        # listen can fail synchronously: don't report success or start workers first.
        voice_client.listen(voice_recv.BasicSink(self._receive), after=self._receive_finished)
        if self.visao_bionica:
            self.screen_buffer = ScreenCaptureBuffer()
            self.screen_buffer.running = True
            self.screen_buffer.start_capturing()
            self.screen_buffer.start()
        self._tts_connection = prepare_speech_connection()
        self.thread = threading.Thread(target=self._run, daemon=True,
                                       name=f"DiscordCall-{self.guild_id}")
        self._timer_thread = threading.Thread(target=self._flush_loop, daemon=True,
                                             name=f"DiscordVAD-{self.guild_id}")
        self.thread.start()
        self._timer_thread.start()
        print(f"[Discord Call] Ouvindo participantes do canal {self.channel_id} via DAVE.")

    def stop(self):
        # Do not join the worker from the Discord loop: it may be awaiting playback.
        self.stop_event.set()
        if self.screen_buffer:
            self.screen_buffer.stop()
        if self._tts_connection:
            self._tts_connection.close()
            self._tts_connection = None
        if self._speech_session:
            self._speech_session.abort()
        with self._lock:
            self._segmenter.speakers.clear()
            self._revision += 1
        if self._vc and self._vc.is_listening():
            self._vc.stop_listening()
        if self._vc:
            self._vc.stop_playing()

    def _receive_finished(self, error):
        self.stop_event.set()
        if self.screen_buffer:
            self.screen_buffer.stop()
        if self._tts_connection:
            self._tts_connection.close()
        if self._speech_session:
            self._speech_session.abort()
        if error:
            print(f"[Discord Call] A recepção parou ({type(error).__name__}). Use /entrar_call para reconectar.")

    def interrupt(self):
        """Invalida a resposta atual sem desconectar ou encerrar a escuta."""
        with self._lock:
            self._revision += 1
            self._segmenter.speakers.clear()
            session = self._speech_session
        if session:
            threading.Thread(target=session.abort, daemon=True, name='CallAbort').start()
        if self._vc:
            self._vc.stop_playing()
        print('[Discord Call] Fala interrompida pelo End.')

    async def close(self):
        reader = getattr(self._vc, "_reader", None)
        self.stop()
        if reader:
            # The old router's finalizer calls vc.stop_listening(). Wait for it
            # before installing a new reader on the same voice connection.
            def join_reader():
                for thread in (reader.packet_router, reader.event_router):
                    if thread.is_alive():
                        thread.join(timeout=2)
                return not reader.packet_router.is_alive() and not reader.event_router.is_alive()
            if not await asyncio.to_thread(join_reader):
                raise RuntimeError("A recepção anterior ainda está encerrando; tente novamente.")

    def _receive(self, user, data):
        if (self.stop_event.is_set() or user is None or getattr(user, "bot", False)
                or not can_hear_call(user, self.channel_id)):
            return
        with self._lock:
            if (self.stop_event.is_set() or self._responding
                    or self._vc.is_playing() or self._vc.is_paused()):
                self._segmenter.speakers.clear()
                return
            began, ready = self._segmenter.feed(user, data.pcm, time.monotonic())
            for state in self._segmenter.speakers.values():
                self._last_voice_at = max(self._last_voice_at, state.last_voice)
            if began:
                self._revision += 1
            self._enqueue(ready)

    def receive_chat_message(self, message):
        """Inclui texto no mesmo lote de voz, somente durante a escuta."""
        from types import SimpleNamespace
        text = message.content.strip()
        if not text or getattr(message.author, "bot", False):
            return
        with self._lock:
            if not can_hear_call(message.author, self.channel_id):
                return
            if (not self._is_current(self._revision) or self._responding
                    or self._vc.is_playing() or self._vc.is_paused()):
                return
            utterance = SimpleNamespace(user=message.author, pcm=b"",
                                        continued=False, chat_text=text)
            try:
                self._pending.put_nowait((utterance, self._revision))
            except queue.Full:
                print("[Discord Call] Fila de falas cheia; mensagem descartada.")
                return
            self._last_voice_at = time.monotonic()

    def _enqueue(self, utterances):
        for utterance in utterances:
            try:
                self._pending.put_nowait((utterance, self._revision))
            except queue.Full:
                print("[Discord Call] Fila de falas cheia; trecho descartado.")

    def _flush_loop(self):
        while not self.stop_event.wait(0.05):
            if not self._vc.is_connected():
                # discord.py may be reconnecting; discard the old conversation audio.
                with self._lock:
                    self._segmenter.speakers.clear()
                    self._revision += 1
                continue
            with self._lock:
                if self._responding or self._vc.is_playing() or self._vc.is_paused():
                    self._segmenter.speakers.clear()
                    continue
                self._enqueue(self._segmenter.flush(time.monotonic()))

    def _is_current(self, revision):
        return (not self.stop_event.is_set() and revision == self._revision
                and self._vc is not None and self._vc.is_connected()
                and self._vc.channel.id == self.channel_id)

    def _transcrever(self, wav_bytes: bytes, settings: dict) -> str:
        if settings.get("stt_engine") == "gemini_live":
            try:
                return transcribe_gemini_live(wav_bytes, settings)
            except Exception as exc:
                print(f"[VoiceBridge] {exc}")
                return ""
        if settings.get("stt_engine") == "zai":
            try:
                from zai_provider import ZaiAttachment
                client = getattr(self.bot, "zai_client", None)
                if client:
                    text = client.transcribe_audio(
                        ZaiAttachment(data=wav_bytes, mime_type="audio/wav", filename="speech.wav")
                    )
                    if text:
                        return text.strip()
            except Exception as e:
                print(f"⚠️ [VoiceBridge] Erro ao transcrever via Z.ai: {e}")

            return ""

        # 1. Tenta Groq Whisper se a chave estiver configurada
        groq_key = settings.get("groq_api_key", "").strip() or os.getenv("GROQ_API_KEY", "").strip()
        if groq_key:
            try:
                import requests
                from whisper_audio import prepare_whisper_audio
                wav_bytes = prepare_whisper_audio(wav_bytes)
                if not wav_bytes:
                    print("[Discord Call] Áudio sem fala descartado antes do Whisper.")
                    return ""
                url = "https://api.groq.com/openai/v1/audio/transcriptions"
                headers = {"Authorization": f"Bearer {groq_key}"}
                files = {"file": ("speech.wav", wav_bytes, "audio/wav")}
                data = {
                    "model": "whisper-large-v3",
                    "language": "pt",
                    "response_format": "verbose_json",
                    "temperature": 0.0
                }
                res = requests.post(url, headers=headers, files=files, data=data, timeout=12)
                if res.status_code == 200:
                    result = res.json()
                    txt = clean_whisper_transcription(result)
                    print(f"[Discord Call] STT whisper-large-v3: "
                          f"áudio={result.get('duration', '?')}s, "
                          f"segmentos={len(result.get('segments') or [])}, "
                          f"resultado={'aceito' if txt else 'descartado'}.")
                    if txt:
                        return txt
                    # Silêncio não é falha: não reenviar para outro ASR.
                    return ""
                print(f"[VoiceBridge] Groq Whisper falhou (HTTP {res.status_code}).")
            except Exception as e:
                print(f"⚠️ [VoiceBridge] Erro ao transcrever via Groq: {e}")
        else:
            print("[VoiceBridge] Groq Whisper indisponível: configure GROQ_API_KEY.")

        return ""

    def _run(self):
        from ayla_discord_voice import pcm_to_stt_wav
        from types import SimpleNamespace
        unanswered = []
        last_user = None
        while not self.stop_event.is_set():
            queued = True
            try:
                utterance, revision = self._pending.get(timeout=0.2)
            except queue.Empty:
                if not unanswered or time.monotonic() - self._last_voice_at < 2.0:
                    continue
                queued = False
                utterance = SimpleNamespace(user=last_user, pcm=b"", continued=False)
                revision = self._revision
            arquivos = []
            chose_silence = False
            try:
                if self.stop_event.is_set() or not self._vc.is_connected():
                    unanswered.clear()
                    self._batch_count = 0
                    continue
                settings = {}
                if SETTINGS_PATH.exists():
                    settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
                trecho = getattr(utterance, "chat_text", "")
                if utterance.pcm:
                    trecho = self._transcrever(pcm_to_stt_wav(utterance.pcm), settings)
                if trecho and trecho.strip():
                    last_user = utterance.user
                    unanswered.append((utterance.user.display_name, trecho.strip()))
                    self._batch_count = len(unanswered)
                    print(f"[Discord Call] {utterance.user.display_name}: {trecho.strip()}")
                force_response = len(unanswered) >= 10
                with self._lock:
                    silence_response = (bool(unanswered) and self._pending.empty()
                                        and not any(state.frames or state.confirmed
                                                    for state in self._segmenter.speakers.values())
                                        and time.monotonic() - self._last_voice_at >= 2.0)
                    if not force_response and not silence_response:
                        if trecho and trecho.strip():
                            print(f"[Discord Call] Falas acumuladas: {len(unanswered)}/10.")
                        continue
                    texto = "\n".join(f"{name}: {text}" for name, text in unanswered)
                    revision = self._revision
                    if not self._is_current(revision):
                        continue
                    self._responding = True
                    if self.screen_buffer:
                        self.screen_buffer.pause_capturing()
                    self._segmenter.speakers.clear()
                # O lote já pertence a esta resposta. Não o reapresentar no
                # próximo ciclo caso o modelo retorne vazio ou ocorra erro.
                unanswered.clear()
                self._batch_count = 0
                manager = self.bot.voice_manager
                manager.atualizar_status(self.guild_id, "Pensando", ttft=None,
                                         guard=lambda: not self.stop_event.is_set())
                reason = "10 falas" if force_response else "2 segundos de silêncio"
                print(f"[Discord Call] Escuta suspensa: {reason}; enviando lote ao pensamento.")
                context = SimpleNamespace(guild=self._vc.guild, channel=self._vc.channel,
                                          author=utterance.user, origem="Discord-Call")
                prompt = (texto + "\n\n[Modo voz: responda em português, de forma curta e falada, "
                          "em até 500 caracteres. Não use emojis, links ou a ferramenta "
                          "converter_texto_para_audio_discord: sua resposta será falada automaticamente.]")
                prompt += "\n" + LIVE_TURN_PROMPT
                arquivos = self._screen_attachments()
                if arquivos:
                    prompt += ("\n[Visão biônica: o vídeo anexado mostra até 1 minuto da tela "
                               "do computador da dona. Use o clipe para responder sobre a tela. "
                               "Evite ver_tela_atual se o vídeo já contém a informação.]")
                session = None
                fish_key = settings.get("fish_audio_api_key", "").strip() or os.getenv("FISH_AUDIO_API_KEY", "").strip()
                voice_id = settings.get("fish_audio_voice_id", "").strip() or os.getenv("FISH_AUDIO_VOICE_ID", "").strip()
                guard = lambda revision=revision: self._is_current(revision)
                if fish_key and settings.get("tts_engine", "fish_audio") != "disabled":
                    try:
                        from fish_audio_live import LiveSpeechSession, DiscordStreamingAudioPlayer
                        player = DiscordStreamingAudioPlayer(self.bot.voice_manager, self.guild_id, guard)
                        session = LiveSpeechSession(api_key=fish_key, voice_id=voice_id, player=player,
                                                    connection_pool=self._tts_connection)
                        self._speech_session = session
                        if not session.start():
                            session.close()
                            session = None
                    except Exception as exc:
                        if session:
                            session.close()
                        session = None
                        print(f"[Discord Call] WebSocket indisponível: {exc}. Usando TTS completo.")
                try:
                    from zai_provider import observar_primeiro_token
                    def token_received(model, ttft):
                        manager.atualizar_status(
                            self.guild_id, model=model, ttft=ttft, guard=guard)
                    with observar_primeiro_token(token_received):
                        resposta, _ = self.bot.processar_zai(
                            prompt, arquivos=arquivos or None, origem="Discord-Call", contexto_discord=context,
                            # Aguarde a decisão completa: nenhum trecho ou sinal de
                            # silêncio pode vazar para a síntese durante a geração.
                            stream_callback=lambda text: None)
                    if should_remain_silent(resposta):
                        chose_silence = True
                        print("[Discord Call] Ayla escolheu continuar ouvindo em silêncio.")
                        if session:
                            session.abort()
                        continue
                    if session:
                        if guard():
                            session.feed_delta(resposta)
                            session.finish()
                        else:
                            session.abort()
                        # Não repetir texto que já foi falado durante a geração.
                        continue
                finally:
                    if session:
                        session.close()
                    self._speech_session = None
                if should_remain_silent(resposta) or not self._is_current(revision):
                    continue
                wav = generate_tts_audio(resposta, settings)
                if wav and self._is_current(revision):
                    manager = self.bot.voice_manager
                    played = manager.tocar_wav_na_call(self.guild_id, wav,
                                                       guard=lambda revision=revision: self._is_current(revision))
                    if not played and self._is_current(revision):
                        print("[Discord Call] Não foi possível reproduzir a resposta.")
            except Exception as exc:
                print(f"[Discord Call] Falha ao processar fala ({type(exc).__name__}): {exc}")
            finally:
                arquivos.clear()
                with self._lock:
                    self._responding = False
                    if self.screen_buffer and not self.stop_event.is_set():
                        self.screen_buffer.start_capturing()
                if not self.stop_event.is_set() and not self._vc.is_playing():
                    self.bot.voice_manager.atualizar_status(
                        self.guild_id,
                        "a ayla escolheu nao falar" if chose_silence else "Ouvindo",
                        duration=2.0 if chose_silence else None,
                        guard=lambda: not self.stop_event.is_set())
                if queued:
                    self._pending.task_done()


# ══════════════════════════════════════════════════════════
#  GERENCIADOR COMPLETO DE VOZ DO DISCORD (2.3)
# ══════════════════════════════════════════════════════════

class DiscordVoiceManager:
    """Gerencia conexões, recepção DAVE e respostas de voz no Discord."""
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self._voice_clients: dict[int, object] = {}
        self._voice_bridges: dict[int, VoiceCallBridge] = {}
        self._connection_locks = {}
        self._loop = None
        self._call_status = {}
        self._status_locks = {}

    def interromper_fala(self):
        def interrupt():
            for bridge in list(self._voice_bridges.values()):
                bridge.interrupt()
            for vc in list(self._voice_clients.values()):
                vc.stop_playing()
            return True
        return self._on_voice_loop(interrupt)

    def route_call_chat(self, message):
        """Consome o chat da call ativa para evitar uma segunda resposta por texto."""
        guild = getattr(message, "guild", None)
        if guild is None or getattr(message.author, "bot", False):
            return False
        bridge = self._voice_bridges.get(guild.id)
        if (bridge is None or bridge.stop_event.is_set()
                or message.channel.id != bridge.channel_id):
            return False
        bridge.receive_chat_message(message)
        return True

    async def _editar_status(self, channel, text, guard=None):
        lock = self._status_locks.setdefault(channel.id, asyncio.Lock())
        async with lock:
            if guard and not guard():
                return
            try:
                await channel.edit(status=text)
            except Exception as exc:
                print(f"[Discord Call] Não consegui atualizar o status do canal {channel.id}: {exc}")

    def atualizar_status(self, guild_id, state=None, *, model=None, ttft=..., guard=None,
                         duration=None):
        """Agenda no loop Discord; coalesce estados antigos durante rate limits."""
        def update():
            if guard and not guard():
                return
            vc = self.get_voice_client(guild_id)
            if not vc or not vc.is_connected():
                return
            current = self._call_status.setdefault(guild_id, {
                'state': 'Ouvindo', 'model': self._modelo_call(), 'ttft': None,
                'revision': 0,
            })
            if state is not None:
                current['state'] = state
            if model is not None:
                current['model'] = model
            if ttft is not ...:
                current['ttft'] = ttft
            display_state = current['state']
            if display_state == "Ouvindo":
                bridge = self._voice_bridges.get(guild_id)
                count = getattr(bridge, "_batch_count", 0)
                display_state = f"Ouvindo {count}/10"
            text = f"{display_state} | modelo:{current['model']}"
            if current['state'] == 'falando' and current['ttft'] is not None:
                text += f" | ping:{current['ttft']:.2f}s"
            current['revision'] += 1
            revision = current['revision']
            channel = vc.channel
            def valid():
                return (self._call_status.get(guild_id) is current
                        and current['revision'] == revision
                        and vc.is_connected() and vc.channel.id == channel.id
                        and (guard is None or guard()))
            async def publish():
                await self._editar_status(channel, text, valid)
                if duration is not None and valid():
                    # Conta a duração após a edição, sem bloquear a escuta.
                    await asyncio.sleep(duration)
                    if valid():
                        self.atualizar_status(guild_id, "Ouvindo", guard=guard)
            asyncio.create_task(publish())
        self._on_voice_loop(update)

    def _modelo_call(self):
        policy = getattr(self.bot, 'model_policy', {})
        return (policy.get('call') or policy.get('principal')
                or getattr(self.bot, 'modelo_atual', 'desconhecido'))

    async def _limpar_status(self, guild_id, vc):
        self._call_status.pop(guild_id, None)
        if vc and vc.is_connected():
            await self._editar_status(vc.channel, None)

    def get_voice_client(self, guild_id: int):
        vc = self._voice_clients.get(guild_id)
        if not vc or not getattr(vc, "is_connected", lambda: False)():
            if hasattr(self.bot, "voice_clients"):
                for client in self.bot.voice_clients:
                    if getattr(getattr(client, "guild", None), "id", None) == guild_id and getattr(client, "is_connected", lambda: False)():
                        self._voice_clients[guild_id] = client
                        return client
        return vc

    async def conectar_canal_voz(self, voice_channel, *, visao_bionica=False) -> tuple[bool, str]:
        """Conecta com DAVE e recebe áudio diretamente dos participantes."""
        try:
            from ayla_discord_voice import DaveVoiceRecvClient, check_voice_dependencies
            check_voice_dependencies()
        except Exception as exc:
            return False, (f"⚠️ Recepção de voz indisponível ({exc}). "
                           "Instale as dependências de requirements-call.txt e reinicie a Ayla.")
        guild_id = voice_channel.guild.id
        lock = self._connection_locks.setdefault(guild_id, asyncio.Lock())
        async with lock:
            self._loop = asyncio.get_running_loop()
            old_bridge = self._voice_bridges.pop(guild_id, None)
            vc = self.get_voice_client(guild_id)
            bridge = None
            try:
                if old_bridge:
                    await old_bridge.close()
                await self._limpar_status(guild_id, vc)
                # A regular VoiceClient cannot receive; replace an existing send-only connection.
                if vc and (not isinstance(vc, DaveVoiceRecvClient) or not vc.is_connected()):
                    await vc.disconnect(force=True)
                    vc = None
                if vc:
                    if vc.channel.id != voice_channel.id:
                        await vc.move_to(voice_channel)
                    await voice_channel.guild.change_voice_state(channel=voice_channel,
                                                                self_deaf=False, self_mute=False)
                else:
                    vc = await voice_channel.connect(cls=DaveVoiceRecvClient, timeout=30.0,
                                                     reconnect=True, self_deaf=False, self_mute=False)
                self._voice_clients[guild_id] = vc
                bridge = VoiceCallBridge(self.bot, guild_id, voice_channel.id, visao_bionica=visao_bionica)
                bridge.start(vc)
                self._voice_bridges[guild_id] = bridge
                self.atualizar_status(guild_id, "Ouvindo")
            except Exception as exc:
                if bridge:
                    bridge.stop()
                self._voice_clients.pop(guild_id, None)
                if vc:
                    with contextlib.suppress(Exception):
                        await vc.disconnect(force=True)
                return False, f"⚠️ Não consegui ativar a escuta do canal de voz: {exc}"
        return True, (f"🩵 Conectei no canal de voz **#{voice_channel.name}**!\n"
                      "🎙️ Ouço as vozes dos participantes diretamente pelo Discord.\n"
                      "🔊 Respondo nesta chamada; use End no computador da Ayla para interromper.\n"
                      f"👁️ Visão biônica: {'Sim' if visao_bionica else 'Não'}.")

    async def desconectar_canal_voz(self, guild_id: int) -> tuple[bool, str]:
        lock = self._connection_locks.setdefault(guild_id, asyncio.Lock())
        async with lock:
            bridge = self._voice_bridges.pop(guild_id, None)
            if bridge:
                await bridge.close()
            vc = self.get_voice_client(guild_id)
            await self._limpar_status(guild_id, vc)
            self._voice_clients.pop(guild_id, None)
            if vc:
                await vc.disconnect(force=True)
                return True, "👋 Saí do canal de voz e parei de ouvir a chamada!"
            return False, "Não estou conectada em nenhum canal de voz neste servidor."

    def _on_voice_loop(self, callback):
        """Executa operações de voz no loop do Discord, sem bloquear esse mesmo loop."""
        from concurrent.futures import Future, TimeoutError
        loop = self._loop or getattr(self.bot, "discord_loop", None)
        if not loop or not loop.is_running():
            return False
        try:
            if asyncio.get_running_loop() is loop:
                return callback()
        except RuntimeError:
            pass
        future = Future()
        def run():
            if future.set_running_or_notify_cancel():
                try:
                    future.set_result(callback())
                except Exception as exc:
                    future.set_exception(exc)
        try:
            loop.call_soon_threadsafe(run)
            return future.result(timeout=5)
        except TimeoutError:
            future.cancel()
            return False
        except Exception as exc:
            print(f"[Discord Call] Erro de reprodução: {exc}")
            return False

    def _play_source(self, guild_id, source_factory, guard=None):
        def play():
            if guard and not guard():
                return False
            vc = self.get_voice_client(guild_id)
            if not vc or not vc.is_connected():
                return False
            source = None
            try:
                source = source_factory()
                if vc.is_playing() or vc.is_paused():
                    stop_playing = getattr(vc, "stop_playing", vc.stop)
                    stop_playing()
                def after(error):
                    if error:
                        print(f"[Discord Call] Falha durante reprodução: {error}")
                    bridge = self._voice_bridges.get(guild_id)
                    self.atualizar_status(
                        guild_id, "Pensando" if bridge and bridge._responding else "Ouvindo",
                        guard=lambda: (not vc.is_playing() and self.get_voice_client(guild_id) is vc
                                       and (guard is None or guard())))
                vc.play(source, after=after)
                self.atualizar_status(guild_id, "falando", guard=guard)
                return True
            except Exception as exc:
                if source:
                    source.cleanup()
                print(f"[Discord Call] Erro ao tocar áudio: {exc}")
                return False
        return self._on_voice_loop(play)

    def tocar_wav_na_call(self, guild_id: int, wav_bytes: bytes, *, guard=None) -> bool:
        import discord
        from ayla_discord_voice import wav_to_discord_pcm
        pcm = wav_to_discord_pcm(wav_bytes)
        if not pcm:
            return False
        return self._play_source(guild_id, lambda: discord.PCMAudio(io.BytesIO(pcm)), guard)

    def tocar_audio_na_call(self, guild_id: int, caminho_audio: str) -> bool:
        """Toca WAV diretamente; outros formatos usam FFmpeg quando disponível."""
        import discord
        path = Path(caminho_audio)
        if not path.is_file():
            return False
        try:
            if path.suffix.lower() == ".wav":
                return self.tocar_wav_na_call(guild_id, path.read_bytes())
        except (ValueError, wave.Error):
            pass
        return self._play_source(guild_id, lambda: discord.FFmpegPCMAudio(str(path)))

    def registrar_comandos_discord(self, tree):
        """Registra os slash commands /entrar_call e /sair_call na CommandTree do Discord."""
        try:
            import discord
            from discord import app_commands
        except ImportError:
            return

        manager = self

        @tree.command(name="entrar_call", description="Faz a Ayla entrar no seu canal de voz atual")
        @app_commands.allowed_installs(guilds=True, users=False)
        @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
        @app_commands.describe(visao_bionica="Visão biônica? Capturar a tela do computador da dona?")
        @app_commands.choices(visao_bionica=[app_commands.Choice(name="Sim", value="sim"),
                                           app_commands.Choice(name="Não", value="nao")])
        async def cmd_entrar_call(interaction: discord.Interaction, visao_bionica: str):
            if not getattr(manager.bot, "owner_id", 0) or interaction.user.id != manager.bot.owner_id:
                await interaction.response.send_message("⚠️ Apenas a usuario Usuario pode usar este comando.", ephemeral=True)
                return
            if not interaction.user or not hasattr(interaction.user, "voice") or not interaction.user.voice or not interaction.user.voice.channel:
                await interaction.response.send_message("⚠️ Você precisa estar conectado em um canal de voz primeiro!", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=False)
            follower = getattr(manager.bot, '_seguir_call', None)
            if follower and interaction.user.id == follower.owner_id:
                msg = await follower.sincronizar(interaction.user.voice.channel.id, solicitado=True, visao_bionica=visao_bionica == "sim")
            else:
                sucesso, msg = await manager.conectar_canal_voz(interaction.user.voice.channel, visao_bionica=visao_bionica == "sim")
            await interaction.followup.send(msg)

        @tree.command(name="sair_call", description="Faz a Ayla sair do canal de voz")
        @app_commands.allowed_installs(guilds=True, users=False)
        @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
        async def cmd_sair_call(interaction: discord.Interaction):
            if not getattr(manager.bot, "owner_id", 0) or interaction.user.id != manager.bot.owner_id:
                await interaction.response.send_message("⚠️ Apenas a usuario Usuario pode usar este comando.", ephemeral=True)
                return
            if not interaction.guild:
                await interaction.response.send_message("⚠️ Este comando só pode ser usado em servidores.", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=False)
            follower = getattr(manager.bot, '_seguir_call', None)
            if follower and interaction.user.id == follower.owner_id:
                msg = await follower.sair()
            else:
                sucesso, msg = await manager.desconectar_canal_voz(interaction.guild.id)
            await interaction.followup.send(msg)


