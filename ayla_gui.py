#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Interface grafica da Ayla em PySide6/Qt."""

from __future__ import annotations
from ayla_platform import IS_WINDOWS, open_path, set_wallpaper, startup_path, set_startup, play_wav_fallback, stop_wav_fallback

import asyncio
import ctypes
import hashlib
import importlib.util
import json
import os
import queue
import shutil
import sys
import threading
import time
#import winsound
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path

try:
    from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, QSize, Signal
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
        QSpinBox,
        QStackedWidget,
        QTabWidget,
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

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
MEMORIA_PATH = BASE_DIR / "Ayla_Memoria.json"
MODELS_PATH = BASE_DIR / "ayla_models.json"
SETTINGS_PATH = BASE_DIR / "ayla_settings.json"
TTS_OUTPUT_DIR = BASE_DIR / "audio_output"
ICON_PATH = BASE_DIR / "ico.png"
ICON_ICO_PATH = BASE_DIR / "ico.ico"
PHOTO_DIRS = [BASE_DIR / "Aylafotitos"]
VIDEO_DIR = BASE_DIR / "VideosBaixados"
MODOS_DIR = BASE_DIR / "MODOS"
BUFFER_VIDEO_DIR = BASE_DIR / "Buffer de video"
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
VIDEO_EXTS = (".mp4", ".mkv", ".avi", ".mov", ".webm")
SENSITIVE_WORDS = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "SENHA")


PAGES = [
    ("status", "Status"),
    ("voice_chat", "Conversa por Voz"),
    ("media_manager", "Emojis & GIFs"),
    ("tts", "TTS"),
    ("config", "ENV"),
    ("models", "Modelos"),
    ("fish_audio", "Fish Audio"),
    ("gallery", "Galeria"),
    ("videos", "Videos"),
    ("memory", "Memoria"),
    ("auto_memory", "Memórias Automáticas"),
    ("memory_test", "Teste de memórias"),
    ("forgetting", "Esquecimento natural"),
    ("console", "Console"),
]


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


class AylaGUI(QMainWindow):
    handoff_finished = Signal(bool, str)
    handoff_progress = Signal(int, str)

    def __init__(self, bot_instance=None):
        if bot_instance is None:
            raise ValueError("A Ayla precisa estar aberta e iniciada para a GUI funcionar.")
        super().__init__()
        self.bot = bot_instance
        self.handoff_finished.connect(self._on_handoff_finished)
        self.handoff_progress.connect(self._on_handoff_progress)
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
        self.zai_balance_refreshing = False
        self.zai_balance_last_refresh = 0.0
        self.deepseek_balance_refreshing = False
        self.deepseek_balance_last_refresh = 0.0
        self._deepseek_balance_identity = None
        self.profile_cache: dict[int, dict] = {}
        self.settings_checks: dict[str, QCheckBox] = {}
        self.copilot_checks: dict[str, QCheckBox] = {}


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

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll_queues)
        self.poll_timer.start(150)

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._update_status)
        self.status_timer.start(1000)
        self._update_status()

        from ayla_hotkeys import EndShortcut
        self.end_shortcut = EndShortcut(self, self._interrupt_voice)

    def _interrupt_voice(self):
        manager = getattr(self.bot, 'voice_manager', None)
        if manager:
            threading.Thread(target=manager.interromper_fala, daemon=True,
                             name='EndVoice').start()
        stop_wav_fallback()


    # ------------------------------------------------------------------
    # Shell
    # ------------------------------------------------------------------

    def _set_windows_app_id(self):
        if not IS_WINDOWS:
            return
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
        self._add_page("tts", self._build_tts_page())
        self._add_page("config", self._build_config_page())
        self._add_page("models", self._build_models_page())
        self._add_page("fish_audio", self._build_fish_audio_page())
        self._add_page("gallery", self._build_gallery_page())
        self._add_page("videos", self._build_videos_page())
        self._add_page("memory", self._build_memory_page())
        self._add_page("auto_memory", self._build_auto_memory_page())
        self._add_page("memory_test", self._build_memory_test_page())
        self._add_page("forgetting", self._build_forgetting_page())
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
        elif key == "tts":
            self._refresh_settings_ui()
        elif key == "config":
            self._reload_env()
        elif key == "fish_audio":
            self._refresh_fish_audio_ui()
        elif key == "gallery":
            self._refresh_gallery()
        elif key == "videos":
            self._refresh_videos()
        elif key == "memory":
            self._refresh_memory()
        elif key == "auto_memory":
            self._refresh_auto_memory()
        elif key == "status":
            self._update_status()
            self._refresh_zai_balance()
            self._refresh_deepseek_balance()

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
            "tts_engine": "fish_audio",
            "fish_audio_api_key": "",
            "fish_audio_voice_id": "",
            "name_trigger": True,
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
                ("Salvar", self._save_voice_chat_settings, "primary")
            ]
        )

        # Info Card
        info, info_lay = self._card()
        title = QLabel("Instruções")
        title.setObjectName("sectionTitle")
        info_lay.addWidget(title)
        text = QLabel(
            "Use /entrar_call no Discord e escolha obrigatoriamente Visão biônica: Sim ou Não.\n"
            "Com Sim, a Ayla recebe vídeos de até 1 minuto da tela deste computador junto das falas.\n"
            "Com Não, a conversa usa apenas as vozes da call. Use /sair_call para encerrar."
        )
        text.setObjectName("muted")
        text.setWordWrap(True)
        info_lay.addWidget(text)
        layout.addWidget(info)

        # Card 3: Fala por Texto (TTS - Síntese de Voz)
        tts_card, tts_lay = self._card()
        tts_title = QLabel("Fala por Texto (TTS - Síntese de Voz)")
        tts_title.setObjectName("sectionTitle")
        tts_lay.addWidget(tts_title)

        tts_lay.addWidget(QLabel("Selecionar Motor de Fala por Texto (TTS):"))
        self.tts_combo = QComboBox()
        self.tts_combo.setObjectName("settingsComboBox")
        self.tts_combo.addItem("Fish Audio API (Nuvem - Modelo s2.1-pro-free)", "fish_audio")
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
        self.stt_combo.addItem("Automático (Groq Whisper)", "auto")
        self.stt_combo.addItem("Groq Whisper (Nuvem - Alta velocidade)", "groq_whisper")
        self.stt_combo.addItem("Gemini 3.5 Transcribe Live (Nuvem)", "gemini_live")
        self.stt_combo.addItem("Z.ai GLM-ASR-2512 (Nuvem - Transcrição)", "zai")
        stt_lay.addWidget(self.stt_combo)

        stt_lay.addWidget(QLabel("API Key do Groq (para Whisper) [Opcional]:"))
        self.groq_key_input = QLineEdit()
        self.groq_key_input.setPlaceholderText("Cole sua chave API do Groq aqui (gsk_...)...")
        self.groq_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        stt_lay.addWidget(self.groq_key_input)
        stt_lay.addWidget(QLabel("API Key do Gemini (para Transcribe Live):"))
        self.gemini_key_input = QLineEdit()
        self.gemini_key_input.setPlaceholderText("Chave do Google AI Studio ou GEMINI_API_KEY no .env")
        self.gemini_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        stt_lay.addWidget(self.gemini_key_input)

        stt_note = QLabel("Z.ai usa a chave já configurada para a Ayla e divide áudios longos em blocos de até 30 segundos. Cada motor usa somente o serviço selecionado. Gemini Live usa exclusivamente o modelo Live, em uma sessão por fala, e avisa se houver erro. A transcrição começa após terminar a gravação. O serviço tem limites de sessão e cotas do Google.")
        stt_note.setObjectName("muted")
        stt_note.setWordWrap(True)
        stt_lay.addWidget(stt_note)

        layout.addWidget(stt_card)

        # Conexões para autosave
        self.tts_combo.currentIndexChanged.connect(self._save_voice_chat_settings)
        self.stt_combo.currentIndexChanged.connect(self._save_voice_chat_settings)
        self.groq_key_input.editingFinished.connect(self._save_voice_chat_settings)
        self.gemini_key_input.editingFinished.connect(self._save_voice_chat_settings)

        layout.addStretch(1)
        return page

    def _refresh_voice_chat_ui(self):
        self._refresh_settings_ui()

    def _save_voice_chat_settings(self):
        self._save_settings_from_ui()

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
        etitle = QLabel("🌟 Emojis do Discord (%Nome do Emoji%)")
        etitle.setObjectName("sectionTitle")
        emoji_lay.addWidget(etitle)

        edesc = QLabel(
            "Cadastre o apelido/nome simples que a Ayla usará nas mensagens e a tag bruta oficial do Discord.\n"
            "Exemplo: Nome: Miku bebendo monster | Tag: <:Miku_bebendo_monster:000000000000000000>"
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
        self.emoji_tag_input.setPlaceholderText("Tag Discord (ex: <:ayla_fofa:000000000000000000>)")
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
        if not self.bot or not hasattr(self.bot, "loop") or not self.bot.loop or not self.bot.is_ready():
            QMessageBox.warning(self, "Bot Desconectado", "O Bot da Ayla precisa estar conectado ao Discord para puxar os Emojis de Aplicativo!")
            return

        importados = 0
        existentes = set()
        for r in range(self.emoji_table.rowCount()):
            item = self.emoji_table.item(r, 0)
            if item:
                existentes.add(item.text().strip().lower())

        try:
            future = asyncio.run_coroutine_threadsafe(self.bot.fetch_application_emojis(), self.bot.loop)
            app_emojis = future.result(timeout=10)
        except Exception as e:
            QMessageBox.warning(self, "Erro ao buscar Emojis", f"Não foi possível buscar os Emojis de Aplicativo do Bot: {e}")
            return

        if not app_emojis:
            QMessageBox.information(
                self,
                "Nenhum Emoji de Aplicativo",
                "Não foram encontrados Emojis de Aplicativo (Application Emojis) cadastrados na conta do Bot no Developer Portal do Discord."
            )
            return

        for emoji in app_emojis:
            nome_formatado = emoji.name.replace("_", " ")
            tag_bruta = f"<a:{emoji.name}:{emoji.id}>" if emoji.animated else f"<:{emoji.name}:{emoji.id}>"
            if nome_formatado.lower() not in existentes and emoji.name.lower() not in existentes:
                self._insert_table_row(self.emoji_table, nome_formatado, tag_bruta)
                existentes.add(nome_formatado.lower())
                importados += 1

        if importados > 0:
            QMessageBox.information(self, "Importação Concluída", f"Foram importados {importados} Emojis de Aplicativo do Bot!")
        else:
            QMessageBox.information(self, "Nenhum Emoji Novo", "Todos os Emojis de Aplicativo do Bot já estão cadastrados na lista!")

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

    def _refresh_settings_ui(self):
        data = self._load_settings()
        # Carrega engine TTS
        if hasattr(self, "tts_combo"):
            was_blocked_tts = self.tts_combo.signalsBlocked()
            self.tts_combo.blockSignals(True)
            selected_tts = "fish_audio"
            idx_tts = self.tts_combo.findData(selected_tts)
            if idx_tts >= 0:
                self.tts_combo.setCurrentIndex(idx_tts)
            else:
                self.tts_combo.setCurrentIndex(0)
            self.tts_combo.blockSignals(was_blocked_tts)

        # Carrega campos do TTS (com fallback para .env)
        from dotenv import load_dotenv
        load_dotenv(ENV_PATH, override=True)

        fish_key_env = os.getenv("FISH_AUDIO_API_KEY", "")
        fish_voice_env = os.getenv("FISH_AUDIO_VOICE_ID", "")

        if hasattr(self, "fish_key_input"):
            self.fish_key_input.setText(data.get("fish_audio_api_key") or fish_key_env)
        if hasattr(self, "fish_voice_input"):
            self.fish_voice_input.setText(data.get("fish_audio_voice_id") or fish_voice_env)
        # Carrega engine STT
        if hasattr(self, "stt_combo"):
            was_blocked_stt = self.stt_combo.blockSignals(True)
            selected_stt = data.get("stt_engine", "auto")
            idx_stt = self.stt_combo.findData(selected_stt)
            if idx_stt >= 0:
                self.stt_combo.setCurrentIndex(idx_stt)
            else:
                self.stt_combo.setCurrentIndex(0)

            self.stt_combo.blockSignals(was_blocked_stt)

        groq_key_env = os.getenv("GROQ_API_KEY", "")
        if hasattr(self, "gemini_key_input"):
            self.gemini_key_input.setText(data.get("gemini_api_key") or os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", ""))
        if hasattr(self, "groq_key_input"):
            self.groq_key_input.setText(data.get("groq_api_key") or groq_key_env)

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
        if hasattr(self, "tts_combo"):
            data["tts_engine"] = self.tts_combo.currentData()
        if hasattr(self, "stt_combo"):
            data["stt_engine"] = self.stt_combo.currentData()

        if hasattr(self, "groq_key_input"):
            groq_val = self.groq_key_input.text().strip()
            # Um campo vazio em autosave não deve apagar a credencial salva.
            if groq_val:
                data["groq_api_key"] = groq_val
                self._update_env_var("GROQ_API_KEY", groq_val)

        if hasattr(self, "gemini_key_input"):
            data["gemini_api_key"] = self.gemini_key_input.text().strip()

        if hasattr(self, "fish_key_input"):
            key_val = self.fish_key_input.text().strip()
            data["fish_audio_api_key"] = key_val
            self._update_env_var("FISH_AUDIO_API_KEY", key_val)

        if hasattr(self, "fish_voice_input"):
            voice_val = self.fish_voice_input.text().strip()
            data["fish_audio_voice_id"] = voice_val
            self._update_env_var("FISH_AUDIO_VOICE_ID", voice_val)

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
        text = QLabel("Configure o Fish Audio para as respostas faladas da Ayla.")
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

        layout.addStretch(1)

        # Conexões para salvamento automático
        self.tts_combo.currentIndexChanged.connect(self._save_settings_from_ui)
        self.fish_key_input.editingFinished.connect(self._save_settings_from_ui)
        self.fish_voice_input.editingFinished.connect(self._save_settings_from_ui)

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
        self._env_loaded_text = ""
        if not ENV_PATH.exists():
            lbl = QLabel(".env nao encontrado")
            lbl.setObjectName("muted")
            self.env_container.addWidget(lbl)
            return
        try:
            self._env_loaded_text = ENV_PATH.read_text(encoding="utf-8")
            lines = self._env_loaded_text.splitlines()
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
            current = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""
            if current != getattr(self, "_env_loaded_text", current):
                self._toast("O .env mudou desde a abertura. Recarregue a aba antes de salvar.")
                return
            lines: list[str] = []
            for row in self.env_rows:
                kind = row.get("kind")
                if kind == "entry":
                    lines.append(f"{row['key']}={row['entry'].text().strip()}{row.get('comment', '')}")
                elif kind in ("comment", "raw"):
                    lines.append(row.get("line", ""))
            ENV_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
            self._env_loaded_text = ENV_PATH.read_text(encoding="utf-8")
            self._hot_reload_api_keys()
            self._toast(".env salvo")
        except Exception as exc:
            self._toast(f"Erro ao salvar .env: {exc}")

    def _hot_reload_api_keys(self):
        try:
            from dotenv import load_dotenv
            load_dotenv(ENV_PATH, override=True)
            keys = [os.getenv(f"ZAI_API_KEY_{i}", "") for i in range(1, 7)]
            keys.append(os.getenv("ZAI_API_KEY", ""))
            keys = list(dict.fromkeys([key.strip() for key in keys if key.strip()]))
            if hasattr(self.bot, "api_keys"):
                keys = keys or ['']
                with self.bot.lock:
                    self.bot._api_client_pool.retire()
                    for lease in self.bot._client_leases:
                        lease.close()
                    self.bot._client_leases = []
                    self.bot._pool_clientes = {}
                    self.bot.api_keys = keys
                    self.bot.idx_api_atual = 0
                    self.bot._trocar_cliente_zai(keys[0])
                print("[GUI] APIs Z.ai / Gemini / Groq / DeepSeek recarregadas na memória do bot.")
        except Exception as exc:
            print(f"Erro ao recarregar APIs: {exc}")

    # ------------------------------------------------------------------
    # Modelos
    # ------------------------------------------------------------------

    def _load_models_config(self):
        defaults = {
            "padrao": [
                {"name": "glm-5.3-flash", "desc": "Modelo oficial Z.ai da Ayla", "tags": ["Rápido", "Multimodal"]},
            ]
        }
        data = self._safe_load_json(MODELS_PATH, defaults)
        if not isinstance(data, dict):
            data = defaults
        data.pop("raciocinar", None)
        data.pop("modo", None)
        data.setdefault("padrao", defaults["padrao"])
        self.loaded_models = data

    def _save_models_config(self):
        try:
            from ayla_model_policy import normalize_policy, ordered_models
            raw = dict(self.loaded_models.get("roteamento", {}))
            if hasattr(self, "model_role_combos"):
                raw.update({role: combo.currentText().strip() for role, combo in self.model_role_combos.items()})
                raw.update({key: spin.value() for key, spin in self.model_policy_spins.items()})
            for mode, combo in getattr(self, "model_mode_combos", {}).items():
                raw[mode] = "" if combo.currentText().strip() == "Usar ciclo padrão" else combo.currentText().strip()
            names = [m.get("name", "") for m in self.loaded_models.get("padrao", [])]
            policy = normalize_policy(raw, names)
            self.loaded_models["roteamento"] = policy
            self._safe_write_json(MODELS_PATH, self.loaded_models)
            if self.bot:
                self.bot.modelos_avancados = []
                self.bot.model_policy = dict(policy)
                self.bot.modelos_padrao = ordered_models(names, policy)
                self.bot.modelos_disponiveis = self.bot.modelos_padrao
            if hasattr(self, 'compactor_provider'):
                settings = self._load_settings()
                if hasattr(self, 'groq_output_spin'):
                    settings['groq_max_tokens'] = self.groq_output_spin.value()
                settings['context_compactor_provider'] = self.compactor_provider.currentData()
                settings['context_compactor_model'] = self.compactor_model.currentText().strip()
                self._safe_write_json(SETTINGS_PATH, settings)
                if self.bot:
                    self.bot.ayla_settings = settings
            self._toast("Modelos salvos")
        except Exception as exc:
            self._toast(f"Erro ao salvar modelos: {exc}")

    def _build_models_page(self):
        page, layout = self._scroll_page("Modelos", [("Salvar", self._save_models_config, "primary"), ("Testar", self._test_models, ""), ("Atualizar Gemini", self._refresh_gemini_catalog, ""), ("Atualizar Groq", self._refresh_groq_catalog, ""), ("Atualizar DeepSeek", self._refresh_deepseek_catalog, "")])
        self.model_active_label = QLabel()
        self.model_active_label.setObjectName("sectionTitle")
        layout.addWidget(self.model_active_label)
        self.model_test_label = QLabel("Clique em Testar para verificar os modelos configurados.")
        self.model_test_label.setObjectName("muted")
        self.model_test_label.setWordWrap(True)
        layout.addWidget(self.model_test_label)

        from ayla_model_policy import PRICES, PRICING_SOURCE, PRICING_DATE, normalize_policy
        names = [m.get("name", "") for m in self.loaded_models.get("padrao", [])]
        policy = normalize_policy(self.loaded_models.get("roteamento"), names)
        route_card, route = self._card()
        title = QLabel("Escolha por situação")
        title.setObjectName("sectionTitle")
        route.addWidget(title)
        self.model_role_combos = {}
        labels = {"principal": "Modelo principal", "lento": "Se ficar lento",
                  "erro": "Erro ou indisponibilidade", "quota": "Cota esgotada / limite de uso",
                  "midia": "Mídia não suportada", "conexao": "Falha de conexão"}
        from gemini_catalog import GEMINI_MODELS
        from groq_catalog import GROQ_MODELS, is_groq
        from deepseek_catalog import DEEPSEEK_MODELS, chat_model as deepseek_chat_model
        deepseek_models = [m for m in self.loaded_models.get('catalogo_deepseek', DEEPSEEK_MODELS)
                        if deepseek_chat_model({'id': m})]
        choices = list(dict.fromkeys([*names, *PRICES,
                                      *self.loaded_models.get('catalogo_gemini', GEMINI_MODELS),
                                      *self.loaded_models.get('catalogo_groq', GROQ_MODELS), *deepseek_models]))
        choices = [m for m in choices if m != "glm-ocr"]
        compact_card, compact_layout = self._card()
        compact_layout.addWidget(QLabel("Compactador de contexto"))
        note = QLabel("Ao atingir 8.000 tokens estimados, compacta toda a conversa para até "
                      "4.000 tokens ou menos. Em caso de falha, preserva o histórico. Usa as chaves já configuradas.")
        note.setWordWrap(True)
        compact_layout.addWidget(note)
        self.compactor_provider = QComboBox()
        for label, value in (("GLM (Z.ai)", "glm"), ("Gemini", "gemini"), ("Groq", "groq"), ("DeepSeek", "deepseek")):
            self.compactor_provider.addItem(label, value)
        self.compactor_model = QComboBox()
        self.compactor_model.setEditable(True)
        compact_settings = self._load_settings()
        def update_compactor_models():
            provider = self.compactor_provider.currentData()
            self.compactor_model.clear()
            options = ([m for m in choices if m.startswith('glm-')] if provider == 'glm'
                       else [m for m in choices if m.startswith('gemini-')] if provider == 'gemini'
                       else [m for m in self.loaded_models.get('catalogo_deepseek', DEEPSEEK_MODELS)
                             if deepseek_chat_model({'id': m})] if provider == 'deepseek'
                       else list(self.loaded_models.get('catalogo_groq', GROQ_MODELS)))
            self.compactor_model.addItems(options)
        self.compactor_provider.currentIndexChanged.connect(update_compactor_models)
        self.compactor_provider.setCurrentIndex(max(0, self.compactor_provider.findData(
            compact_settings.get('context_compactor_provider', 'glm'))))
        update_compactor_models()
        if compact_settings.get('context_compactor_model'):
            self.compactor_model.setCurrentText(compact_settings['context_compactor_model'])
        elif self.compactor_provider.currentData() == 'glm':
            self.compactor_model.setCurrentText('glm-5.3-flash')
        compact_layout.addWidget(QLabel("API de compactação"))
        compact_layout.addWidget(self.compactor_provider)
        compact_layout.addWidget(QLabel("Modelo (pode digitar o identificador)"))
        compact_layout.addWidget(self.compactor_model)
        layout.addWidget(compact_card)
        for role, label in labels.items():
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            combo = QComboBox()
            combo.setEditable(True)
            if role != "principal":
                combo.addItem("")
            combo.addItems(choices)
            combo.setCurrentText(policy[role])
            combo.setToolTip("Deixe vazio para seguir a fila de reservas. Também aceita um nome personalizado.")
            row.addWidget(combo, 1)
            route.addLayout(row)
            price = QLabel()
            price.setObjectName("dim")
            price.setWordWrap(True)
            from ayla_model_policy import price_label
            combo.currentTextChanged.connect(lambda name, target=price:
                                             target.setText(price_label(name) if name else 'Usar fila de reservas'))
            price.setText(price_label(combo.currentText()) if combo.currentText() else 'Usar fila de reservas')
            route.addWidget(price)
            self.model_role_combos[role] = combo
        self.model_policy_spins = {}
        for key, label, low, high in (
            ("espera_segundos", "Considerar lento após segundos sem receber dados", 5, 300),
            ("testar_a_cada", "Testar retorno ao principal a cada N mensagens", 1, 100),
            ("rodadas", "Máximo de rodadas se todos falharem", 1, 3),
        ):
            row = QHBoxLayout()
            row.addWidget(QLabel(label), 1)
            spin = QSpinBox()
            spin.setRange(low, high)
            spin.setValue(policy[key])
            row.addWidget(spin)
            route.addLayout(row)
            self.model_policy_spins[key] = spin
        note = QLabel("O reserva permanece ativo até o principal passar no teste periódico. "
                      "O teste é uma chamada curta à API e pode consumir créditos. "
                      "Mensagens internas de ferramentas não contam no intervalo. "
                      "A lentidão é medida por espera sem dados, não pela duração total de uma resposta. "
                      "Se já houver texto transmitido, uma falha encerra a resposta para evitar misturar modelos. "
                      "Em caso de cota Z.ai, outras chaves são tentadas antes de trocar de modelo. Groq, Gemini e DeepSeek seguem para o reserva. Clique em Salvar para aplicar.")
        note.setWordWrap(True)
        route.addWidget(note)
        tabs = QTabWidget()
        tabs.addTab(route_card, "Ciclo padrão")
        mode_card, mode_layout = self._card()
        mode_note = QLabel("Escolha o modelo preferido para responder no Call. "
                           "Usar ciclo padrão segue a seleção geral. Um modelo específico usa "
                           "as mesmas regras de reserva e reteste, separadamente por modo.")
        mode_note.setWordWrap(True)
        mode_layout.addWidget(mode_note)
        self.model_mode_combos = {}
        for mode, label in (("call", "Modelo preferido para o modo Call"),):
            mode_layout.addWidget(QLabel(label))
            combo = QComboBox()
            combo.setEditable(True)
            combo.addItem("Usar ciclo padrão")
            combo.addItems(choices)
            combo.setCurrentText(policy[mode] or "Usar ciclo padrão")
            mode_layout.addWidget(combo)
            self.model_mode_combos[mode] = combo
        mode_layout.addStretch()
        tabs.addTab(mode_card, "Call")
        layout.addWidget(tabs)

        from gemini_catalog import CATALOG_SOURCE, CATALOG_DATE
        gemini_note = QLabel(
            f'Google AI Studio / Gemini · catálogo de {CATALOG_DATE}. '
            'Escolha um gemini-* nos mesmos seletores de principal, reservas e Call. '
            'Use GEMINI_API_KEY ou GOOGLE_API_KEY no .env, ou a chave Gemini nas configurações de voz. '
            'Os modelos Pro 3.1 não têm cota gratuita na API; os demais dependem da disponibilidade da conta. '
            'Atualizar Gemini consulta os modelos de conversa da sua chave; Testar verifica os selecionados. '
            'Modelos exclusivos de imagem, voz, vídeo e embeddings não servem como cérebro da Ayla. '
            f'<a href="{CATALOG_SOURCE}">Catálogo oficial</a>')
        gemini_note.setWordWrap(True)
        gemini_note.setOpenExternalLinks(True)
        layout.addWidget(gemini_note)

        from groq_catalog import FREE_LIMITS, LIMITS_SOURCE, CATALOG_DATE as GROQ_DATE
        groq_card, groq_layout = self._card()
        groq_note = QLabel(
            f'Groq · catálogo de {GROQ_DATE}. Use a chave Groq das configurações de voz ou GROQ_API_KEY no .env. '
            'Selecione groq:… no principal, reservas, Call ou compactador. Atualizar Groq consulta a API. '
            'As cotas são compartilhadas pela organização; o primeiro limite atingido bloqueia a chamada. '
            'TPM combinado não é o limite de entrada: ITPM e OTPM podem ter tetos separados e menores. '
            'Erro 413 de entrada ajusta o contexto enviado usando o limite real da API; histórico salvo é preservado. '
            'Ao receber 429, respeita a espera da API e usa o reserva de cota configurado, sem repetir texto já transmitido. '
            'Plano Free não cobra uso; a Ayla não altera o plano da conta. Contas pagas seguem a cobrança da Groq. '
            'Modelos Enterprise exigem acesso próprio; Safeguard é especializado em moderação. '
            'Áudio, embeddings e classificadores Prompt Guard não entram no catálogo de conversa. '
            f'<a href="{LIMITS_SOURCE}">Limites oficiais</a> · '
            '<a href="https://console.groq.com/settings/organization/limits">Limites reais da organização</a>')
        groq_note.setWordWrap(True)
        groq_note.setOpenExternalLinks(True)
        groq_layout.addWidget(groq_note)
        from groq_catalog import output_limit
        groq_layout.addWidget(QLabel('Limite de saída Groq por resposta (inclui raciocínio; padrão econômico: 2.048 tokens)'))
        self.groq_output_spin = QSpinBox()
        self.groq_output_spin.setRange(128, 65536)
        self.groq_output_spin.setValue(output_limit(self._load_settings()))
        self.groq_output_spin.setToolTip('Também limitado pelo máximo geral e pelo modelo. Respostas longas podem ficar incompletas; aumente conforme sua cota.')
        groq_layout.addWidget(self.groq_output_spin)
        limits_table = QTableWidget(len(FREE_LIMITS), 5)
        limits_table.setHorizontalHeaderLabels(['Modelo (Free)', 'Req/min', 'Req/dia', 'TPM combinado*', 'Tokens/dia'])
        limits_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        limits_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for row, (name, limits) in enumerate(FREE_LIMITS.items()):
            for col, value in enumerate((name, *limits)):
                limits_table.setItem(row, col, QTableWidgetItem(str(value)))
        limits_table.setMinimumHeight(180)
        groq_layout.addWidget(limits_table)
        layout.addWidget(groq_card)

        deepseek_note = QLabel(
            'DeepSeek · API oficial. Preencha DEEPSEEK_API_KEY na aba ENV. '
            'Modelos: deepseek:deepseek-flash (DeepSeek-V4.1-Flash, texto e imagens) e '
            'deepseek:deepseek-v4-pro (texto). Selecione no principal, reservas, Call ou compactador. '
            'Ambos têm contexto de 1.048.576 tokens e saída até 393.216 tokens, limitada pelo máximo geral. '
            'Usa os parâmetros gerais: none desliga o raciocínio; minimal/low → low; '
            'medium/high/xhigh → high; max → max. Temperatura só tem efeito sem raciocínio. '
            'Streaming, ferramentas e histórico seguem o ciclo normal da Ayla. '
            'Saldo, autenticação e limite de uso seguem para o reserva configurado. '
            'Atualizar DeepSeek consulta os modelos da chave; Testar chama os modelos selecionados. '
            '<a href="https://api-docs.deepseek.com/api/list-models/">Catálogo oficial DeepSeek</a>')
        deepseek_note.setWordWrap(True)
        deepseek_note.setOpenExternalLinks(True)
        layout.addWidget(deepseek_note)

        catalog_card, catalog = self._card()
        catalog_title = QLabel(f'Preços da API Z.ai · US$ / 1 milhão de tokens · consultados em {PRICING_DATE}')
        catalog_title.setWordWrap(True)
        catalog.addWidget(catalog_title)
        table = QTableWidget(len(PRICES), 4)
        table.setHorizontalHeaderLabels(["Modelo", "Entrada", "Leitura de cache", "Saída"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setMinimumHeight(350)
        for row, (name, prices) in enumerate(PRICES.items()):
            for col, value in enumerate([name, *prices]):
                text = value if col == 0 else ("—" if value is None else f"US$ {value:g}")
                table.setItem(row, col, QTableWidgetItem(text))
        catalog.addWidget(table)
        source = QLabel(f'<a href="{PRICING_SOURCE}">Fonte oficial dos preços</a> · API por uso; não é o Coding Plan. '
                        'Leitura de cache é a reutilização dos tokens guardados, cobrada pela tarifa da tabela. '
                        'Apenas o armazenamento desses tokens está gratuito por tempo limitado. '
                        'Os custos exibidos são estimativas pela tabela pública atual; confira a cobrança na fatura. '
                        'OCR é listado apenas para consulta de preço.')
        source.setOpenExternalLinks(True)
        source.setWordWrap(True)
        catalog.addWidget(source)
        layout.addWidget(catalog_card)

        add_card, add = self._card()
        title = QLabel("Adicionar à fila de reservas")
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
        section = QLabel("Fila de reservas após o modelo escolhido para cada situação")
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
            from ayla_model_policy import price_label
            price = QLabel(price_label(model.get("name", "")))
            price.setWordWrap(True)
            lay.addWidget(price)
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
        from ayla_model_policy import normalize_policy, ordered_models
        names = [m.get('name', '') for m in self.loaded_models.get('padrao', []) if m.get('name')]
        raw = {role: combo.currentText().strip() for role, combo in self.model_role_combos.items()}
        selected_models = ordered_models(names, normalize_policy(raw, names))
        selected_models += [combo.currentText().strip() for combo in self.model_mode_combos.values()
                            if combo.currentText().strip() not in ('', 'Usar ciclo padrão')]
        selected_models = list(dict.fromkeys(selected_models))
        settings = self._load_settings()

        def worker():
            try:
                from zai_provider import ZaiChatConfig, ZaiMessage
                from ayla_provider import AylaClient
                key = self.bot.api_keys[0] if hasattr(self.bot, "api_keys") and self.bot.api_keys else ""
                client = AylaClient(api_key=key, settings=settings)
                config = ZaiChatConfig(
                    max_tokens=512,
                    thinking_level="minimal",
                )
                lines = []
                for model in selected_models:
                    try:
                        start = time.time()
                        result = client.complete(model=model, messages=[ZaiMessage.user("Responda apenas OK")], config=config)
                        if not result.text.strip():
                            raise RuntimeError('Resposta vazia')
                        elapsed = time.time() - start
                        status = "slow" if elapsed > 5 else "ok"
                        self.response_queue.put(("model_status_update", model, status, f"{elapsed:.1f}s", ""))
                        lines.append(f"OK  {model}  {elapsed:.1f}s")
                        from groq_catalog import is_groq
                        if is_groq(model):
                            limits = client._client(model).rate_limits(model)
                            requests_left = limits.get('x-ratelimit-remaining-requests', 'não informado')
                            tokens_left = limits.get('x-ratelimit-remaining-tokens', 'não informado')
                            lines.append(f'  Groq: saldo informado pela API — {requests_left} requisições/dia; {tokens_left} tokens/min.')
                            if limits.get('input_token_limit'):
                                lines.append(f"  Limite de entrada observado (ITPM): {limits['input_token_limit']} tokens/min.")
                    except Exception as exc:
                        msg = str(exc)[:90]
                        self.response_queue.put(("model_status_update", model, "error", "N/A", msg))
                        lines.append(f"ERRO  {model}  {msg}")
                self.response_queue.put(("test", "\n".join(lines)))
            except Exception as exc:
                self.response_queue.put(("test", f"Erro ao testar modelos: {exc}"))
            finally:
                if 'client' in locals():
                    client.close()

        threading.Thread(target=worker, daemon=True).start()

    def _refresh_deepseek_catalog(self):
        self.model_test_label.setText('Consultando modelos da API oficial DeepSeek...')
        settings = self._load_settings()

        def worker():
            from deepseek_catalog import deepseek_key
            from deepseek_provider import DeepSeekClient
            client = None
            try:
                client = DeepSeekClient(deepseek_key(settings))
                self.response_queue.put(('deepseek_catalog', client.list_chat_models()))
            except Exception as exc:
                self.response_queue.put(('test', f'Erro ao consultar DeepSeek: {exc}'))
            finally:
                if client is not None:
                    client.close()

        threading.Thread(target=worker, daemon=True).start()

    def _refresh_groq_catalog(self):
        self.model_test_label.setText('Consultando modelos de texto da Groq...')
        settings = self._load_settings()
        def worker():
            from groq_catalog import groq_key
            from groq_provider import GroqClient
            client = None
            try:
                client = GroqClient(groq_key(settings))
                self.response_queue.put(('groq_catalog', client.list_chat_models()))
            except Exception as exc:
                self.response_queue.put(('test', f'Erro ao consultar Groq: {exc}'))
            finally:
                if client:
                    client.close()
        threading.Thread(target=worker, daemon=True).start()

    def _refresh_gemini_catalog(self):
        self.model_test_label.setText('Consultando modelos do Google AI Studio...')
        settings = self._load_settings()
        def worker():
            from gemini_catalog import gemini_key
            from gemini_provider import GeminiClient
            client = None
            try:
                client = GeminiClient(gemini_key(settings))
                self.response_queue.put(('gemini_catalog', client.list_chat_models()))
            except Exception as exc:
                self.response_queue.put(('test', f'Erro ao consultar Gemini: {exc}'))
            finally:
                if client:
                    client.close()
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
        self.fish_audio_text.setPlainText("Oi, usuario! Testando minha voz nova pelo Fish Audio. O que achou?")
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
                    output_path = TTS_OUTPUT_DIR / f"saida_fish_audio_teste_{timestamp}.wav"

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
                            stop_wav_fallback()
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
                                play_wav_fallback(output_path)
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
        play.clicked.connect(lambda: open_path(path))
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
            set_wallpaper(self.selected_image)
            self._toast("Wallpaper alterado")
        except Exception as exc:
            self._toast(f"Erro: {exc}")

    def _open_in_explorer(self, path: Path):
        try:
            open_path(path, reveal=True)
        except Exception as exc:
            self._toast(f"Erro ao abrir gerenciador de arquivos: {exc}")

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

    def _build_memory_test_page(self):
        page, layout = self._page("Teste de carregamento de memórias")
        description = QLabel(
            "Busca com gemini-embedding-001 e fallback para vetores salvos no SQLite. "
            "A busca combina palavras e significado; pode retornar menos que o limite, inclusive zero. "
            "Sem vetores suficientes, usa busca textual local. O teste não altera as memórias; "
            "o modo Gemini pode atualizar o cache e consumir cota da API.")
        description.setWordWrap(True)
        layout.addWidget(description)
        self.memory_test_query = QLineEdit()
        self.memory_test_query.setPlaceholderText("Digite uma pergunta ou informação para lembrar…")
        layout.addWidget(self.memory_test_query)
        controls = QHBoxLayout()
        self.memory_test_offline = QCheckBox("Somente SQLite (sem chamar Gemini)")
        controls.addWidget(self.memory_test_offline)
        self.memory_test_limit = QSpinBox()
        self.memory_test_limit.setRange(1, 50)
        self.memory_test_limit.setValue(10)
        controls.addWidget(QLabel("Limite:"))
        controls.addWidget(self.memory_test_limit)
        self.memory_test_button = QPushButton("Testar carregamento")
        self.memory_test_button.clicked.connect(self._run_memory_test)
        self.memory_test_query.returnPressed.connect(self._run_memory_test)
        controls.addWidget(self.memory_test_button)
        layout.addLayout(controls)
        self.memory_test_status = QLabel("Aguardando consulta.")
        layout.addWidget(self.memory_test_status)
        self.memory_test_output = QPlainTextEdit()
        self.memory_test_output.setReadOnly(True)
        layout.addWidget(self.memory_test_output)
        self.memory_test_running = False
        return page

    def _run_memory_test(self):
        if self.memory_test_running:
            return
        query = self.memory_test_query.text().strip()
        if not query:
            self.memory_test_status.setText("Digite uma consulta para testar.")
            return
        offline = self.memory_test_offline.isChecked()
        limit = self.memory_test_limit.value()
        self.memory_test_running = True
        self.memory_test_button.setEnabled(False)
        self.memory_test_output.clear()
        self.memory_test_status.setText("Carregando memórias…")

        def work():
            started = time.monotonic()
            try:
                from ayla_cerebro import buscar_memorias_estruturadas, formatar_memorias_encontradas
                info = {}
                results = buscar_memorias_estruturadas(
                    consulta=query, limite=limit, sqlite_only=offline, diagnostico=info)
                status = (f"{len(results)} memória(s) • {time.monotonic() - started:.2f} s • "
                          f"{info.get('origem', 'Busca textual local')} • "
                          f"{info.get('vetores', 0)} comparadas por vetor • "
                          f"{info.get('descartadas', 0)} descartadas por relevância")
                output = formatar_memorias_encontradas(
                    results, limite_caracteres=50000, incluir_diagnostico=True)
                if not results:
                    output += ("\nO limite é um máximo; a busca não completa a lista com memórias fracas."
                               f"\nCorte semântico desta consulta: {info.get('corte_semantico', 0):.3f}.")
                if info.get("erro_embedding"):
                    output += "\nGemini indisponível; usados os vetores válidos em cache e a busca textual."
                self.response_queue.put(("memory_test_result", status, output))
            except Exception as exc:
                self.response_queue.put(("memory_test_result",
                                         f"Falha no carregamento: {type(exc).__name__}", ""))

        threading.Thread(target=work, name="ayla-memory-test", daemon=True).start()

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
        review_btn = QPushButton("Revisar")
        review_btn.clicked.connect(self._review_memory)
        trash_btn = QPushButton("Lixeira")
        trash_btn.clicked.connect(self._show_memory_trash)
        row2.addWidget(self.mem_value, 1)
        row2.addWidget(add_btn)
        row2.addWidget(review_btn)
        row2.addWidget(trash_btn)
        fl.addLayout(row2)
        layout.addWidget(form)
        self.memory_container = QVBoxLayout()
        self.memory_container.setSpacing(8)
        layout.addLayout(self.memory_container)
        layout.addStretch(1)
        self._refresh_memory()
        return page

    def _load_mem(self):
        if self.bot:
            try:
                import Ayla
                return Ayla.carregar_memoria()
            except Exception:
                pass
        data = self._safe_load_json(MEMORIA_PATH, {})
        return data if isinstance(data, dict) else {}

    def _save_mem(self, data):
        salvo = False
        if self.bot:
            try:
                import Ayla
                Ayla.salvar_memoria(data)
                salvo = True
            except Exception as exc:
                print(f"Erro ao salvar memória estruturada: {exc}")
        if not salvo:
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
            if self.bot:
                try:
                    import Ayla
                    resultado = Ayla.criar_ou_atualizar_memoria(
                        key, value, sobrescrever=True, tag=tag, origem="GUI"
                    )
                    if not resultado.get("ok"):
                        self._toast(resultado.get("mensagem", "Não foi possível salvar a memória"))
                        return
                except Exception as exc:
                    self._toast(f"Erro ao salvar memória: {exc}")
                    return
            else:
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
            tipo = value.get("tipo")
            escopo = value.get("escopo")
            status = value.get("status")
            extras = " | ".join(str(x) for x in (tipo, escopo, status) if x)
            if extras:
                data_com_acessos = f"{data_com_acessos} | {extras}"
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
            if self.bot:
                try:
                    import Ayla
                    removida = bool(Ayla.enviar_memoria_para_lixeira(key, "Removida pela interface" ).get("ok"))
                except Exception as exc:
                    self._toast(f"Erro ao mover memória para a lixeira: {exc}")
            else:
                mem = self._load_mem()
                if key in mem:
                    mem.pop(key)
                    self._save_mem(mem)
                    removida = True
        if removida:
            self._refresh_memory()
            self._toast("Memoria movida para a lixeira")

    def _review_memory(self):
        if not self.bot:
            self._toast("A revisão estruturada requer a Ayla em execução")
            return
        try:
            import Ayla
            report = Ayla.revisar_memorias_estruturadas()
            text = (
                f"Memórias ativas: {report['total_ativas']}\n"
                f"Expiradas: {', '.join(report['expiradas']) or 'nenhuma'}\n"
                f"Possíveis duplicatas: {', '.join(f'{a} ↔ {b}' for a, b, _ in report['duplicatas']) or 'nenhuma'}\n"
                f"Possíveis conflitos: {', '.join(f'{a} ↔ {b}' for a, b in report['possiveis_conflitos']) or 'nenhum'}\n"
                f"Itens na lixeira: {report['lixeira']}"
            )
            QMessageBox.information(self, "Revisão de memória", text)
        except Exception as exc:
            QMessageBox.critical(self, "Erro na revisão", str(exc))

    def _show_memory_trash(self):
        if not self.bot:
            self._toast("A lixeira estruturada requer a Ayla em execução")
            return
        try:
            import Ayla
            itens = Ayla.listar_lixeira_memoria()
            if not itens:
                QMessageBox.information(self, "Lixeira", "A lixeira de memórias está vazia.")
                return
            text = "\n".join(f"• {item['chave']} — {item['removida_em']}" for item in itens)
            QMessageBox.information(self, "Lixeira de memórias", text)
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao abrir lixeira", str(exc))

    # ------------------------------------------------------------------
    # Memórias Automáticas (Ayla Cérebro)
    # ------------------------------------------------------------------

    def _build_forgetting_page(self):
        # A GUI pode ser recriada sem encerrar o bot; atualize os modelos em cache.
        import importlib
        if "ayla_esquecimento" in sys.modules:
            importlib.reload(sys.modules["ayla_esquecimento"])
        page, layout = self._scroll_page("Esquecimento natural", [])
        desc = QLabel("Clique em Analisar para revisar as memórias manuais e automáticas. "
                      "Só as sugestões de apagar aparecem aqui. Escolha Manter ou Apagar em cada sugestão. "
                      "Apagar sugestões move as sugestões restantes para a lixeira da Ayla.")
        desc.setWordWrap(True)
        layout.addWidget(desc)
        row = QHBoxLayout()
        row.addWidget(QLabel('Raciocínio:'))
        self.forgetting_reasoning = QComboBox()
        self.forgetting_reasoning.addItem('Automático (alto → baixo)', 'auto')
        self.forgetting_reasoning.addItem('Baixo', 'low')
        row.addWidget(self.forgetting_reasoning)
        self.forgetting_analyze = QPushButton("Analisar")
        self.forgetting_analyze.clicked.connect(self._analyze_forgetting)
        row.addWidget(self.forgetting_analyze)
        self.forgetting_stop = QPushButton("Parar")
        self.forgetting_stop.setEnabled(False)
        self.forgetting_stop.clicked.connect(self._stop_forgetting)
        row.addWidget(self.forgetting_stop)
        self.forgetting_timer = QTimer(self)
        self.forgetting_timer.setInterval(50)
        self.forgetting_timer.timeout.connect(self._poll_forgetting)
        self.forgetting_delete = QPushButton("Apagar sugestões")
        self.forgetting_delete.setObjectName("danger")
        self.forgetting_delete.setEnabled(False)
        self.forgetting_delete.clicked.connect(self._delete_forgetting)
        row.addWidget(self.forgetting_delete)
        layout.addLayout(row)
        self.forgetting_status = QLabel("Aguardando análise.")
        self.forgetting_status.setWordWrap(True)
        layout.addWidget(self.forgetting_status)
        self.forgetting_glm_offer = QWidget()
        glm_row = QHBoxLayout(self.forgetting_glm_offer)
        glm_row.addWidget(QLabel('Usar o GLM?'))
        self.forgetting_glm_model = QComboBox()
        from ayla_model_policy import PRICES
        names = [m.get('name', '') for m in self.loaded_models.get('padrao', [])]
        self.forgetting_glm_model.addItems(list(dict.fromkeys(
            ['glm-5.3-flash'] + [m for m in [*names, *PRICES]
                               if m.startswith('glm-') and m not in ('glm-ocr', 'glm-4.7-flash')])))
        glm_row.addWidget(self.forgetting_glm_model)
        glm_use = QPushButton('Usar GLM')
        glm_use.clicked.connect(lambda: self._analyze_forgetting(
            modelo_glm=self.forgetting_glm_model.currentText()))
        glm_row.addWidget(glm_use)
        self.forgetting_glm_offer.hide()
        layout.addWidget(self.forgetting_glm_offer)
        self.forgetting_page = 0
        navigation = QHBoxLayout()
        previous = QPushButton("Anterior")
        previous.clicked.connect(lambda: self._change_forgetting_page(-1))
        following = QPushButton("Próxima")
        following.clicked.connect(lambda: self._change_forgetting_page(1))
        navigation.addWidget(previous)
        navigation.addWidget(following)
        layout.addLayout(navigation)
        self.forgetting_container = QVBoxLayout()
        layout.addLayout(self.forgetting_container)
        layout.addStretch(1)
        self.forgetting_items = []
        self.forgetting_running = False
        self.forgetting_loaded = False
        self.forgetting_choices = set()
        self.forgetting_pending = set()
        self.forgetting_bulk_keys = set()
        return page

    def _analyze_forgetting(self, checked=False, *, modelo_glm=None):
        if self.forgetting_running or self.forgetting_pending:
            return
        self.forgetting_running = True
        self.forgetting_glm_offer.hide()
        if modelo_glm is None:
            self.forgetting_choices = set()
        self.forgetting_items = []
        self._render_forgetting()
        self.forgetting_analyze.setEnabled(False)
        self.forgetting_reasoning.setEnabled(False)
        self.forgetting_status.setText("Carregando memórias…")
        keys = list(getattr(self.bot, 'api_keys', []) or [])
        index = getattr(self.bot, 'idx_api_atual', 0)
        glm_key = keys[index] if 0 <= index < len(keys) else (keys[0] if keys else None)

        self.forgetting_page = 0
        try:
            # O bot pode manter a versão anterior do worker ao reabrir a GUI.
            # Recarregue antes de passar opções adicionadas em atualizações.
            import importlib
            import ayla_esquecimento_worker
            worker = importlib.reload(ayla_esquecimento_worker)
            self.forgetting_session = worker.AnaliseProcesso(
                api_key=glm_key if modelo_glm else None, modelo_glm=modelo_glm,
                raciocinio=self.forgetting_reasoning.currentData())
        except Exception as exc:
            self.forgetting_reasoning.setEnabled(True)
            self._finish_forgetting("forgetting_result", None, type(exc).__name__)
            return
        self.forgetting_stop.setEnabled(True)
        self.forgetting_timer.start()

    def _stop_forgetting(self):
        self.forgetting_timer.stop()
        session = getattr(self, 'forgetting_session', None)
        if session is not None:
            session.parar()
            self.forgetting_session = None
        self.forgetting_running = False
        self.forgetting_stop.setEnabled(False)
        self.forgetting_reasoning.setEnabled(True)
        self.forgetting_analyze.setEnabled(not self.forgetting_pending)
        self.forgetting_status.setText("Análise interrompida. Nenhuma exclusão foi feita pela análise.")
        self._render_forgetting()

    def _poll_forgetting(self):
        session = getattr(self, 'forgetting_session', None)
        if session is None:
            return
        if time.monotonic() - session.inicio > 600:
            self._stop_forgetting()
            self.forgetting_status.setText("Análise interrompida: limite de 10 minutos atingido.")
            return
        for _ in range(8):
            try:
                item = session.eventos.get_nowait()
            except queue.Empty:
                break
            kind = item[0]
            if kind == 'forgetting_item':
                self._receive_forgetting_item(item[1], item[2])
            elif kind == 'forgetting_progress':
                self.forgetting_status.setText(item[1])
            elif kind == 'forgetting_result':
                self._stop_forgetting()
                self._finish_forgetting(kind, item[1], item[2])
                return
            elif kind == 'fim':
                self._stop_forgetting()
                self.forgetting_status.setText("O processo da análise encerrou sem resultado.")
                return

    def _change_forgetting_page(self, delta):
        last = max(0, (len(self.forgetting_items) - 1) // 50)
        self.forgetting_page = max(0, min(last, self.forgetting_page + delta))
        self._render_forgetting()

    def _render_forgetting(self):
        # Agrupa eventos de uma mesma rodada da fila, sem recriar a lista inteira.
        if getattr(self, '_forgetting_render_scheduled', False):
            return
        self._forgetting_render_scheduled = True
        QTimer.singleShot(16, self._flush_forgetting_cards)

    def _flush_forgetting_cards(self):
        self._forgetting_render_scheduled = False
        if not hasattr(self, '_forgetting_cards'):
            self._forgetting_cards = {}
        last = max(0, (len(self.forgetting_items) - 1) // 50)
        self.forgetting_page = min(getattr(self, 'forgetting_page', 0), last)
        start = self.forgetting_page * 50
        desired = {item['chave']: item for item in self.forgetting_items[start:start + 50]}
        self.forgetting_delete.setEnabled(
            any(i.get('decisao', 'esquecer') == 'esquecer' for i in self.forgetting_items)
            and not self.forgetting_running and not self.forgetting_pending)
        started, changes = time.monotonic(), 0
        for key in list(self._forgetting_cards):
            card, keep, delete, previous = self._forgetting_cards[key]
            if key not in desired or previous != desired[key]:
                self.forgetting_container.removeWidget(card)
                card.hide()
                card.deleteLater()
                del self._forgetting_cards[key]
                changes += 1
            else:
                enabled = key not in self.forgetting_pending
                keep.setEnabled(enabled)
                delete.setEnabled(enabled)
            if changes >= 8 or (changes and time.monotonic() - started >= 0.008):
                self._render_forgetting()
                return
        for key, item in desired.items():
            if key not in self._forgetting_cards:
                self._forgetting_cards[key] = self._create_forgetting_card(item)
                changes += 1
            if changes >= 8 or (changes and time.monotonic() - started >= 0.008):
                self._render_forgetting()
                return

    def _create_forgetting_card(self, item):
        card, lay = self._card()
        text, tag, date = self._memory_parts(item["registro"])
        label = QLabel(f"{item['chave']} · {tag} · {date}\n{text}\n\nAvaliação: {item.get('decisao', 'esquecer')}\nMotivo: {item['motivo']}")
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(label)
        keep = QPushButton("Manter")
        keep.setEnabled(item['chave'] not in self.forgetting_pending)
        keep.clicked.connect(lambda checked=False, k=item["chave"]: self._keep_forgetting(k))
        buttons = QHBoxLayout()
        buttons.addWidget(keep)
        delete = QPushButton('Apagar')
        delete.setObjectName('danger')
        delete.setEnabled(item['chave'] not in self.forgetting_pending)
        delete.clicked.connect(lambda checked=False, i=item: self._delete_forgetting_one(i))
        buttons.addWidget(delete)
        lay.addLayout(buttons)
        self.forgetting_container.addWidget(card)
        return card, keep, delete, item

    def _keep_forgetting(self, chave):
        if chave in self.forgetting_pending:
            return
        self.forgetting_choices.add(chave)
        self.forgetting_items = [i for i in self.forgetting_items if i["chave"] != chave]
        self._render_forgetting()

    def _receive_forgetting_item(self, kind, item):
        if kind == 'inicio':
            self.forgetting_items = []
        elif item.get('decisao', 'esquecer') == 'esquecer' and item['chave'] not in self.forgetting_choices:
            self.forgetting_items = [i for i in self.forgetting_items if i['chave'] != item['chave']]
            self.forgetting_items.append(item)
        self._render_forgetting()

    def _update_forgetting_context(self, result):
        # Executado pelo worker; as páginas de memória se atualizam ao abri-las.
        if result.get('removidas') and self.bot and hasattr(self.bot, 'atualizar_prompt_memoria'):
            try:
                self.bot.atualizar_prompt_memoria()
            except Exception:
                result['context_error'] = True

    def _delete_forgetting_one(self, item):
        chave = item['chave']
        if chave in self.forgetting_pending or chave in self.forgetting_choices:
            return
        self.forgetting_pending.add(chave)
        self.forgetting_analyze.setEnabled(False)
        self._render_forgetting()
        def worker():
            try:
                from ayla_esquecimento import apagar
                lock = getattr(self.bot, 'memoria_lock', None)
                with lock if lock is not None else nullcontext():
                    result = apagar([item])
                self._update_forgetting_context(result)
                self.response_queue.put(('forgetting_deleted_one', item, result, None))
            except Exception as exc:
                self.response_queue.put(('forgetting_deleted_one', item, None, str(exc)))
        threading.Thread(target=worker, daemon=True, name='AylaApagarUmaMemoria').start()

    def _finish_forgetting_one(self, item, result, error):
        chave = item['chave']
        self.forgetting_pending.discard(chave)
        if not error and (result['removidas'] or result['ignoradas']):
            self.forgetting_choices.add(chave)
            self.forgetting_items = [i for i in self.forgetting_items if i['chave'] != chave]
            if result['removidas']:
                self.forgetting_status.setText(f'{chave}: movida para a lixeira.')
            else:
                self.forgetting_status.setText(f'{chave}: preservada porque mudou ou já não existe.')
        else:
            self.forgetting_status.setText(f'Não foi possível apagar {chave}: {error or result["falhas"]}')
        if result and result.get('context_error'):
            self.forgetting_status.setText(self.forgetting_status.text() + ' Falha ao atualizar o contexto.')
        self.forgetting_analyze.setEnabled(not self.forgetting_running and not self.forgetting_pending)
        self._render_forgetting()

    def _delete_forgetting(self):
        if self.forgetting_running or self.forgetting_pending or not self.forgetting_items:
            return
        self.forgetting_running = True
        items = [i for i in self.forgetting_items if i.get('decisao', 'esquecer') == 'esquecer']
        self.forgetting_bulk_keys = {i['chave'] for i in items}
        self.forgetting_pending.update(self.forgetting_bulk_keys)
        self.forgetting_analyze.setEnabled(False)
        self._render_forgetting()
        self.forgetting_status.setText("Movendo a lista revisada para a lixeira…")

        def worker():
            try:
                from ayla_esquecimento import apagar
                lock = getattr(self.bot, "memoria_lock", None)
                with lock if lock is not None else nullcontext():
                    result = apagar(items)
                self._update_forgetting_context(result)
                self.response_queue.put(("forgetting_deleted", result, None))
            except Exception as exc:
                self.response_queue.put(("forgetting_deleted", None, str(exc)))
        threading.Thread(target=worker, daemon=True, name="AylaApagarEsquecimento").start()

    def _finish_forgetting(self, kind, result, error):
        self.forgetting_running = False
        if kind == 'forgetting_deleted':
            self.forgetting_pending.difference_update(self.forgetting_bulk_keys)
            self.forgetting_bulk_keys.clear()
        self.forgetting_analyze.setEnabled(not self.forgetting_pending)
        if error:
            self.forgetting_status.setText(f"Não foi possível concluir: {error}")
            self.forgetting_glm_offer.setVisible(bool(result and result.get('oferecer_glm')))
        elif kind == "forgetting_result":
            self.forgetting_loaded = True
            self.forgetting_items = [i for i in result.get('avaliacoes', result['itens'])
                                     if i.get('decisao', 'esquecer') == 'esquecer'
                                     and i['chave'] not in self.forgetting_choices]
            self.forgetting_status.setText(
                f"{result['analisadas']} memórias com avaliação individual por {result['modelo']} "
                f"(raciocínio {'fraco' if result.get('nivel') == 'low' else 'alto'}). "
                f"{len(self.forgetting_items)} sugestões de apagar para conferir.")
        else:
            removed = set(result["removidas"]) | set(result["ignoradas"])
            self.forgetting_choices.update(removed)
            self.forgetting_items = [i for i in self.forgetting_items if i["chave"] not in removed]
            self.forgetting_status.setText(
                f"{len(result['removidas'])} movidas para a lixeira. "
                f"{len(result['ignoradas'])} preservadas por alteração desde a análise ou já ausentes. "
                f"{len(result['falhas'])} falhas." +
                (" Tente novamente: " + ", ".join(result["falhas"]) if result["falhas"] else ""))
        self._render_forgetting()

    def _build_auto_memory_page(self):
        page, layout = self._scroll_page(
            "Memórias Automáticas (Cérebro da Ayla)",
            [
                ("🔄 Atualizar", self._refresh_auto_memory, "primary"),
                ("📜 Ver Logs do Cérebro", self._show_auto_memory_logs, ""),
                ("Lixeira", self._show_memory_trash, "")
            ]
        )

        info_card, info_lay = self._card()
        ititle = QLabel("Subsistema Cérebro em Segundo Plano")
        ititle.setObjectName("sectionTitle")
        info_lay.addWidget(ititle)

        desc = QLabel(
            "As memórias abaixo foram analisadas e aprendidas automaticamente em segundo plano pelo Cérebro da Ayla "
            "(via Gemini 3.5 Flash Lite, Gemini 3.1 Flash Lite e fallback GPT-OSS 120B no Groq), filtradas com regras rígidas estilo MemGPT para capturar apenas gostos, "
            "hábitos e projetos duradouros da usuario Usuario sem causar lag nas conversas.\n"
            "Você pode buscar e excluir qualquer memória gerada automaticamente se desejar. O botão de conferência "
            "pede ao gptOSS_120b para revisar a lista inteira e remover somente as lembranças inúteis."
        )
        desc.setObjectName("muted")
        desc.setWordWrap(True)
        info_lay.addWidget(desc)
        conferir_btn = QPushButton("Conferir memórias úteis")
        conferir_btn.setObjectName("pink")
        conferir_btn.clicked.connect(self._conferir_memorias_uteis)
        info_lay.addWidget(conferir_btn)
        layout.addWidget(info_card)

        # Barra de Busca
        search_card, sl = self._card()
        row = QHBoxLayout()
        self.auto_mem_search = QLineEdit()
        self.auto_mem_search.setPlaceholderText("Buscar nas memórias automáticas...")
        self.auto_mem_search.textChanged.connect(self._refresh_auto_memory)
        row.addWidget(self.auto_mem_search, 1)
        search_card.layout().addLayout(row)
        layout.addWidget(search_card)

        self.auto_memory_container = QVBoxLayout()
        self.auto_memory_container.setSpacing(8)
        layout.addLayout(self.auto_memory_container)
        layout.addStretch(1)
        self._refresh_auto_memory()
        return page

    def _refresh_auto_memory(self):
        if not hasattr(self, "auto_memory_container"):
            return
        self._clear_layout(self.auto_memory_container)
        query = self.auto_mem_search.text().strip().lower() if hasattr(self, "auto_mem_search") else ""
        shown = 0

        all_mems = self._load_mem()
        for key, value in all_mems.items():
            if not isinstance(value, dict):
                continue
            origem = str(value.get("origem", "")).lower()
            # Mostra apenas memórias com origem cerebro_automatico ou automatico
            if "cerebro" not in origem and "automatic" not in origem:
                continue

            text, tag, date = self._memory_parts(value)
            if query and query not in key.lower() and query not in text.lower() and query not in tag.lower():
                continue

            card, lay = self._card()
            top = QHBoxLayout()
            title = QLabel(f"🧠 {key}")
            title.setObjectName("sectionTitle")
            top.addWidget(title, 1)
            tag_lbl = QLabel(f"🏷️ {tag}")
            tag_lbl.setObjectName("muted")
            top.addWidget(tag_lbl)
            delete = QPushButton("Excluir")
            delete.setObjectName("danger")
            delete.clicked.connect(lambda checked=False, k=key: self._delete_auto_memory(k))
            top.addWidget(delete)
            lay.addLayout(top)

            body = QLabel(text)
            body.setWordWrap(True)
            lay.addWidget(body)

            dt = QLabel(date)
            dt.setObjectName("dim")
            lay.addWidget(dt)
            self.auto_memory_container.addWidget(card)
            shown += 1

        if shown == 0:
            lbl = QLabel("Nenhuma memória automática gerada ainda pelo Cérebro.")
            lbl.setObjectName("muted")
            self.auto_memory_container.addWidget(lbl)

    def _delete_auto_memory(self, key: str):
        self._delete_memory(key)
        self._refresh_auto_memory()

    def _conferir_memorias_uteis(self):
        if getattr(self, "auto_memory_review_running", False):
            self._toast("A conferência de memórias já está em andamento")
            return
        resposta = QMessageBox.question(
            self,
            "Conferir memórias úteis",
            "O gptOSS_120b vai analisar todas as memórias automáticas e mover as inúteis para a lixeira. "
            "Memórias manuais não serão alteradas. Deseja continuar?",
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return

        self.auto_memory_review_running = True
        self._toast("gptOSS_120b está conferindo todas as memórias automáticas...")

        def worker():
            try:
                import ayla_cerebro
                relatorio = ayla_cerebro.conferir_memorias_uteis()
            except Exception as exc:
                relatorio = {"ok": False, "mensagem": f"Erro durante a conferência: {exc}"}
            self.response_queue.put(("auto_memory_review_result", relatorio))

        threading.Thread(target=worker, daemon=True, name="AylaConferirMemorias").start()

    def _show_auto_memory_logs(self):
        try:
            import ayla_cerebro
            logs = ayla_cerebro.listar_memorias_automaticas_log(limite=30)
            status_c = ayla_cerebro.obter_status_cerebro()

            if not logs:
                QMessageBox.information(
                    self, 
                    "Logs do Cérebro", 
                    f"Nenhum log de extração registrado ainda.\n\n"
                    f"Status do Cérebro:\n"
                    f"• Worker Ativo: {'Sim' if status_c.get('worker_ativo') else 'Não'}\n"
                    f"• Fila Pendente: {status_c.get('fila_pendente', 0)}\n"
                    f"• Total Analisados: {status_c.get('total_analisados', 0)}\n"
                    f"• Memórias Extraídas: {status_c.get('memorias_extraidas', 0)}\n"
                    f"• Descartados por Similaridade: {status_c.get('descartados_por_similaridade', 0)}\n"
                    f"• Consolidados em Chave Existente: {status_c.get('consolidados_chave_existente', 0)}"
                )
                return

            linhas = [
                f"📊 STATUS OPERACIONAL: Analisados: {status_c.get('total_analisados', 0)} | Extraídas: {status_c.get('memorias_extraidas', 0)} | Descarte Similaridade: {status_c.get('descartados_por_similaridade', 0)} | Último modelo: {status_c.get('ultimo_modelo_usado', 'N/A')}\n",
                "📜 ÚLTIMAS EXTRAÇÕES AUTOMÁTICAS:"
            ]
            for item in logs:
                ts = item.get("timestamp", "")[:19].replace("T", " ")
                mod = item.get("modelo_origem", "desconhecido")
                k = item.get("chave", "")
                v = item.get("valor", "")
                st = item.get("status", "")
                if st == "descartado_similaridade":
                    linhas.append(f"[{ts}] [{mod}] 🛡️ [IGNORADO - SIMILAR] 🔑 '{k}' ➔ {item.get('motivo', v)}")
                else:
                    linhas.append(f"[{ts}] [{mod}] 🔑 '{k}' ➔ {v}")

            text = "\n\n".join(linhas)
            QMessageBox.information(self, "Logs do Cérebro Automático", text)
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao abrir logs", f"Erro: {exc}")


    # ------------------------------------------------------------------
    # Status e console
    # ------------------------------------------------------------------

    def _build_status_page(self):
        page, layout = self._scroll_page(
            "Status",
            [
                ("🔄 Reiniciar GUI", self.reload_gui, "primary"),
            ]
        )
        status_names = ["Discord", "Modelo", "Chave API", "APIs", "Saldo Z.AI", "Saldo DeepSeek", "Memorias", "Carregamento de memória", "Memorização automática", "Indexação de memórias", "Contexto", "Iniciar com o sistema", "Tempo de Resposta", "Tarefas simultâneas", "Sessão global", "Tarifa DeepSeek"]
        cost_names = ["Gasto GLM nesta sessão", "Gasto DeepSeek nesta sessão",
                      "Gasto GLM acumulado", "Gasto DeepSeek acumulado"]
        for heading, names in ((None, status_names), ("Gastos estimados (USD)", cost_names)):
            if heading:
                layout.addWidget(QLabel(heading))
            grid = QGridLayout()
            grid.setSpacing(10)
            layout.addLayout(grid)
            for idx, name in enumerate(names):
                card, lay = self._card()
                title = QLabel(name)
                title.setObjectName("muted")
                value = QLabel("-")
                value.setObjectName("sectionTitle")
                value.setWordWrap(True)
                if name == 'Tarifa DeepSeek':
                    value.setToolTip('Estimativa pelo horário oficial: pico de segunda a sexta, '
                                     '01:00–04:00 e 06:00–10:00 UTC. Fora dessas faixas, metade do preço. '
                                     'Descontos de feriados chineses não estão cadastrados.')
                if heading:
                    value.setToolTip('Estimativa em USD a partir do uso registrado pela Ayla; '
                                     'o acumulado inclui sessões anteriores salvas deste provedor.')
                lay.addWidget(title)
                lay.addWidget(value)
                self.status_labels[name] = value
                grid.addWidget(card, idx // 2, idx % 2)

        row_buttons = QHBoxLayout()
        startup = QPushButton("Alternar inicializacao com o sistema")
        startup.clicked.connect(self._toggle_startup)
        row_buttons.addWidget(startup, 1)

        latency_btn = QPushButton("Testar Latência da Chave")
        latency_btn.clicked.connect(self._test_active_key_latency)
        row_buttons.addWidget(latency_btn, 1)

        balance_row = QHBoxLayout()
        balance_btn = QPushButton("Atualizar saldo Z.AI")
        balance_btn.clicked.connect(lambda: self._refresh_zai_balance(force=True))
        balance_row.addWidget(balance_btn, 1)

        deepseek_balance_btn = QPushButton("Atualizar saldo DeepSeek")
        deepseek_balance_btn.clicked.connect(lambda: self._refresh_deepseek_balance(force=True))
        balance_row.addWidget(deepseek_balance_btn, 1)

        reload_btn = QPushButton("🔄 Reiniciar GUI")
        reload_btn.clicked.connect(self.reload_gui)
        row_buttons.addWidget(reload_btn, 1)
        layout.addLayout(row_buttons)
        layout.addLayout(balance_row)

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
        layout.addWidget(QLabel("Tarefas em andamento e resultados recentes"))
        self.tasks_status_box = QPlainTextEdit()
        self.tasks_status_box.setReadOnly(True)
        self.tasks_status_box.setMinimumHeight(140)
        layout.addWidget(self.tasks_status_box)
        layout.addWidget(QLabel("Disponibilidade dos modos"))
        self.modules_status_box = QPlainTextEdit()
        self.modules_status_box.setReadOnly(True)
        layout.addWidget(self.modules_status_box)
        return page

    def _refresh_deepseek_balance(self, force=False):
        """Atualização em segundo plano, no máximo a cada cinco minutos automaticamente."""
        label = self.status_labels.get('Saldo DeepSeek')
        if label is None:
            return
        from dotenv import dotenv_values
        from deepseek_catalog import deepseek_key
        settings = self._load_settings()
        env = dotenv_values(ENV_PATH) if ENV_PATH.exists() else {}
        key = str(settings.get('deepseek_api_key') or (
            (env.get('DEEPSEEK_API_KEY') or '') if 'DEEPSEEK_API_KEY' in env else deepseek_key())).strip()
        identity = hashlib.sha256(key.encode()).hexdigest()
        changed = identity != self._deepseek_balance_identity
        if not changed:
            if self.deepseek_balance_refreshing:
                return
            if not force and time.monotonic() - self.deepseek_balance_last_refresh < 300:
                return
        self._deepseek_balance_identity = identity
        label.setToolTip('')
        if not key:
            self.deepseek_balance_refreshing = False
            self.deepseek_balance_last_refresh = time.monotonic()
            label.setText('Sem chave — preencha DEEPSEEK_API_KEY na aba ENV')
            return
        self.deepseek_balance_refreshing = True
        label.setText('Consultando...')

        def worker():
            client = None
            try:
                from deepseek_provider import DeepSeekClient
                client = DeepSeekClient(key, timeout=15)
                result = client.get_balance()
            except Exception as exc:
                status = getattr(exc, 'status_code', None)
                result = {
                    401: 'Chave DeepSeek inválida ou recusada',
                    403: 'Consulta de saldo DeepSeek sem permissão',
                    429: 'Limite de consultas atingido; tente novamente mais tarde',
                }.get(status, 'Saldo indisponível; tente atualizar novamente')
            finally:
                if client is not None:
                    client.close()
            self.response_queue.put(('deepseek_balance_result', identity, result))

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def _format_deepseek_balance(result):
        from decimal import Decimal, InvalidOperation
        if not isinstance(result, dict):
            return str(result), str(result)
        summaries, details = [], []
        try:
            for balance in result['balance_infos']:
                currency = balance['currency']
                if currency not in ('USD', 'CNY'):
                    raise ValueError('Moeda desconhecida')
                prefix = 'US$' if currency == 'USD' else 'CNY'
                def amount(field, precision):
                    value = Decimal(str(balance[field]))
                    if not value.is_finite():
                        raise ValueError('Saldo inválido')
                    return f'{prefix} {value:.{precision}f}'.replace('.', ',')
                summaries.append(amount('total_balance', 2))
                details.append(f"{currency}: total {amount('total_balance', 6)} · "
                               f"créditos concedidos {amount('granted_balance', 6)} · "
                               f"recargas {amount('topped_up_balance', 6)}")
            if not summaries:
                raise ValueError('Saldo ausente')
            available = result['is_available']
            if not isinstance(available, bool):
                raise ValueError('Disponibilidade inválida')
            summary = ' · '.join(summaries)
            if not available:
                summary += ' · saldo insuficiente para chamadas'
            details.append('Saldo suficiente para chamadas' if available else 'Saldo insuficiente para chamadas')
            return summary, '\n'.join(details)
        except (KeyError, TypeError, ValueError, InvalidOperation):
            return 'Saldo indisponível', 'A DeepSeek retornou dados de saldo incompletos ou inválidos.'

    def _refresh_zai_balance(self, force=False):
        """Consulta o saldo fora da thread da interface e limita atualizações automáticas."""
        if self.zai_balance_refreshing:
            return
        if not force and time.monotonic() - self.zai_balance_last_refresh < 300:
            return

        label = self.status_labels.get("Saldo Z.AI")
        if label is not None:
            label.setText("Consultando...")
        self.zai_balance_refreshing = True

        keys = list(getattr(self.bot, "api_keys", []) or [])
        active_index = getattr(self.bot, "idx_api_atual", 0)

        def worker():
            try:
                module_path = MODOS_DIR / "MODOS ADICIONAIS" / "consultar_saldo_zai.py"
                spec = importlib.util.spec_from_file_location("ayla_gui_saldo_zai", module_path)
                if spec is None or spec.loader is None:
                    raise RuntimeError("não foi possível carregar o módulo de saldo")
                module = importlib.util.module_from_spec(spec)
                module.ZAI_API_KEYS = keys
                module.TOOL_MAP = {}
                module.FUNCTION_DECLARATIONS = []
                spec.loader.exec_module(module)

                key_number = active_index + 1 if 0 <= active_index < len(keys) else 1
                result = module.consultar_saldo_zai(key_number)
                self.response_queue.put(("zai_balance_result", result))
            except Exception as exc:
                self.response_queue.put(("zai_balance_result", f"Indisponível: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def _format_zai_balance_status(result):
        text = str(result or "Indisponível").replace("**", "").strip()
        first_line = text.splitlines()[0] if text else "Indisponível"
        prefix = "💰 Saldo Pay-as-you-go da Z.AI:"
        if first_line.startswith(prefix):
            return first_line[len(prefix):].strip()
        return first_line

    def _test_active_key_latency(self):
        if "Tempo de Resposta" in self.status_labels:
            self.status_labels["Tempo de Resposta"].setText("Medindo...")

        def worker():
            try:
                from zai_provider import ZaiChatConfig, ZaiClient, ZaiMessage
                key = ""
                if hasattr(self.bot, "api_keys") and self.bot.api_keys:
                    idx = getattr(self.bot, "idx_api_atual", 0)
                    if 0 <= idx < len(self.bot.api_keys):
                        key = self.bot.api_keys[idx]
                if not key:
                    from dotenv import load_dotenv
                    load_dotenv(ENV_PATH, override=True)
                    key = os.getenv("ZAI_API_KEY", "") or os.getenv("ZAI_API_KEY_1", "")

                if not key:
                    self.response_queue.put(("latency_result", "Sem chave"))
                    return

                client = ZaiClient(api_key=key)
                start = time.time()
                client.complete(
                    model="glm-5.3-flash",
                    messages=[ZaiMessage.user("Responda OK")],
                    config=ZaiChatConfig(
                        max_tokens=16,
                        thinking_level="low",
                    ),
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


        runtime = self.bot.obter_resumo_runtime() if hasattr(self.bot,"obter_resumo_runtime") else {}
        try:
            from zai_provider import obter_gasto_total_sessao_zai, obter_gasto_total_acumulado_zai
            gasto_sessao = obter_gasto_total_sessao_zai()
        except Exception:
            gasto_sessao = 0.0
        try:
            from zai_provider import obter_gasto_total_acumulado_zai
            gasto_acumulado = f"US$ {obter_gasto_total_acumulado_zai():.6f}".replace(".", ",")
        except Exception:
            gasto_acumulado = 'Indisponível — confira o console'
        try:
            from deepseek_consumo import obter_gasto_total_sessao_deepseek
            gasto_deepseek_sessao = f'US$ {obter_gasto_total_sessao_deepseek():.6f}'.replace('.', ',')
        except Exception:
            gasto_deepseek_sessao = 'Indisponível — confira o console'
        try:
            from deepseek_consumo import obter_gasto_total_acumulado_deepseek
            gasto_deepseek_acumulado = f'US$ {obter_gasto_total_acumulado_deepseek():.6f}'.replace('.', ',')
        except Exception:
            gasto_deepseek_acumulado = 'Indisponível — confira o console'
        from ayla_embeddings import obter_status_carregamento, obter_status_indexacao
        from ayla_cerebro import obter_status_cerebro
        memoria_status = obter_status_cerebro()
        indexacao = obter_status_indexacao()
        from deepseek_catalog import is_peak_time
        values = {
            "Indexação de memórias": (
                f"{indexacao['indexadas']} indexadas · {indexacao['pendentes']} pendentes · "
                f"{indexacao['falhas']} com falha"
            ),
            "Carregamento de memória": obter_status_carregamento(),
            "Memorização automática": memoria_status.get("modelo_em_uso", "Aguardando análise"),
            "Discord": "Online" if ready else "Conectando",
            "Modelo": str(getattr(self.bot, "modelo_atual", "N/A")),
            "Chave API": str(getattr(self.bot, "idx_api_atual", 0) + 1),
            "APIs": str(len(getattr(self.bot, "api_keys", []))),
            "Memorias": str(len(self._load_mem())),
            "Contexto": f"{self._get_context_tokens():,} tokens",
            "Iniciar com o sistema": "Ativado" if self._is_startup_enabled() else "Desativado",
            "Tempo de Resposta": current_latency,
            "Tarefas simultâneas": str(runtime.get("interacoes_ativas",0)),
            "Sessão global": str(runtime.get("sessoes",0)),
            "Tarifa DeepSeek": 'Pico (estimado)' if is_peak_time() else 'Fora do pico · 50% do preço de pico',
            "Gasto GLM nesta sessão": f"US$ {gasto_sessao:.6f}".replace(".", ","),
            "Gasto GLM acumulado": gasto_acumulado,
            "Gasto DeepSeek nesta sessão": gasto_deepseek_sessao,
            "Gasto DeepSeek acumulado": gasto_deepseek_acumulado,
        }
        for key, value in values.items():
            label = self.status_labels.get(key)
            if label is not None:
                label.setText(value)
        self._refresh_zai_balance()
        self._refresh_deepseek_balance()
        if hasattr(self,"tasks_status_box"):
            import ayla_state
            active = ayla_state.listar_tarefas_detalhadas()
            recent = ayla_state.listar_tarefas_recentes()[:8]
            lines = [f"{t['status']} • {t['origem']} • {t['descricao']}" for t in active+recent]
            text = "\n".join(lines) or "Nenhuma tarefa em andamento."
            if self.tasks_status_box.toPlainText()!=text: self.tasks_status_box.setPlainText(text)
        if hasattr(self,"modules_status_box"):
            import Ayla
            lines = [f"{m['nome']} • {m['tipo']} • {m['status']}" + (f" • {m['erro']}" if m['erro'] else "") for m in Ayla._MODULE_MANAGER.status()]
            text = "\n".join(lines)
            if self.modules_status_box.toPlainText()!=text: self.modules_status_box.setPlainText(text)
        if hasattr(self, "model_active_label"):
            text = f"Modelo ativo: {getattr(self.bot, 'modelo_atual', 'N/A')}"
            recovery = getattr(self.bot, "_model_recovery", None)
            if recovery:
                from ayla_model_policy import normalize_policy
                policy = normalize_policy(getattr(self.bot, "model_policy", {}), [])
                remaining = max(1, policy["testar_a_cada"] - recovery.get("messages", 0))
                text += f" · Reserva em uso; teste do principal em {remaining} mensagem(ns)"
            self.model_active_label.setText(text)

    def _get_context_tokens(self):
        if hasattr(self.bot, 'obter_resumo_runtime'):
            return self.bot.obter_resumo_runtime().get('tokens_estimados', 0)
        try:
            session = getattr(self.bot, "chat_session", None)
            if not session:
                return 0
            total_chars = 0
            for message in session.get_history():
                total_chars += len(getattr(message, "text", "") or "")
                for attachment in getattr(message, "attachments", None) or []:
                    total_chars += min(len(getattr(attachment, "data", b"") or b""), 100_000)
            return int(total_chars / 4.5)
        except Exception:
            return 0

    def _poll_queues(self):
        # Trigger externo para recarregar a GUI por fora
        trigger_file = BASE_DIR / ".reload_gui_trigger"
        if trigger_file.exists():
            try:
                trigger_file.unlink()
            except Exception:
                pass
            print("[GUI] Trigger externo de reinicializacao detectado. Reiniciando interface...")
            QTimer.singleShot(50, self.reload_gui)
            return

        deadline = time.monotonic() + 0.008
        try:
            for _ in range(32):
                if time.monotonic() >= deadline:
                    break
                item = self.response_queue.get_nowait()
                kind = item[0]
                if kind == "memory_test_result":
                    self.memory_test_running = False
                    self.memory_test_button.setEnabled(True)
                    self.memory_test_status.setText(item[1])
                    self.memory_test_output.setPlainText(item[2])
                elif kind == "test":
                    self.model_test_label.setText(item[1])
                elif kind in ('gemini_catalog', 'groq_catalog', 'deepseek_catalog'):
                    from gemini_catalog import is_gemini
                    from groq_catalog import is_groq
                    from deepseek_catalog import is_deepseek, chat_model as deepseek_chat_model
                    is_provider, catalog_key, provider_label, provider_id = {
                        'groq_catalog': (is_groq, 'catalogo_groq', 'Groq', 'groq'),
                        'gemini_catalog': (is_gemini, 'catalogo_gemini', 'Gemini', 'gemini'),
                        'deepseek_catalog': (is_deepseek, 'catalogo_deepseek', 'DeepSeek', 'deepseek'),
                    }[kind]
                    models = item[1]
                    if provider_id == 'deepseek':
                        models = [m for m in models if deepseek_chat_model({'id': m})]
                    self.loaded_models[catalog_key] = models
                    # Catálogo separado da fila: atualizar não ativa novos fallbacks.
                    saved = self._safe_load_json(MODELS_PATH, {})
                    saved[catalog_key] = models
                    self._safe_write_json(MODELS_PATH, saved)
                    for combo in [*self.model_role_combos.values(), *self.model_mode_combos.values()]:
                        selected = combo.currentText()
                        combo.blockSignals(True)
                        for index in range(combo.count() - 1, -1, -1):
                            if is_provider(combo.itemText(index)):
                                combo.removeItem(index)
                        combo.addItems(models)
                        combo.setCurrentText(selected)
                        combo.blockSignals(False)
                    if self.compactor_provider.currentData() == provider_id:
                        selected = self.compactor_model.currentText()
                        self.compactor_model.clear()
                        self.compactor_model.addItems(models)
                        self.compactor_model.setCurrentText(selected)
                    self.model_test_label.setText(f'{len(models)} modelos {provider_label} de conversa listados pela API. Acesso e cota são verificados ao testar.')
                elif kind == "model_status_update":
                    self.model_status[item[1]] = {"status": item[2], "latency": item[3], "error": item[4]}
                    self._refresh_models_ui()
                elif kind == "latency_result":
                    if hasattr(self, "status_labels") and "Tempo de Resposta" in self.status_labels:
                        self.status_labels["Tempo de Resposta"].setText(item[1])
                elif kind == 'deepseek_balance_result':
                    # Uma resposta da chave anterior não pode sobrescrever a conta atual.
                    if item[1] != self._deepseek_balance_identity:
                        continue
                    self.deepseek_balance_refreshing = False
                    self.deepseek_balance_last_refresh = time.monotonic()
                    label = self.status_labels.get('Saldo DeepSeek')
                    if label is not None:
                        summary, details = self._format_deepseek_balance(item[2])
                        label.setText(summary)
                        label.setToolTip(details)
                elif kind == "zai_balance_result":
                    self.zai_balance_refreshing = False
                    self.zai_balance_last_refresh = time.monotonic()
                    if hasattr(self, "status_labels") and "Saldo Z.AI" in self.status_labels:
                        result = item[1]
                        self.status_labels["Saldo Z.AI"].setText(self._format_zai_balance_status(result))
                        self.status_labels["Saldo Z.AI"].setToolTip(str(result).replace("**", ""))
                elif kind == "fish_audio_result":
                    success = item[1]
                    msg = item[2]
                    if hasattr(self, "fish_audio_status"):
                        self.fish_audio_status.setText(msg)
                    self._toast("Fish Audio pronto" if success else "Fish Audio falhou")
                elif kind == "forgetting_item":
                    self._receive_forgetting_item(item[1], item[2])
                elif kind == "forgetting_deleted_one":
                    self._finish_forgetting_one(item[1], item[2], item[3])
                elif kind == "forgetting_progress":
                    self.forgetting_status.setText(item[1])
                elif kind in ("forgetting_result", "forgetting_deleted"):
                    self._finish_forgetting(kind, item[1], item[2])
                elif kind == "auto_memory_review_result":
                    self.auto_memory_review_running = False
                    relatorio = item[1]
                    if relatorio.get("ok"):
                        apagadas = relatorio.get("apagadas", [])
                        detalhes = "\n".join(
                            f"• {mem.get('chave', '')}: {mem.get('motivo', '')}" for mem in apagadas[:20]
                        )
                        if len(apagadas) > 20:
                            detalhes += f"\n• ... e mais {len(apagadas) - 20} memória(s)."
                        texto = (
                            f"Modelo: {relatorio.get('modelo', 'gptOSS_120b')}\n"
                            f"Memórias analisadas: {relatorio.get('analisadas', 0)}\n"
                            f"Memórias mantidas: {relatorio.get('mantidas', 0)}\n"
                            f"Memórias inúteis removidas: {len(apagadas)}\n"
                            f"Registros removidos do histórico automático: "
                            f"{relatorio.get('registros_log_removidos', 0)}"
                        )
                        if detalhes:
                            texto += f"\n\nRemovidas:\n{detalhes}"
                        QMessageBox.information(self, "Conferência concluída", texto)
                        self._refresh_auto_memory()
                        self._refresh_memory()
                    else:
                        QMessageBox.critical(
                            self,
                            "Conferência não realizada",
                            str(relatorio.get("mensagem", "Não foi possível conferir as memórias.")),
                        )
        except queue.Empty:
            pass
        chunks = []
        deadline = time.monotonic() + 0.004
        try:
            for _ in range(64):
                if time.monotonic() >= deadline:
                    break
                chunks.append(self.console_queue.get_nowait())
        except queue.Empty:
            pass
        chunk = "".join(chunks)
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
        if not IS_WINDOWS:
            return startup_path().is_file()
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
            if not IS_WINDOWS:
                enabled = not self._is_startup_enabled()
                set_startup(enabled)
                self._toast('Inicialização ativada' if enabled else 'Inicialização desativada')
                self._update_status()
                return
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
        if getattr(self, '_closing', False):
            return
        print("[GUI] Reiniciando interface grafica da Ayla...")
        app = QApplication.instance()
        if app:
            app.setQuitOnLastWindowClosed(False)

        self.poll_timer.stop()
        self.status_timer.stop()


        self._restore_streams()

        self._reloading_gui = True
        self.close()

        # Recarrega os modulos para que todas as alteracoes de codigo sejam aplicadas
        import importlib
        import sys
        if 'ayla_gui' in sys.modules:
            try:
                importlib.reload(sys.modules['ayla_gui'])
            except Exception as e:
                print(f"[GUI Reload] Erro ao recarregar o modulo ayla_gui: {e}")
        if 'ayla_live' in sys.modules:
            try:
                importlib.reload(sys.modules['ayla_live'])
            except Exception as e:
                print(f"[GUI Reload] Erro ao recarregar o modulo ayla_live: {e}")

        from ayla_gui import AylaGUI
        new_gui = AylaGUI(self.bot)
        new_gui._shutdown_callback = getattr(self, '_shutdown_callback', None)
        new_gui.show()

        if app:
            app.setQuitOnLastWindowClosed(True)

    def closeEvent(self, event):
        try:
            from deepseek_consumo import salvar_consumo_deepseek
            salvar_consumo_deepseek()
        except Exception as exc:
            print(f'⚠️ Não foi possível salvar o consumo DeepSeek ao fechar ({type(exc).__name__}).')
        try:
            from zai_provider import salvar_consumo_zai
            salvar_consumo_zai()
        except Exception as exc:
            print(f'⚠️ Não foi possível salvar o consumo Z.ai ao fechar ({type(exc).__name__}).')
        callback = getattr(self, '_shutdown_callback', None)
        if (callback is not None and not getattr(self, '_reloading_gui', False)
                and not getattr(self, '_shutdown_complete', False)):
            event.ignore()
            if not getattr(self, '_closing', False):
                if getattr(callback, 'requires_handoff_confirmation', False):
                    answer = QMessageBox.question(
                        self,
                        "Transferir Ayla para o host",
                        "Deseja transferir a Ayla para o host agora?\n\n"
                        "Ela só fechará neste computador depois que o host confirmar "
                        "o recebimento do estado e a inicialização da Ayla.",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No,
                    )
                    if answer != QMessageBox.StandardButton.Yes:
                        return
                self._closing = True
                self.setWindowTitle("Ayla — Transferindo estado para o host...")
                QTimer.singleShot(0, self._finish_shutdown)
            return
        self._stop_forgetting()
        self.end_shortcut.close()
        self._restore_streams()
        event.accept()

    def _finish_shutdown(self):
        callback = self._shutdown_callback
        transfer = getattr(callback, 'transfer_to_host_in_background', None)
        if callable(transfer):
            from PySide6.QtWidgets import QProgressDialog
            self._progress_dialog = QProgressDialog("Iniciando transferência para o host...", None, 0, 100, self)
            self._progress_dialog.setWindowTitle("Sincronizando com o Host")
            self._progress_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
            self._progress_dialog.setCancelButton(None)
            self._progress_dialog.setAutoClose(False)
            self._progress_dialog.setAutoReset(False)
            self._progress_dialog.setMinimumWidth(420)
            self._progress_dialog.setValue(0)
            self._progress_dialog.setStyleSheet(
                "QProgressDialog { background-color: #1e1e2e; color: #cdd6f4; font-family: 'Segoe UI', sans-serif; }"
                "QLabel { color: #89dceb; font-size: 13px; font-weight: bold; margin: 12px; }"
                "QProgressBar { border: 2px solid #313244; border-radius: 6px; text-align: center; color: #ffffff; background-color: #181825; height: 24px; font-weight: bold; }"
                "QProgressBar::chunk { background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #89dceb, stop:1 #cba6f7); border-radius: 4px; }"
            )
            self._progress_dialog.show()
            threading.Thread(
                target=self._run_handoff_transfer,
                args=(transfer,), daemon=True, name="AylaHostHandoff",
            ).start()
            return
        try:
            completed = callback()
            if completed is False:
                self._closing = False
                self.setWindowTitle("Ayla - Painel de Controle")
                return
        except Exception as exc:
            self._closing = False
            self.setWindowTitle("Ayla — Falha ao encerrar")
            print(f"[GUI] Não foi possível concluir o encerramento: {exc}")
            return
        self._shutdown_complete = True
        self.close()

    def _run_handoff_transfer(self, transfer):
        try:
            import inspect
            sig = inspect.signature(transfer)
            if 'on_progress' in sig.parameters:
                completed = bool(transfer(on_progress=lambda p, m: self.handoff_progress.emit(p, m)))
            else:
                completed = bool(transfer())
            self.handoff_finished.emit(completed, '')
        except Exception as exc:
            self.handoff_finished.emit(False, str(exc))

    def _on_handoff_progress(self, percent: int, message: str):
        if hasattr(self, '_progress_dialog') and self._progress_dialog is not None:
            self._progress_dialog.setValue(percent)
            self._progress_dialog.setLabelText(f"{message}\nProgresso: {percent}%")
        self.setWindowTitle(f"Ayla — Transferindo para o host [{percent}%]: {message}")

    def _on_handoff_finished(self, completed: bool, error: str):
        if hasattr(self, '_progress_dialog') and self._progress_dialog is not None:
            if completed:
                self._progress_dialog.setValue(100)
                self._progress_dialog.setLabelText("Transferência concluída com sucesso! (100%)")
            self._progress_dialog.close()
            self._progress_dialog = None
        if not completed:
            self._closing = False
            self.setWindowTitle("Ayla - Painel de Controle")
            if error:
                print(f"[GUI] Transferência para o host falhou: {error}")
            return
        try:
            finalize = getattr(self._shutdown_callback, 'finish_handoff_shutdown', self._shutdown_callback)
            finalize()
        except Exception as exc:
            self._closing = False
            self.setWindowTitle("Ayla — Falha ao encerrar")
            print(f"[GUI] Não foi possível concluir o encerramento: {exc}")
            return
        self._shutdown_complete = True
        self.close()


def abrir_gui(bot_instance, shutdown_callback=None):
    """Abre a interface grafica da Ayla em Qt/PySide6."""
    app = QApplication.instance()
    owns_app = app is None
    if app is None:
        app = QApplication(sys.argv)
    app.setApplicationName("Ayla")
    gui = AylaGUI(bot_instance)
    gui._shutdown_callback = shutdown_callback
    gui.show()
    code = app.exec() if owns_app else 0
    sys.exit(code)


if __name__ == "__main__":
    print("Esta GUI deve ser iniciada pelo Ayla.py, que passa a instancia do bot.")
    sys.exit(1)
