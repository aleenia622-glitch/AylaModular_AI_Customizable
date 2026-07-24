#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Módulo independente do Modo Live da Ayla.
Contém a lógica de captura de tela, gravação de áudio com VAD dinâmico,
geração de áudio (TTS), janela flutuante da personagem (Sprite) e do microfone flutuante.
Pode ser importado pelo ayla_gui.py ou executado diretamente (`python ayla_live.py`).
"""

from __future__ import annotations

import collections
import contextlib
import io
import json
import os
import queue
import re
import shutil
import sys
import threading
import time
import wave
import warnings
from datetime import datetime
from pathlib import Path

try:
    from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, QSize, QObject, Signal
    from PySide6.QtGui import QColor, QIcon, QImage, QPixmap, QTextCursor
    from PySide6.QtWidgets import (
        QApplication,
        QFrame,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QGraphicsDropShadowEffect,
        QPushButton as QtPushButton,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 precisa estar instalado para abrir o Modo Live da Ayla.") from exc

try:
    import cv2
except Exception:
    cv2 = None

try:
    import soundcard as sc
    import numpy as np
except ImportError:
    sc = None
    np = None


BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
SETTINGS_PATH = BASE_DIR / "ayla_settings.json"
VOICEVOX_OUTPUT_PATH = BASE_DIR / "voicevox" / "saida_gui.wav"
BUFFER_VIDEO_DIR = BASE_DIR / "Buffer de video"


class SmoothButton(QtPushButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setOffset(0, 2)
        self._shadow.setBlurRadius(0)
        self._shadow.setColor(QColor(126, 232, 250, 0))
        self.setGraphicsEffect(self._shadow)
        self._shadow_anim = QPropertyAnimation(self._shadow, b"blurRadius", self)
        self._shadow_anim.setDuration(135)
        self._shadow_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _animate_shadow(self, blur: float, color: QColor):
        self._shadow_anim.stop()
        self._shadow.setColor(color)
        self._shadow_anim.setStartValue(self._shadow.blurRadius())
        self._shadow_anim.setEndValue(blur)
        self._shadow_anim.start()

    def enterEvent(self, event):
        self._animate_shadow(18, QColor(126, 232, 250, 72))
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate_shadow(0, QColor(126, 232, 250, 0))
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        self._animate_shadow(7, QColor(255, 158, 187, 90))
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self.rect().contains(event.pos()):
            self._animate_shadow(18, QColor(126, 232, 250, 72))
        else:
            self._animate_shadow(0, QColor(126, 232, 250, 0))
        super().mouseReleaseEvent(event)


QPushButton = SmoothButton


class ConsoleRedirector:
    def __init__(self, queue_obj: queue.Queue[str], original_stream):
        self.queue = queue_obj
        self.original_stream = original_stream

    def write(self, text: str):
        if self.original_stream:
            try:
                self.original_stream.write(text)
            except Exception:
                pass
        if text:
            if "Loop de mensagens espontâneas" in text or "[Mensagens Espontâneas] Próxima verificação" in text:
                return
            self.queue.put(str(text))

    def flush(self):
        if self.original_stream:
            try:
                self.original_stream.flush()
            except Exception:
                pass


class ClickableImage(QPushButton):
    def __init__(self, path: Path, callback, parent=None):
        super().__init__(parent)
        self.path = path
        self.clicked.connect(lambda: callback(path))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("mediaButton")


class ScreenCaptureBuffer(threading.Thread):
    def __init__(self, fps=2, duration_sec=60):
        super().__init__()
        self.fps = fps
        self.duration_sec = duration_sec
        self.maxlen = int(fps * duration_sec)
        self.frames = collections.deque(maxlen=self.maxlen)
        self.running = False
        self.active = False
        self.daemon = True
        self._lock = threading.Lock()

    def run(self):
        import cv2
        import numpy as np
        from PIL import ImageGrab
        import time

        frame_delay = 1.0 / self.fps
        while self.running:
            start_time = time.time()
            if self.active:
                try:
                    img = ImageGrab.grab()
                    img = img.resize((1280, 720))
                    frame = np.array(img)
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

                    with self._lock:
                        self.frames.append(frame)
                except Exception as e:
                    print(f"[Screen Buffer] Erro ao capturar tela: {e}")

            elapsed = time.time() - start_time
            sleep_time = frame_delay - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                time.sleep(0.01)

    def start_capturing(self):
        self.active = True

    def pause_capturing(self):
        self.active = False

    def save_video(self, output_path) -> bool:
        import cv2
        with self._lock:
            frames_to_write = list(self.frames)

        if not frames_to_write:
            print("[Screen Buffer] Nenhum frame capturado para salvar.")
            return False

        try:
            height, width, _ = frames_to_write[0].shape
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            out = cv2.VideoWriter(output_path, fourcc, self.fps, (width, height))
            for f in frames_to_write:
                out.write(f)
            out.release()
            print(f"[Screen Buffer] Vídeo de {len(frames_to_write)} frames salvo em {output_path}")
            return True
        except Exception as e:
            print(f"[Screen Buffer] Erro ao gravar vídeo: {e}")
            return False


class AudioRecorder:
    def __init__(self, samplerate=16000, silence_threshold=800, dynamic_noise_gate=True, parent_window=None, mic_name=None, live_call_mode=False, mix_system_audio=True, speaker_name=None):
        self.fs = samplerate
        self.recording = False
        self.audio_data = []
        self.thread = None
        self.live_mode = False
        self.live_call_mode = live_call_mode
        self.mix_system_audio = mix_system_audio
        self.silence_threshold = silence_threshold
        self.dynamic_noise_gate = dynamic_noise_gate
        self.parent_window = parent_window
        self.mic_name = mic_name
        self.speaker_name = speaker_name

        self.has_spoken = False
        self.last_speech_time = time.time()

    def start(self, live_mode=False):
        self.recording = True
        self.live_mode = live_mode
        self.audio_data = []
        self.has_spoken = False
        self.start_time = time.time()
        self.last_speech_time = time.time()

        self.pre_buffer = collections.deque(maxlen=13)
        self.initial_volumes = []
        self.dynamic_threshold = self.silence_threshold

        self.thread = threading.Thread(target=self._record_loop, daemon=True)
        self.thread.start()

    def _record_loop(self):
        warnings.filterwarnings("ignore", message="data discontinuity in recording")
        try:
            mic = None
            if not self.live_call_mode:
                if self.mic_name:
                    for m in sc.all_microphones():
                        if m.name == self.mic_name:
                            mic = m
                            break
                    if mic is None:
                        for m in sc.all_microphones():
                            if self.mic_name.lower() in m.name.lower() or m.name.lower() in self.mic_name.lower():
                                mic = m
                                break
                if mic is None:
                    mic = sc.default_microphone()

            loopback = None
            if self.live_mode or self.live_call_mode:
                try:
                    default_speaker_name = sc.default_speaker().name
                    for m in sc.all_microphones(include_loopback=True):
                        if m.isloopback and default_speaker_name.lower() in m.name.lower():
                            loopback = m
                            break
                    if not loopback:
                        for m in sc.all_microphones(include_loopback=True):
                            if m.isloopback:
                                loopback = m
                                break
                except Exception as e:
                    print(f"[AudioRecorder] Erro ao buscar loopback padrão: {e}")

            block_size = 1024

            if self.live_call_mode:
                if not loopback:
                    raise RuntimeError("Dispositivo de loopback (som do PC) não encontrado para o modo Chamada.")
                recorder_context = loopback.recorder(samplerate=self.fs, channels=1)
                loopback_context = contextlib.nullcontext()
            else:
                recorder_context = mic.recorder(samplerate=self.fs, channels=1)
                loopback_context = loopback.recorder(samplerate=self.fs, channels=1) if loopback else contextlib.nullcontext()

            with recorder_context as rec_device, loopback_context as loop_rec:
                print(f"[AudioRecorder] Gravação iniciada. Modo Chamada: {self.live_call_mode}. Loopback: {loopback.name if loopback else 'Desativado'}")

                while self.recording:
                    if self.live_call_mode:
                        loop_data = rec_device.record(block_size)
                        analyzed_data = loop_data
                        mixed_data = loop_data
                    else:
                        mic_data = rec_device.record(block_size)
                        analyzed_data = mic_data

                        if loopback and loop_rec:
                            try:
                                loop_data = loop_rec.record(block_size)
                                mixed_data = mic_data * 0.7 + loop_data * 0.3
                            except Exception:
                                mixed_data = mic_data
                        else:
                            mixed_data = mic_data

                    current_time = time.time()
                    clean_audio = analyzed_data - np.mean(analyzed_data) if analyzed_data is not None else np.zeros((block_size, 1))
                    volume = np.sqrt(np.mean((clean_audio * 32767)**2))

                    if self.dynamic_noise_gate:
                        if current_time - self.start_time <= 0.5:
                            if volume < 20000:
                                self.initial_volumes.append(volume)
                        else:
                            if len(self.initial_volumes) > 0:
                                avg_noise = np.mean(self.initial_volumes)
                                self.dynamic_threshold = min(max(avg_noise * 2.2, 1500.0), 8000.0)
                                self.initial_volumes = []
                                print(f"[AudioRecorder] Ruído de fundo calibrado. Médio: {avg_noise:.1f} -> Threshold Dinâmico: {self.dynamic_threshold:.1f}")

                            if volume > self.dynamic_threshold:
                                self.last_speech_time = current_time
                                if not self.has_spoken:
                                    self.has_spoken = True
                                    print("[AudioRecorder] Voz detectada!")
                                    if (self.live_mode or self.live_call_mode) and self.parent_window and self.parent_window.parent_gui:
                                        self.parent_window.parent_gui.response_queue.put(("voice_chat_user_speaking", None))
                    else:
                        if current_time - self.start_time > 0.5:
                            if volume > self.silence_threshold:
                                self.last_speech_time = current_time
                                if not self.has_spoken:
                                    self.has_spoken = True
                                    print("[AudioRecorder] Voz detectada!")
                                    if (self.live_mode or self.live_call_mode) and self.parent_window and self.parent_window.parent_gui:
                                        self.parent_window.parent_gui.response_queue.put(("voice_chat_user_speaking", None))

                    if not self.live_mode and not self.live_call_mode:
                        self.audio_data.append(mixed_data.copy())
                    else:
                        if self.has_spoken:
                            if self.pre_buffer:
                                self.audio_data.extend(self.pre_buffer)
                                self.pre_buffer.clear()
                            self.audio_data.append(mixed_data.copy())
                        else:
                            self.pre_buffer.append(mixed_data.copy())

        except Exception as e:
            print(f"[AudioRecorder] Erro na thread de gravação: {e}")

    def stop(self, force: bool = False) -> bytes | None:
        self.recording = False
        if self.thread:
            try:
                self.thread.join(timeout=1.0)
            except Exception:
                pass
            self.thread = None

        if force and not self.audio_data and getattr(self, "pre_buffer", None):
            self.audio_data.extend(self.pre_buffer)
            self.pre_buffer.clear()

        if not self.audio_data or np is None:
            return None

        audio_np = np.concatenate(self.audio_data, axis=0)

        chunk_samples = int(self.fs * 0.1)
        num_samples = len(audio_np)
        active_chunks = 0
        threshold = getattr(self, "dynamic_threshold", self.silence_threshold)
        if threshold is None:
            threshold = 1500

        for i in range(0, num_samples, chunk_samples):
            chunk = audio_np[i : i + chunk_samples]
            if len(chunk) < chunk_samples // 2:
                continue
            chunk_clean = chunk - np.mean(chunk)
            chunk_rms = np.sqrt(np.mean((chunk_clean * 32767)**2))
            if chunk_rms > threshold:
                active_chunks += 1

        duration_sec = num_samples / self.fs
        print(f"[AudioRecorder] VAD Final - Duração total: {duration_sec:.2f}s, Blocos ativos: {active_chunks} (limiar de voz: {threshold:.1f})")

        if not force and active_chunks < 2:
            print("[AudioRecorder] Gravação descartada localmente: nenhum som/fala ativa suficiente acima do ruído de fundo.")
            return None

        audio_int16 = (audio_np * 32767).astype(np.int16)

        wav_io = io.BytesIO()
        with wave.open(wav_io, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.fs)
            wf.writeframes(audio_int16.tobytes())

        return wav_io.getvalue()


class AylaSpriteWindow(QWidget):
    def __init__(self, parent_gui):
        super().__init__()
        self.parent_gui = parent_gui
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(259, 292)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.sprite_label = QLabel(self)
        self.sprite_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sprite_label.setFixedSize(259, 292)
        self.sprite_label.setStyleSheet("background: transparent;")
        self.layout.addWidget(self.sprite_label)

        self._drag_position = None
        self.load_position()

    def update_sprite(self, state_name):
        if not state_name:
            self.sprite_label.clear()
            return

        sprite_dir = Path(r"c:\Users\Aleenia\Documents\AI\sprite\processados")
        sprite_files = {
            "esperando": sprite_dir / "sprite_esperando.png",
            "falandousuario": sprite_dir / "sprite_ouvindo.png",
            "processando": sprite_dir / "sprite_processando.png",
            "falandobot": sprite_dir / "sprite_falando.png"
        }

        file_path = sprite_files.get(state_name)
        if file_path and file_path.is_file():
            pixmap = QPixmap(str(file_path))
            self.sprite_label.setPixmap(pixmap)
        else:
            self.sprite_label.clear()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_position is not None:
            self.move(event.globalPosition().toPoint() - self._drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_position = None
        self.save_position()
        event.accept()

    def save_position(self):
        settings = self.parent_gui._load_settings()
        settings["sprite_window_x"] = self.x()
        settings["sprite_window_y"] = self.y()
        self.parent_gui._safe_write_json(SETTINGS_PATH, settings)

    def load_position(self):
        settings = self.parent_gui._load_settings()
        x = settings.get("sprite_window_x")
        y = settings.get("sprite_window_y")
        if x is not None and y is not None:
            self.move(x, y)
        else:
            screen = QApplication.primaryScreen()
            if screen:
                screen_geometry = screen.geometry()
                x_center = (screen_geometry.width() - self.width()) // 2
                y_center = (screen_geometry.height() - self.height()) // 2
                self.move(x_center, y_center)
            else:
                self.move(100, 100)


def generate_tts_audio(clean_text: str, settings: dict) -> bytes | None:
    primary_engine = settings.get("tts_engine", "voicevox")

    all_engines = ["fish_audio", "voicevox", "sapi5"]
    engine_order = [primary_engine] + [e for e in all_engines if e != primary_engine]

    wav_out = None

    for engine in engine_order:
        if engine == "fish_audio":
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
                        break
                    else:
                        print(f"[Voice Chat] Erro no Fish Audio (Status {response.status_code}): {response.text}")
                except Exception as exc:
                    print(f"[Voice Chat] Exceção no Fish Audio: {exc}")
            else:
                print("[Voice Chat] Fish Audio sem API Key. Tentando próximo motor TTS...")

        elif engine == "voicevox":
            style_id = settings.get("voice_chat_style_id", 3)
            try:
                print("[Voice Chat] Tentando gerar áudio via Voicevox Local...")
                sys.path.append(str(BASE_DIR / "voicevox"))
                from falar_texto import gerar_audio_voicevox_bytes
                wav_out = gerar_audio_voicevox_bytes(clean_text, style_id)
                if wav_out and len(wav_out) > 100:
                    print("[Voice Chat] Áudio gerado com sucesso via Voicevox!")
                    break
            except Exception as exc:
                print(f"[Voice Chat] Erro no Voicevox Local: {exc}")

        elif engine == "sapi5":
            try:
                print("[Voice Chat] Tentando gerar áudio via SAPI5 (Voz Nativa do Windows)...")
                import win32com.client
                import tempfile
                import time
                speaker = win32com.client.Dispatch('SAPI.SpVoice')
                stream = win32com.client.Dispatch('SAPI.SpFileStream')
                tmp_sapi = Path(tempfile.gettempdir()) / f"sapi_temp_{int(time.time()*1000)}.wav"
                stream.Open(str(tmp_sapi), 3, False)
                speaker.AudioOutputStream = stream
                speaker.Speak(clean_text)
                stream.Close()
                if tmp_sapi.exists() and tmp_sapi.stat().st_size > 100:
                    wav_out = tmp_sapi.read_bytes()
                    try:
                        tmp_sapi.unlink()
                    except Exception:
                        pass
                    print("[Voice Chat] Áudio gerado com sucesso via SAPI5 Nativo!")
                    break
            except Exception as exc:
                print(f"[Voice Chat] Erro na voz nativa SAPI5: {exc}")

    return wav_out


class FloatingMicrophoneWindow(QWidget):
    def __init__(self, parent_gui):
        super().__init__()
        self.parent_gui = parent_gui
        self.state = "idle"  # idle, listening, processing
        self.is_speaking = False
        self.recorder = None
        self._drag_position = None

        self.live_mode = False
        self.live_call_mode = False
        self.silence_threshold = 1500
        self.dynamic_noise_gate = True
        self.screen_recording_enabled = True
        self.screen_buffer = None
        self.live_video_path = str(BUFFER_VIDEO_DIR / "live_screen.mp4")

        self.last_user_speech_time = time.time()
        self.last_inactivity_prompt_time = 0.0
        self.inactivity_timeout = 120.0  # 2 minutos de silêncio para a Ayla agir
        self.inactivity_cooldown = 180.0 # 3 minutos de intervalo entre avisos de inatividade
        self.is_processing_inactivity = False

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(340)

        self._init_ui()

        self.speech_timer = QTimer(self)
        self.speech_timer.setSingleShot(True)
        self.speech_timer.timeout.connect(self.on_speech_finished)

        self.record_safety_timer = QTimer(self)
        self.record_safety_timer.setSingleShot(True)
        self.record_safety_timer.timeout.connect(self.stop_recording_and_process)

        self.live_silence_timer = QTimer(self)
        self.live_silence_timer.timeout.connect(self.check_live_silence)
        self.live_silence_timer.start(100)

        self.pulse_timer = QTimer(self)
        self.pulse_timer.timeout.connect(self.on_pulse_tick)
        self.pulse_angle = 0.0

        self.mic_shadow = QGraphicsDropShadowEffect(self.mic_btn)
        self.mic_shadow.setOffset(0, 0)
        self.mic_shadow.setBlurRadius(0)
        self.mic_shadow.setColor(QColor(126, 232, 250, 0))
        self.mic_btn.setGraphicsEffect(self.mic_shadow)

        self.reposition_to_default()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.bubble_frame = QFrame()
        self.bubble_frame.setObjectName("bubbleFrame")
        self.bubble_frame.setStyleSheet("""
            QFrame#bubbleFrame {
                background-color: rgba(22, 23, 38, 0.95);
                border: 1.5px solid #2d304e;
                border-radius: 12px;
            }
        """)

        bubble_layout = QVBoxLayout(self.bubble_frame)
        bubble_layout.setContentsMargins(12, 10, 12, 10)

        self.bubble_label = QLabel("Olá! Em que posso ajudar?")
        self.bubble_label.setObjectName("bubbleLabel")
        self.bubble_label.setWordWrap(True)
        self.bubble_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bubble_label.setStyleSheet("color: #f1f5f9; font-size: 13px; font-weight: 500;")
        bubble_layout.addWidget(self.bubble_label)

        layout.addWidget(self.bubble_frame)
        self.bubble_frame.hide()

        self.panel_frame = QFrame()
        self.panel_frame.setObjectName("micPanel")
        self.panel_frame.setStyleSheet("""
            QFrame#micPanel {
                background-color: #161726;
                border: 1px solid #26283f;
                border-radius: 16px;
            }
        """)

        panel_layout = QVBoxLayout(self.panel_frame)
        panel_layout.setContentsMargins(10, 8, 10, 12)
        panel_layout.setSpacing(4)

        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(4, 0, 4, 0)

        handle = QFrame()
        handle.setFixedSize(36, 4)
        handle.setStyleSheet("background-color: #4a4d68; border-radius: 2px;")

        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("closeBtn")
        self.close_btn.setFixedSize(20, 20)
        self.close_btn.setStyleSheet("""
            QPushButton#closeBtn {
                background: transparent;
                border: none;
                color: #a5a9c0;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton#closeBtn:hover {
                color: #ff5c8a;
            }
        """)
        self.close_btn.clicked.connect(self.hide_window)

        top_bar.addStretch(1)
        top_bar.addWidget(handle)
        top_bar.addStretch(1)
        top_bar.addWidget(self.close_btn)

        panel_layout.addLayout(top_bar)

        controls = QHBoxLayout()
        controls.setContentsMargins(10, 2, 10, 2)
        controls.setSpacing(12)

        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setObjectName("iconBtn")
        self.settings_btn.setFixedSize(36, 36)
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.setStyleSheet(self._icon_btn_style())
        self.settings_btn.clicked.connect(self.go_to_settings)

        self.noisegate_btn = QPushButton("🛡️")
        self.noisegate_btn.setObjectName("iconBtn")
        self.noisegate_btn.setFixedSize(36, 36)
        self.noisegate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_noisegate_button_style()
        self.noisegate_btn.clicked.connect(self.toggle_noisegate)

        self.mic_btn = QtPushButton("🎙")
        self.mic_btn.setObjectName("micBtn")
        self.mic_btn.setFixedSize(70, 70)
        self.mic_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_mic_button_style()
        self.mic_btn.clicked.connect(self.on_mic_btn_clicked)

        self.screen_record_btn = QPushButton("📺")
        self.screen_record_btn.setObjectName("iconBtn")
        self.screen_record_btn.setFixedSize(36, 36)
        self.screen_record_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_screen_record_button_style()
        self.screen_record_btn.clicked.connect(self.toggle_screen_recording)

        self.help_btn = QPushButton("?")
        self.help_btn.setObjectName("iconBtn")
        self.help_btn.setFixedSize(36, 36)
        self.help_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.help_btn.setStyleSheet(self._icon_btn_style())
        self.help_btn.clicked.connect(self.show_help)

        controls.addWidget(self.settings_btn)
        controls.addWidget(self.noisegate_btn)
        controls.addWidget(self.mic_btn)
        controls.addWidget(self.screen_record_btn)
        controls.addWidget(self.help_btn)

        panel_layout.addLayout(controls)
        layout.addWidget(self.panel_frame, 0, Qt.AlignmentFlag.AlignCenter)

    def _icon_btn_style(self):
        return """
            QPushButton#iconBtn {
                background: transparent;
                border: none;
                color: #a5a9c0;
                font-size: 18px;
            }
            QPushButton#iconBtn:hover {
                color: #7ee8fa;
            }
        """

    def update_mic_button_style(self):
        if self.state == "idle":
            bg = "#252744"
            border = "#2d304e"
            color = "#f1f5f9"
        elif self.state == "listening":
            bg = "#7ee8fa"
            border = "#7ee8fa"
            color = "#071018"
        elif self.state == "processing":
            bg = "#ff9ebb"
            border = "#ff9ebb"
            color = "#071018"

        self.mic_btn.setStyleSheet(f"""
            QPushButton#micBtn {{
                background-color: {bg};
                border: 2px solid {border};
                border-radius: 35px;
                color: {color};
                font-size: 26px;
            }}
            QPushButton#micBtn:hover {{
                border-color: #7ee8fa;
            }}
        """)

        if getattr(self, "live_call_mode", False):
            self.mic_btn.setText("📞")
            self.mic_btn.setToolTip("Chamada de Voz Ativada (Clique para desligar)")
        else:
            self.mic_btn.setText("🎙")
            if getattr(self, "live_mode", False):
                self.mic_btn.setToolTip("Modo Live Ativado (Aviso: Ayla recebe vídeos da sua tela)")
            else:
                self.mic_btn.setToolTip("Modo Normal (Apenas voz)")

    def on_pulse_tick(self):
        import math
        self.pulse_angle += 0.15
        radius = 14 + int(8 * math.sin(self.pulse_angle))
        self.mic_shadow.setBlurRadius(radius)

    def start_pulse_animation(self, color: QColor):
        self.mic_shadow.setColor(color)
        self.pulse_angle = 0.0
        self.pulse_timer.start(40)

    def stop_pulse_animation(self):
        self.pulse_timer.stop()
        self.mic_shadow.setBlurRadius(0)
        self.mic_shadow.setColor(QColor(0, 0, 0, 0))

    def reposition_to_default(self):
        screen = QApplication.primaryScreen().geometry()
        x = screen.width() - 320
        y = screen.height() - 250
        self.move(x, y)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_position is not None:
            self.move(event.globalPosition().toPoint() - self._drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_position = None
        event.accept()

    def show_bubble(self, text):
        self.bubble_label.setText(text)
        self.bubble_frame.show()
        self.adjustSize()

    def toggle_screen_recording(self):
        if getattr(self, "screen_recording_enabled", True):
            self.screen_recording_enabled = False
            self.show_bubble("Gravação de Tela: DESATIVADA")
            if self.live_mode and self.screen_buffer:
                self.screen_buffer.pause_capturing()
                with self.screen_buffer._lock:
                    self.screen_buffer.frames.clear()
        else:
            self.screen_recording_enabled = True
            self.show_bubble("Gravação de Tela: ATIVADA")
            if self.live_mode and self.screen_buffer:
                with self.screen_buffer._lock:
                    self.screen_buffer.frames.clear()
                self.screen_buffer.start_capturing()
        self.update_screen_record_button_style()

    def update_screen_record_button_style(self):
        if getattr(self, "screen_recording_enabled", True):
            self.screen_record_btn.setStyleSheet("""
                QPushButton#iconBtn {
                    background: transparent;
                    border: none;
                    color: #7ee8fa;
                    font-size: 18px;
                }
                QPushButton#iconBtn:hover {
                    color: #ff5c8a;
                }
            """)
            self.screen_record_btn.setToolTip("Gravação de Tela: ATIVADA")
        else:
            self.screen_record_btn.setStyleSheet("""
                QPushButton#iconBtn {
                    background: transparent;
                    border: none;
                    color: #4a4d68;
                    font-size: 18px;
                }
                QPushButton#iconBtn:hover {
                    color: #7ee8fa;
                }
            """)
            self.screen_record_btn.setToolTip("Gravação de Tela: DESATIVADA")

    def start_recording(self):
        try:
            import soundcard as sc
            import numpy as np
        except ImportError:
            self.show_bubble("Erro: soundcard/numpy não instalado.")
            return

        self.state = "listening"
        self.update_mic_button_style()
        if self.live_mode:
            self.show_bubble("Ouvindo... 🎙\n(Aviso: Os vídeos recebidos são a sua tela)")
        elif getattr(self, "live_call_mode", False):
            self.show_bubble("Ouvindo (Chamada)... 🎙")
        else:
            self.show_bubble("Listening...")
        self.start_pulse_animation(QColor(126, 232, 250, 220))

        if self.live_mode and self.screen_buffer and getattr(self, "screen_recording_enabled", True):
            with self.screen_buffer._lock:
                self.screen_buffer.frames.clear()
            self.screen_buffer.start_capturing()

        try:
            if self.live_mode or getattr(self, "live_call_mode", False):
                self.update_sprite_image("esperando")

            settings = self.parent_gui._load_settings()
            selected_mic = settings.get("selected_mic_name")
            selected_speaker = settings.get("selected_speaker_name")
            mix_audio = settings.get("mix_system_audio", True)

            self.recorder = AudioRecorder(
                silence_threshold=self.silence_threshold,
                dynamic_noise_gate=self.dynamic_noise_gate,
                parent_window=self,
                mic_name=selected_mic,
                live_call_mode=getattr(self, "live_call_mode", False),
                mix_system_audio=mix_audio,
                speaker_name=selected_speaker
            )
            self.recorder.start(live_mode=(self.live_mode or getattr(self, "live_call_mode", False)))
            self.record_safety_timer.start(90000 if (self.live_mode or getattr(self, "live_call_mode", False)) else 30000)
        except Exception as exc:
            self.state = "idle"
            self.update_mic_button_style()
            self.stop_pulse_animation()
            self.show_bubble(f"Erro ao gravar: {exc}")

    def stop_recording_and_process(self, force=False):
        if not isinstance(force, bool):
            force = False

        if self.state != "listening":
            return

        if not force and (self.live_mode or getattr(self, "live_call_mode", False)) and self.recorder and not self.recorder.has_spoken:
            print("[Live/Call Mode] Nenhum som/fala detectada. Mantendo microfone aberto...")
            self.recorder.stop()
            self.start_recording()
            return

        if force and self.recorder:
            self.recorder.has_spoken = True
            if not self.recorder.audio_data and getattr(self.recorder, "pre_buffer", None):
                self.recorder.audio_data.extend(self.recorder.pre_buffer)
                self.recorder.pre_buffer.clear()

        self.state = "processing"
        if self.live_mode or getattr(self, "live_call_mode", False):
            self.update_sprite_image("processando")
        self.update_mic_button_style()
        self.show_bubble("Processing...")
        self.stop_pulse_animation()
        self.record_safety_timer.stop()

        if self.live_mode and self.screen_buffer and getattr(self, "screen_recording_enabled", True):
            self.screen_buffer.pause_capturing()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.live_video_path = str(BUFFER_VIDEO_DIR / f"clip_{timestamp}.mp4")
            self.screen_buffer.save_video(self.live_video_path)

        try:
            wav_bytes = self.recorder.stop(force=force)
            if not wav_bytes:
                self.state = "idle"
                self.update_mic_button_style()
                self.show_bubble("Nenhum som gravado.")
                if self.live_mode or getattr(self, "live_call_mode", False):
                    self.start_recording()
                return

            self.run_background_processing(wav_bytes)
        except Exception as exc:
            self.state = "idle"
            self.update_mic_button_style()
            self.show_bubble(f"Erro ao processar: {exc}")

    def run_background_processing(self, wav_bytes):
        def worker():
            try:
                try:
                    from dotenv import load_dotenv
                    load_dotenv()
                except ImportError:
                    pass

                settings = self.parent_gui._load_settings()
                stt_engine = settings.get("stt_engine", "auto")
                groq_key = settings.get("groq_api_key", "").strip() or os.getenv("GROQ_API_KEY", "").strip()

                text = ""
                transcription_success = False

                def try_groq():
                    nonlocal text, transcription_success
                    if not groq_key:
                        return False
                    try:
                        print("[Voice Chat] Tentando transcrição via Groq Whisper...")
                        import requests
                        url = "https://api.groq.com/openai/v1/audio/transcriptions"
                        headers = {"Authorization": f"Bearer {groq_key}"}
                        files = {"file": ("speech.wav", wav_bytes, "audio/wav")}
                        data = {
                            "model": "whisper-large-v3",
                            "language": "pt",
                            "response_format": "json",
                            "prompt": "Se houver apenas silêncio, ruído, música de fundo ou estática de microfone, ignore totalmente e retorne vazio. Não transcreva legendas fantasma.",
                            "temperature": 0.0
                        }
                        response = requests.post(url, headers=headers, files=files, data=data, timeout=15)
                        if response.status_code == 200:
                            res_json = response.json()
                            t = res_json.get("text", "").strip()
                            if t:
                                text = t
                                transcription_success = True
                                print(f"[Voice Chat] Transcrição Groq (Sucesso): '{text}'")
                                return True
                        print(f"[Voice Chat] Groq falhou (Status {response.status_code}): {response.text}")
                    except Exception as e:
                        print(f"[Voice Chat] Erro ao usar Groq Whisper: {e}")
                    return False

                def try_gemini():
                    nonlocal text, transcription_success
                    try:
                        print("[Voice Chat] Tentando transcrição via Gemini Multimodal...")
                        client = self.parent_gui.bot.genai_client
                        model = getattr(self.parent_gui.bot, "modelo_atual", "gemini-2.5-flash-lite")
                        from google.genai import types
                        response = client.models.generate_content(
                            model=model,
                            contents=[
                                types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
                                "Transcreva este audio de fala do usuario de forma direta e exata. Retorne APENAS a transcricao pura, sem introducoes, aspas ou comentarios. Se for apenas silencio ou ruido, retorne vazio."
                            ]
                        )
                        t = response.text.strip() if response.text else ""
                        if t:
                            text = t
                            transcription_success = True
                            print(f"[Voice Chat] Transcrição Gemini (Sucesso): '{text}'")
                            return True
                    except Exception as e:
                        print(f"[Voice Chat] Erro ao usar Gemini para transcrição: {e}")
                    return False

                if stt_engine == "gemini":
                    if not try_gemini():
                        print("[Voice Chat] Fallback STT: tentando Groq Whisper...")
                        try_groq()
                elif stt_engine == "groq_whisper":
                    if not try_groq():
                        print("[Voice Chat] Fallback STT: tentando Gemini...")
                        try_gemini()
                else:
                    if not try_groq():
                        try_gemini()

                if text:
                    test_text = text.lower().strip()
                    is_hallucination = False
                    hallucination_patterns = [
                        r"legenda(s)? por\b",
                        r"legendado por\b",
                        r"subtitles? by\b",
                        r"thank you for watching\b",
                        r"obrigado por assistir\b",
                        r"inscreva-se no canal\b",
                        r"acesse o nosso site\b",
                        r"acesse o site\b",
                        r"visite o nosso site\b",
                        r"visite o site\b",
                        r"opusdei\.pt",
                        r"\bopus dei\b",
                        r"amara\.org",
                        r"legendas\.tv",
                        r"sônia ruberti",
                        r"sonia ruberti",
                        r"deixe seu like\b",
                        r"deixe o seu like\b",
                        r"um grande abraço e até a próxima\b",
                        r"um abraço e até a próxima\b",
                        r"assista ao próximo vídeo\b",
                        r"assistir a este vídeo\b",
                        r"assistir ao vídeo\b",
                        r"deixe nos comentários\b",
                        r"deixe seu comentário\b",
                        r"não transcreva\b",
                        r"legendas fantasma\b"
                    ]
                    for pattern in hallucination_patterns:
                        if re.search(pattern, test_text):
                            is_hallucination = True
                            break
                    if is_hallucination:
                        print(f"[Voice Chat] Alucinação do Whisper detectada e descartada: '{text}'")
                        text = ""

                if not text:
                    if getattr(self, "live_mode", False) or getattr(self, "live_call_mode", False):
                        print("[Live/Call Mode] Transcrição vazia ou ruído descartado. Reiniciando microfone silenciosamente...")
                        self.parent_gui.response_queue.put(("voice_chat_text_silent_restart", ""))
                    else:
                        self.parent_gui.response_queue.put(("voice_chat_text", "Não consegui entender nada..."))
                        self.parent_gui.response_queue.put(("voice_chat_audio", None))
                    return

                self.last_user_speech_time = time.time()
                self.is_processing_inactivity = False

                arquivos_anexados = []
                if hasattr(self, "live_mode") and self.live_mode and getattr(self, "screen_recording_enabled", True):
                    video_path = Path(self.live_video_path)
                    if video_path.is_file():
                        try:
                            video_bytes = video_path.read_bytes()
                            arquivos_anexados.append((video_bytes, "video/mp4"))
                            print(f"[Voice Chat] Vídeo anexado e preservado: {video_path.name} ({len(video_bytes)} bytes)")
                        except Exception as e:
                            print(f"[Voice Chat] Erro ao ler vídeo para anexo: {e}")

                tts_engine = settings.get("tts_engine", "voicevox")

                if tts_engine == "fish_audio":
                    user_msg = f"{text}\n\n[Modo voz: Você está FALANDO diretamente com o usuário e não escrevendo no chat. Limite máximo de 500 caracteres. Não use a ferramenta 'converter_texto_para_audio_discord' de forma alguma (sua resposta de texto já será falada automaticamente). Não use emojis nem links.]"
                else:
                    user_msg = f"{text}\n\n[Modo voz: Você está FALANDO diretamente com o usuário e não escrevendo no chat. Responda de forma extremamente curta e concisa, no máximo em uma ou duas frases curtas (limite de 150 caracteres). Não use a ferramenta 'converter_texto_para_audio_discord' de forma alguma (sua resposta de texto já será falada automaticamente). Não use emojis nem links.]"

                if arquivos_anexados:
                    user_msg += "\n\n[Modo Live: Os vídeos recebidos são gravações em tempo real da tela do usuário. Analise o clipe de vídeo da tela anexado para responder ao usuário. Use as informações visuais desse vídeo de até 1 minuto para responder sobre a tela. Evite chamar a ferramenta 'ver_tela_atual', a menos que precise ver algo que não esteja no vídeo.]"

                resposta, img_path = self.parent_gui.bot.processar_gemini(
                    user_msg,
                    arquivos=arquivos_anexados if arquivos_anexados else None,
                    origem="GUI"
                )

                if arquivos_anexados:
                    try:
                        for f in BUFFER_VIDEO_DIR.glob("*.mp4"):
                            try:
                                f.unlink()
                                print(f"[Voice Chat] Buffer de vídeo excluído após envio: {f.name}")
                            except Exception as ex:
                                print(f"[Voice Chat] Não foi possível excluir buffer de vídeo {f.name}: {ex}")
                    except Exception as e:
                        print(f"[Voice Chat] Erro ao limpar pasta de buffer de vídeo: {e}")

                clean_text = self.clean_response(resposta)
                print(f"[Voice Chat] Resposta Ayla: '{clean_text}'")

                self.parent_gui.response_queue.put(("voice_chat_text", clean_text))

                wav_out = generate_tts_audio(clean_text, settings)

                if wav_out:
                    out_path = Path(VOICEVOX_OUTPUT_PATH.parent) / f"saida_voice_chat_{int(time.time())}.wav"
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_bytes(wav_out)
                    self.parent_gui.response_queue.put(("voice_chat_audio", str(out_path)))
                else:
                    self.parent_gui.response_queue.put(("voice_chat_audio", None))

            except Exception as exc:
                print(f"[Voice Chat] Erro na thread de processamento: {exc}")
                self.parent_gui.response_queue.put(("voice_chat_text", f"Erro: {exc}"))
                self.parent_gui.response_queue.put(("voice_chat_audio", None))

        threading.Thread(target=worker, daemon=True).start()

    def clean_response(self, text: str) -> str:
        text = re.sub(r'<a?:[a-zA-Z0-9_]+:[0-9]+>', '', text)
        text = re.sub(r'[*_`#~]', '', text)
        text = re.sub(r'https?://\S+', '', text)
        try:
            emoji_pattern = re.compile(
                '['
                '\U00010000-\U0010ffff'
                '\u2600-\u27bf'
                '\u2300-\u23ff'
                '\u2b50'
                '\u2934-\u2935'
                ']+', flags=re.UNICODE
            )
            text = emoji_pattern.sub('', text)
        except Exception:
            pass
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def handle_text_ready(self, text):
        self.state = "idle"
        self.update_mic_button_style()
        self.show_bubble(text)

    def _stop_playback(self):
        try:
            import winsound
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass
        try:
            import pygame
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()
        except Exception:
            pass

    def handle_audio_ready(self, audio_path):
        if audio_path and Path(audio_path).is_file():
            self._stop_playback()

            try:
                for old_file in Path(audio_path).parent.glob("saida_voice_chat_*.wav"):
                    if old_file.is_file() and old_file != Path(audio_path):
                        try:
                            old_file.unlink()
                        except Exception:
                            pass
            except Exception:
                pass

            played_via_soundcard = False
            settings = self.parent_gui._load_settings()
            selected_speaker = settings.get("selected_speaker_name", "")

            if selected_speaker:
                try:
                    duration = self.get_wav_duration(audio_path)
                    self.is_speaking = True
                    if self.live_mode or self.live_call_mode:
                        self.update_sprite_image("falandobot")
                    self.start_pulse_animation(QColor(255, 158, 187, 220))

                    def play_worker():
                        self.play_wav_on_device(audio_path, selected_speaker)
                        self.parent_gui.response_queue.put(("voice_chat_speech_finished", None))

                    threading.Thread(target=play_worker, daemon=True).start()
                    played_via_soundcard = True
                    print(f"[Voice Chat] Áudio reproduzido via soundcard no dispositivo '{selected_speaker}' (Duração: {duration:.2f}s).")
                except Exception as sc_err:
                    print(f"[Voice Chat] Erro ao tentar reproduzir via soundcard: {sc_err}. Tentando fallbacks...")

            if not played_via_soundcard:
                played_via_pygame = False
                duration = 5.0

                try:
                    import pygame
                    if not pygame.mixer.get_init():
                        pygame.mixer.init()

                    sound_obj = pygame.mixer.Sound(str(audio_path))
                    duration = sound_obj.get_length()

                    self.is_speaking = True
                    if self.live_mode or self.live_call_mode:
                        self.update_sprite_image("falandobot")
                    self.start_pulse_animation(QColor(255, 158, 187, 220))

                    pygame.mixer.music.load(str(audio_path))
                    pygame.mixer.music.play()
                    played_via_pygame = True

                    def pygame_waiter():
                        import time
                        time.sleep(duration)
                        self.parent_gui.response_queue.put(("voice_chat_speech_finished", None))

                    threading.Thread(target=pygame_waiter, daemon=True).start()
                    print(f"[Voice Chat] Áudio reproduzido com sucesso via Pygame Mixer (Duração: {duration:.2f}s).")
                except Exception as py_err:
                    print(f"[Voice Chat] Pygame Mixer falhou ({py_err}). Usando winsound como fallback...")

                if not played_via_pygame:
                    try:
                        duration = self.get_wav_duration(audio_path)
                        self.is_speaking = True

                        if self.live_mode or self.live_call_mode:
                            self.update_sprite_image("falandobot")

                        self.start_pulse_animation(QColor(255, 158, 187, 220))

                        import winsound
                        winsound.PlaySound(audio_path, winsound.SND_FILENAME | winsound.SND_ASYNC)

                        def winsound_waiter():
                            import time
                            time.sleep(duration)
                            self.parent_gui.response_queue.put(("voice_chat_speech_finished", None))

                        threading.Thread(target=winsound_waiter, daemon=True).start()
                        print(f"[Voice Chat] Áudio reproduzido via winsound fallback.")
                    except Exception as exc:
                        print(f"[Voice Chat] Erro no fallback do winsound: {exc}")
                        self.is_speaking = False
                        self.stop_pulse_animation()
                        if self.live_mode or self.live_call_mode:
                            self.update_sprite_image("esperando")
                            QTimer.singleShot(1000, self.start_recording_live_mode_helper)
                        return

        else:
            self.is_speaking = False
            self.stop_pulse_animation()
            if self.live_mode or self.live_call_mode:
                self.update_sprite_image("esperando")
                QTimer.singleShot(3500, self.start_recording_live_mode_helper)

    def play_wav_on_device(self, audio_path, speaker_name):
        try:
            import soundcard as sc
            import wave
            import numpy as np

            speaker = None
            if speaker_name:
                for s in sc.all_speakers():
                    if s.name == speaker_name:
                        speaker = s
                        break
                if not speaker:
                    for s in sc.all_speakers():
                        if speaker_name.lower() in s.name.lower() or s.name.lower() in speaker_name.lower():
                            speaker = s
                            break
            if not speaker:
                speaker = sc.default_speaker()

            print(f"[Voice Chat] Reproduzindo áudio no alto-falante: {speaker.name}")

            with wave.open(str(audio_path), 'rb') as wf:
                samplerate = wf.getframerate()
                channels = wf.getnchannels()
                data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
                data = data.astype(np.float32) / 32768.0

                if channels > 1:
                    data = data.reshape(-1, channels)
                else:
                    data = data.reshape(-1, 1)

                with speaker.player(samplerate=samplerate, channels=channels) as player:
                    player.play(data)
            return True
        except Exception as e:
            print(f"[Voice Chat] Erro ao reproduzir via soundcard: {e}")
            return False

    def get_wav_duration(self, file_path) -> float:
        try:
            import wave
            with wave.open(file_path, 'rb') as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                return frames / float(rate)
        except Exception:
            return 5.0

    def on_speech_finished(self):
        self.is_speaking = False
        self.last_user_speech_time = time.time()
        self.stop_pulse_animation()
        QTimer.singleShot(4000, self.hide_bubble_if_idle)
        if self.live_mode or getattr(self, "live_call_mode", False):
            self.update_sprite_image("esperando")
            QTimer.singleShot(800, self.start_recording_live_mode_helper)

    def hide_bubble_if_idle(self):
        if not self.is_speaking and self.state == "idle":
            self.bubble_frame.hide()
            self.adjustSize()

    def hide_window(self):
        if self.live_mode:
            self.toggle_live_mode()
        if getattr(self, "live_call_mode", False):
            self.toggle_live_call()

        if self.state == "listening":
            self.toggle_recording_or_state()
        if self.is_speaking:
            self._stop_playback()
            self.is_speaking = False
            self.speech_timer.stop()
            self.stop_pulse_animation()
        self.hide()

    def start_recording_live_mode_helper(self):
        if (self.live_mode or getattr(self, "live_call_mode", False)) and self.state == "idle" and not self.is_speaking:
            self.start_recording()

    def check_live_silence(self):
        if self.live_mode or getattr(self, "live_call_mode", False):
            current_time = time.time()

            if self.state == "listening" and self.recorder:
                if self.recorder.has_spoken and (current_time - self.recorder.last_speech_time >= 3.0):
                    print("[Live Mode] 3 segundos de silêncio detectados. Parando gravação...")
                    self.stop_recording_and_process()
                    return

            # Checagem de inatividade prolongada do usuário
            if self.state == "listening" and not self.is_speaking and not getattr(self, "is_processing_inactivity", False):
                if (current_time - self.last_user_speech_time >= self.inactivity_timeout) and \
                   (current_time - self.last_inactivity_prompt_time >= self.inactivity_cooldown):
                    print(f"[Live Mode] Inatividade do usuário detectada ({int(current_time - self.last_user_speech_time)}s). Disparando comentário autônomo da Ayla...")
                    self.trigger_inactivity_prompt()

    def trigger_inactivity_prompt(self):
        if self.is_processing_inactivity or self.state == "processing" or self.is_speaking:
            return

        self.is_processing_inactivity = True
        self.last_inactivity_prompt_time = time.time()

        if self.state == "listening":
            self.record_safety_timer.stop()
            if self.recorder:
                self.recorder.stop()

        self.state = "processing"
        if self.live_mode or getattr(self, "live_call_mode", False):
            self.update_sprite_image("processando")
        self.update_mic_button_style()
        self.show_bubble("Pensando...")
        self.stop_pulse_animation()

        if self.live_mode and self.screen_buffer and getattr(self, "screen_recording_enabled", True):
            self.screen_buffer.pause_capturing()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.live_video_path = str(BUFFER_VIDEO_DIR / f"clip_inactivity_{timestamp}.mp4")
            self.screen_buffer.save_video(self.live_video_path)

        def worker():
            try:
                settings = self.parent_gui._load_settings()
                arquivos_anexados = []
                if hasattr(self, "live_mode") and self.live_mode and getattr(self, "screen_recording_enabled", True):
                    video_path = Path(self.live_video_path)
                    if video_path.is_file():
                        try:
                            video_bytes = video_path.read_bytes()
                            arquivos_anexados.append((video_bytes, "video/mp4"))
                            print(f"[Live Mode Inatividade] Vídeo anexado para aviso: {video_path.name}")
                        except Exception as e:
                            print(f"[Live Mode Inatividade] Erro ao ler vídeo: {e}")

                prompt = (
                    "[Aviso do Sistema - Inatividade do Usuário]: O usuário está em silêncio no Modo Live/Chamada há bastante tempo. "
                    "Ele não disse nada recentemente. Comente de forma natural, descontraída, curiosa ou ligeiramente provocativa "
                    "sobre o silêncio dele ou sobre o que você está vendo no clipe de vídeo da tela gravada (caso haja vídeo anexado). "
                    "Responda diretamente ao usuário em no máximo 1 ou 2 frases curtas (limite de 150 caracteres). "
                    "Não use emojis nem links."
                )

                resposta, img_path = self.parent_gui.bot.processar_gemini(
                    prompt,
                    arquivos=arquivos_anexados if arquivos_anexados else None,
                    origem="GUI"
                )

                if arquivos_anexados:
                    try:
                        for f in BUFFER_VIDEO_DIR.glob("*.mp4"):
                            try:
                                f.unlink()
                            except Exception:
                                pass
                    except Exception:
                        pass

                clean_text = self.clean_response(resposta)
                print(f"[Live Mode Inatividade] Resposta Ayla: '{clean_text}'")

                self.parent_gui.response_queue.put(("voice_chat_text", clean_text))

                wav_out = generate_tts_audio(clean_text, settings)

                if wav_out:
                    out_path = Path(VOICEVOX_OUTPUT_PATH.parent) / f"saida_voice_chat_{int(time.time())}.wav"
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_bytes(wav_out)
                    self.parent_gui.response_queue.put(("voice_chat_audio", str(out_path)))
                else:
                    self.parent_gui.response_queue.put(("voice_chat_audio", None))

            except Exception as exc:
                print(f"[Live Mode Inatividade] Erro no processamento de inatividade: {exc}")
                self.parent_gui.response_queue.put(("voice_chat_text_silent_restart", ""))
            finally:
                self.is_processing_inactivity = False

        threading.Thread(target=worker, daemon=True).start()

    def on_mic_btn_clicked(self):
        if getattr(self, "live_call_mode", False):
            self.toggle_live_call()
        elif self.live_mode:
            self.toggle_live_mode()
        else:
            self.toggle_live_mode()

    def toggle_live_mode(self):
        if self.is_speaking:
            self._stop_playback()
            self.is_speaking = False
            self.speech_timer.stop()
            self.stop_pulse_animation()

        self.last_user_speech_time = time.time()
        self.last_inactivity_prompt_time = 0.0
        self.is_processing_inactivity = False

        if not self.live_mode:
            self.live_mode = True

            if getattr(self, "live_call_mode", False):
                self.live_call_mode = False
                settings = self.parent_gui._load_settings()
                settings["live_call_mode"] = False
                self.parent_gui._safe_write_json(SETTINGS_PATH, settings)

            self.show_bubble("Modo Live Ativado! 🎙📺\n(Os vídeos recebidos são a sua tela)")
            self.update_sprite_image("esperando")

            self.screen_buffer = ScreenCaptureBuffer(fps=2, duration_sec=60)
            self.screen_buffer.running = True
            if getattr(self, "screen_recording_enabled", True):
                self.screen_buffer.start_capturing()
            self.screen_buffer.start()

            if self.state == "idle":
                self.start_recording()
        else:
            self.live_mode = False
            self.show_bubble("Modo Live Desativado")
            self.update_sprite_image(None)

            if self.screen_buffer:
                self.screen_buffer.running = False
                self.screen_buffer = None

            if self.state == "listening":
                self.state = "idle"
                self.stop_pulse_animation()
                self.record_safety_timer.stop()
                if self.recorder:
                    self.recorder.stop()

        self.update_mic_button_style()

    def toggle_live_call(self):
        if self.is_speaking:
            self._stop_playback()
            self.is_speaking = False
            self.speech_timer.stop()
            self.stop_pulse_animation()

        settings = self.parent_gui._load_settings()
        if not getattr(self, "live_call_mode", False):
            self.live_call_mode = True
            settings["live_call_mode"] = True
            self.parent_gui._safe_write_json(SETTINGS_PATH, settings)

            if self.live_mode:
                self.live_mode = False
                self.update_sprite_image(None)
                if self.screen_buffer:
                    self.screen_buffer.running = False
                    self.screen_buffer = None

            self.show_bubble("Modo Chamada de Voz Ativado! 🎙📞\nAyla usará os canais virtuais.")
            self.update_sprite_image("esperando")

            if self.state == "idle":
                self.start_recording()
        else:
            self.live_call_mode = False
            settings["live_call_mode"] = False
            self.parent_gui._safe_write_json(SETTINGS_PATH, settings)
            self.show_bubble("Modo Chamada de Voz Desativado")
            self.update_sprite_image(None)

            if self.state == "listening":
                self.state = "idle"
                self.stop_pulse_animation()
                self.record_safety_timer.stop()
                if self.recorder:
                    self.recorder.stop()

        self.update_mic_button_style()

    def handle_silent_restart(self):
        self.state = "idle"
        self.update_mic_button_style()
        self.start_recording()

    def update_sprite_image(self, state_name):
        if not (self.live_mode or getattr(self, "live_call_mode", False)) or not state_name:
            if getattr(self.parent_gui, "sprite_window", None):
                self.parent_gui.sprite_window.hide()
            return

        if not getattr(self.parent_gui, "sprite_window", None):
            self.parent_gui.sprite_window = AylaSpriteWindow(self.parent_gui)

        self.parent_gui.sprite_window.update_sprite(state_name)
        if not self.parent_gui.sprite_window.isVisible():
            self.parent_gui.sprite_window.show()

    def toggle_noisegate(self):
        if getattr(self, "dynamic_noise_gate", True):
            self.dynamic_noise_gate = False
            self.show_bubble("Anti-Ruído Dinâmico: DESATIVADO")
        else:
            self.dynamic_noise_gate = True
            self.show_bubble("Anti-Ruído Dinâmico: ATIVADO")
        self.update_noisegate_button_style()
        if self.recorder:
            self.recorder.dynamic_noise_gate = self.dynamic_noise_gate

    def update_noisegate_button_style(self):
        if getattr(self, "dynamic_noise_gate", True):
            self.noisegate_btn.setStyleSheet("""
                QPushButton#iconBtn {
                    background: transparent;
                    border: none;
                    color: #7ee8fa;
                    font-size: 18px;
                }
                QPushButton#iconBtn:hover {
                    color: #ff5c8a;
                }
            """)
            self.noisegate_btn.setToolTip("Anti-Ruído Dinâmico: ATIVADO")
        else:
            self.noisegate_btn.setStyleSheet("""
                QPushButton#iconBtn {
                    background: transparent;
                    border: none;
                    color: #4a4d68;
                    font-size: 18px;
                }
                QPushButton#iconBtn:hover {
                    color: #7ee8fa;
                }
            """)
            self.noisegate_btn.setToolTip("Anti-Ruído Dinâmico: DESATIVADO")

    def go_to_settings(self):
        if hasattr(self.parent_gui, "_switch_page"):
            self.parent_gui._switch_page("voice_chat")
            self.parent_gui.show()
            self.parent_gui.raise_()
            self.parent_gui.activateWindow()

    def show_help(self):
        self.show_bubble(
            "Ajuda:\n"
            "- Pressione o atalho global no PC ou clique no microfone para gravar.\n"
            "- Fale e clique/aperte novamente para enviar.\n"
            "- A Ayla responderá pela voz do Voicevox e texto no balão.\n"
            "- Os vídeos que ela receber são da sua tela."
        )


class StandaloneLiveController:
    """Controlador leve para executar o Modo Live sem carregar a GUI principal de 14 abas."""
    def __init__(self, bot_instance=None):
        self.bot = bot_instance
        self.response_queue = queue.Queue()
        self.sprite_window = None
        self.floating_mic = None

        if self.bot is None:
            self._try_load_bot()

        self.poll_timer = QTimer()
        self.poll_timer.timeout.connect(self._poll_queues)
        self.poll_timer.start(100)

    def _try_load_bot(self):
        try:
            print("[Standalone Live] Tentando carregar bot Ayla de Ayla.py...")
            sys.path.append(str(BASE_DIR))
            import Ayla
            if hasattr(Ayla, "bot"):
                self.bot = Ayla.bot
            elif hasattr(Ayla, "AylaBot"):
                self.bot = Ayla.AylaBot()
        except Exception as e:
            print(f"[Standalone Live] Não foi possível carregar Ayla.py automaticamente: {e}")

    def _load_settings(self):
        if SETTINGS_PATH.exists():
            try:
                return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "screenshot_before_response": False,
            "voice_chat_enabled": True,
            "voice_chat_hotkey": "end",
            "voice_chat_style_id": 3,
            "selected_mic_name": "",
            "selected_speaker_name": "",
            "mix_system_audio": True,
            "live_call_mode": False,
            "tts_engine": "voicevox",
            "fish_audio_api_key": "",
            "fish_audio_voice_id": "",
            "public_mode": False
        }

    def _safe_write_json(self, path: Path, data: dict):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            print(f"[Standalone Live] Erro ao salvar JSON: {e}")

    def _poll_queues(self):
        try:
            while True:
                item = self.response_queue.get_nowait()
                kind = item[0]
                if kind == "voice_chat_text":
                    if self.floating_mic:
                        self.floating_mic.handle_text_ready(item[1])
                elif kind == "voice_chat_text_silent_restart":
                    if self.floating_mic:
                        self.floating_mic.handle_silent_restart()
                elif kind == "voice_chat_audio":
                    if self.floating_mic:
                        self.floating_mic.handle_audio_ready(item[1])
                elif kind == "voice_chat_user_speaking":
                    if self.floating_mic:
                        self.floating_mic.update_sprite_image("falandousuario")
                elif kind == "voice_chat_speech_finished":
                    if self.floating_mic:
                        self.floating_mic.on_speech_finished()
        except queue.Empty:
            pass


if __name__ == "__main__":
    app = QApplication(sys.argv)
    controller = StandaloneLiveController()
    mic = FloatingMicrophoneWindow(controller)
    controller.floating_mic = mic
    mic.show()
    print("[Standalone Live] Modo Live independente da Ayla iniciado com sucesso!")
    sys.exit(app.exec())
