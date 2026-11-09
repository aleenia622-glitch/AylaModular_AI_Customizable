"""Detecção local de fala antes de enviar áudio ao Whisper."""

import audioop
import io
from pathlib import Path
import subprocess
import tempfile
import wave

import webrtcvad


def prepare_whisper_audio(audio: bytes, filename: str = "audio.wav") -> bytes:
    """Retorna WAV mono 16 kHz com fala ou b'' quando não há fala.

    Falhas de decodificação são propagadas: áudio não verificado não é enviado.
    Preserva 300 ms ao redor da fala e pausas curtas entre palavras.
    """
    pcm = None
    try:
        with wave.open(io.BytesIO(audio), "rb") as source:
            if (source.getnchannels() == 1 and source.getsampwidth() == 2
                    and source.getframerate() == 16000
                    and source.getcomptype() == "NONE"):
                pcm = source.readframes(source.getnframes())
    except (wave.Error, EOFError):
        pass
    if pcm is None:
        # Arquivo buscável também suporta M4A/MP4 com índice no final.
        with tempfile.TemporaryDirectory(prefix="ayla-whisper-") as directory:
            source_path = Path(directory) / ("input" + Path(filename).suffix)
            source_path.write_bytes(audio)
            decoded = subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
                 "-i", str(source_path), "-vn", "-ac", "1", "-ar", "16000",
                 "-f", "s16le", "pipe:1"],
                capture_output=True, timeout=120,
            )
            if decoded.returncode:
                raise ValueError("Não foi possível decodificar o áudio para detectar fala.")
            pcm = decoded.stdout

    frame_bytes = 960  # 30 ms, PCM 16 bits, 16 kHz.
    padding_bytes = 9600  # 300 ms.
    vad = webrtcvad.Vad(2)
    intervals = []
    voiced_bytes = 0
    for start in range(0, len(pcm), frame_bytes):
        frame = pcm[start:start + frame_bytes]
        speech = vad.is_speech(frame.ljust(frame_bytes, b"\0"), 16000)
        if not speech or audioop.rms(frame, 2) < 100:
            continue
        voiced_bytes += len(frame)
        left = max(0, start - padding_bytes)
        right = min(len(pcm), start + len(frame) + padding_bytes)
        if intervals and left <= intervals[-1][1]:
            intervals[-1][1] = right
        else:
            intervals.append([left, right])
    # Exige ao menos 90 ms de fala para rejeitar estalos isolados.
    if voiced_bytes < 2880:
        return b""
    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16000)
        for left, right in intervals:
            target.writeframesraw(pcm[left:right])
    return output.getvalue()
