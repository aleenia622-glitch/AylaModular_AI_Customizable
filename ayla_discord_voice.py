"""Recepção de voz da call: transporte Discord -> DAVE -> Opus -> PCM.

Adaptador local para discord.py 2.7.1 + discord-ext-voice-recv 0.5.2a179.
O discord.py negocia MLS/DAVE; a extensão publicada ainda só remove a
criptografia do transporte. Deciframos DAVE antes do jitter buffer, inclusive
antes de um pacote ser reutilizado para recuperação de áudio perdido (FEC).
Nenhuma classe instalada é alterada e nenhum dispositivo local é aberto.
"""

from __future__ import annotations

import audioop
import collections
import io
import logging
import struct
import time
import wave
import webrtcvad
from dataclasses import dataclass, field

import davey
import discord
from discord.ext import voice_recv
from discord.ext.voice_recv import rtp
from discord.ext.voice_recv.opus import PacketDecoder
from discord.ext.voice_recv.reader import AudioReader, UDPKeepAlive
from discord.ext.voice_recv.router import PacketRouter

log = logging.getLogger(__name__)
PCM_BYTES_PER_SECOND = 48000 * 2 * 2


def check_voice_dependencies():
    if discord.version_info[:3] < (2, 7, 1):
        raise RuntimeError("O modo call precisa de discord.py[voice] >= 2.7.1.")
    # Fail before reporting a successful connection if libopus is unavailable.
    discord.opus.Decoder()


def decrypt_transport(data: bytes, box) -> bytes:
    """Remove XChaCha20, extensões RTP e padding, preservando o frame DAVE.

    O tamanho das extensões é medido em palavras de 32 bits, não em número
    de elementos. Não interpretar bytes do frame como extensões de áudio.
    """
    if len(data) < 12 + 16 + 4 or data[0] >> 6 != 2:
        raise ValueError("Pacote RTP incompleto")
    header_size = 12 + 4 * (data[0] & 15)
    extension_size = 0
    if data[0] & 0x10:
        if len(data) < header_size + 4 + 20:
            raise ValueError("Extensão RTP incompleta")
        extension_size = struct.unpack_from(">H", data, header_size + 2)[0] * 4
        header_size += 4
    if len(data) < header_size + 20:
        raise ValueError("Cabeçalho RTP incompleto")
    payload = box.decrypt(data[header_size:-4], data[:header_size], data[-4:] + bytes(20))
    if extension_size > len(payload):
        raise ValueError("Tamanho de extensão RTP inválido")
    payload = payload[extension_size:]
    if data[0] & 0x20:
        padding = payload[-1] if payload else 0
        if not padding or padding > len(payload):
            raise ValueError("Padding RTP inválido")
        payload = payload[:-padding]
    return payload


def decrypt_dave(connection, user_id: int, payload: bytes) -> bytes:
    # Discord's explicit silence frame is not DAVE-encrypted.
    if payload == rtp.OPUS_SILENCE:
        return payload
    session = connection.dave_session
    if connection.dave_protocol_version:
        if session is None or not session.ready:
            raise ValueError("Aguardando chaves DAVE")
        return session.decrypt(user_id, davey.MediaType.audio, payload)
    # Preserve the session for late encrypted frames during a negotiated transition.
    if session and session.ready and session.can_passthrough(user_id):
        return session.decrypt(user_id, davey.MediaType.audio, payload)
    return payload


class RecoveringPacketDecoder(PacketDecoder):
    def pop_data(self, *, timeout=0):
        try:
            return super().pop_data(timeout=timeout)
        except discord.opus.OpusError:
            # A lost/corrupt frame must not kill reception for the entire channel.
            self.reset()
            self.router.reader.note_drop("opus")
            return None


class RecoveringPacketRouter(PacketRouter):
    def get_decoder(self, ssrc):
        with self._lock:
            if ssrc not in self.decoders:
                self.decoders[ssrc] = RecoveringPacketDecoder(self, ssrc)
            return self.decoders[ssrc]


class CallKeepAlive(UDPKeepAlive):
    def run(self):
        # Upstream sleeps for 5000 seconds, retaining the old voice client on
        # every rejoin. An interruptible wait also permits prompt shutdown.
        while not self._end_thread.is_set():
            vc = self.voice_client
            if vc.is_connected():
                try:
                    vc._connection.socket.sendto(
                        self.counter.to_bytes(8, "big"),
                        (vc._connection.endpoint_ip, vc._connection.voice_port),
                    )
                    self.counter = (self.counter + 1) % (2 ** 64)
                except OSError:
                    pass  # The connection state owns reconnect/recovery.
            self._end_thread.wait(5)


class DaveAudioReader(AudioReader):
    def __init__(self, sink, voice_client, *, after=None):
        super().__init__(sink, voice_client, after=after)
        self.packet_router = RecoveringPacketRouter(sink, self)
        self.keepalive = CallKeepAlive(voice_client)
        self.received_packets = 0
        self.dropped_packets = collections.Counter()
        self._last_warning = 0.0

    def note_drop(self, reason):
        self.dropped_packets[reason] += 1
        now = time.monotonic()
        if reason != "unknown_speaker" and now - self._last_warning >= 10:
            self._last_warning = now
            log.warning("[Discord Call] Pacotes descartados (%s); recebidos=%d, descartes=%s",
                        reason, self.received_packets, dict(self.dropped_packets))

    def callback(self, packet_data):
        if (not self.active or len(packet_data) < 2 or packet_data[0] >> 6 != 2
                or self._is_ip_discovery_packet(packet_data)):
            return
        try:
            if rtp.is_rtcp(packet_data):
                packet = rtp.decode_rtcp(self.decryptor.decrypt_rtcp(packet_data))
                self.packet_router.feed_rtcp(packet)
                return
            packet = rtp.decode_rtp(packet_data)
            user_id = self.voice_client._get_id_from_ssrc(packet.ssrc)
            if user_id is None:
                self.note_drop("unknown_speaker")
                return
            member = self.voice_client.guild.get_member(user_id)
            if user_id == self.voice_client.user.id or (member and member.bot):
                return
            payload = decrypt_transport(packet_data, self.decryptor.box)
        except Exception:
            # Never log encrypted payloads or voice session keys.
            self.note_drop("transport")
            return
        try:
            packet.decrypted_data = decrypt_dave(self.voice_client._connection, user_id, payload)
            if not packet.decrypted_data:
                return
        except Exception:
            self.note_drop("dave")
            return
        self.received_packets += 1
        self.speaking_timer.notify(packet.ssrc)
        try:
            self.packet_router.feed_rtp(packet)
        except Exception as exc:
            self.error = exc
            self.stop()


class DaveVoiceRecvClient(voice_recv.VoiceRecvClient):
    # Both Discord and the installed receive extension support this transport.
    supported_modes = ("aead_xchacha20_poly1305_rtpsize",)

    def listen(self, sink, *, after=None):
        if not self.is_connected():
            raise discord.ClientException("Not connected to voice")
        if not isinstance(sink, voice_recv.AudioSink):
            raise TypeError("sink must be an AudioSink")
        if self.is_listening():
            raise discord.ClientException("Already receiving audio")
        self._reader = DaveAudioReader(sink, self, after=after)
        self._reader.start()

    def _remove_ssrc(self, *, user_id):
        # Upstream dereferences _reader even when listening has already stopped.
        ssrc = self._id_to_ssrc.pop(user_id, None)
        if ssrc is not None:
            self._ssrc_to_id.pop(ssrc, None)
            if self._reader:
                self._reader.speaking_timer.drop_ssrc(ssrc)


@dataclass
class Utterance:
    user: object
    pcm: bytes
    continued: bool = False


@dataclass
class SpeakerBuffer:
    user: object
    pre_roll: collections.deque = field(default_factory=lambda: collections.deque(maxlen=40))
    frames: list = field(default_factory=list)
    size: int = 0
    voiced_seconds: float = 0.0
    last_voice: float = 0.0
    last_packet: float = 0.0
    started: float = 0.0
    confirmed: bool = False
    trailing_bytes: int = 0
    voice_run: float = 0.0
    chunk_voiced_seconds: float = 0.0
    vad: object = field(default_factory=lambda: webrtcvad.Vad(2))


class VoiceSegmenter:
    """VAD WebRTC e energia por pessoa, sem modificar o áudio recebido.

    feed/flush devem ser chamados sob o mesmo lock. O relógio de flush fecha
    frases mesmo quando o Discord para completamente de enviar pacotes.
    """
    def __init__(self, silence_seconds=0.7, threshold=350, max_seconds=20):
        self.silence_seconds = silence_seconds
        self.threshold = threshold
        self.max_seconds = max_seconds
        self.speakers = {}

    def feed(self, user, pcm, now):
        if not pcm or len(pcm) % 4 or len(pcm) > PCM_BYTES_PER_SECOND:
            return False, []
        ready = self.flush(now)
        if user.id not in self.speakers and len(self.speakers) >= 64:
            return False, ready
        state = self.speakers.setdefault(user.id, SpeakerBuffer(user))
        state.last_packet = now
        mono = audioop.tomono(pcm, 2, 0.5, 0.5)
        voiced_seconds = 0.0
        for offset in range(0, len(mono), 960):
            frame = mono[offset:offset + 960]
            speech = state.vad.is_speech(frame.ljust(960, b"\0"), 48000)
            if speech and audioop.rms(frame, 2) >= self.threshold:
                voiced_seconds += len(frame) / 96000
        voiced = voiced_seconds > 0
        state.voice_run = state.voice_run + voiced_seconds if voiced else 0.0
        if voiced:
            state.trailing_bytes = 0
            if not state.frames:
                state.started = now
                state.frames.extend(state.pre_roll)
                state.size = sum(map(len, state.frames))
                state.pre_roll.clear()
            state.last_voice = now
            state.voiced_seconds += voiced_seconds
            state.chunk_voiced_seconds += voiced_seconds
        confirmed_now = False
        if state.frames or voiced:
            state.frames.append(pcm)
            state.size += len(pcm)
            if not voiced:
                state.trailing_bytes += len(pcm)
            if state.voice_run >= 0.12 and not state.confirmed:
                state.confirmed = confirmed_now = True
            if state.size >= self.max_seconds * PCM_BYTES_PER_SECOND:
                item = self._split(user.id, now)
                if item:
                    ready.append(item)
        else:
            state.pre_roll.append(pcm)
        return confirmed_now, ready

    def _split(self, user_id, now):
        state = self.speakers[user_id]
        item = None
        if state.confirmed:
            item = Utterance(state.user, b"".join(state.frames), continued=True)
        state.frames = []
        state.size = 0
        state.trailing_bytes = 0
        state.chunk_voiced_seconds = 0.0
        state.started = now
        # A divisão limita memória; não é um novo início de fala.
        return item

    def _finish(self, user_id):
        state = self.speakers.pop(user_id)
        if (state.confirmed and state.voiced_seconds >= 0.18
                and state.chunk_voiced_seconds > 0 and state.frames):
            pcm = b"".join(state.frames)
            trim_bytes = max(0, state.trailing_bytes - int(0.2 * PCM_BYTES_PER_SECOND))
            if trim_bytes:
                pcm = pcm[:-trim_bytes]
            log.info("[Discord Call] Áudio validado: duração=%.2fs, voz=%.2fs",
                     len(pcm) / PCM_BYTES_PER_SECOND, state.chunk_voiced_seconds)
            return Utterance(state.user, pcm)
        if state.frames:
            log.info("[Discord Call] Áudio descartado: voz insuficiente (%.2fs).",
                     state.chunk_voiced_seconds)
        return None

    def flush(self, now):
        ready = []
        for user_id, state in list(self.speakers.items()):
            if (state.frames or state.confirmed) and now - state.last_voice >= self.silence_seconds:
                item = self._finish(user_id)
                if item:
                    ready.append(item)
            elif state.frames and now - state.started >= self.max_seconds:
                item = self._split(user_id, now)
                if item:
                    ready.append(item)
            elif not state.frames and now - state.last_packet > 5:
                self.speakers.pop(user_id, None)
        return ready


def pcm_to_stt_wav(pcm):
    mono = audioop.tomono(pcm, 2, 0.5, 0.5)
    mono, _ = audioop.ratecv(mono, 2, 1, 48000, 16000, None)
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(mono)
    return output.getvalue()


def wav_to_discord_pcm(wav_bytes):
    """Normaliza TTS WAV para PCM 48 kHz estéreo, sem FFmpeg/dispositivo de som."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
        channels, width, rate = wav.getnchannels(), wav.getsampwidth(), wav.getframerate()
        pcm = wav.readframes(wav.getnframes())
    if channels not in (1, 2) or width not in (1, 2, 3, 4):
        raise ValueError("Formato WAV não suportado para a call")
    if width == 1:
        pcm = audioop.bias(pcm, 1, -128)
    if width != 2:
        pcm = audioop.lin2lin(pcm, width, 2)
    if rate != 48000:
        pcm, _ = audioop.ratecv(pcm, 2, channels, rate, 48000, None)
    if channels == 1:
        pcm = audioop.tostereo(pcm, 2, 1, 1)
    # PCMAudio expects complete 20 ms frames, including the final one.
    return pcm + bytes((-len(pcm)) % 3840) if pcm else b""
