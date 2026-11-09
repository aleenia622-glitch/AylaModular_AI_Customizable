#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Módulo de WebSocket TTS Streaming contínuo da Fish Audio para o Modo Live da Ayla.
Mantém uma conexão aberta com a Fish Audio (wss://api.fish.audio/v1/tts/live),
envia pedaços de texto incrementalmente (tokens do LLM), recebe blocos PCM de áudio
e toca em tempo real via PyAudio, além de controlar pausas silenciosas durante o uso
de ferramentas e continuação sem repetição.
"""

from __future__ import annotations

import asyncio
import contextlib
import ctypes
import io
import json
import os
import queue
import re
import threading
import time
import wave
from pathlib import Path
from typing import Callable, Optional

import msgpack
import websockets

try:
    import pyaudio
except ImportError:
    pyaudio = None

BASE_DIR = Path(__file__).resolve().parent
TTS_OUTPUT_DIR = BASE_DIR / "audio_output"
METRICS_PATH = BASE_DIR / "ayla_metrics.json"
SETTINGS_PATH = BASE_DIR / "ayla_settings.json"
ENV_PATH = BASE_DIR / ".env"

FISH_WS_URL = "wss://api.fish.audio/v1/tts/live"


@contextlib.contextmanager
def suppress_alsa_errors():
    """Suprime avisos e mensagens espúrias da ALSA no stderr durante o init do PyAudio."""
    try:
        asound = ctypes.cdll.LoadLibrary("libasound.so.2")
        c_error_handler = ctypes.CFUNCTYPE(
            None,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
        )

        def _null_handler(filename, line, function, err, fmt):
            pass

        handler_ptr = c_error_handler(_null_handler)
        asound.snd_lib_error_set_handler(handler_ptr)
        yield
    except Exception:
        yield


def clean_text_for_tts(text: str) -> str:
    """Limpa formatação, markdown, menções, emojis e tags para envio ao TTS."""
    if not text:
        return ""
    # Remove blocos de raciocínio/pensamento
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'<thought>.*?</thought>', '', text, flags=re.DOTALL)
    # Remove emojis do Discord <:nome:123>
    text = re.sub(r'<a?:[a-zA-Z0-9_]+:[0-9]+>', '', text)
    # Remove tags %feliz%, %triste%, etc.
    text = re.sub(r'[%&][^%&\n]+[%&]', '', text)
    # Remove URLs
    text = re.sub(r'https?://\S+', '', text)
    # Remove símbolos de markdown
    text = re.sub(r'[*_`#~>|]', '', text)
    # Remove emojis Unicode
    text = re.sub(
        r'[\U00010000-\U0010ffff]|[\u2600-\u27bf]|[\u2300-\u23ff]|[\u2b50-\u2b55]|[\ufe00-\ufe0f]|[\u200d]',
        '',
        text,
    )
    # Normaliza espaços
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


class StreamingAudioPlayer:
    """Reprodutor de áudio PCM em tempo real (16-bit, 44.1kHz mono) com PyAudio."""

    def __init__(self, sample_rate: int = 44100, channels: int = 1):
        self.sample_rate = sample_rate
        self.channels = channels
        self.audio_queue: queue.Queue[bytes | None] = queue.Queue()
        self.pcm_accumulator = bytearray()
        self.running = False
        self.is_playing = False
        self.thread: Optional[threading.Thread] = None
        self._pa: Optional[pyaudio.PyAudio] = None
        self._stream = None
        self._lock = threading.Lock()
        self.on_start_playing: Optional[Callable[[], None]] = None
        self.on_stop_playing: Optional[Callable[[], None]] = None

    def start(self) -> bool:
        if self.running:
            return True
        if pyaudio is None:
            print("⚠️ [StreamingAudioPlayer] PyAudio não está instalado.")
            return False

        with suppress_alsa_errors():
            try:
                self._pa = pyaudio.PyAudio()
                self._stream = self._pa.open(
                    format=pyaudio.paInt16,
                    channels=self.channels,
                    rate=self.sample_rate,
                    output=True,
                    frames_per_buffer=1024,
                )
            except Exception as e:
                print(f"⚠️ [StreamingAudioPlayer] Falha ao abrir stream PyAudio: {e}")
                if self._pa:
                    try:
                        self._pa.terminate()
                    except Exception:
                        pass
                    self._pa = None
                return False

        self.running = True
        self.thread = threading.Thread(target=self._play_loop, daemon=True, name="LiveAudioPlayer")
        self.thread.start()
        return True

    def feed(self, chunk: bytes) -> None:
        if not chunk:
            return
        with self._lock:
            self.pcm_accumulator.extend(chunk)
        self.audio_queue.put(chunk)

    def _play_loop(self) -> None:
        notified_start = False
        while self.running:
            try:
                chunk = self.audio_queue.get(timeout=0.04)
                if chunk is None:  # Sinal de parada
                    self.audio_queue.task_done()
                    break

                if not notified_start:
                    deadline = time.monotonic() + 0.3
                    while self.running and time.monotonic() < deadline:
                        with self._lock:
                            buffered = len(self.pcm_accumulator)
                        if buffered >= self.sample_rate * self.channels * 2 * 0.24:
                            break
                        time.sleep(0.01)

                if not self.is_playing:
                    self.is_playing = True
                    if not notified_start and self.on_start_playing:
                        notified_start = True
                        try:
                            self.on_start_playing()
                        except Exception:
                            pass

                if self._stream and self.running:
                    self._stream.write(chunk)
                self.audio_queue.task_done()
            except queue.Empty:
                if self.is_playing and self.audio_queue.empty():
                    self.is_playing = False
                    if self.on_stop_playing:
                        try:
                            self.on_stop_playing()
                        except Exception:
                            pass
                        notified_start = False

    def wait_drain(self, timeout: float = 20.0) -> bool:
        """Aguarda até que todas as amostras pendentes sejam reproduzidas."""
        deadline = time.monotonic() + timeout
        # get() esvazia a fila antes de write() reproduzir o último pacote.
        # task_done() é a confirmação de que esse pacote foi tocado.
        with self.audio_queue.all_tasks_done:
            while self.audio_queue.unfinished_tasks:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not self.running:
                    return False
                self.audio_queue.all_tasks_done.wait(min(remaining, 0.1))
        return True

    def stop(self) -> None:
        """Interrompe a reprodução imediatamente."""
        self.running = False
        # Limpa fila
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
                self.audio_queue.task_done()
            except Exception:
                break

        if self.thread and self.thread.is_alive():
            self.audio_queue.put(None)
            self.thread.join(timeout=0.5)

        with self._lock:
            if self._stream:
                try:
                    self._stream.stop_stream()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None

            if self._pa:
                try:
                    self._pa.terminate()
                except Exception:
                    pass
                self._pa = None

        self.is_playing = False

    def get_wav_bytes(self) -> bytes:
        """Retorna todas as amostras acumuladas encapsuladas em cabeçalho WAV."""
        with self._lock:
            pcm = bytes(self.pcm_accumulator)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm)
        return buf.getvalue()

    def save_wav(self, file_path: Path | str) -> str:
        """Grava todo o áudio acumulado em disco."""
        p = Path(file_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        wav_bytes = self.get_wav_bytes()
        p.write_bytes(wav_bytes)
        return str(p)


class DiscordStreamingAudioPlayer(StreamingAudioPlayer):
    """PCM incremental para Discord, sem abrir a saída de som local."""

    def __init__(self, manager, guild_id, guard):
        super().__init__()
        self.manager = manager
        self.guild_id = guild_id
        self.guard = guard
        self._condition = threading.Condition()
        self._pending_pcm = bytearray()
        self._sample_tail = b""
        self._rate_state = None
        self._input_finished = False
        self._playback_started = False
        self._playback_complete = False
        self._drained = threading.Event()
        self._prebuffer_until = None
        self._prebuffering = True
        self._buffer_target_frames = 30  # 600 ms de reserva inicial.
        self.underrun_count = 0

    def start(self):
        self.running = bool(self.guard())
        return self.running

    def feed(self, chunk):
        import audioop
        import discord
        if not self.running or not self.guard():
            self.stop()
            return
        with self._lock:
            self.pcm_accumulator.extend(chunk)
        data = self._sample_tail + chunk
        aligned = len(data) // 2 * 2
        self._sample_tail = data[aligned:]
        if not aligned:
            return
        pcm, self._rate_state = audioop.ratecv(
            data[:aligned], 2, 1, self.sample_rate, 48000, self._rate_state)
        pcm = audioop.tostereo(pcm, 2, 1, 1)
        with self._condition:
            if self._prebuffer_until is None:
                self._prebuffer_until = time.monotonic() + 1.5
            self._pending_pcm.extend(pcm)
            self._condition.notify_all()
        if not self._playback_started:
            self._playback_started = True
            player = self

            class Source(discord.AudioSource):
                def read(self):
                    return player._read_frame()

                def is_opus(self):
                    return False

                def cleanup(self):
                    player.stop()

            if not self.manager._play_source(self.guild_id, Source, self.guard):
                self.stop()
                raise RuntimeError("Não foi possível iniciar o streaming na call.")
            self.is_playing = True
            if self.on_start_playing:
                self.on_start_playing()

    def _read_frame(self):
        # Discord consome 20 ms: 960 amostras estéreo PCM16 (3840 bytes).
        with self._condition:
            if not self.running or not self.guard():
                self._drained.set()
                return b""
            if self._prebuffering:
                if (not self._input_finished
                        and len(self._pending_pcm) < 3840 * self._buffer_target_frames
                        and time.monotonic() < (self._prebuffer_until or 0)):
                    return bytes(3840)
                self._prebuffering = False
            if len(self._pending_pcm) >= 3840 or self._input_finished:
                if not self._pending_pcm:
                    self._playback_complete = True
                    self._drained.set()
                    return b""
                frame = bytes(self._pending_pcm[:3840])
                del self._pending_pcm[:3840]
                self._condition.notify_all()
                return frame.ljust(3840, b"\x00")
            # O relógio de 20 ms pertence ao Discord: nunca aguardar aqui.
            # Reacumular reserva evita alternar cada pacote com silêncio.
            self.underrun_count += 1
            self._buffer_target_frames = min(60, self._buffer_target_frames + 10)
            self._prebuffering = True
            self._prebuffer_until = time.monotonic() + 1.5
            return bytes(3840)

    def finish_input(self):
        with self._condition:
            self._input_finished = True
            if not self._playback_started:
                self._playback_complete = True
                self._drained.set()
            self._condition.notify_all()

    def wait_drain(self, timeout=20.0):
        if self._input_finished:
            return self._drained.wait(timeout) and self._playback_complete
        deadline = time.monotonic() + timeout
        with self._condition:
            while self._pending_pcm and self.running and self.guard():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(min(remaining, 0.1))
            return not self._pending_pcm and self.running and self.guard()

    def stop(self):
        with self._condition:
            self.running = False
            self.is_playing = False
            self._pending_pcm.clear()
            self._drained.set()
            self._condition.notify_all()


class FishAudioLiveStreamer:
    """Cliente WebSocket assíncrono para o serviço Live TTS da Fish Audio."""

    def __init__(
        self,
        api_key: str,
        voice_id: str,
        model: str = "s2.1-pro-free",
        sample_rate: int = 44100,
        chunk_length: int = 100,
        latency: str = "balanced",
        on_audio_chunk: Optional[Callable[[bytes], None]] = None,
        on_finish: Optional[Callable[[], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ):
        self.api_key = api_key
        self.voice_id = voice_id
        self.model = model
        self.sample_rate = sample_rate
        self.chunk_length = chunk_length
        self.latency = latency
        self.on_audio_chunk = on_audio_chunk
        self.on_finish = on_finish
        self.on_error = on_error

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._send_queue: Optional[asyncio.Queue] = None
        self._ws = None
        self._ready_event = threading.Event()
        self._finish_event = threading.Event()
        self._finish_reason = None
        self.is_connected = False
        self.is_closed = False

    def start(self) -> bool:
        if not self.api_key:
            print("⚠️ [FishAudioLive] API Key da Fish Audio não informada.")
            return False

        self._thread = threading.Thread(target=self._worker, daemon=True, name="FishAudioWS")
        self._thread.start()

        # Aguarda conexão inicial por até 6 segundos
        connected = self._ready_event.wait(timeout=6.0)
        if not connected or not self.is_connected:
            print("⚠️ [FishAudioLive] Tempo esgotado para conectar ao WebSocket da Fish Audio.")
            self.close()
            return False
        return True

    def _worker(self) -> None:
        async def run():
            self._loop = asyncio.get_running_loop()
            if not self.is_closed:
                await self._run_ws()
        try:
            # Drena e cancela tarefas pendentes antes de fechar o loop.
            asyncio.run(run())
        except Exception as e:
            if not self.is_closed:
                print(f"⚠️ [FishAudioLive] Erro no loop WebSocket: {e}")
                if self.on_error:
                    self.on_error(str(e))
        finally:
            self._ws = None
            self.is_connected = False
            self._ready_event.set()
            self._finish_event.set()

    async def _run_ws(self) -> None:
        self._send_queue = asyncio.Queue()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "model": self.model,
        }

        async with websockets.connect(
            FISH_WS_URL,
            additional_headers=headers,
            ping_interval=20,
            ping_timeout=20,
        ) as ws:
            self._ws = ws
            if self.is_closed:
                return
            self.is_connected = True

            # 1. Envia StartEvent com a configuração
            start_payload = {
                "event": "start",
                "request": {
                    "text": "",
                    "format": "pcm",
                    "sample_rate": self.sample_rate,
                    "latency": self.latency,
                    "chunk_length": self.chunk_length,
                    "reference_id": self.voice_id or None,
                    "normalize": True,
                },
            }
            await ws.send(msgpack.packb(start_payload))
            self._ready_event.set()
            print(f"🎙️ [FishAudioLive] WebSocket conectado com sucesso! (Voice: {self.voice_id[:8]}..., chunk: {self.chunk_length})")

            # Inicia tarefas concorrentes: envio e recepção
            sender_task = asyncio.create_task(self._sender_loop(ws))
            receiver_task = asyncio.create_task(self._receiver_loop(ws))

            done, pending = await asyncio.wait(
                [sender_task, receiver_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            try:
                for task in done:
                    task.result()
                # Sending stop only ends input; synthesis continues until finish.
                if sender_task in done and receiver_task in pending:
                    await asyncio.wait_for(receiver_task, timeout=60.0)
            finally:
                for task in pending:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)

    async def _sender_loop(self, ws) -> None:
        while not self.is_closed:
            action, data = await self._send_queue.get()
            try:
                if action == "text":
                    await ws.send(msgpack.packb({"event": "text", "text": data}))
                elif action == "flush":
                    await ws.send(msgpack.packb({"event": "flush"}))
                elif action == "stop":
                    await ws.send(msgpack.packb({"event": "stop"}))
                    break
            finally:
                self._send_queue.task_done()

    async def _receiver_loop(self, ws) -> None:
        async for frame in ws:
            try:
                data = msgpack.unpackb(frame)
                event_type = data.get("event")

                if event_type == "audio":
                    audio_bytes = data.get("audio")
                    if audio_bytes and self.on_audio_chunk:
                        self.on_audio_chunk(audio_bytes)
                elif event_type == "finish":
                    reason = data.get("reason")
                    self._finish_reason = reason
                    if reason == "error":
                        err_msg = data.get("message", "synthesis failed")
                        print(f"⚠️ [FishAudioLive] Fish Audio reportou erro de síntese: {err_msg}")
                        if self.on_error:
                            self.on_error(err_msg)
                    self._finish_event.set()
                    if self.on_finish:
                        self.on_finish()
                    break
                elif event_type == "error":
                    err_msg = data.get("error", "unknown error")
                    print(f"⚠️ [FishAudioLive] Fish Audio error event: {err_msg}")
                    if self.on_error:
                        self.on_error(err_msg)
                    self._finish_event.set()
                    break
            except Exception as e:
                print(f"⚠️ [FishAudioLive] Erro ao decodificar frame: {e}")

    def send_text(self, text: str) -> None:
        if not text or self.is_closed or not self._loop or not self._send_queue:
            return
        self._loop.call_soon_threadsafe(self._send_queue.put_nowait, ("text", text))

    def send_flush(self) -> None:
        if self.is_closed or not self._loop or not self._send_queue:
            return
        self._loop.call_soon_threadsafe(self._send_queue.put_nowait, ("flush", None))

    def send_stop(self) -> None:
        if self.is_closed or not self._loop or not self._send_queue:
            return
        self._loop.call_soon_threadsafe(self._send_queue.put_nowait, ("stop", None))

    def wait_finished(self, timeout: float = 25.0) -> bool:
        return self._finish_event.wait(timeout=timeout) and self._finish_reason == "stop"

    def close(self) -> None:
        if self.is_closed:
            return
        self.is_closed = True
        self._ready_event.set()
        self._finish_event.set()
        loop = self._loop
        if loop and loop.is_running() and not loop.is_closed():
            def fechar_no_loop():
                # Cria a corrotina apenas quando o loop realmente a executar.
                if self._ws:
                    loop.create_task(self._ws.close())
            try:
                loop.call_soon_threadsafe(fechar_no_loop)
            except RuntimeError:
                pass


class ReadySpeechConnection:
    """Pré-conecta o WebSocket; cada resposta termina com confirmação do servidor."""

    def __init__(self, api_key, voice_id):
        self.api_key = api_key
        self.voice_id = voice_id
        self._lock = threading.Lock()
        self._closed = threading.Event()
        self._ready = None
        self._active = None
        self._thread = threading.Thread(target=self._maintain, daemon=True, name="FishAudioReady")
        self._thread.start()

    def _connect(self):
        connection = FishAudioLiveStreamer(self.api_key, self.voice_id, chunk_length=100)
        if connection.start():
            return connection
        connection.close()
        return None

    def _maintain(self):
        while not self._closed.is_set():
            with self._lock:
                if not self._closed.is_set() and self._active is None:
                    if self._ready and not self._ready.is_connected:
                        self._ready.close()
                        self._ready = None
                    if self._ready is None:
                        self._ready = self._connect()
            self._closed.wait(2.0)

    def acquire(self, session):
        with self._lock:
            if self._closed.is_set():
                return None
            if self._active is not None:
                raise RuntimeError("Já existe uma resposta de voz em andamento.")
            connection = self._ready
            self._ready = None
            if connection and not connection.is_connected:
                connection.close()
                connection = None
            connection = connection or self._connect()
            if connection:
                connection.on_audio_chunk = session._on_audio_chunk
                connection.on_finish = session._on_streamer_finish
                connection.on_error = session._on_streamer_error
                self._active = connection
            return connection

    def release(self, connection, reusable=False):
        with self._lock:
            if self._active is connection:
                self._active = None
                if (reusable and not self._closed.is_set()
                        and connection.is_connected and not connection.is_closed):
                    connection.on_audio_chunk = None
                    connection.on_finish = None
                    connection.on_error = None
                    self._ready = connection
                    return
            connection.close()

    def close(self):
        self._closed.set()
        # Nunca bloquear o loop Qt/Discord aguardando a conexão em andamento.
        def cleanup():
            with self._lock:
                for connection in (self._ready, self._active):
                    if connection:
                        connection.close()
                self._ready = self._active = None
        threading.Thread(target=cleanup, daemon=True).start()


class LiveSpeechSession:
    """
    Sessão completa de fala contínua com streaming e suporte a ferramentas.
    Funciona como stream_callback para AylaBot.processar_zai.
    """

    def __init__(
        self,
        api_key: str,
        voice_id: str,
        model: str = "s2.1-pro-free",
        tokens_per_second: float = 35.0,
        on_speaking_start: Optional[Callable[[], None]] = None,
        on_speaking_chunk: Optional[Callable[[str], None]] = None,
        on_speaking_finished: Optional[Callable[[str], None]] = None,
        player=None,
        connection_pool=None,
    ):
        self.connection_pool = connection_pool
        self.api_key = api_key
        self.voice_id = voice_id
        self.model = model
        self.tokens_per_second = tokens_per_second

        # Adapta parâmetros com base na velocidade do modelo (tokens/s)
        self._adapt_parameters(tokens_per_second)

        self.on_speaking_start = on_speaking_start
        self.on_speaking_chunk = on_speaking_chunk
        self.on_speaking_finished = on_speaking_finished

        # Flags exigidas pelo pipeline do AylaBot
        self.is_live = True
        self.live_mode = True
        self.chunk_size = 20
        self.max_interval = 0.1

        self.player = player if player is not None else StreamingAudioPlayer()
        self.streamer: Optional[FishAudioLiveStreamer] = None

        self._lock = threading.Lock()
        self.buffer_text = ""
        self.accumulated_text_all = ""
        self.current_turn_text = ""
        self.in_tool_pause = False
        self.is_aborted = False
        self.started = False
        self.last_token_time = time.time()
        self._audio_received = False
        self._saved_wav_path: Optional[str] = None
        self._connection_reusable = False

    def _adapt_parameters(self, tps: float) -> None:
        """Adapta chunk_length, buffers e limiares de flush dinamicamente ao token/s."""
        self.tps = max(5.0, tps)
        self.chunk_length = 100
        self.min_flush_chars = 32
        self.max_buffer_chars = 64
        self.idle_flush_timeout = 0.35
        self._text_stop = threading.Event()
        self._text_thread = None
        self._pending_synthesis_chars = 0
        self._last_flush = time.monotonic()
        self._first_flush = True

    def _start_text_pump(self):
        self._last_flush = time.monotonic()
        self._text_thread = threading.Thread(target=self._pump_text, daemon=True, name="FishTextPump")
        self._text_thread.start()

    def _pump_text(self):
        while not self._text_stop.wait(0.06):
            with self._lock:
                if self.is_aborted or self.in_tool_pause:
                    continue
                self._send_buffered_text(timed=True)

    def _send_buffered_text(self, *, timed=False, final=False):
        now = time.monotonic()
        due = now - self._last_flush >= self.idle_flush_timeout
        while self.buffer_text:
            if not final and len(self.buffer_text) < 32 and not (timed and due):
                break
            window = self.buffer_text[:self.max_buffer_chars]
            boundaries = [m.end() for m in re.finditer(r"\s+", window)]
            if final and len(self.buffer_text) <= self.max_buffer_chars:
                cut = len(self.buffer_text)
            elif boundaries:
                cut = boundaries[-1]
            else:
                # Uma palavra extensa continua no próximo pacote, sem inserir espaço.
                if len(window) < self.max_buffer_chars and not final:
                    break
                cut = len(window)
            raw, self.buffer_text = self.buffer_text[:cut], self.buffer_text[cut:]
            text = clean_text_for_tts(raw)
            if not text or not self.streamer:
                continue
            text += " " if raw[-1:].isspace() else ""
            self.streamer.send_text(text)
            self._pending_synthesis_chars += len(text)
        # Texto viaja em pacotes pequenos; flush não acompanha cada pacote.
        if self.streamer and self._pending_synthesis_chars and (
            final or due or (self._first_flush and self._pending_synthesis_chars >= self.min_flush_chars)
        ):
            self.streamer.send_flush()
            self._pending_synthesis_chars = 0
            self._last_flush = now
            self._first_flush = False

    def start(self) -> bool:
        if self.started:
            return True

        if not self.player.start():
            print("⚠️ [LiveSpeechSession] Falha ao iniciar reprodutor de áudio.")
            return False

        if self.on_speaking_start:
            self.player.on_start_playing = self.on_speaking_start

        if self.connection_pool:
            self.streamer = self.connection_pool.acquire(self)
            if self.streamer is None:
                self.player.stop()
                return False
            self.started = True
            self._start_text_pump()
            return True

        self.streamer = FishAudioLiveStreamer(
            api_key=self.api_key,
            voice_id=self.voice_id,
            model=self.model,
            chunk_length=self.chunk_length,
            latency="balanced",
            on_audio_chunk=self._on_audio_chunk,
            on_finish=self._on_streamer_finish,
            on_error=self._on_streamer_error,
        )

        if not self.streamer.start():
            self.player.stop()
            return False

        self.started = True
        self._start_text_pump()
        return True

    def _on_audio_chunk(self, chunk: bytes) -> None:
        self._audio_received = True
        if not self.is_aborted:
            self.player.feed(chunk)

    def _on_streamer_finish(self) -> None:
        pass

    def _on_streamer_error(self, err: str) -> None:
        print(f"⚠️ [LiveSpeechSession] Erro do sintetizador: {err}")

    def feed_delta(self, delta: str) -> None:
        """Recebe token/delta bruto gerado pelo modelo em tempo real."""
        if not delta or self.is_aborted or not self.started:
            return

        now = time.time()
        with self._lock:
            self.buffer_text += delta
            self.current_turn_text += delta
            self.last_token_time = now

            self._send_buffered_text()

    def __call__(self, partial_text: str) -> None:
        """Chamado pelo AylaBot para atualizar o texto do turno."""
        if self.is_aborted:
            return
        clean_display = clean_text_for_tts(partial_text)
        if clean_display and self.on_speaking_chunk:
            try:
                self.on_speaking_chunk(clean_display)
            except Exception:
                pass

    def on_tool_start(self, tool_name: str = "") -> None:
        """
        Notificado antes da IA rodar uma ferramenta.
        Esvazia o buffer de fala pré-ferramenta, executa flush e aguarda a fala
        terminar antes de deixar o silêncio da execução acontecer.
        """
        if self.is_aborted or not self.started:
            return

        print(f"🛠️ [LiveSpeechSession] Ferramenta '{tool_name}' detectada. Finalizando fala pré-ferramenta...")
        with self._lock:
            self._send_buffered_text(final=True)
            self.in_tool_pause = True

        # Aguarda a Ayla terminar de falar o que gerou antes da ferramenta
        self.player.wait_drain(timeout=8.0)
        self.in_tool_pause = True
        print(f"🤫 [LiveSpeechSession] Ayla aguarda ferramenta '{tool_name}' em silêncio...")

    def on_tool_end(self, tool_name: str = "") -> None:
        """
        Notificado após o término da ferramenta.
        Reseta o texto do turno para enviar SOMENTE a continuação, sem repetir!
        """
        if self.is_aborted or not self.started:
            return

        with self._lock:
            # A ferramenta pode demorar mais que a sessão do sintetizador.
            # Renova apenas a conexão; mantém o player e o áudio já reproduzido.
            if not self.streamer or not self.streamer.is_connected or self.streamer.is_closed:
                if self.streamer:
                    if self.connection_pool:
                        self.connection_pool.release(self.streamer)
                    else:
                        self.streamer.close()
                self.streamer = None
                if self.connection_pool:
                    self.streamer = self.connection_pool.acquire(self)
                else:
                    connection = FishAudioLiveStreamer(
                        api_key=self.api_key, voice_id=self.voice_id, model=self.model,
                        chunk_length=self.chunk_length, latency="balanced",
                        on_audio_chunk=self._on_audio_chunk,
                        on_finish=self._on_streamer_finish, on_error=self._on_streamer_error)
                    if connection.start():
                        self.streamer = connection
                    else:
                        connection.close()
                if self.streamer is None:
                    self.in_tool_pause = False
                    raise RuntimeError("Não foi possível reconectar a voz após a ferramenta.")
                self._pending_synthesis_chars = 0
                self._first_flush = True
                self._last_flush = time.monotonic()
            self.in_tool_pause = False
            self.current_turn_text = ""
            self.buffer_text = ""
        print(f"✨ [LiveSpeechSession] Ferramenta concluída. Continuando fala diretamente sem repetição!")

    def finish(self) -> Optional[str]:
        """Finaliza a resposta, aguarda reprodução e grava arquivo WAV completo."""
        if not self.started or self.is_aborted:
            return None

        self._text_stop.set()
        with self._lock:
            self._send_buffered_text(final=True)
            if self.streamer:
                self.streamer.send_stop()

        # Aguarda recebimento do finish event e reprodução do áudio
        # Uma pausa entre pacotes não confirma que todas as frases chegaram.
        # stop encerra somente a entrada; Fish envia o restante antes de finish.
        synthesis_finished = self.streamer and self.streamer.wait_finished(timeout=60.0)
        self._connection_reusable = False
        if hasattr(self.player, "finish_input"):
            self.player.finish_input()
        # O modelo pode entregar minutos de fala em poucos segundos.
        # Dimensiona a espera pelo PCM recebido, sem cortar no limite fixo de 60s.
        audio_seconds = (len(self.player.pcm_accumulator)
                         / (self.player.sample_rate * self.player.channels * 2))
        playback_finished = self.player.wait_drain(timeout=max(60.0, audio_seconds + 5.0))
        if not synthesis_finished and not self.is_aborted:
            self.close()
            raise RuntimeError("O TTS não confirmou o fim da síntese; a fala pode estar incompleta.")
        if playback_finished is False and not self.is_aborted:
            self.close()
            raise RuntimeError("A reprodução não terminou; ainda havia áudio pendente.")
        if self.is_aborted or not self._audio_received:
            self.close()
            return None

        # Salva o arquivo WAV completo consolidado
        out_path = TTS_OUTPUT_DIR / f"saida_voice_chat_{int(time.time())}.wav"
        self._saved_wav_path = self.player.save_wav(out_path)

        if self.on_speaking_finished:
            try:
                self.on_speaking_finished(self._saved_wav_path)
            except Exception:
                pass

        self.close()
        return self._saved_wav_path

    def abort(self) -> None:
        """Interrupção imediata pelo usuário (hotkey, fala do usuário ou cancelamento)."""
        self.is_aborted = True
        if self.player:
            self.player.stop()
        self.close()

    def close(self) -> None:
        self._text_stop.set()
        if self.streamer:
            connection, self.streamer = self.streamer, None
            if self.connection_pool:
                self.connection_pool.release(
                    connection, reusable=self._connection_reusable and not self.is_aborted)
            else:
                connection.close()
        if self.player:
            self.player.stop()


class ModelSpeedCalibrator:
    """Mede token/s do modelo com 1 mensagem curta e calibra os parâmetros adaptativos."""

    _cached_calibration: Optional[dict] = None
    _lock = threading.Lock()

    @classmethod
    def obter_calibracao(cls) -> dict:
        with cls._lock:
            if cls._cached_calibration is not None:
                return cls._cached_calibration

            # Tenta carregar de ayla_metrics.json
            if METRICS_PATH.is_file():
                try:
                    data = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
                    cal = data.get("live_model_calibration")
                    if isinstance(cal, dict) and "tokens_per_second" in cal:
                        cls._cached_calibration = cal
                        return cal
                except Exception:
                    pass

            default_cal = {
                "tokens_per_second": 35.0,
                "ttft": 1.2,
                "chunk_length": 100,
                "min_flush_chars": 25,
                "max_buffer_chars": 80,
                "idle_flush_timeout": 0.55,
                "calibrated_at": 0,
            }
            cls._cached_calibration = default_cal
            return default_cal

    @classmethod
    def calibrar_velocidade_modelo(cls, bot_instance, force: bool = False) -> dict:
        """Manda 1 mensagem rápida de calibração para medir os tokens/s do modelo."""
        cal = cls.obter_calibracao()
        # Se já foi calibrado nas últimas 2 horas e não for forçado, usa o cache
        if not force and cal.get("calibrated_at", 0) > (time.time() - 7200) and cal.get("tokens_per_second", 0) > 0:
            return cal

        client = getattr(bot_instance, "zai_client", None)
        if client is None:
            try:
                from zai_provider import ZaiClient
                api_key = os.getenv("ZAI_API_KEY", "").strip()
                if not api_key and SETTINGS_PATH.is_file():
                    st = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
                    api_key = st.get("zai_api_key", "").strip()
                if api_key:
                    client = ZaiClient(api_key=api_key)
            except Exception:
                pass

        if client is None:
            return cal

        print("⚡ [Live Speed] Enviando 1 mensagem para calibrar velocidade e tokens/s do modelo...")
        try:
            model_target = getattr(bot_instance, "modelo_atual", "glm-5.3-flash") if bot_instance else "glm-5.3-flash"
            session = client.create_session(model=model_target)

            t0 = time.time()
            ttft = None
            tokens_count = 0
            chars_count = 0
            usage = None

            prompt_calibracao = ""
            events = session.stream(prompt_calibracao)
            for ev in events:
                if ev.text_delta:
                    if ttft is None:
                        ttft = time.time() - t0
                    chars_count += len(ev.text_delta)
                if ev.usage:
                    usage = ev.usage

            t1 = time.time()
            ttft = ttft or (t1 - t0)
            elapsed_gen = max(0.05, t1 - (t0 + ttft))

            # Obtém tokens de saída
            completion_tokens = getattr(usage, "completion_tokens", None) if usage else None
            if completion_tokens is None or completion_tokens <= 0:
                completion_tokens = max(1, int(chars_count / 3.2))

            tps = completion_tokens / elapsed_gen
            print(f"📊 [Live Speed] Calibração: {tps:.1f} tokens/s (TTFT: {ttft:.2f}s, tokens: {completion_tokens}).")

            # Adaptação
            if tps >= 40.0:
                chunk_len = 100
                min_flush = 25
                max_buf = 80
                idle_to = 0.55
            elif tps >= 20.0:
                chunk_len = 140
                min_flush = 45
                max_buf = 110
                idle_to = 0.85
            else:
                chunk_len = 180
                min_flush = 70
                max_buf = 150
                idle_to = 1.2

            new_cal = {
                "tokens_per_second": round(tps, 2),
                "ttft": round(ttft, 3),
                "chunk_length": chunk_len,
                "min_flush_chars": min_flush,
                "max_buffer_chars": max_buf,
                "idle_flush_timeout": idle_to,
                "calibrated_at": time.time(),
            }

            with cls._lock:
                cls._cached_calibration = new_cal

            # Salva métricas
            try:
                metrics_data = {}
                if METRICS_PATH.is_file():
                    metrics_data = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
                metrics_data["live_model_calibration"] = new_cal
                METRICS_PATH.write_text(json.dumps(metrics_data, indent=2), encoding="utf-8")
            except Exception as me:
                print(f"⚠️ [Live Speed] Erro ao salvar métricas: {me}")

            print(f"✨ [Live Speed] Parâmetros adaptados com sucesso: chunk_length={chunk_len}, min_flush={min_flush}. Nanodaze ~🐾")
            return new_cal

        except Exception as exc:
            print(f"⚠️ [Live Speed] Falha ao calibrar modelo: {exc}")
            return cal
