#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Interface grafica da Ayla em PySide6/Qt."""

from __future__ import annotations

import asyncio
import ctypes
import io
import json
import os
import queue
import shutil
import sys
import threading
import re
import time
import winsound
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path

try:
    from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, QSize, QObject, Signal
    from PySide6.QtGui import QColor, QIcon, QImage, QPixmap, QTextCursor
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QGraphicsDropShadowEffect,
        QPushButton as QtPushButton,
        QPlainTextEdit,
        QScrollArea,
        QSizePolicy,
        QStackedWidget,
        QTableWidget,
        QTableWidgetItem,
        QHeaderView,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PySide6 precisa estar instalado para abrir a GUI Qt da Ayla.") from exc

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None

try:
    import keyboard
except ImportError:
    keyboard = None

try:
    import sounddevice as sd
    import numpy as np
except ImportError:
    sd = None
    np = None


BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
MEMORIA_PATH = BASE_DIR / "Ayla_Memoria.json"
MODELS_PATH = BASE_DIR / "ayla_models.json"
PERMISSIONS_PATH = BASE_DIR / "ayla_permissions.json"
BLOCKED_PATH = BASE_DIR / "ayla_blocked_users.json"
BLOCK_PATH = BASE_DIR / "ayla_block.json"
SETTINGS_PATH = BASE_DIR / "ayla_settings.json"
HISTORY_PATH = BASE_DIR / "ayla_interaction_history.jsonl"
VOICEVOX_OUTPUT_PATH = BASE_DIR / "voicevox" / "saida_gui.wav"
ICON_PATH = BASE_DIR / "ico.png"
ICON_ICO_PATH = BASE_DIR / "ico.ico"
PHOTO_DIRS = [BASE_DIR / "Aylafotitos", Path(r"C:\Users\Aleenia\Documents\IA\Aylafotitos")]
VIDEO_DIR = BASE_DIR / "VideosBaixados"
MODOS_DIR = BASE_DIR / "MODOS"
BUFFER_VIDEO_DIR = BASE_DIR / "Buffer de video"
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
VIDEO_EXTS = (".mp4", ".mkv", ".avi", ".mov", ".webm")
SENSITIVE_WORDS = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "SENHA")


def parse_hotkey_to_win32(hotkey_str):
    if not hotkey_str:
        return None, None
    tokens = [t.strip().lower() for t in hotkey_str.split('+')]
    mods = 0
    key_token = None

    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    MOD_SHIFT = 0x0004
    MOD_WIN = 0x0008
    MOD_NOREPEAT = 0x4000

    for token in tokens:
        if token in ['ctrl', 'control']:
            mods |= MOD_CONTROL
        elif token == 'alt':
            mods |= MOD_ALT
        elif token == 'shift':
            mods |= MOD_SHIFT
        elif token in ['win', 'windows']:
            mods |= MOD_WIN
        else:
            key_token = token

    if not key_token:
        return None, None

    mods |= MOD_NOREPEAT

    VK_MAP = {
        'home': 0x24,
        'end': 0x23,
        'insert': 0x2D,
        'delete': 0x2E,
        'prior': 0x21,
        'pageup': 0x21,
        'page_up': 0x21,
        'next': 0x22,
        'pagedown': 0x22,
        'page_down': 0x22,
        'space': 0x20,
        'tab': 0x09,
        'escape': 0x1B,
        'esc': 0x1B,
        'backspace': 0x08,
        'return': 0x0D,
        'enter': 0x0D,
    }

    if key_token.startswith('f') and key_token[1:].isdigit():
        f_num = int(key_token[1:])
        if 1 <= f_num <= 24:
            return mods, 0x70 + (f_num - 1)

    if key_token in VK_MAP:
        return mods, VK_MAP[key_token]

    if len(key_token) == 1:
        char = key_token.upper()
        if 'A' <= char <= 'Z' or '0' <= char <= '9':
            return mods, ord(char)

    return None, None


PAGES = [
    ("status", "Status"),
    ("voice_chat", "Conversa por Voz"),
    ("media_manager", "Emojis & GIFs"),
    ("settings", "Configuracoes"),
    ("public_mode", "Modo Publico"),
    ("bloqueios", "Bloqueios"),
    ("tts", "TTS"),
    ("config", "ENV"),
    ("models", "Modelos"),
    ("voicevox", "VoiceVox"),
    ("fish_audio", "Fish Audio"),
    ("gallery", "Galeria"),
    ("videos", "Videos"),
    ("memory", "Memoria"),
    ("console", "Console"),
]


class HotkeySignalEmitter(QObject):
    triggered = Signal()
    raw_down = Signal()
    raw_up = Signal()


from ayla_live import (
    ScreenCaptureBuffer,
    AudioRecorder,
    generate_tts_audio,
    AylaSpriteWindow,
    FloatingMicrophoneWindow,
    ConsoleRedirector,
    ClickableImage,
    SmoothButton,
)

QPushButton = SmoothButton



class AylaGUI(QMainWindow):
    def __init__(self, bot_instance=None):
        if bot_instance is None:
            raise ValueError("A Ayla precisa estar aberta e iniciada para a GUI funcionar.")
        super().__init__()
        self.bot = bot_instance
        self.response_queue: queue.Queue[tuple] = queue.Queue()
        self.console_queue: queue.Queue[str] = queue.Queue()
        self.stdout_redirector = ConsoleRedirector(self.console_queue, sys.stdout)
        self.stderr_redirector = ConsoleRedirector(self.console_queue, sys.stderr)
        sys.stdout = self.stdout_redirector
        sys.stderr = self.stderr_redirector

        self.env_rows: list[dict] = []
        self.model_status: dict[str, dict] = {}
        self.loaded_models: dict = {}
        self.gallery_items: list[Path] = []
        self.video_items: list[Path] = []
        self.selected_image: Path | None = None
        self.selected_video: Path | None = None
        self.permission_checks: dict[str, QCheckBox] = {}
        self.status_labels: dict[str, QLabel] = {}
        self.profile_cache: dict[int, dict] = {}
        self.settings_checks: dict[str, QCheckBox] = {}
        self.copilot_checks: dict[str, QCheckBox] = {}
        
        self.floating_mic = None
        self.sprite_window = None
        
        # Variáveis e controle de atalho inteligente (Press/Hold de 2 segundos)
        self.hotkey_is_pressed = False
        self.hotkey_hold_triggered = False
        self.hotkey_trigger_key = "end"
        self.hotkey_modifiers = []
        self.hotkey_hook_callback = None
        
        self.hotkey_hold_timer = QTimer(self)
        self.hotkey_hold_timer.setSingleShot(True)
        self.hotkey_hold_timer.timeout.connect(self._on_hotkey_hold_timeout)

        self.hotkey_emitter = HotkeySignalEmitter()
        self.hotkey_emitter.triggered.connect(self._on_hotkey_triggered)
        self.hotkey_emitter_live = HotkeySignalEmitter()
        self.hotkey_emitter_live.triggered.connect(self._on_hotkey_live_triggered)
        self.hotkey_emitter_live.raw_down.connect(self._on_hotkey_raw_down)
        self.hotkey_emitter_live.raw_up.connect(self._on_hotkey_raw_up)

        self.setWindowTitle("Ayla - Painel de Controle")
        self.resize(950, 630)
        self.setMinimumSize(800, 520)
        self._set_windows_app_id()
        self._set_icon()
        self._apply_style()

        self._build_shell()
        self._load_models_config()
        self._build_pages()
        self._switch_page("status")
        self._update_hotkey_listener()

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll_queues)
        self.poll_timer.start(150)

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._update_status)
        self.status_timer.start(4000)
        self._update_status()

    # ------------------------------------------------------------------
    # Shell
    # ------------------------------------------------------------------

    def _set_windows_app_id(self):
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ayla.qt.gui.v1")
        except Exception:
            pass

    def _set_icon(self):
        icon_file = ICON_ICO_PATH if ICON_ICO_PATH.exists() else ICON_PATH
        if icon_file.exists():
            self.setWindowIcon(QIcon(str(icon_file)))

    def _apply_style(self):
        self.setStyleSheet(
            """
            * { font-family: 'Segoe UI', Arial; }
            QMainWindow, QWidget#root { background: #12131c; color: #f1f5f9; }
            QWidget#sidebar { background: #161726; border-right: 1px solid #26283f; }
            QLabel#brand { color: #7ee8fa; font-size: 25px; font-weight: 800; }
            QLabel#subtle { color: #626680; }
            QLabel#pageTitle { color: #f1f5f9; font-size: 18px; font-weight: 800; }
            QLabel#sectionTitle { color: #7ee8fa; font-size: 15px; font-weight: 800; }
            QLabel#muted { color: #a5a9c0; }
            QLabel#dim { color: #626680; }
            QPushButton { background: #252744; color: #f1f5f9; border: 1px solid #2d304e; border-radius: 8px; padding: 7px 12px; }
            QPushButton:hover { background: #303456; border-color: #7ee8fa; }
            QPushButton#primary { background: #7ee8fa; color: #071018; border-color: #7ee8fa; font-weight: 800; }
            QPushButton#pink { background: #ff9ebb; color: #071018; border-color: #ff9ebb; font-weight: 800; }
            QPushButton#danger { background: #ff5c8a; color: white; border-color: #ff5c8a; font-weight: 700; }
            QPushButton#ghost { background: transparent; border-color: transparent; color: #a5a9c0; text-align: left; }
            QPushButton#ghost:hover { background: #252744; color: #7ee8fa; border-color: #2d304e; }
            QPushButton#ghost[active='true'] { background: #252744; color: #7ee8fa; border-left: 4px solid #ff9ebb; font-weight: 800; }
            QPushButton#mediaButton { background: #12131c; border: 1px solid #2d304e; padding: 6px; }
            QLineEdit, QPlainTextEdit { background: #12131c; color: #f1f5f9; border: 1px solid #2d304e; border-radius: 7px; padding: 7px; selection-background-color: #244a5e; }
            QLineEdit:focus, QPlainTextEdit:focus { border-color: #7ee8fa; }
            QFrame#card { background: #1a1b2f; border: 1px solid #26283f; border-radius: 10px; }
            QFrame#header { background: #1a1b2f; border-bottom: 1px solid #26283f; }
            QScrollArea { border: none; background: #12131c; }
            QScrollArea > QWidget > QWidget { background: #12131c; }
            QCheckBox { color: #f1f5f9; spacing: 8px; }
            QCheckBox::indicator { width: 18px; height: 18px; border-radius: 5px; border: 1px solid #2d304e; background: #12131c; }
            QCheckBox::indicator:checked { background: #7ee8fa; border-color: #7ee8fa; }
            QStatusBar { background: #1a1b2f; color: #a5a9c0; border-top: 1px solid #26283f; }
            """
        )

    def _build_shell(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(224)
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(16, 18, 12, 14)
        sb.setSpacing(8)
        brand = QLabel("Ayla")
        brand.setObjectName("brand")
        sb.addWidget(brand)
        sub = QLabel("Painel Qt / PySide6")
        sub.setObjectName("subtle")
        sb.addWidget(sub)
        sb.addSpacing(18)

        self.nav_buttons: dict[str, QPushButton] = {}
        nav_scroll = QScrollArea()
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        nav_scroll.setFrameShape(QFrame.Shape.NoFrame)
        nav_host = QWidget()
        nav_host.setStyleSheet("background: transparent;")
        nav_layout = QVBoxLayout(nav_host)
        nav_layout.setContentsMargins(0, 0, 4, 0)
        nav_layout.setSpacing(8)
        for key, label in PAGES:
            btn = QPushButton(label)
            btn.setObjectName("ghost")
            btn.setCheckable(False)
            btn.clicked.connect(lambda checked=False, page=key: self._switch_page(page))
            btn.setMinimumHeight(38)
            self.nav_buttons[key] = btn
            nav_layout.addWidget(btn)
        nav_layout.addStretch(1)
        nav_scroll.setWidget(nav_host)
        sb.addWidget(nav_scroll, 1)
        foot = QLabel("Ayla GUI v2 - Qt")
        foot.setObjectName("dim")
        sb.addWidget(foot)
        outer.addWidget(sidebar)

        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)
        self.page_index: dict[str, int] = {}
        self.statusBar().showMessage("Qt pronto")

    def _build_pages(self):
        self._add_page("voice_chat", self._build_voice_chat_page())
        self._add_page("media_manager", self._build_media_manager_page())
        self._add_page("settings", self._build_settings_page())
        self._add_page("public_mode", self._build_public_mode_page())
        self._add_page("bloqueios", self._build_bloqueios_page())
        self._add_page("tts", self._build_tts_page())
        self._add_page("config", self._build_config_page())
        self._add_page("models", self._build_models_page())
        self._add_page("voicevox", self._build_voicevox_page())
        self._add_page("fish_audio", self._build_fish_audio_page())
        self._add_page("gallery", self._build_gallery_page())
        self._add_page("videos", self._build_videos_page())
        self._add_page("memory", self._build_memory_page())
        self._add_page("status", self._build_status_page())
        self._add_page("console", self._build_console_page())

    def _add_page(self, key: str, widget: QWidget):
        self.page_index[key] = self.stack.addWidget(widget)

    def _switch_page(self, key: str):
        if key not in self.page_index:
            return
        self.stack.setCurrentIndex(self.page_index[key])
        for page_key, btn in self.nav_buttons.items():
            btn.setProperty("active", "true" if page_key == key else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        if key == "voice_chat":
            self._refresh_voice_chat_ui()
        elif key == "media_manager":
            self._refresh_media_manager()
        elif key == "settings":
            self._refresh_settings_ui()
        elif key == "public_mode":
            self._refresh_public_mode_ui()
        elif key == "bloqueios":
            self._refresh_bloqueios()
        elif key == "tts":
            self._refresh_settings_ui()
        elif key == "config":
            self._reload_env()
        elif key == "voicevox":
            pass
        elif key == "fish_audio":
            self._refresh_fish_audio_ui()
        elif key == "gallery":
            self._refresh_gallery()
        elif key == "videos":
            self._refresh_videos()
        elif key == "memory":
            self._refresh_memory()
        elif key == "status":
            self._update_status()

    def _page(self, title: str, actions: list[tuple[str, callable, str]] | None = None):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QFrame()
        header.setObjectName("header")
        h = QHBoxLayout(header)
        h.setContentsMargins(20, 12, 20, 12)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("pageTitle")
        h.addWidget(title_lbl)
        h.addStretch(1)
        for label, callback, style_name in actions or []:
            btn = QPushButton(label)
            if style_name:
                btn.setObjectName(style_name)
            btn.clicked.connect(callback)
            h.addWidget(btn)
        layout.addWidget(header)
        return page, layout

    def _scroll_page(self, title: str, actions=None):
        page, layout = self._page(title, actions)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 16, 16, 16)
        content_layout.setSpacing(10)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        return page, content_layout

    def _card(self):
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        return card, layout

    def _toast(self, message: str):
        self.statusBar().showMessage(str(message), 4200)

    # ------------------------------------------------------------------
    # JSON e arquivos
    # ------------------------------------------------------------------

    def _safe_load_json(self, path: Path, default):
        for candidate in (path, path.with_name(path.name + ".bak")):
            try:
                if candidate.exists():
                    data = json.loads(candidate.read_text(encoding="utf-8"))
                    if candidate != path:
                        print(f"Arquivo {path.name} recuperado do backup.")
                    return data
            except Exception as exc:
                print(f"Erro ao ler {candidate.name}: {exc}")
        return default

    def _safe_write_json(self, path: Path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        for i in range(5):
            try:
                with open(temporary, "w", encoding="utf-8", newline="") as file:
                    file.write(json.dumps(data, indent=4, ensure_ascii=False))
                    file.flush()
                    try:
                        os.fsync(file.fileno())
                    except Exception:
                        pass
                if path.exists():
                    try:
                        json.loads(path.read_text(encoding="utf-8"))
                        shutil.copy2(path, path.with_name(path.name + ".bak"))
                    except Exception:
                        pass
                os.replace(temporary, path)
                break
            except OSError as exc:
                if i == 4:
                    print(f"⚠️ Erro ao salvar {path.name}: {exc}")
                    raise exc
                time.sleep(0.05)


    # ------------------------------------------------------------------
    # Configuracoes JSON da Ayla
    # ------------------------------------------------------------------

    def _default_settings(self):
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

    def _load_settings(self):
        defaults = self._default_settings()
        data = self._safe_load_json(SETTINGS_PATH, defaults)
        if not isinstance(data, dict):
            data = defaults
        # Preserva todas as chaves originais do JSON para evitar deleção acidental de novas variáveis
        merged = data.copy()
        for key, val in defaults.items():
            if key not in merged:
                merged[key] = val
            elif isinstance(val, bool):
                merged[key] = bool(data[key])
            elif isinstance(val, int):
                try:
                    merged[key] = int(data[key])
                except ValueError:
                    merged[key] = val
        return merged

    def _build_voice_chat_page(self):
        page, layout = self._scroll_page(
            "Conversa por Voz",
            [
                ("Salvar", self._save_voice_chat_settings, "primary"),
                ("Iniciar Modo Live", self._open_floating_mic, "pink"),
                ("Iniciar Chamada (Voz)", self._open_floating_call, "")
            ]
        )
        
        # Info Card
        info, info_lay = self._card()
        title = QLabel("Instruções")
        title.setObjectName("sectionTitle")
        info_lay.addWidget(title)
        text = QLabel(
            "Pressione o atalho global no seu PC para exibir o microfone flutuante e iniciar a conversa em tempo real (Modo Live).\n"
            "Fale naturally. A Ayla detectará quando você terminar de falar para responder via voz e texto no balão.\n"
            "Pressione o atalho novamente para forçar a resposta imediata ou clique no microfone para ativar/desativar.\n\n"
            "Aviso: No Modo Live, os vídeos que a Ayla recebe são gravações em tempo real da sua tela."
        )
        text.setObjectName("muted")
        text.setWordWrap(True)
        info_lay.addWidget(text)
        layout.addWidget(info)
        
        # Card 1: Atalho Global & Modo Live
        settings, set_lay = self._card()
        stitle = QLabel("Modo Live & Atalho Global")
        stitle.setObjectName("sectionTitle")
        set_lay.addWidget(stitle)
        
        self.voice_chat_enabled_check = QCheckBox("Ativar atalho global do Modo Live")
        set_lay.addWidget(self.voice_chat_enabled_check)
        
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Atalho de Teclado:"))
        self.voice_chat_hotkey_input = QLineEdit()
        self.voice_chat_hotkey_input.setPlaceholderText("ex: end, f4, ctrl+alt+v, scroll lock")
        row1.addWidget(self.voice_chat_hotkey_input)
        set_lay.addLayout(row1)
        
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Voicevox Style ID:"))
        self.voice_chat_style_input = QLineEdit()
        self.voice_chat_style_input.setMaximumWidth(80)
        self.voice_chat_style_input.setPlaceholderText("ex: 3")
        row2.addWidget(self.voice_chat_style_input)
        row2.addStretch(1)
        set_lay.addLayout(row2)
        
        layout.addWidget(settings)
        
        # Card 2: Dispositivos de Áudio (Microfone, Saída de Voz e Ouvir Áudio do PC)
        audio_card, audio_lay = self._card()
        audio_title = QLabel("Dispositivos de Áudio")
        audio_title.setObjectName("sectionTitle")
        audio_lay.addWidget(audio_title)
        
        audio_lay.addWidget(QLabel("Selecionar Microfone (Dispositivo de Entrada que a Ayla escuta):"))
        self.mic_combo = QComboBox()
        self.mic_combo.setObjectName("settingsComboBox")
        self.mic_combo.setStyleSheet("""
            QComboBox {
                background-color: #1b1c30;
                border: 1px solid #32355a;
                border-radius: 6px;
                padding: 6px 10px;
                color: #f1f5f9;
                font-size: 13px;
            }
            QComboBox::drop-down {
                border: none;
            }
        """)
        audio_lay.addWidget(self.mic_combo)
        
        audio_lay.addWidget(QLabel("Selecionar Saída de Voz (Alto-falante/Cabo onde a Ayla fala):"))
        self.speaker_combo = QComboBox()
        self.speaker_combo.setObjectName("settingsComboBox")
        self.speaker_combo.setStyleSheet(self.mic_combo.styleSheet())
        audio_lay.addWidget(self.speaker_combo)
        
        self.mix_audio_check = QCheckBox("Ouvir áudio do PC (som do sistema) como entrada de voz")
        audio_lay.addWidget(self.mix_audio_check)
        
        try:
            import soundcard as sc
            mics = sc.all_microphones()
            self.mic_combo.addItem("Padrão do Sistema (Windows)", "")
            for mic in mics:
                self.mic_combo.addItem(mic.name, mic.name)
                
            speakers = sc.all_speakers()
            self.speaker_combo.addItem("Padrão do Sistema (Windows)", "")
            for speaker in speakers:
                self.speaker_combo.addItem(speaker.name, speaker.name)
        except Exception as e:
            self.mic_combo.addItem("Erro ao listar microfones", "")
            self.speaker_combo.addItem("Erro ao listar alto-falantes", "")
            print(f"[Voice Chat] Erro ao listar dispositivos de áudio: {e}")
            
        layout.addWidget(audio_card)

        # Card 3: Fala por Texto (TTS - Síntese de Voz)
        tts_card, tts_lay = self._card()
        tts_title = QLabel("Fala por Texto (TTS - Síntese de Voz)")
        tts_title.setObjectName("sectionTitle")
        tts_lay.addWidget(tts_title)
        
        tts_lay.addWidget(QLabel("Selecionar Motor de Fala por Texto (TTS):"))
        self.tts_combo = QComboBox()
        self.tts_combo.setObjectName("settingsComboBox")
        self.tts_combo.setStyleSheet(self.mic_combo.styleSheet())
        self.tts_combo.addItem("Fish Audio API (Nuvem - Modelo s2.1-pro-free)", "fish_audio")
        self.tts_combo.addItem("VoiceVox (Local)", "voicevox")
        self.tts_combo.addItem("Voz Nativa do Windows (SAPI5)", "sapi5")
        tts_lay.addWidget(self.tts_combo)
        
        tts_note = QLabel("Nota: O motor selecionado é a sua preferência principal. Se ele estiver indisponível ou falhar, o sistema fará fallback automático para os outros motores.")
        tts_note.setObjectName("muted")
        tts_note.setWordWrap(True)
        tts_lay.addWidget(tts_note)
        
        layout.addWidget(tts_card)

        # Card 4: Reconhecimento de Fala (STT - Speech to Text)
        stt_card, stt_lay = self._card()
        stt_title = QLabel("Reconhecimento de Fala (STT - Transcrição de Voz)")
        stt_title.setObjectName("sectionTitle")
        stt_lay.addWidget(stt_title)
        
        stt_lay.addWidget(QLabel("Selecionar Motor de STT (Reconhecimento de Fala):"))
        self.stt_combo = QComboBox()
        self.stt_combo.setObjectName("settingsComboBox")
        self.stt_combo.setStyleSheet(self.mic_combo.styleSheet())
        self.stt_combo.addItem("Automático (Groq Whisper -> Fallback Gemini)", "auto")
        self.stt_combo.addItem("Groq Whisper (Nuvem - Alta velocidade)", "groq_whisper")
        self.stt_combo.addItem("Gemini Multimodal (Nuvem - Nativo)", "gemini")
        stt_lay.addWidget(self.stt_combo)
        
        stt_lay.addWidget(QLabel("API Key do Groq (para Whisper) [Opcional]:"))
        self.groq_key_input = QLineEdit()
        self.groq_key_input.setPlaceholderText("Cole sua chave API do Groq aqui (gsk_...)...")
        self.groq_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        stt_lay.addWidget(self.groq_key_input)
        
        stt_note = QLabel("Nota: Se o motor STT selecionado falhar ou não possuir chave configurada, o sistema alternará automaticamente para o motor secundário.")
        stt_note.setObjectName("muted")
        stt_note.setWordWrap(True)
        stt_lay.addWidget(stt_note)
        
        layout.addWidget(stt_card)
        
        # Conexões para autosave
        self.mic_combo.currentIndexChanged.connect(self._save_voice_chat_settings)
        self.speaker_combo.currentIndexChanged.connect(self._save_voice_chat_settings)
        self.mix_audio_check.stateChanged.connect(self._save_voice_chat_settings)
        self.tts_combo.currentIndexChanged.connect(self._save_voice_chat_settings)
        self.stt_combo.currentIndexChanged.connect(self._save_voice_chat_settings)
        self.groq_key_input.editingFinished.connect(self._save_voice_chat_settings)
        
        layout.addStretch(1)
        return page

    def _refresh_voice_chat_ui(self):
        if not hasattr(self, "voice_chat_enabled_check"):
            return
        data = self._load_settings()
        self.voice_chat_enabled_check.setChecked(bool(data.get("voice_chat_enabled", True)))
        self.voice_chat_hotkey_input.setText(str(data.get("voice_chat_hotkey", "end")))
        self.voice_chat_style_input.setText(str(data.get("voice_chat_style_id", 3)))
        self._refresh_settings_ui()

    def _save_voice_chat_settings(self):
        enabled = self.voice_chat_enabled_check.isChecked()
        hotkey = self.voice_chat_hotkey_input.text().strip().lower()
        try:
            style_id = int(self.voice_chat_style_input.text().strip() or "3")
        except ValueError:
            style_id = 3
            
        data = self._load_settings()
        data["voice_chat_enabled"] = enabled
        data["voice_chat_hotkey"] = hotkey
        data["voice_chat_style_id"] = style_id
        
        self._safe_write_json(SETTINGS_PATH, data)
        self._save_settings_from_ui()
        self._update_hotkey_listener()
        self._toast("Configurações de voz salvas")

    def _open_floating_mic(self):
        if not self.floating_mic:
            self.floating_mic = FloatingMicrophoneWindow(self)
        self.floating_mic.show()
        self.floating_mic.raise_()
        self.floating_mic.activateWindow()
        
        # Desativa o modo chamada se estiver ativo
        if getattr(self.floating_mic, "live_call_mode", False):
            self.floating_mic.toggle_live_call()
            
        if not self.floating_mic.live_mode:
            self.floating_mic.toggle_live_mode()

    def _open_floating_call(self):
        if not self.floating_mic:
            self.floating_mic = FloatingMicrophoneWindow(self)
        self.floating_mic.show()
        self.floating_mic.raise_()
        self.floating_mic.activateWindow()
        
        # Se o modo live padrão estiver ativo, desativa para entrar em chamada pura
        if self.floating_mic.live_mode:
            self.floating_mic.toggle_live_mode()
            
        if not getattr(self.floating_mic, "live_call_mode", False):
            self.floating_mic.toggle_live_call()

    def _on_hotkey_triggered(self):
        self._handle_hotkey_press()

    def _on_hotkey_live_triggered(self):
        self._handle_hotkey_press()

    def _on_hotkey_raw_down(self):
        if self.hotkey_is_pressed:
            return
        
        # Verifica modificadores
        for mod in self.hotkey_modifiers:
            if not keyboard.is_pressed(mod):
                return

        self.hotkey_is_pressed = True
        self.hotkey_hold_triggered = False

        # Se estiver pensando (processing), a hotkey perde o poder
        if self.floating_mic and (self.floating_mic.live_mode or getattr(self.floating_mic, "live_call_mode", False)) and self.floating_mic.state == "processing":
            print("[Hotkey] Ayla pensando. Atalho desativado.")
            return

        # Inicia o timer de 2 segundos (2000 ms) para hold
        self.hotkey_hold_timer.start(2000)

    def _on_hotkey_raw_up(self):
        if not self.hotkey_is_pressed:
            return
        self.hotkey_is_pressed = False
        self.hotkey_hold_timer.stop()

        # Se estiver pensando (processing), a hotkey perde o poder
        if self.floating_mic and (self.floating_mic.live_mode or getattr(self.floating_mic, "live_call_mode", False)) and self.floating_mic.state == "processing":
            return

        # Se o hold de 2s não disparou, faz a ação rápida
        if not self.hotkey_hold_triggered:
            self._handle_hotkey_press()

    def _on_hotkey_hold_timeout(self):
        self.hotkey_hold_triggered = True
        self._handle_hotkey_hold()

    def _handle_hotkey_press(self):
        print("[Hotkey] Press (Aperto rápido) acionado.")
        
        has_active_mode = self.floating_mic and (self.floating_mic.live_mode or getattr(self.floating_mic, "live_call_mode", False))
        if not self.floating_mic or not has_active_mode or self.floating_mic.isHidden():
            if not self.floating_mic:
                self.floating_mic = FloatingMicrophoneWindow(self)
            self.floating_mic.show()
            self.floating_mic.raise_()
            self.floating_mic.activateWindow()
            if not (self.floating_mic.live_mode or getattr(self.floating_mic, "live_call_mode", False)):
                self.floating_mic.toggle_live_mode()
            return

        # Se Modo Live está ligado:
        # 3. Pensando (processing) -> ignora
        if self.floating_mic.state == "processing":
            print("[Hotkey] Ayla está pensando. Ignorado no press.")
            return

        # 4. Falando (is_speaking) -> interrompe a fala e vai para ouvir (start_recording)
        if self.floating_mic.is_speaking:
            print("[Hotkey] Interrompendo fala e indo para ouvir.")
            self.floating_mic._stop_playback()
            self.floating_mic.is_speaking = False
            self.floating_mic.speech_timer.stop()
            self.floating_mic.stop_pulse_animation()
            self.floating_mic.start_recording()
            return

        # 2. Ouvindo (listening) -> ao invés de desativar o microfone, força o pensamento!
        if self.floating_mic.state == "listening":
            print("[Hotkey] Forçando o pensamento (processamento de áudio).")
            self.floating_mic.stop_recording_and_process(force=True)
        elif self.floating_mic.state == "idle":
            print("[Hotkey] Ativando microfone.")
            self.floating_mic.start_recording()

    def _handle_hotkey_hold(self):
        print("[Hotkey] Hold (2 segundos pressionado) acionado.")
        
        has_active_mode = self.floating_mic and (self.floating_mic.live_mode or getattr(self.floating_mic, "live_call_mode", False))
        if not self.floating_mic or not has_active_mode or self.floating_mic.isHidden():
            return

        # 3. Pensando -> ignora
        if self.floating_mic.state == "processing":
            print("[Hotkey] Ayla está pensando. Ignorado no hold.")
            return

        # 2 ou 4 -> desliga/fechar modo live
        print("[Hotkey] Desligando/fechando Modo.")
        self.floating_mic.hide_window()

    def _update_hotkey_listener(self):
        self.unregister_native_hotkey()

        if keyboard is None:
            print("[Voice Chat] Biblioteca 'keyboard' nao instalada. Nao foi possivel ativar atalho global.")
            return
        try:
            # Remove o hook anterior se houver
            if getattr(self, "hotkey_hook_callback", None) is not None:
                try:
                    keyboard.unhook(self.hotkey_hook_callback)
                except Exception:
                    pass
                self.hotkey_hook_callback = None

            if hasattr(self, "hotkey_handle") and self.hotkey_handle is not None:
                try:
                    keyboard.remove_hotkey(self.hotkey_handle)
                except Exception:
                    pass
                self.hotkey_handle = None

            settings = self._load_settings()
            if not settings.get("voice_chat_enabled", True):
                return
            hotkey = settings.get("voice_chat_hotkey", "end").strip().lower()
            if not hotkey:
                return

            # Analisa se há modificadores
            parts = [p.strip() for p in hotkey.split('+')]
            self.hotkey_trigger_key = parts[-1]
            self.hotkey_modifiers = parts[:-1]

            # Callback do hook global do keyboard
            def on_key_event(event):
                ev_name = (event.name or "").lower().strip()
                trig_name = self.hotkey_trigger_key.lower().strip()
                if ev_name == trig_name:
                    if event.event_type == 'down':
                        self.hotkey_emitter_live.raw_down.emit()
                    elif event.event_type == 'up':
                        self.hotkey_emitter_live.raw_up.emit()

            self.hotkey_hook_callback = on_key_event
            keyboard.hook(self.hotkey_hook_callback)
            print(f"[Voice Chat] Hook global do atalho '{hotkey}' registrado.")
        except Exception as exc:
            print(f"[Voice Chat] Erro ao registrar hook global: {exc}")

    # ------------------------------------------------------------------
    # Página: Modo Público
    # ------------------------------------------------------------------

    def _build_public_mode_page(self):
        page, layout = self._scroll_page(
            "Modo Público",
            [("Salvar", self._save_public_mode, "primary"), ("Recarregar", self._refresh_public_mode_ui, "")]
        )

        # Card de explicação
        info_card, info_lay = self._card()
        info_title = QLabel("🌐 O que é o Modo Público?")
        info_title.setObjectName("sectionTitle")
        info_lay.addWidget(info_title)

        desc = QLabel(
            "Quando ativado, qualquer pessoa pode conversar com a Ayla no Discord "
            "(via menção ou DM).\n\n"
            "Porém, somente a dona (você!) pode executar ferramentas/funções. "
            "Se alguém que não é a dona tentar usar uma ferramenta, a Ayla vai "
            "dar uma bronca fofa explicando que só a dona pode fazer isso. 💜\n\n"
            "Quando desativado, a Ayla ignora completamente qualquer pessoa que não seja a dona."
        )
        desc.setObjectName("muted")
        desc.setWordWrap(True)
        info_lay.addWidget(desc)
        layout.addWidget(info_card)

        # Card do toggle
        toggle_card, toggle_lay = self._card()
        toggle_title = QLabel("Ativar / Desativar")
        toggle_title.setObjectName("sectionTitle")
        toggle_lay.addWidget(toggle_title)

        self.public_mode_check = QCheckBox("Permitir que outras pessoas conversem com a Ayla")
        self.public_mode_check.setStyleSheet("""
            QCheckBox {
                color: #f1f5f9;
                font-size: 14px;
                spacing: 10px;
                padding: 8px 4px;
            }
            QCheckBox::indicator {
                width: 22px;
                height: 22px;
                border-radius: 6px;
                border: 2px solid #6366f1;
                background: #1b1c30;
            }
            QCheckBox::indicator:checked {
                background: #6366f1;
                border-color: #818cf8;
            }
        """)
        toggle_lay.addWidget(self.public_mode_check)

        # Status label
        self.public_mode_status = QLabel("")
        self.public_mode_status.setStyleSheet("""
            QLabel {
                font-size: 13px;
                padding: 6px 12px;
                border-radius: 8px;
                font-weight: bold;
            }
        """)
        toggle_lay.addWidget(self.public_mode_status)

        self.public_mode_check.stateChanged.connect(self._save_public_mode)
        layout.addWidget(toggle_card)

        # Card de regras
        rules_card, rules_lay = self._card()
        rules_title = QLabel("📋 Regras do Modo Público")
        rules_title.setObjectName("sectionTitle")
        rules_lay.addWidget(rules_title)

        regras = [
            "✅  Qualquer pessoa pode enviar mensagens e anexos",
            "✅  A Ayla responde normalmente com texto",
            "🔒  Somente a dona pode executar ferramentas (tool_map)",
            "💜  Se alguém tentar usar ferramentas, a Ayla dá uma bronca fofa",
            "📎  Anexos (imagens, vídeos, docs) são aceitos de qualquer pessoa",
        ]
        for r in regras:
            lbl = QLabel(r)
            lbl.setStyleSheet("color: #cbd5e1; font-size: 13px; padding: 3px 0px;")
            lbl.setWordWrap(True)
            rules_lay.addWidget(lbl)
        layout.addWidget(rules_card)

        # Card do Modo Socializar (Chat Livre em Lotes de 5)
        social_card, social_lay = self._card()
        social_title = QLabel("💬 Modo Socializar (Chat Livre 5 em 5)")
        social_title.setObjectName("sectionTitle")
        social_lay.addWidget(social_title)

        social_desc = QLabel(
            "No Modo Socializar, a Ayla lê temporariamente o chat do Discord sem precisar que ninguém a mencione (@ayla ou /ayla).\n"
            "Ela lê as mensagens em lotes de 5 em 5 e decide quem responder ou o que comentar até você fechar o modo."
        )
        social_desc.setObjectName("muted")
        social_desc.setWordWrap(True)
        social_lay.addWidget(social_desc)

        self.social_mode_btn = QPushButton("Ativar Modo Socializar")
        self.social_mode_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.social_mode_btn.setStyleSheet("""
            QPushButton {
                background: #8b5cf6;
                color: white;
                font-weight: bold;
                padding: 10px 16px;
                border-radius: 8px;
            }
            QPushButton:hover {
                background: #a855f7;
            }
        """)
        self.social_mode_status = QLabel("Status: DESATIVADO")
        self.social_mode_status.setStyleSheet("color: #94a3b8; font-size: 13px; font-weight: bold;")

        social_row = QHBoxLayout()
        social_row.addWidget(self.social_mode_btn)
        social_row.addWidget(self.social_mode_status)
        social_row.addStretch(1)
        social_lay.addLayout(social_row)

        def _toggle_social():
            try:
                import ayla_state
                if ayla_state.is_modo_socializar_ativo():
                    ayla_state.desativar_modo_socializar()
                else:
                    ayla_state.ativar_modo_socializar("GLOBAL")
                self._refresh_public_mode_ui()
            except Exception as e:
                print(f"⚠️ Erro ao alterar Modo Socializar: {e}")

        self.social_mode_btn.clicked.connect(_toggle_social)
        layout.addWidget(social_card)

        layout.addStretch(1)
        self._refresh_public_mode_ui()
        return page

    def _refresh_public_mode_ui(self):
        if not hasattr(self, "public_mode_check"):
            return
        data = self._load_settings()
        enabled = bool(data.get("public_mode", False))
        was_blocked = self.public_mode_check.signalsBlocked()
        self.public_mode_check.blockSignals(True)
        self.public_mode_check.setChecked(enabled)
        self.public_mode_check.blockSignals(was_blocked)
        if enabled:
            self.public_mode_status.setText("🟢  Modo Público ATIVO — qualquer pessoa pode conversar")
            self.public_mode_status.setStyleSheet("""
                QLabel {
                    color: #4ade80; font-size: 13px; padding: 6px 12px;
                    border-radius: 8px; font-weight: bold;
                    background: rgba(74, 222, 128, 0.08);
                    border: 1px solid rgba(74, 222, 128, 0.2);
                }
            """)
        else:
            self.public_mode_status.setText("🔴  Modo Público DESATIVADO — apenas a dona pode conversar")
            self.public_mode_status.setStyleSheet("""
                QLabel {
                    color: #f87171; font-size: 13px; padding: 6px 12px;
                    border-radius: 8px; font-weight: bold;
                    background: rgba(248, 113, 113, 0.08);
                    border: 1px solid rgba(248, 113, 113, 0.2);
                }
            """)

        # Atualiza Status do Modo Socializar se o elemento existir
        if hasattr(self, "social_mode_btn") and hasattr(self, "social_mode_status"):
            import ayla_state
            if ayla_state.is_modo_socializar_ativo():
                self.social_mode_btn.setText("Fechar Modo Socializar")
                self.social_mode_btn.setStyleSheet("""
                    QPushButton {
                        background: #ef4444;
                        color: white;
                        font-weight: bold;
                        padding: 10px 16px;
                        border-radius: 8px;
                    }
                    QPushButton:hover {
                        background: #dc2626;
                    }
                """)
                self.social_mode_status.setText("🟢 Status: ATIVO (Lendo chat em lotes de 5 em 5)")
                self.social_mode_status.setStyleSheet("color: #4ade80; font-size: 13px; font-weight: bold;")
            else:
                self.social_mode_btn.setText("Ativar Modo Socializar")
                self.social_mode_btn.setStyleSheet("""
                    QPushButton {
                        background: #8b5cf6;
                        color: white;
                        font-weight: bold;
                        padding: 10px 16px;
                        border-radius: 8px;
                    }
                    QPushButton:hover {
                        background: #a855f7;
                    }
                """)
                self.social_mode_status.setText("🔴 Status: DESATIVADO")
                self.social_mode_status.setStyleSheet("color: #94a3b8; font-size: 13px; font-weight: bold;")

    def _save_public_mode(self):
        if not hasattr(self, "public_mode_check"):
            return
        data = self._load_settings()
        data["public_mode"] = self.public_mode_check.isChecked()
        self._safe_write_json(SETTINGS_PATH, data)
        try:
            setattr(self.bot, "ayla_settings", data)
        except Exception:
            pass
        self._refresh_public_mode_ui()
        estado = "ativado" if data["public_mode"] else "desativado"
        self._toast(f"Modo Público {estado}")

    # ------------------------------------------------------------------
    # Página: Bloqueios
    # ------------------------------------------------------------------

    def _load_block_list(self) -> list:
        try:
            data = json.loads(BLOCK_PATH.read_text(encoding="utf-8"))
            return data.get("blocked_users", [])
        except Exception:
            return []

    def _save_block_list(self, lista: list):
        self._safe_write_json(BLOCK_PATH, {"blocked_users": lista})

    def _build_bloqueios_page(self):
        page, layout = self._scroll_page(
            "Bloqueios",
            [("Recarregar", self._refresh_bloqueios, "")]
        )

        # Card: Adicionar bloqueio
        add_card, add_lay = self._card()
        add_title = QLabel("🚫 Bloquear Usuário por ID")
        add_title.setObjectName("sectionTitle")
        add_lay.addWidget(add_title)

        add_desc = QLabel(
            "Digite o ID do Discord do usuário para bloqueá-lo. "
            "O nome será buscado automaticamente via Discord."
        )
        add_desc.setObjectName("muted")
        add_desc.setWordWrap(True)
        add_lay.addWidget(add_desc)

        input_row = QHBoxLayout()
        self.block_id_input = QLineEdit()
        self.block_id_input.setPlaceholderText("ID do usuário (ex: 123456789012345678)")
        self.block_id_input.setStyleSheet("""
            QLineEdit {
                background: #1b1c30; border: 1px solid #32355a;
                border-radius: 6px; padding: 8px 12px;
                color: #f1f5f9; font-size: 13px;
            }
            QLineEdit:focus { border-color: #6366f1; }
        """)
        input_row.addWidget(self.block_id_input, 1)

        self.block_reason_input = QLineEdit()
        self.block_reason_input.setPlaceholderText("Motivo (opcional)")
        self.block_reason_input.setStyleSheet("""
            QLineEdit {
                background: #1b1c30; border: 1px solid #32355a;
                border-radius: 6px; padding: 8px 12px;
                color: #f1f5f9; font-size: 13px;
            }
            QLineEdit:focus { border-color: #6366f1; }
        """)
        input_row.addWidget(self.block_reason_input, 1)

        add_btn = QPushButton("Bloquear")
        add_btn.setObjectName("primary")
        add_btn.clicked.connect(self._add_block_user)
        input_row.addWidget(add_btn)
        add_lay.addLayout(input_row)

        self.block_status_label = QLabel("")
        self.block_status_label.setStyleSheet("color: #94a3b8; font-size: 12px; padding: 4px 0;")
        self.block_status_label.setWordWrap(True)
        add_lay.addWidget(self.block_status_label)

        layout.addWidget(add_card)

        # Card: Lista de bloqueados
        list_card, list_lay = self._card()
        list_title = QLabel("📋 Usuários Bloqueados")
        list_title.setObjectName("sectionTitle")
        list_lay.addWidget(list_title)

        self.block_list_container = QVBoxLayout()
        list_lay.addLayout(self.block_list_container)

        self.block_empty_label = QLabel("Nenhum usuário bloqueado.")
        self.block_empty_label.setStyleSheet("color: #64748b; font-size: 13px; padding: 8px 0;")
        list_lay.addWidget(self.block_empty_label)

        layout.addWidget(list_card)
        layout.addStretch(1)

        self._refresh_bloqueios()
        return page

    def _refresh_bloqueios(self):
        if not hasattr(self, "block_list_container"):
            return
        # Limpa widgets anteriores
        while self.block_list_container.count():
            item = self.block_list_container.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        bloqueios = self._load_block_list()
        self.block_empty_label.setVisible(len(bloqueios) == 0)

        for entry in bloqueios:
            uid = entry.get("id", "?")
            reason = entry.get("reason", "Sem motivo")
            blocked_at = entry.get("blocked_at", "?")
            blocked_by = entry.get("blocked_by", "?")
            name = entry.get("name", "")

            row = QFrame()
            row.setStyleSheet("""
                QFrame {
                    background: #1b1c30; border: 1px solid #32355a;
                    border-radius: 8px; padding: 6px;
                }
            """)
            h = QHBoxLayout(row)
            h.setContentsMargins(12, 8, 12, 8)

            info_text = f"<b style='color:#f1f5f9;'>{name or uid}</b>"
            if name:
                info_text += f"  <span style='color:#64748b;'>({uid})</span>"
            info_text += (
                f"<br/><span style='color:#94a3b8; font-size:12px;'>"
                f"Motivo: {reason} · {blocked_at} · por {blocked_by}</span>"
            )
            lbl = QLabel(info_text)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setWordWrap(True)
            h.addWidget(lbl, 1)

            remove_btn = QPushButton("Desbloquear")
            remove_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(248, 113, 113, 0.15); color: #f87171;
                    border: 1px solid rgba(248, 113, 113, 0.3); border-radius: 6px;
                    padding: 6px 14px; font-size: 12px; font-weight: bold;
                }
                QPushButton:hover { background: rgba(248, 113, 113, 0.25); }
            """)
            remove_btn.clicked.connect(lambda checked=False, u=uid: self._remove_block_user(u))
            h.addWidget(remove_btn)

            self.block_list_container.addWidget(row)

    def _add_block_user(self):
        raw_id = self.block_id_input.text().strip()
        motivo = self.block_reason_input.text().strip() or "Bloqueado manualmente pela dona"

        try:
            user_id = int(raw_id)
        except ValueError:
            self.block_status_label.setText("❌ ID inválido. Use apenas números.")
            self.block_status_label.setStyleSheet("color: #f87171; font-size: 12px; padding: 4px 0;")
            return

        # Verifica se é a dona
        owner_id = int(os.getenv("DISCORD_OWNER_ID", "0"))
        if user_id == owner_id:
            self.block_status_label.setText("❌ Você não pode se bloquear! Você é imune. 💜")
            self.block_status_label.setStyleSheet("color: #f87171; font-size: 12px; padding: 4px 0;")
            return

        bloqueios = self._load_block_list()
        if any(u["id"] == user_id for u in bloqueios):
            self.block_status_label.setText(f"⚠️ Usuário {user_id} já está bloqueado.")
            self.block_status_label.setStyleSheet("color: #fbbf24; font-size: 12px; padding: 4px 0;")
            return

        # Tenta resolver o nome via Discord API
        nome_discord = ""
        try:
            import asyncio
            bot = self.bot
            if bot and bot.is_ready():
                future = asyncio.run_coroutine_threadsafe(bot.fetch_user(user_id), bot.loop)
                user_obj = future.result(timeout=5)
                if user_obj:
                    nome_discord = str(user_obj.display_name)
        except Exception as e:
            print(f"[Bloqueios] Não conseguiu resolver nome do ID {user_id}: {e}")

        from datetime import datetime
        bloqueios.append({
            "id": user_id,
            "name": nome_discord,
            "reason": motivo,
            "blocked_at": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "blocked_by": "dona (GUI)",
        })
        self._save_block_list(bloqueios)

        display = nome_discord or str(user_id)
        self.block_status_label.setText(f"✅ {display} bloqueado com sucesso!")
        self.block_status_label.setStyleSheet("color: #4ade80; font-size: 12px; padding: 4px 0;")
        self.block_id_input.clear()
        self.block_reason_input.clear()
        self._refresh_bloqueios()

    def _remove_block_user(self, user_id):
        user_id = int(user_id)
        bloqueios = self._load_block_list()
        nova = [u for u in bloqueios if u["id"] != user_id]
        self._save_block_list(nova)
        self._toast(f"Usuário {user_id} desbloqueado")
        self._refresh_bloqueios()

    # ------------------------------------------------------------------
    # Gerenciador de Mídias (Emojis, GIFs e Fotos)
    # ------------------------------------------------------------------

    def _build_media_manager_page(self):
        page, layout = self._scroll_page(
            "Gerenciador de Emojis, GIFs & Fotos",
            [
                ("🔄 Importar do Discord", self._import_emojis_from_discord, ""),
                ("💾 Salvar Mídias", self._save_media_changes, "primary")
            ]
        )

        # Card 1: Emojis do Discord
        emoji_card, emoji_lay = self._card()
        etitle = QLabel("🌟 Emojis do Discord (&Nome do Emoji&)")
        etitle.setObjectName("sectionTitle")
        emoji_lay.addWidget(etitle)

        edesc = QLabel(
            "Cadastre o apelido/nome simples que a Ayla usará nas mensagens e a tag bruta oficial do Discord.\n"
            "Exemplo: Nome: Miku bebendo monster | Tag: <:Miku_bebendo_monster:1508877471884509314>"
        )
        edesc.setObjectName("muted")
        edesc.setWordWrap(True)
        emoji_lay.addWidget(edesc)

        self.emoji_table = QTableWidget()
        self.emoji_table.setColumnCount(3)
        self.emoji_table.setHorizontalHeaderLabels(["Nome para a Ayla", "Tag / Código no Discord", "Ação"])
        self.emoji_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.emoji_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.emoji_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.emoji_table.setColumnWidth(2, 90)
        self.emoji_table.setStyleSheet("background: #12131c; color: #f1f5f9; border: 1px solid #2d304e; gridline-color: #26283f;")
        emoji_lay.addWidget(self.emoji_table)

        erow = QHBoxLayout()
        self.emoji_name_input = QLineEdit()
        self.emoji_name_input.setPlaceholderText("Nome (ex: Ayla fofa)")
        self.emoji_tag_input = QLineEdit()
        self.emoji_tag_input.setPlaceholderText("Tag Discord (ex: <:ayla_fofa:1508877427584139406>)")
        add_emoji_btn = QPushButton("➕ Adicionar Emoji")
        add_emoji_btn.clicked.connect(self._add_emoji_from_inputs)

        erow.addWidget(self.emoji_name_input, 1)
        erow.addWidget(self.emoji_tag_input, 1)
        erow.addWidget(add_emoji_btn)
        emoji_lay.addLayout(erow)

        layout.addWidget(emoji_card)

        # Card 2: GIFs e Fotos
        gif_card, gif_lay = self._card()
        gtitle = QLabel("🎬 GIFs e Fotos (%Nome do GIF%)")
        gtitle.setObjectName("sectionTitle")
        gif_lay.addWidget(gtitle)

        gdesc = QLabel(
            "Cadastre o nome do GIF/Foto que a Ayla usará nas mensagens e a URL/link puro da imagem.\n"
            "Exemplo: Nome: Gold Ship aplaudindo | URL: https://klipy.com/gifs/uma-musume-clapping"
        )
        gdesc.setObjectName("muted")
        gdesc.setWordWrap(True)
        gif_lay.addWidget(gdesc)

        self.gif_table = QTableWidget()
        self.gif_table.setColumnCount(3)
        self.gif_table.setHorizontalHeaderLabels(["Nome para a Ayla", "URL / Link da Imagem", "Ação"])
        self.gif_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.gif_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.gif_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.gif_table.setColumnWidth(2, 90)
        self.gif_table.setStyleSheet("background: #12131c; color: #f1f5f9; border: 1px solid #2d304e; gridline-color: #26283f;")
        gif_lay.addWidget(self.gif_table)

        grow = QHBoxLayout()
        self.gif_name_input = QLineEdit()
        self.gif_name_input.setPlaceholderText("Nome (ex: Gold Ship aplaudindo)")
        self.gif_url_input = QLineEdit()
        self.gif_url_input.setPlaceholderText("URL / Link (ex: https://klipy.com/...)")
        add_gif_btn = QPushButton("➕ Adicionar GIF")
        add_gif_btn.clicked.connect(self._add_gif_from_inputs)

        grow.addWidget(self.gif_name_input, 1)
        grow.addWidget(self.gif_url_input, 1)
        grow.addWidget(add_gif_btn)
        gif_lay.addLayout(grow)

        layout.addWidget(gif_card)

        return page

    def _refresh_media_manager(self):
        try:
            import Ayla
            midias = Ayla.carregar_midias_ayla()
        except Exception:
            midias = {"emojis": {}, "gifs_e_fotos": {}}

        emojis = midias.get("emojis", {})
        gifs = midias.get("gifs_e_fotos", {})

        self.emoji_table.setRowCount(0)
        for name, tag in emojis.items():
            self._insert_table_row(self.emoji_table, name, tag)

        self.gif_table.setRowCount(0)
        for name, url in gifs.items():
            self._insert_table_row(self.gif_table, name, url)

    def _insert_table_row(self, table: QTableWidget, name: str, value: str):
        row = table.rowCount()
        table.insertRow(row)
        item_name = QTableWidgetItem(name)
        item_val = QTableWidgetItem(value)
        table.setItem(row, 0, item_name)
        table.setItem(row, 1, item_val)

        btn_del = QPushButton("🗑️ Excluir")
        btn_del.setObjectName("danger")
        btn_del.clicked.connect(lambda _, t=table, b=btn_del: self._delete_table_row(t, b))
        table.setCellWidget(row, 2, btn_del)

    def _delete_table_row(self, table: QTableWidget, btn: QPushButton):
        for r in range(table.rowCount()):
            if table.cellWidget(r, 2) == btn:
                table.removeRow(r)
                break

    def _add_emoji_from_inputs(self):
        nome = self.emoji_name_input.text().strip()
        tag = self.emoji_tag_input.text().strip()
        if not nome or not tag:
            QMessageBox.warning(self, "Campos Inválidos", "Preencha o Nome e a Tag do Emoji do Discord!")
            return
        self._insert_table_row(self.emoji_table, nome, tag)
        self.emoji_name_input.clear()
        self.emoji_tag_input.clear()

    def _add_gif_from_inputs(self):
        nome = self.gif_name_input.text().strip()
        url = self.gif_url_input.text().strip()
        if not nome or not url:
            QMessageBox.warning(self, "Campos Inválidos", "Preencha o Nome e o Link do GIF/Foto!")
            return
        self._insert_table_row(self.gif_table, nome, url)
        self.gif_name_input.clear()
        self.gif_url_input.clear()

    def _import_emojis_from_discord(self):
        if not self.bot or not hasattr(self.bot, "guilds") or not self.bot.guilds:
            QMessageBox.warning(self, "Bot Desconectado", "O Bot da Ayla precisa estar conectado ao Discord para puxar os emojis dos servidores!")
            return

        importados = 0
        existentes = set()
        for r in range(self.emoji_table.rowCount()):
            item = self.emoji_table.item(r, 0)
            if item:
                existentes.add(item.text().strip().lower())

        for guild in self.bot.guilds:
            for emoji in guild.emojis:
                nome_formatado = emoji.name.replace("_", " ")
                tag_bruta = f"<a:{emoji.name}:{emoji.id}>" if emoji.animated else f"<:{emoji.name}:{emoji.id}>"
                if nome_formatado.lower() not in existentes and emoji.name.lower() not in existentes:
                    self._insert_table_row(self.emoji_table, nome_formatado, tag_bruta)
                    existentes.add(nome_formatado.lower())
                    importados += 1

        if importados > 0:
            QMessageBox.information(self, "Importação Concluída", f"Foram importados {importados} emojis dos servidores do Discord!")
        else:
            QMessageBox.information(self, "Nenhum Emoji Novo", "Todos os emojis dos servidores já estão cadastrados na lista!")

    def _save_media_changes(self):
        emojis = {}
        for r in range(self.emoji_table.rowCount()):
            name_item = self.emoji_table.item(r, 0)
            val_item = self.emoji_table.item(r, 1)
            if name_item and val_item:
                n = name_item.text().strip()
                v = val_item.text().strip()
                if n and v:
                    emojis[n] = v

        gifs = {}
        for r in range(self.gif_table.rowCount()):
            name_item = self.gif_table.item(r, 0)
            val_item = self.gif_table.item(r, 1)
            if name_item and val_item:
                n = name_item.text().strip()
                v = val_item.text().strip()
                if n and v:
                    gifs[n] = v

        dados = {
            "emojis": emojis,
            "gifs_e_fotos": gifs
        }

        try:
            import Ayla
            Ayla.salvar_midias_ayla(dados)
            if self.bot:
                self.bot.prompt_com_memoria = Ayla.montar_prompt_com_memoria()
            QMessageBox.information(self, "Sucesso", "Mídias salvas com sucesso! O prompt da Ayla foi atualizado em tempo real.")
        except Exception as e:
            QMessageBox.critical(self, "Erro ao Salvar", f"Ocorreu um erro ao salvar as mídias: {e}")

    def _build_settings_page(self):
        page, layout = self._scroll_page("Configuracoes da Ayla", [("Salvar", self._save_settings_from_ui, "primary"), ("Recarregar", self._refresh_settings_ui, ""), ("Recarregar GUI", self.reload_gui, "pink")])
        intro, intro_lay = self._card()
        title = QLabel("Arquivo separado do ENV")
        title.setObjectName("sectionTitle")
        intro_lay.addWidget(title)
        text = QLabel("Estas opcoes ficam em ayla_settings.json e nao alteram suas chaves do .env.")
        text.setObjectName("muted")
        text.setWordWrap(True)
        intro_lay.addWidget(text)
        layout.addWidget(intro)

        behavior, behavior_lay = self._card()
        behavior_title = QLabel("Comportamento")
        behavior_title.setObjectName("sectionTitle")
        behavior_lay.addWidget(behavior_title)
        self.settings_checks = {
            "screenshot_before_response": QCheckBox("Tirar print e anexar para a Ayla antes de responder"),
        }
        for check in self.settings_checks.values():
            behavior_lay.addWidget(check)
        layout.addWidget(behavior)
        layout.addStretch(1)
        self.speaker_combo.currentIndexChanged.connect(self._save_settings_from_ui)
        self.mix_audio_check.stateChanged.connect(self._save_settings_from_ui)
        for check in self.settings_checks.values():
            check.stateChanged.connect(self._save_settings_from_ui)

        self._refresh_settings_ui()
        return page

    def _refresh_settings_ui(self):
        if not hasattr(self, "settings_checks") or not self.settings_checks:
            return
        data = self._load_settings()
        
        # Bloqueia sinais temporariamente para evitar loops de salvamento automático
        was_blocked_checks = {}
        for key, check in self.settings_checks.items():
            was_blocked_checks[key] = check.signalsBlocked()
            check.blockSignals(True)
            
        was_blocked_mic = False
        if hasattr(self, "mic_combo"):
            was_blocked_mic = self.mic_combo.signalsBlocked()
            self.mic_combo.blockSignals(True)
            
        was_blocked_speaker = False
        if hasattr(self, "speaker_combo"):
            was_blocked_speaker = self.speaker_combo.signalsBlocked()
            self.speaker_combo.blockSignals(True)
            
        was_blocked_mix = False
        if hasattr(self, "mix_audio_check"):
            was_blocked_mix = self.mix_audio_check.signalsBlocked()
            self.mix_audio_check.blockSignals(True)
            
        was_blocked_tts = False
        if hasattr(self, "tts_combo"):
            was_blocked_tts = self.tts_combo.signalsBlocked()
            self.tts_combo.blockSignals(True)
            
        for key, check in self.settings_checks.items():
            check.setChecked(bool(data.get(key, False)))
            
        # Carrega microfone selecionado
        if hasattr(self, "mic_combo"):
            selected_mic = data.get("selected_mic_name", "")
            idx = self.mic_combo.findData(selected_mic)
            if idx < 0 and selected_mic:
                # Se não encontrar por correspondência exata, tenta correspondência parcial/insensível
                for i in range(self.mic_combo.count()):
                    item_data = self.mic_combo.itemData(i)
                    if item_data and (selected_mic.lower() in item_data.lower() or item_data.lower() in selected_mic.lower()):
                        idx = i
                        break
            if idx >= 0:
                self.mic_combo.setCurrentIndex(idx)
            else:
                self.mic_combo.setCurrentIndex(0)
                
        # Carrega alto-falante selecionado
        if hasattr(self, "speaker_combo"):
            selected_speaker = data.get("selected_speaker_name", "")
            idx = self.speaker_combo.findData(selected_speaker)
            if idx < 0 and selected_speaker:
                for i in range(self.speaker_combo.count()):
                    item_data = self.speaker_combo.itemData(i)
                    if item_data and (selected_speaker.lower() in item_data.lower() or item_data.lower() in selected_speaker.lower()):
                        idx = i
                        break
            if idx >= 0:
                self.speaker_combo.setCurrentIndex(idx)
            else:
                self.speaker_combo.setCurrentIndex(0)
                
        # Carrega mix_system_audio
        if hasattr(self, "mix_audio_check"):
            self.mix_audio_check.setChecked(bool(data.get("mix_system_audio", True)))
            
        # Carrega engine TTS
        if hasattr(self, "tts_combo"):
            selected_tts = data.get("tts_engine", "voicevox")
            idx_tts = self.tts_combo.findData(selected_tts)
            if idx_tts >= 0:
                self.tts_combo.setCurrentIndex(idx_tts)
            else:
                self.tts_combo.setCurrentIndex(0)
                
        # Carrega campos do TTS (com fallback para .env)
        from dotenv import load_dotenv
        load_dotenv(ENV_PATH, override=True)
        
        fish_key_env = os.getenv("FISH_AUDIO_API_KEY", "")
        fish_voice_env = os.getenv("FISH_AUDIO_VOICE_ID", "")
        
        if hasattr(self, "fish_key_input"):
            self.fish_key_input.setText(data.get("fish_audio_api_key") or fish_key_env)
        if hasattr(self, "fish_voice_input"):
            self.fish_voice_input.setText(data.get("fish_audio_voice_id") or fish_voice_env)
        if hasattr(self, "voicevox_style_input"):
            self.voicevox_style_input.setText(str(data.get("voice_chat_style_id", 3)))
            
        # Carrega engine STT
        if hasattr(self, "stt_combo"):
            selected_stt = data.get("stt_engine", "auto")
            idx_stt = self.stt_combo.findData(selected_stt)
            if idx_stt >= 0:
                self.stt_combo.setCurrentIndex(idx_stt)
            else:
                self.stt_combo.setCurrentIndex(0)

        groq_key_env = os.getenv("GROQ_API_KEY", "")
        if hasattr(self, "groq_key_input"):
            self.groq_key_input.setText(data.get("groq_api_key") or groq_key_env)

        # Desbloqueia os sinais
        for key, check in self.settings_checks.items():
            check.blockSignals(was_blocked_checks.get(key, False))
        if hasattr(self, "mic_combo"):
            self.mic_combo.blockSignals(was_blocked_mic)
        if hasattr(self, "speaker_combo"):
            self.speaker_combo.blockSignals(was_blocked_speaker)
        if hasattr(self, "mix_audio_check"):
            self.mix_audio_check.blockSignals(was_blocked_mix)
        if hasattr(self, "tts_combo"):
            self.tts_combo.blockSignals(was_blocked_tts)

    def _update_env_var(self, key, value):
        if not ENV_PATH.exists():
            ENV_PATH.write_text(f"{key}={value}\n", encoding="utf-8")
            return
        try:
            lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
            found = False
            for i, line in enumerate(lines):
                if line.strip().startswith(f"{key}="):
                    lines[i] = f"{key}={value}"
                    found = True
                    break
            if not found:
                lines.append(f"{key}={value}")
            ENV_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        except Exception as e:
            print(f"[GUI] Erro ao atualizar {key} no .env: {e}")

    def _save_settings_from_ui(self):
        data = self._load_settings()
        if hasattr(self, "settings_checks") and "screenshot_before_response" in self.settings_checks:
            data["screenshot_before_response"] = self.settings_checks["screenshot_before_response"].isChecked()
        if hasattr(self, "mic_combo"):
            data["selected_mic_name"] = self.mic_combo.currentData()
        if hasattr(self, "speaker_combo"):
            data["selected_speaker_name"] = self.speaker_combo.currentData()
        if hasattr(self, "mix_audio_check"):
            data["mix_system_audio"] = self.mix_audio_check.isChecked()
        if hasattr(self, "tts_combo"):
            data["tts_engine"] = self.tts_combo.currentData()
        if hasattr(self, "stt_combo"):
            data["stt_engine"] = self.stt_combo.currentData()
            
        if hasattr(self, "groq_key_input"):
            groq_val = self.groq_key_input.text().strip()
            data["groq_api_key"] = groq_val
            self._update_env_var("GROQ_API_KEY", groq_val)

        if hasattr(self, "fish_key_input"):
            key_val = self.fish_key_input.text().strip()
            data["fish_audio_api_key"] = key_val
            self._update_env_var("FISH_AUDIO_API_KEY", key_val)
            
        if hasattr(self, "fish_voice_input"):
            voice_val = self.fish_voice_input.text().strip()
            data["fish_audio_voice_id"] = voice_val
            self._update_env_var("FISH_AUDIO_VOICE_ID", voice_val)
            
        if hasattr(self, "voicevox_style_input"):
            try:
                data["voice_chat_style_id"] = int(self.voicevox_style_input.text().strip())
            except ValueError:
                data["voice_chat_style_id"] = 3
        
        last_id = getattr(self.bot, "last_active_channel_id", None)
        if last_id:
            data["last_active_channel_id"] = last_id

        self._safe_write_json(SETTINGS_PATH, data)
        try:
            setattr(self.bot, "ayla_settings", data)
        except Exception:
            pass
        self._toast("Configurações salvas")

    def _build_tts_page(self):
        page, layout = self._scroll_page("Configurações de Voz (TTS)", [("Salvar", self._save_settings_from_ui, "primary"), ("Recarregar", self._refresh_settings_ui, "")])
        
        intro, intro_lay = self._card()
        title = QLabel("Configurações do Motor TTS")
        title.setObjectName("sectionTitle")
        intro_lay.addWidget(title)
        text = QLabel("Escolha o motor de síntese de voz (TTS) para as respostas faladas da Ayla.")
        text.setObjectName("muted")
        text.setWordWrap(True)
        intro_lay.addWidget(text)
        layout.addWidget(intro)

        # Card de Seleção do Motor
        engine_card, engine_lay = self._card()
        engine_title = QLabel("Selecione o Motor TTS")
        engine_title.setObjectName("sectionTitle")
        engine_lay.addWidget(engine_title)

        if not hasattr(self, "tts_combo"):
            self.tts_combo = QComboBox()
            self.tts_combo.setObjectName("settingsComboBox")
            self.tts_combo.addItem("Fish Audio API (Nuvem - Modelo s2.1-pro-free)", "fish_audio")
            self.tts_combo.addItem("VoiceVox (Local)", "voicevox")
            self.tts_combo.addItem("Voz Nativa do Windows (SAPI5)", "sapi5")
            self.tts_combo.setStyleSheet("""
                QComboBox {
                    background-color: #1b1c30;
                    border: 1px solid #32355a;
                    border-radius: 6px;
                    padding: 6px 10px;
                    color: #f1f5f9;
                    font-size: 13px;
                }
                QComboBox::drop-down {
                    border: none;
                }
            """)
            engine_lay.addWidget(self.tts_combo)
            layout.addWidget(engine_card)
        else:
            engine_lay.addWidget(QLabel("O motor TTS selecionado no momento está configurado na aba Conversa por Voz."))
            layout.addWidget(engine_card)

        # Card de Configurações do Fish Audio
        fish_card, fish_lay = self._card()
        fish_title = QLabel("Opções do Fish Audio API")
        fish_title.setObjectName("sectionTitle")
        fish_lay.addWidget(fish_title)
        
        fish_lay.addWidget(QLabel("API Key do Fish Audio:"))
        self.fish_key_input = QLineEdit()
        self.fish_key_input.setPlaceholderText("Cole sua chave API do Fish Audio aqui...")
        self.fish_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        fish_lay.addWidget(self.fish_key_input)
        
        fish_lay.addWidget(QLabel("ID do Modelo de Voz (reference_id) [Opcional]:"))
        self.fish_voice_input = QLineEdit()
        self.fish_voice_input.setPlaceholderText("ID da voz clonada ou pública do Fish Audio (deixe vazio para voz padrão)...")
        fish_lay.addWidget(self.fish_voice_input)
        
        layout.addWidget(fish_card)

        # Card de Configurações do Voicevox
        voicevox_card, voicevox_lay = self._card()
        voicevox_title = QLabel("Opções do VoiceVox (Local)")
        voicevox_title.setObjectName("sectionTitle")
        voicevox_lay.addWidget(voicevox_title)
        
        voicevox_lay.addWidget(QLabel("ID do Personagem (Speaker ID / Style ID):"))
        self.voicevox_style_input = QLineEdit()
        self.voicevox_style_input.setPlaceholderText("Ex: 3 (voz padrão da Ayla)")
        voicevox_lay.addWidget(self.voicevox_style_input)
        
        layout.addWidget(voicevox_card)
        layout.addStretch(1)
        
        # Conexões para salvamento automático
        self.tts_combo.currentIndexChanged.connect(self._save_settings_from_ui)
        self.fish_key_input.editingFinished.connect(self._save_settings_from_ui)
        self.fish_voice_input.editingFinished.connect(self._save_settings_from_ui)
        self.voicevox_style_input.editingFinished.connect(self._save_settings_from_ui)
        
        self._refresh_settings_ui()
        return page


    # ------------------------------------------------------------------
    # ENV
    # ------------------------------------------------------------------

    def _build_config_page(self):
        page, layout = self._scroll_page("Configuracoes (.env)", [("Salvar", self._save_env, "primary"), ("Recarregar", self._reload_env, "")])
        add_card, add = self._card()
        title = QLabel("Adicionar variavel")
        title.setObjectName("sectionTitle")
        add.addWidget(title)
        row = QHBoxLayout()
        self.env_new_key = QLineEdit()
        self.env_new_key.setPlaceholderText("NOME_DA_VARIAVEL")
        self.env_new_value = QLineEdit()
        self.env_new_value.setPlaceholderText("valor")
        add_btn = QPushButton("Adicionar")
        add_btn.setObjectName("pink")
        add_btn.clicked.connect(self._add_env_var)
        row.addWidget(self.env_new_key, 1)
        row.addWidget(self.env_new_value, 2)
        row.addWidget(add_btn)
        add.addLayout(row)
        layout.addWidget(add_card)

        self.env_container = QVBoxLayout()
        self.env_container.setSpacing(8)
        layout.addLayout(self.env_container)
        layout.addStretch(1)
        return page

    def _clear_layout(self, layout: QVBoxLayout | QGridLayout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget:
                widget.deleteLater()
            elif child_layout:
                self._clear_layout(child_layout)

    def _reload_env(self):
        if not hasattr(self, "env_container"):
            return
        self._clear_layout(self.env_container)
        self.env_rows = []
        if not ENV_PATH.exists():
            lbl = QLabel(".env nao encontrado")
            lbl.setObjectName("muted")
            self.env_container.addWidget(lbl)
            return
        try:
            lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
        except Exception as exc:
            self._toast(f"Erro ao ler .env: {exc}")
            return

        for idx, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#") and len(stripped) > 1:
                lbl = QLabel(stripped.lstrip("# ").strip())
                lbl.setObjectName("sectionTitle")
                self.env_container.addWidget(lbl)
                self.env_rows.append({"kind": "comment", "line": line})
                continue
            if "=" not in stripped or stripped.startswith("#"):
                self.env_rows.append({"kind": "raw", "line": line})
                continue
            line_no_comment = stripped
            comment = ""
            if " #" in stripped:
                line_no_comment, _, tail = stripped.partition(" #")
                comment = " #" + tail
            key, _, value = line_no_comment.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            sensitive = any(word in key.upper() for word in SENSITIVE_WORDS)
            card, card_lay = self._card()
            row = QHBoxLayout()
            key_lbl = QLabel(key)
            key_lbl.setMinimumWidth(230)
            key_lbl.setObjectName("muted")
            entry = QLineEdit(value)
            entry.setEchoMode(QLineEdit.EchoMode.Password if sensitive else QLineEdit.EchoMode.Normal)
            row.addWidget(key_lbl)
            row.addWidget(entry, 1)
            if sensitive:
                reveal = QPushButton("Ver")
                reveal.clicked.connect(lambda checked=False, e=entry, b=reveal: self._toggle_secret(e, b))
                row.addWidget(reveal)
            remove = QPushButton("Remover")
            remove.setObjectName("danger")
            remove.clicked.connect(lambda checked=False, e=entry: self._remove_env_row(e))
            row.addWidget(remove)
            card_lay.addLayout(row)
            self.env_container.addWidget(card)
            self.env_rows.append({"kind": "entry", "key": key, "comment": comment, "entry": entry, "card": card})

    def _toggle_secret(self, entry: QLineEdit, button: QPushButton):
        if entry.echoMode() == QLineEdit.EchoMode.Password:
            entry.setEchoMode(QLineEdit.EchoMode.Normal)
            button.setText("Ocultar")
        else:
            entry.setEchoMode(QLineEdit.EchoMode.Password)
            button.setText("Ver")

    def _remove_env_row(self, entry: QLineEdit):
        for row in self.env_rows:
            if row.get("entry") is entry:
                row["kind"] = "removed"
                card = row.get("card")
                if card:
                    card.hide()
                break

    def _add_env_var(self):
        key = self.env_new_key.text().strip()
        value = self.env_new_value.text().strip()
        if not key or "=" in key:
            self._toast("Nome de variavel invalido")
            return
        if any(row.get("kind") == "entry" and row.get("key") == key for row in self.env_rows):
            self._toast("Essa variavel ja existe")
            return
        self.env_new_key.clear()
        self.env_new_value.clear()
        self.env_rows.append({"kind": "raw", "line": f"{key}={value}"})
        self._save_env()
        self._reload_env()

    def _save_env(self):
        try:
            lines: list[str] = []
            for row in self.env_rows:
                kind = row.get("kind")
                if kind == "entry":
                    lines.append(f"{row['key']}={row['entry'].text().strip()}{row.get('comment', '')}")
                elif kind in ("comment", "raw"):
                    lines.append(row.get("line", ""))
            ENV_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
            self._hot_reload_api_keys()
            self._toast(".env salvo")
        except Exception as exc:
            self._toast(f"Erro ao salvar .env: {exc}")

    def _hot_reload_api_keys(self):
        try:
            from dotenv import load_dotenv
            load_dotenv(ENV_PATH, override=True)
            keys = [os.getenv(f"GEMINI_API_KEY_{i}", "") for i in range(1, 7)]
            keys = [key for key in keys if key.strip()]
            if keys and hasattr(self.bot, "api_keys"):
                self.bot.api_keys = keys
                self.bot.idx_api_atual = 0
                from google import genai
                self.bot.genai_client = genai.Client(api_key=keys[0])
                print("[GUI] APIs recarregadas na memoria do bot.")
        except Exception as exc:
            print(f"Erro ao recarregar APIs: {exc}")

    # ------------------------------------------------------------------
    # Modelos
    # ------------------------------------------------------------------

    def _load_models_config(self):
        defaults = {
            "padrao": [
                {"name": "gemini-3.1-flash-lite", "desc": "Ultra-rapido e eficiente", "tags": ["Rapido", "Economico"]},
                {"name": "gemini-2.5-flash-lite", "desc": "Modelo compacto rapido", "tags": ["Economico", "Rapido"]},
            ]
        }
        data = self._safe_load_json(MODELS_PATH, defaults)
        if not isinstance(data, dict):
            data = defaults
        data.pop("raciocinar", None)
        data.pop("modo", None)
        data.setdefault("padrao", defaults["padrao"])
        self.loaded_models = {"padrao": data.get("padrao", [])}

    def _save_models_config(self):
        try:
            self.loaded_models = {"padrao": self.loaded_models.get("padrao", [])}
            self._safe_write_json(MODELS_PATH, self.loaded_models)
            if self.bot:
                self.bot.modelos_avancados = []
                self.bot.modelos_padrao = [m.get("name", "") for m in self.loaded_models.get("padrao", [])]
                self.bot.modelos_disponiveis = self.bot.modelos_padrao
                if self.bot.modelos_disponiveis and getattr(self.bot, "modelo_atual", None) not in self.bot.modelos_disponiveis:
                    self.bot.modelo_atual = self.bot.modelos_disponiveis[0]
            self._toast("Modelos salvos")
        except Exception as exc:
            self._toast(f"Erro ao salvar modelos: {exc}")

    def _build_models_page(self):
        page, layout = self._scroll_page("Modelos", [("Salvar", self._save_models_config, "primary"), ("Testar", self._test_models, "")])
        self.model_active_label = QLabel()
        self.model_active_label.setObjectName("sectionTitle")
        layout.addWidget(self.model_active_label)
        self.model_test_label = QLabel("Clique em Testar para verificar os modelos configurados.")
        self.model_test_label.setObjectName("muted")
        self.model_test_label.setWordWrap(True)
        layout.addWidget(self.model_test_label)

        add_card, add = self._card()
        title = QLabel("Adicionar ao fallback padrao")
        title.setObjectName("sectionTitle")
        add.addWidget(title)
        row1 = QHBoxLayout()
        self.model_name = QLineEdit()
        self.model_name.setPlaceholderText("nome do modelo")
        self.model_tags = QLineEdit()
        self.model_tags.setPlaceholderText("tags separadas por virgula")
        row1.addWidget(self.model_name, 2)
        row1.addWidget(self.model_tags, 1)
        add.addLayout(row1)
        row2 = QHBoxLayout()
        self.model_desc = QLineEdit()
        self.model_desc.setPlaceholderText("descricao")
        add_btn = QPushButton("Adicionar")
        add_btn.setObjectName("pink")
        add_btn.clicked.connect(self._add_model)
        row2.addWidget(self.model_desc, 1)
        row2.addWidget(add_btn)
        add.addLayout(row2)
        layout.addWidget(add_card)

        self.models_container = QVBoxLayout()
        self.models_container.setSpacing(8)
        layout.addLayout(self.models_container)
        layout.addStretch(1)
        self._refresh_models_ui()
        return page

    def _refresh_models_ui(self):
        if not hasattr(self, "models_container"):
            return
        self._clear_layout(self.models_container)
        active = getattr(self.bot, "modelo_atual", "N/A")
        self.model_active_label.setText(f"Modelo ativo: {active}")
        models = self.loaded_models.get("padrao", [])
        if not models:
            lbl = QLabel("Nenhum modelo configurado.")
            lbl.setObjectName("muted")
            self.models_container.addWidget(lbl)
            return
        section = QLabel("Fallback padrao")
        section.setObjectName("sectionTitle")
        self.models_container.addWidget(section)
        for idx, model in enumerate(models):
            card, lay = self._card()
            top = QHBoxLayout()
            name = QLabel(model.get("name", "sem_nome"))
            name.setObjectName("sectionTitle" if model.get("name") == active else "muted")
            top.addWidget(name, 1)
            status = self.model_status.get(model.get("name", ""))
            if status:
                st = QLabel(f"{status.get('status')} {status.get('latency', '')} {status.get('error', '')}")
                st.setObjectName("muted")
                top.addWidget(st)
            up = QPushButton("Up")
            up.clicked.connect(lambda checked=False, i=idx: self._move_model(i, -1))
            down = QPushButton("Dn")
            down.clicked.connect(lambda checked=False, i=idx: self._move_model(i, 1))
            rem = QPushButton("Remover")
            rem.setObjectName("danger")
            rem.clicked.connect(lambda checked=False, i=idx: self._remove_model(i))
            top.addWidget(up)
            top.addWidget(down)
            top.addWidget(rem)
            lay.addLayout(top)
            desc = QLabel(model.get("desc", ""))
            desc.setObjectName("muted")
            desc.setWordWrap(True)
            lay.addWidget(desc)
            tags = QLabel(", ".join(model.get("tags", [])))
            tags.setObjectName("dim")
            lay.addWidget(tags)
            self.models_container.addWidget(card)

    def _add_model(self):
        name = self.model_name.text().strip()
        if not name:
            self._toast("Informe o nome do modelo")
            return
        desc = self.model_desc.text().strip() or "Modelo adicionado pela GUI"
        tags = [tag.strip() for tag in self.model_tags.text().split(",") if tag.strip()]
        self.loaded_models.setdefault("padrao", []).append({"name": name, "desc": desc, "tags": tags})
        self.model_name.clear()
        self.model_desc.clear()
        self._save_models_config()
        self._refresh_models_ui()

    def _move_model(self, index: int, direction: int):
        models = self.loaded_models.get("padrao", [])
        target = index + direction
        if 0 <= target < len(models):
            models[index], models[target] = models[target], models[index]
            self._save_models_config()
            self._refresh_models_ui()

    def _remove_model(self, index: int):
        models = self.loaded_models.get("padrao", [])
        if 0 <= index < len(models):
            removed = models.pop(index)
            self._save_models_config()
            self._refresh_models_ui()
            self._toast(f"Modelo removido: {removed.get('name', '')}")

    def _test_models(self):
        self.model_test_label.setText("Testando modelos...")

        def worker():
            try:
                from google import genai as tg
                key = self.bot.api_keys[0] if hasattr(self.bot, "api_keys") and self.bot.api_keys else ""
                if not key:
                    self.response_queue.put(("test", "Nenhuma API key disponivel."))
                    return
                client = tg.Client(api_key=key)
                lines = []
                for model in [m.get("name", "") for m in self.loaded_models.get("padrao", []) if m.get("name")]:
                    try:
                        start = time.time()
                        client.models.generate_content(model=model, contents="Responda apenas OK")
                        elapsed = time.time() - start
                        status = "slow" if elapsed > 5 else "ok"
                        self.response_queue.put(("model_status_update", model, status, f"{elapsed:.1f}s", ""))
                        lines.append(f"OK  {model}  {elapsed:.1f}s")
                    except Exception as exc:
                        msg = str(exc)[:90]
                        self.response_queue.put(("model_status_update", model, "error", "N/A", msg))
                        lines.append(f"ERRO  {model}  {msg}")
                self.response_queue.put(("test", "\n".join(lines)))
            except Exception as exc:
                self.response_queue.put(("test", f"Erro ao testar modelos: {exc}"))

        threading.Thread(target=worker, daemon=True).start()


    # ------------------------------------------------------------------
    # VoiceVox
    # ------------------------------------------------------------------

    def _build_voicevox_page(self):
        page, layout = self._scroll_page("Teste do VoiceVox")
        card, lay = self._card()
        title = QLabel("Gerar voz")
        title.setObjectName("sectionTitle")
        lay.addWidget(title)
        self.voicevox_text = QPlainTextEdit()
        self.voicevox_text.setPlaceholderText("Digite uma frase para a Ayla falar...")
        self.voicevox_text.setPlainText("Oi, Mamãe! Testando minha voz pelo painel novo.")
        self.voicevox_text.setMinimumHeight(120)
        lay.addWidget(self.voicevox_text)
        row = QHBoxLayout()
        row.addWidget(QLabel("Style ID:"))
        self.voicevox_style = QLineEdit("3")
        self.voicevox_style.setMaximumWidth(80)
        row.addWidget(self.voicevox_style)
        gen = QPushButton("Gerar WAV")
        gen.setObjectName("primary")
        gen.clicked.connect(lambda: self._run_voicevox(play=False))
        play = QPushButton("Gerar e tocar")
        play.setObjectName("pink")
        play.clicked.connect(lambda: self._run_voicevox(play=True))
        row.addWidget(gen)
        row.addWidget(play)
        row.addStretch(1)
        lay.addLayout(row)
        self.voicevox_status = QLabel("Pronta para testar.")
        self.voicevox_status.setObjectName("muted")
        self.voicevox_status.setWordWrap(True)
        lay.addWidget(self.voicevox_status)
        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def _run_voicevox(self, play: bool = False):
        text = self.voicevox_text.toPlainText().strip() if hasattr(self, "voicevox_text") else ""
        if not text:
            self._toast("Digite um texto para testar")
            return
        try:
            style_id = int(self.voicevox_style.text().strip() or "3")
        except ValueError:
            style_id = 3
        self.voicevox_status.setText("Gerando audio... o primeiro teste pode demorar um pouquinho.")

        def worker():
            try:
                from voicevox.falar_texto import gerar_audio_voicevox_bytes, portuguese_to_katakana
                katakana = portuguese_to_katakana(text)
                wav_bytes = gerar_audio_voicevox_bytes(text, style_id)
                if not wav_bytes:
                    self.response_queue.put(("voicevox", False, "Falha ao gerar audio.", None, False))
                    return
                VOICEVOX_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
                VOICEVOX_OUTPUT_PATH.write_bytes(wav_bytes)
                if play:
                    try:
                        winsound.PlaySound(str(VOICEVOX_OUTPUT_PATH), winsound.SND_FILENAME | winsound.SND_ASYNC)
                    except Exception as exc:
                        self.response_queue.put(("voicevox", True, f"Audio salvo, mas nao consegui tocar: {exc}", str(VOICEVOX_OUTPUT_PATH), False))
                        return
                self.response_queue.put(("voicevox", True, f"Audio gerado em {VOICEVOX_OUTPUT_PATH}\nKatakana: {katakana}", str(VOICEVOX_OUTPUT_PATH), play))
            except Exception as exc:
                self.response_queue.put(("voicevox", False, f"Erro no VoiceVox: {exc}", None, False))

        threading.Thread(target=worker, daemon=True).start()

    def _build_fish_audio_page(self):
        page, layout = self._scroll_page("Teste do Fish Audio")
        card, lay = self._card()
        title = QLabel("Gerar voz via Fish Audio")
        title.setObjectName("sectionTitle")
        lay.addWidget(title)
        
        self.fish_info_label = QLabel("Carregando configurações...")
        self.fish_info_label.setObjectName("muted")
        lay.addWidget(self.fish_info_label)
        
        self.fish_audio_text = QPlainTextEdit()
        self.fish_audio_text.setPlaceholderText("Digite uma frase para a Ayla falar via Fish Audio...")
        self.fish_audio_text.setPlainText("Oi, Mamãe! Testando minha voz nova pelo Fish Audio. O que achou?")
        self.fish_audio_text.setMinimumHeight(120)
        lay.addWidget(self.fish_audio_text)
        
        row = QHBoxLayout()
        gen = QPushButton("Gerar WAV")
        gen.setObjectName("primary")
        gen.clicked.connect(lambda: self._run_fish_audio(play=False))
        play = QPushButton("Gerar e tocar")
        play.setObjectName("pink")
        play.clicked.connect(lambda: self._run_fish_audio(play=True))
        row.addWidget(gen)
        row.addWidget(play)
        row.addStretch(1)
        lay.addLayout(row)
        
        self.fish_audio_status = QLabel("Pronta para testar.")
        self.fish_audio_status.setObjectName("muted")
        self.fish_audio_status.setWordWrap(True)
        lay.addWidget(self.fish_audio_status)
        
        layout.addWidget(card)
        layout.addStretch(1)
        return page


    def _refresh_fish_audio_ui(self):
        if not hasattr(self, "fish_info_label"):
            return
        settings = self._load_settings()
        
        from dotenv import load_dotenv
        load_dotenv(ENV_PATH, override=True)
        
        fish_key = settings.get("fish_audio_api_key", "").strip() or os.getenv("FISH_AUDIO_API_KEY", "").strip()
        voice_id = settings.get("fish_audio_voice_id", "").strip() or os.getenv("FISH_AUDIO_VOICE_ID", "").strip()
        
        key_status = "Configurada" if fish_key else "Não configurada (insira no ENV ou na aba TTS)"
        voice_status = voice_id if voice_id else "Padrão (sem reference_id)"
        
        self.fish_info_label.setText(
            f"Chave API: {key_status}\n"
            f"ID da Voz: {voice_status}\n"
            f"Modelo: s2.1-pro-free"
        )

    def _run_fish_audio(self, play: bool = False):
        text = self.fish_audio_text.toPlainText().strip() if hasattr(self, "fish_audio_text") else ""
        if not text:
            self._toast("Digite um texto para testar")
            return
            
        settings = self._load_settings()
        
        from dotenv import load_dotenv
        load_dotenv(ENV_PATH, override=True)
        
        fish_key = settings.get("fish_audio_api_key", "").strip() or os.getenv("FISH_AUDIO_API_KEY", "").strip()
        voice_id = settings.get("fish_audio_voice_id", "").strip() or os.getenv("FISH_AUDIO_VOICE_ID", "").strip()
        
        if not fish_key:
            self.fish_audio_status.setText("Erro: API Key do Fish Audio não configurada.")
            return
            
        self.fish_audio_status.setText("Gerando áudio via Fish Audio API...")
        
        def worker():
            try:
                import requests
                url = "https://api.fish.audio/v1/tts"
                headers = {
                    "Authorization": f"Bearer {fish_key}",
                    "Content-Type": "application/json",
                    "model": "s2.1-pro-free"
                }
                payload = {
                    "text": text,
                    "format": "wav",
                    "model": "s2.1-pro-free"
                }
                if voice_id:
                    payload["reference_id"] = voice_id
                    
                print(f"[Fish Audio Test] Enviando requisição para gerar TTS...")
                response = requests.post(url, headers=headers, json=payload, timeout=25)
                if response.status_code == 200:
                    wav_bytes = response.content
                    import time
                    timestamp = int(time.time())
                    output_path = VOICEVOX_OUTPUT_PATH.parent / f"saida_fish_audio_teste_{timestamp}.wav"
                    
                    # Clean up old test files first (ignore if locked)
                    try:
                        for old_file in output_path.parent.glob("saida_fish_audio_teste_*.wav"):
                            try:
                                old_file.unlink()
                            except Exception:
                                pass
                    except Exception:
                        pass
                        
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_bytes(wav_bytes)
                    
                    if play:
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
                            
                        try:
                            if not pygame.mixer.get_init():
                                pygame.mixer.init()
                            pygame.mixer.music.load(str(output_path))
                            pygame.mixer.music.play()
                        except Exception as py_err:
                            try:
                                import winsound
                                winsound.PlaySound(str(output_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
                            except Exception as win_err:
                                self.response_queue.put(("fish_audio_result", True, f"Áudio gerado em {output_path.name}, mas falhou ao tocar.", play))
                                return
                    self.response_queue.put(("fish_audio_result", True, f"Áudio gerado com sucesso via Fish Audio!\nSalvo em: {output_path}", play))
                else:
                    self.response_queue.put(("fish_audio_result", False, f"Erro da API (Status {response.status_code}): {response.text}", play))
            except Exception as exc:
                self.response_queue.put(("fish_audio_result", False, f"Exceção na chamada da API: {exc}", play))
                
        threading.Thread(target=worker, daemon=True).start()



    # ------------------------------------------------------------------
    # Whitelist e perfis do Discord
    # ------------------------------------------------------------------




    # ------------------------------------------------------------------
    # Galeria e videos
    # ------------------------------------------------------------------

    def _build_gallery_page(self):
        page, layout = self._page("Galeria de Fotos", [("Atualizar", self._refresh_gallery, "primary")])
        body = QHBoxLayout()
        body.setContentsMargins(16, 16, 16, 16)
        body.setSpacing(12)
        layout.addLayout(body, 1)
        self.gallery_scroll = QScrollArea()
        self.gallery_scroll.setWidgetResizable(True)
        self.gallery_content = QWidget()
        self.gallery_grid = QGridLayout(self.gallery_content)
        self.gallery_grid.setContentsMargins(0, 0, 0, 0)
        self.gallery_grid.setSpacing(10)
        self.gallery_scroll.setWidget(self.gallery_content)
        body.addWidget(self.gallery_scroll, 3)
        self.gallery_details = QFrame()
        self.gallery_details.setObjectName("card")
        self.gallery_details_layout = QVBoxLayout(self.gallery_details)
        self.gallery_details_layout.setContentsMargins(14, 14, 14, 14)
        body.addWidget(self.gallery_details, 2)
        return page

    def _build_videos_page(self):
        page, layout = self._page("Galeria de Videos", [("Atualizar", self._refresh_videos, "primary")])
        body = QHBoxLayout()
        body.setContentsMargins(16, 16, 16, 16)
        body.setSpacing(12)
        layout.addLayout(body, 1)
        self.video_scroll = QScrollArea()
        self.video_scroll.setWidgetResizable(True)
        self.video_content = QWidget()
        self.video_grid = QGridLayout(self.video_content)
        self.video_grid.setContentsMargins(0, 0, 0, 0)
        self.video_grid.setSpacing(10)
        self.video_scroll.setWidget(self.video_content)
        body.addWidget(self.video_scroll, 3)
        self.video_details = QFrame()
        self.video_details.setObjectName("card")
        self.video_details_layout = QVBoxLayout(self.video_details)
        self.video_details_layout.setContentsMargins(14, 14, 14, 14)
        body.addWidget(self.video_details, 2)
        return page

    def _refresh_gallery(self):
        if not hasattr(self, "gallery_grid"):
            return
        images: list[Path] = []
        for folder in PHOTO_DIRS:
            if folder.exists():
                images.extend(path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTS)
        self.gallery_items = sorted(set(images), key=lambda p: p.stat().st_mtime, reverse=True)
        self._populate_media_grid(self.gallery_grid, self.gallery_items, self._select_image, images=True)
        self._draw_image_details()

    def _refresh_videos(self):
        if not hasattr(self, "video_grid"):
            return
        VIDEO_DIR.mkdir(parents=True, exist_ok=True)
        self.video_items = sorted(
            [path for path in VIDEO_DIR.iterdir() if path.is_file() and path.suffix.lower() in VIDEO_EXTS],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        self._populate_media_grid(self.video_grid, self.video_items, self._select_video, images=False)
        self._draw_video_details()

    def _populate_media_grid(self, grid: QGridLayout, items: list[Path], callback, images: bool):
        self._clear_layout(grid)
        cols = 3 if images else 2
        if not items:
            lbl = QLabel("Nada por aqui ainda.")
            lbl.setObjectName("muted")
            grid.addWidget(lbl, 0, 0)
            return
        for idx, path in enumerate(items):
            btn = ClickableImage(path, callback)
            btn.setMinimumSize(QSize(150 if images else 220, 178 if images else 154))
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            pix = self._pixmap_for(path, QSize(126, 126) if images else QSize(190, 106), video=not images)
            icon = QIcon(pix)
            btn.setIcon(icon)
            btn.setIconSize(QSize(126, 126) if images else QSize(190, 106))
            btn.setText("\n" + self._short_name(path.name, 28))
            btn.setToolTip(str(path))
            grid.addWidget(btn, idx // cols, idx % cols)

    def _select_image(self, path: Path):
        self.selected_image = path
        self._draw_image_details()

    def _select_video(self, path: Path):
        self.selected_video = path
        self._draw_video_details()

    def _draw_image_details(self):
        if not hasattr(self, "gallery_details_layout"):
            return
        self._clear_layout(self.gallery_details_layout)
        title = QLabel("Detalhes")
        title.setObjectName("sectionTitle")
        self.gallery_details_layout.addWidget(title)
        if not self.selected_image or not self.selected_image.exists():
            lbl = QLabel("Selecione uma imagem para ver detalhes.")
            lbl.setObjectName("muted")
            lbl.setWordWrap(True)
            self.gallery_details_layout.addWidget(lbl)
            self.gallery_details_layout.addStretch(1)
            return
        path = self.selected_image
        preview = QLabel()
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setPixmap(self._pixmap_for(path, QSize(300, 300), video=False))
        self.gallery_details_layout.addWidget(preview)
        self.gallery_details_layout.addWidget(self._info_label(path))
        wall = QPushButton("Definir wallpaper")
        wall.setObjectName("primary")
        wall.clicked.connect(self._set_wallpaper)
        open_btn = QPushButton("Abrir no Explorer")
        open_btn.clicked.connect(lambda: self._open_in_explorer(path))
        delete_btn = QPushButton("Excluir foto")
        delete_btn.setObjectName("danger")
        delete_btn.clicked.connect(self._delete_selected_image)
        self.gallery_details_layout.addStretch(1)
        self.gallery_details_layout.addWidget(wall)
        self.gallery_details_layout.addWidget(open_btn)
        self.gallery_details_layout.addWidget(delete_btn)

    def _draw_video_details(self):
        if not hasattr(self, "video_details_layout"):
            return
        self._clear_layout(self.video_details_layout)
        title = QLabel("Detalhes")
        title.setObjectName("sectionTitle")
        self.video_details_layout.addWidget(title)
        if not self.selected_video or not self.selected_video.exists():
            lbl = QLabel("Selecione um video para ver detalhes.")
            lbl.setObjectName("muted")
            lbl.setWordWrap(True)
            self.video_details_layout.addWidget(lbl)
            self.video_details_layout.addStretch(1)
            return
        path = self.selected_video
        preview = QLabel()
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setPixmap(self._pixmap_for(path, QSize(320, 180), video=True))
        self.video_details_layout.addWidget(preview)
        self.video_details_layout.addWidget(self._info_label(path))
        play = QPushButton("Reproduzir")
        play.setObjectName("primary")
        play.clicked.connect(lambda: os.startfile(str(path)))
        open_btn = QPushButton("Abrir no Explorer")
        open_btn.clicked.connect(lambda: self._open_in_explorer(path))
        delete_btn = QPushButton("Excluir video")
        delete_btn.setObjectName("danger")
        delete_btn.clicked.connect(self._delete_selected_video)
        self.video_details_layout.addStretch(1)
        self.video_details_layout.addWidget(play)
        self.video_details_layout.addWidget(open_btn)
        self.video_details_layout.addWidget(delete_btn)

    def _pixmap_for(self, path: Path, size: QSize, video: bool = False):
        pix = QPixmap()
        if video:
            pix = self._video_pixmap(path)
        else:
            pix.load(str(path))
        if pix.isNull():
            pix = QPixmap(size)
            pix.fill(QColor("#252744"))
        return pix.scaled(size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)

    def _video_pixmap(self, path: Path):
        if cv2 is None:
            return QPixmap()
        try:
            cap = cv2.VideoCapture(str(path))
            ok, frame = cap.read()
            cap.release()
            if not ok:
                return QPixmap()
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = frame.shape
            image = QImage(frame.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
            return QPixmap.fromImage(image)
        except Exception:
            return QPixmap()

    def _info_label(self, path: Path):
        stat = path.stat()
        label = QLabel(
            f"Nome: {path.name}\n"
            f"Tamanho: {self._format_size(stat.st_size)}\n"
            f"Data: {datetime.fromtimestamp(stat.st_mtime).strftime('%d/%m/%Y %H:%M')}"
        )
        label.setObjectName("muted")
        label.setWordWrap(True)
        return label

    def _set_wallpaper(self):
        if not self.selected_image:
            return
        try:
            result = ctypes.windll.user32.SystemParametersInfoW(20, 0, str(self.selected_image), 3)
            self._toast("Wallpaper alterado" if result else "Nao consegui alterar o wallpaper")
        except Exception as exc:
            self._toast(f"Erro: {exc}")

    def _open_in_explorer(self, path: Path):
        try:
            os.system(f'explorer /select,"{path}"')
        except Exception as exc:
            self._toast(f"Erro ao abrir Explorer: {exc}")

    def _delete_selected_image(self):
        if not self.selected_image:
            return
        path = self.selected_image
        if QMessageBox.question(self, "Excluir foto", f"Excluir {path.name}?") == QMessageBox.StandardButton.Yes:
            path.unlink(missing_ok=True)
            self.selected_image = None
            self._refresh_gallery()

    def _delete_selected_video(self):
        if not self.selected_video:
            return
        path = self.selected_video
        if QMessageBox.question(self, "Excluir video", f"Excluir {path.name}?") == QMessageBox.StandardButton.Yes:
            path.unlink(missing_ok=True)
            self.selected_video = None
            self._refresh_videos()

    # ------------------------------------------------------------------
    # Memoria
    # ------------------------------------------------------------------

    def _build_memory_page(self):
        page, layout = self._scroll_page("Memoria da Ayla")
        form, fl = self._card()
        title = QLabel("Buscar e adicionar")
        title.setObjectName("sectionTitle")
        fl.addWidget(title)
        row1 = QHBoxLayout()
        self.mem_search = QLineEdit()
        self.mem_search.setPlaceholderText("buscar")
        self.mem_search.textChanged.connect(self._refresh_memory)
        self.mem_key = QLineEdit()
        self.mem_key.setPlaceholderText("chave")
        self.mem_tag = QLineEdit("Gerais")
        self.mem_tag.setPlaceholderText("tag")
        row1.addWidget(self.mem_search, 1)
        row1.addWidget(self.mem_key, 1)
        row1.addWidget(self.mem_tag)
        fl.addLayout(row1)
        row2 = QHBoxLayout()
        self.mem_value = QLineEdit()
        self.mem_value.setPlaceholderText("valor")
        add_btn = QPushButton("Salvar")
        add_btn.setObjectName("pink")
        add_btn.clicked.connect(self._add_memory)
        row2.addWidget(self.mem_value, 1)
        row2.addWidget(add_btn)
        fl.addLayout(row2)
        layout.addWidget(form)
        self.memory_container = QVBoxLayout()
        self.memory_container.setSpacing(8)
        layout.addLayout(self.memory_container)
        layout.addStretch(1)
        self._refresh_memory()
        return page

    def _load_mem(self):
        data = self._safe_load_json(MEMORIA_PATH, {})
        return data if isinstance(data, dict) else {}

    def _save_mem(self, data):
        self._safe_write_json(MEMORIA_PATH, data)
        try:
            if self.bot and hasattr(self.bot, "atualizar_prompt_memoria"):
                self.bot.atualizar_prompt_memoria()
        except Exception as exc:
            print(f"Erro ao atualizar memoria do bot: {exc}")

    def _add_memory(self):
        key = self.mem_key.text().strip()
        value = self.mem_value.text().strip()
        tag = self.mem_tag.text().strip() or "Gerais"
        if not key or not value:
            self._toast("Preencha chave e valor")
            return
        lock = getattr(self.bot, "memoria_lock", None)
        with lock if lock is not None else nullcontext():
            mem = self._load_mem()
            mem[key] = {"Data e hora": datetime.now().strftime("%d/%m/%Y %H:%M:%S"), "Valor": value, "tag": tag}
            self._save_mem(mem)
        self.mem_key.clear()
        self.mem_value.clear()
        self._refresh_memory()
        self._toast("Memoria salva")

    def _refresh_memory(self):
        if not hasattr(self, "memory_container"):
            return
        self._clear_layout(self.memory_container)
        query = self.mem_search.text().strip().lower() if hasattr(self, "mem_search") else ""
        shown = 0
        for key, value in self._load_mem().items():
            text, tag, date = self._memory_parts(value)
            if query and query not in key.lower() and query not in text.lower() and query not in tag.lower():
                continue
            card, lay = self._card()
            top = QHBoxLayout()
            title = QLabel(key)
            title.setObjectName("sectionTitle")
            top.addWidget(title, 1)
            tag_lbl = QLabel(tag)
            tag_lbl.setObjectName("muted")
            top.addWidget(tag_lbl)
            delete = QPushButton("Excluir")
            delete.setObjectName("danger")
            delete.clicked.connect(lambda checked=False, k=key: self._delete_memory(k))
            top.addWidget(delete)
            lay.addLayout(top)
            body = QLabel(text)
            body.setWordWrap(True)
            lay.addWidget(body)
            dt = QLabel(date)
            dt.setObjectName("dim")
            lay.addWidget(dt)
            self.memory_container.addWidget(card)
            shown += 1
        if shown == 0:
            lbl = QLabel("Nenhuma memoria encontrada.")
            lbl.setObjectName("muted")
            self.memory_container.addWidget(lbl)

    def _memory_parts(self, value):
        if isinstance(value, dict):
            acessos = value.get("acessos", 0)
            data_hora = value.get("Data e hora", value.get("data_hora", ""))
            data_com_acessos = f"{data_hora} | Acessos: {acessos}" if data_hora else f"Acessos: {acessos}"
            return (
                str(value.get("Valor", value.get("valor", ""))),
                str(value.get("tag", value.get("Tag", "Gerais"))),
                data_com_acessos,
            )
        return str(value), "Gerais", ""

    def _delete_memory(self, key: str):
        lock = getattr(self.bot, "memoria_lock", None)
        removida = False
        with lock if lock is not None else nullcontext():
            mem = self._load_mem()
            if key in mem:
                mem.pop(key)
                self._save_mem(mem)
                removida = True
        if removida:
            self._refresh_memory()
            self._toast("Memoria removida")




    # ------------------------------------------------------------------
    # Status e console
    # ------------------------------------------------------------------

    def _build_status_page(self):
        page, layout = self._scroll_page("Status")
        grid = QGridLayout()
        grid.setSpacing(10)
        layout.addLayout(grid)
        labels = ["Discord", "Modelo", "Chave API", "APIs", "Memorias", "Contexto", "Iniciar Windows", "Tempo de Resposta"]
        for idx, name in enumerate(labels):
            card, lay = self._card()
            title = QLabel(name)
            title.setObjectName("muted")
            value = QLabel("-")
            value.setObjectName("sectionTitle")
            lay.addWidget(title)
            lay.addWidget(value)
            self.status_labels[name] = value
            grid.addWidget(card, idx // 2, idx % 2)
            
        row_buttons = QHBoxLayout()
        startup = QPushButton("Alternar inicializacao com Windows")
        startup.clicked.connect(self._toggle_startup)
        row_buttons.addWidget(startup, 1)
        
        latency_btn = QPushButton("Testar Latência da Chave")
        latency_btn.clicked.connect(self._test_active_key_latency)
        row_buttons.addWidget(latency_btn, 1)
        layout.addLayout(row_buttons)
        
        layout.addWidget(QLabel("Terminal de Status (Logs):"))
        self.status_console_box = QPlainTextEdit()
        self.status_console_box.setReadOnly(True)
        self.status_console_box.setStyleSheet("""
            QPlainTextEdit {
                background-color: #0c0c0c;
                color: #ffffff;
                font-family: 'Cascadia Mono', 'Consolas', 'Lucida Console', monospace;
                font-size: 11px;
                border: 1.5px solid #2d304e;
                border-radius: 6px;
                padding: 5px;
            }
        """)
        self.status_console_box.setMinimumHeight(180)
        self.status_console_box.setPlaceholderText("Nenhum log registrado ainda...")
        layout.addWidget(self.status_console_box)
        return page

    def _test_active_key_latency(self):
        if "Tempo de Resposta" in self.status_labels:
            self.status_labels["Tempo de Resposta"].setText("Medindo...")
        
        def worker():
            try:
                from google import genai as tg
                key = ""
                if hasattr(self.bot, "api_keys") and self.bot.api_keys:
                    idx = getattr(self.bot, "idx_api_atual", 0)
                    if 0 <= idx < len(self.bot.api_keys):
                        key = self.bot.api_keys[idx]
                if not key:
                    from dotenv import load_dotenv
                    load_dotenv(ENV_PATH, override=True)
                    key = os.getenv("GEMINI_API_KEY_1", "")
                
                if not key:
                    self.response_queue.put(("latency_result", "Sem chave"))
                    return
                    
                client = tg.Client(api_key=key)
                start = time.time()
                client.models.generate_content(
                    model="gemini-2.5-flash-lite",
                    contents="Responda OK"
                )
                elapsed = time.time() - start
                self.response_queue.put(("latency_result", f"{elapsed:.2f}s"))
            except Exception as exc:
                self.response_queue.put(("latency_result", "Erro"))
                print(f"[Latency Test] Erro ao medir latência da chave ativa: {exc}")
                
        threading.Thread(target=worker, daemon=True).start()

    def _build_console_page(self):
        page, layout = self._page("Console", [("Limpar", self._clear_logs, "danger")])
        self.console_box = QPlainTextEdit()
        self.console_box.setReadOnly(True)
        layout.addWidget(self.console_box, 1)
        return page

    def _update_status(self):
        if not self.status_labels:
            return
        try:
            ready = self.bot.is_ready() if hasattr(self.bot, "is_ready") else False
        except Exception:
            ready = False
            
        current_latency = "-"
        if "Tempo de Resposta" in self.status_labels:
            current_latency = self.status_labels["Tempo de Resposta"].text()
            if current_latency == "-":
                current_latency = "Clique em Testar"
                
        values = {
            "Discord": "Online" if ready else "Conectando",
            "Modelo": str(getattr(self.bot, "modelo_atual", "N/A")),
            "Chave API": str(getattr(self.bot, "idx_api_atual", 0) + 1),
            "APIs": str(len(getattr(self.bot, "api_keys", []))),
            "Memorias": str(len(self._load_mem())),
            "Contexto": f"{self._get_context_tokens():,} tokens",
            "Iniciar Windows": "Ativado" if self._is_startup_enabled() else "Desativado",
            "Tempo de Resposta": current_latency,
        }
        for key, value in values.items():
            self.status_labels[key].setText(value)
        if hasattr(self, "model_active_label"):
            self.model_active_label.setText(f"Modelo ativo: {getattr(self.bot, 'modelo_atual', 'N/A')}")

    def _get_context_tokens(self):
        try:
            session = getattr(self.bot, "chat_session", None)
            if not session:
                return 0
            total_chars = 0
            for content in session.get_history():
                for part in getattr(content, "parts", []) or []:
                    texto = getattr(part, "text", None)
                    if texto:
                        total_chars += len(texto)
                    inline_data = getattr(part, "inline_data", None)
                    dados = getattr(inline_data, "data", None) if inline_data else None
                    if dados:
                        total_chars += min(len(dados), 100_000)
            return int(total_chars / 4.5)
        except Exception:
            return 0

    def _poll_queues(self):
        try:
            while True:
                item = self.response_queue.get_nowait()
                kind = item[0]
                if kind == "test":
                    self.model_test_label.setText(item[1])
                elif kind == "model_status_update":
                    self.model_status[item[1]] = {"status": item[2], "latency": item[3], "error": item[4]}
                    self._refresh_models_ui()
                elif kind == "latency_result":
                    if hasattr(self, "status_labels") and "Tempo de Resposta" in self.status_labels:
                        self.status_labels["Tempo de Resposta"].setText(item[1])
                elif kind == "voicevox":
                    if hasattr(self, "voicevox_status"):
                        self.voicevox_status.setText(item[2])
                    self._toast("VoiceVox pronto" if item[1] else "VoiceVox falhou")
                elif kind == "fish_audio_result":
                    success = item[1]
                    msg = item[2]
                    if hasattr(self, "fish_audio_status"):
                        self.fish_audio_status.setText(msg)
                    self._toast("Fish Audio pronto" if success else "Fish Audio falhou")
                elif kind == "voice_chat_text":
                    text = item[1]
                    if self.floating_mic:
                        self.floating_mic.handle_text_ready(text)
                elif kind == "voice_chat_text_silent_restart":
                    if self.floating_mic:
                        self.floating_mic.handle_silent_restart()
                elif kind == "voice_chat_audio":
                    audio_path = item[1]
                    if self.floating_mic:
                        self.floating_mic.handle_audio_ready(audio_path)
                elif kind == "voice_chat_user_speaking":
                    if self.floating_mic:
                        self.floating_mic.update_sprite_image("falandousuario")
                elif kind == "voice_chat_speech_finished":
                    if self.floating_mic:
                        self.floating_mic.on_speech_finished()
        except queue.Empty:
            pass
        chunk = ""
        try:
            while True:
                chunk += self.console_queue.get_nowait()
        except queue.Empty:
            pass
        if chunk:
            if hasattr(self, "console_box") and self.console_box:
                self.console_box.moveCursor(QTextCursor.MoveOperation.End)
                self.console_box.insertPlainText(chunk)
                self.console_box.moveCursor(QTextCursor.MoveOperation.End)
            if hasattr(self, "status_console_box") and self.status_console_box:
                self.status_console_box.moveCursor(QTextCursor.MoveOperation.End)
                self.status_console_box.insertPlainText(chunk)
                self.status_console_box.moveCursor(QTextCursor.MoveOperation.End)

    def _clear_logs(self):
        if hasattr(self, "console_box") and self.console_box:
            self.console_box.clear()
        if hasattr(self, "status_console_box") and self.status_console_box:
            self.status_console_box.clear()

    def _is_startup_enabled(self):
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
            winreg.QueryValueEx(key, "AylaGUI")
            winreg.CloseKey(key)
            return True
        except Exception:
            return False

    def _toggle_startup(self):
        try:
            import winreg
            reg_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_WRITE)
            if self._is_startup_enabled():
                try:
                    winreg.DeleteValue(key, "AylaGUI")
                except FileNotFoundError:
                    pass
                self._toast("Inicializacao desativada")
            else:
                cmd = f'"{BASE_DIR / "ayla.bat"}"'
                winreg.SetValueEx(key, "AylaGUI", 0, winreg.REG_SZ, cmd)
                self._toast("Inicializacao ativada")
            winreg.CloseKey(key)
            self._update_status()
        except Exception as exc:
            self._toast(f"Erro no registro: {exc}")

    def _format_size(self, size: int):
        value = float(size)
        for unit in ("B", "KB", "MB", "GB"):
            if value < 1024 or unit == "GB":
                return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
            value /= 1024
        return f"{value:.1f} GB"

    def _short_name(self, text: str, limit: int):
        return text if len(text) <= limit else text[: max(1, limit - 3)] + "..."

    def _restore_streams(self):
        try:
            sys.stdout = self.stdout_redirector.original_stream
            sys.stderr = self.stderr_redirector.original_stream
        except Exception:
            pass

    def reload_gui(self):
        app = QApplication.instance()
        if app:
            app.setQuitOnLastWindowClosed(False)
            
        self.poll_timer.stop()
        self.status_timer.stop()
        
        if self.floating_mic:
            try:
                self.floating_mic.close()
            except Exception:
                pass
            self.floating_mic = None
            
        if self.sprite_window:
            try:
                self.sprite_window.close()
            except Exception:
                pass
            self.sprite_window = None
            
        self._restore_streams()
        self.unregister_native_hotkey()
        if keyboard is not None:
            if getattr(self, "hotkey_hook_callback", None) is not None:
                try:
                    keyboard.unhook(self.hotkey_hook_callback)
                except Exception:
                    pass
                self.hotkey_hook_callback = None
            try:
                keyboard.clear_all_hotkeys()
            except Exception:
                pass
                
        self.close()
        
        # Recarrega o módulo em si para que novas alterações de código no arquivo sejam aplicadas
        import importlib
        import sys
        if 'ayla_gui' in sys.modules:
            try:
                importlib.reload(sys.modules['ayla_gui'])
            except Exception as e:
                print(f"[GUI Reload] Erro ao recarregar o modulo: {e}")
                
        from ayla_gui import AylaGUI
        new_gui = AylaGUI(self.bot)
        new_gui.show()
        
        if app:
            app.setQuitOnLastWindowClosed(True)

    def register_native_hotkey(self, hotkey_str):
        self.unregister_native_hotkey()
        self.native_hotkey_registered = False
        mods, vk = parse_hotkey_to_win32(hotkey_str)
        if vk is not None:
            try:
                import ctypes
                user32 = ctypes.windll.user32
                res = user32.RegisterHotKey(int(self.winId()), 9001, mods, vk)
                if res != 0:
                    self.native_hotkey_registered = True
                    print(f"[Native Hotkey] Atalho Win32 nativo '{hotkey_str}' registrado com sucesso.")
            except Exception as e:
                print(f"[Native Hotkey] Erro ao registrar RegisterHotKey: {e}")

    def unregister_native_hotkey(self):
        if getattr(self, 'native_hotkey_registered', False):
            try:
                import ctypes
                user32 = ctypes.windll.user32
                user32.UnregisterHotKey(int(self.winId()), 9001)
            except Exception:
                pass
            self.native_hotkey_registered = False

    def nativeEvent(self, eventType, message):
        if eventType == b'windows_generic_MSG' and getattr(self, 'native_hotkey_registered', False):
            try:
                from ctypes import wintypes
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == 0x0312 and msg.wParam == 9001:
                    self.hotkey_emitter_live.triggered.emit()
                    return True, 0
            except Exception:
                pass
        return super().nativeEvent(eventType, message)

    def closeEvent(self, event):
        self._restore_streams()
        self.unregister_native_hotkey()
        if keyboard is not None:
            if getattr(self, "hotkey_hook_callback", None) is not None:
                try:
                    keyboard.unhook(self.hotkey_hook_callback)
                except Exception:
                    pass
                self.hotkey_hook_callback = None
            try:
                keyboard.clear_all_hotkeys()
            except Exception:
                pass
        if self.floating_mic:
            try:
                self.floating_mic.close()
            except Exception:
                pass
        event.accept()


def abrir_gui(bot_instance):
    """Abre a interface grafica da Ayla em Qt/PySide6."""
    app = QApplication.instance()
    owns_app = app is None
    if app is None:
        app = QApplication(sys.argv)
    app.setApplicationName("Ayla")
    gui = AylaGUI(bot_instance)
    gui.show()
    code = app.exec() if owns_app else 0
    os._exit(code)


if __name__ == "__main__":
    print("Esta GUI deve ser iniciada pelo Ayla.py, que passa a instancia do bot.")
    sys.exit(1)
