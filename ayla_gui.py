#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════
  🩵  AYLA GUI — Interface Gráfica de Controle
      Painel com Chat, Configurações e Monitoramento
═══════════════════════════════════════════════════════
"""

import customtkinter as ctk
from PIL import Image, ImageTk, ImageDraw
try:
    import cv2
except ImportError:
    cv2 = None
    import logging
    logging.warning('OpenCV (cv2) not installed. Video functionalities will be disabled. Please install opencv-python.')
import numpy as np
import threading
import queue
import json
import os
import sys
import time
import re
import io
import ctypes
from pathlib import Path
from datetime import datetime
from tkinter import filedialog
import tkinter as tk

# ══════════════════════════════════════════════════════════
#  CONSTANTES E CAMINHOS
# ══════════════════════════════════════════════════════════
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
MEMORIA_PATH = BASE_DIR / "Ayla_Memoria.json"
MODELS_PATH = BASE_DIR / "ayla_models.json"
ICON_PATH = BASE_DIR / "ico.png"
ICON_ICO_PATH = BASE_DIR / "ico.ico"
EMOJI_DIR = BASE_DIR / "emojis da ayla"

# ── Mapeamento automático: emojis do Discord → arquivos locais ──
DISCORD_EMOJI_MAP = {}
if EMOJI_DIR.exists():
    for _f in EMOJI_DIR.iterdir():
        if _f.is_file() and _f.suffix.lower() in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
            DISCORD_EMOJI_MAP[_f.stem.lower()] = str(_f)

_EMOJI_ALIASES = {
    "ena_olhando_perto": "ena_olhando_bem_pertinho",
}

# ══════════════════════════════════════════════════════════
#  PALETA DE CORES — TEMA AYLA 🩵 (IA Fofa e Moderna)
# ══════════════════════════════════════════════════════
C = {
    "bg":           "#12131c",      # Soft midnight dark
    "bg_r":         18,             # RGB for bg
    "bg_g":         19,             # RGB for bg
    "bg_b":         28,             # RGB for bg
    "sidebar":      "#161726",      # Soft dark sidebar
    "sidebar_sel":  "#7ee8fa",      # Pastel cyan selection
    "card":         "#1a1b2f",      # Cozy card background
    "card_hover":   "#252744",      # Hover highlight
    "input_bg":     "#12131c",      # Input background
    "input_border": "#2d304e",      # Input border
    "accent":       "#7ee8fa",      # Pastel cyan main
    "accent_hover": "#9af0ff",      # Lighter pastel cyan
    "accent_dark":  "#244a5e",      # Muted dark cyan
    "text":         "#f1f5f9",      # Crisp soft text
    "text2":        "#a5a9c0",      # Muted lavender-grey
    "text3":        "#626680",      # Deep muted lavender
    "green":        "#70e000",      # Cute lime-green
    "yellow":       "#ffd166",      # Pastel yellow
    "red":          "#ff5c8a",      # Pastel red/pink
    "user_msg":     "#222447",      # Cute indigo bubble
    "ayla_msg":     "#1b1d31",      # Cute dark-blue bubble
    "border":       "#26283f",      # Cute border line
    "pink":         "#ff9ebb",      # Cute pastel pink highlight
    "pink_hover":   "#ffb3c6",      # Lighter pink
}

FONT = "Century Gothic"
FONT_ROUND = "Arial Rounded MT Bold"


# ══════════════════════════════════════════════════════════
#  REDIRECIONAMENTO DE CONSOLE
# ══════════════════════════════════════════════════════

class ConsoleRedirector:
    def __init__(self, queue_obj, original_stream):
        self.queue = queue_obj
        self.original_stream = original_stream

    def write(self, text):
        if self.original_stream:
            try:
                self.original_stream.write(text)
            except Exception:
                pass
        self.queue.put(text)

    def flush(self):
        if self.original_stream:
            try:
                self.original_stream.flush()
            except Exception:
                pass


# ══════════════════════════════════════════════════════════
#  CLASSE PRINCIPAL
# ══════════════════════════════════════════════════════

class AylaGUI(ctk.CTk):
    """Interface gráfica principal da Ayla."""

    def __init__(self, bot_instance=None):
        super().__init__()
        self.bot = bot_instance
        self.response_queue = queue.Queue()

        # Redirecionar logs do console para a GUI
        self.console_queue = queue.Queue()
        self.stdout_redirector = ConsoleRedirector(self.console_queue, sys.stdout)
        self.stderr_redirector = ConsoleRedirector(self.console_queue, sys.stderr)
        sys.stdout = self.stdout_redirector
        sys.stderr = self.stderr_redirector

        self.pages = {}
        self.nav_buttons = {}
        self.nav_indicators = {}
        self.current_page = None
        self.attached_files = []
        self.msg_count = 0
        self.is_processing = False
        self.typing_label = None
        self.typing_frame_ref = None
        self.env_entries = {}
        self.env_raw_lines = []
        self.status_labels = {}
        self.emoji_cache = {}
        self._mini_icon_cache = None
        self.model_status = {}
        self._load_models_config()

        # Forçar o Windows a exibir o ícone personalizado na barra de tarefas
        try:
            myappid = "ayla.paineldecontrole.gui.v1"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

        # ── Janela ──
        self.title("🩵 Ayla — Painel de Controle")
        self.geometry("1120x740")
        self.minsize(960, 620)
        self.configure(fg_color=C["bg"])

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Ícone
        try:
            # 1. Tentar gerar o .ico a partir do .png se ele não existir
            if not ICON_ICO_PATH.exists() and ICON_PATH.exists():
                img = Image.open(ICON_PATH)
                img.save(ICON_ICO_PATH, format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])

            # 2. Definir o ícone usando iconbitmap (mais robusto no Windows)
            if ICON_ICO_PATH.exists():
                self.iconbitmap(str(ICON_ICO_PATH))
            elif ICON_PATH.exists():
                ico = Image.open(ICON_PATH).resize((32, 32), Image.LANCZOS)
                self._icon_ref = ImageTk.PhotoImage(ico)
                self.iconphoto(True, self._icon_ref)
        except Exception:
            pass

        # Polling (escutar fila sempre)
        self.after(150, self._poll_queue)

        # Fechar limpo
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        if self.bot is None:
            raise ValueError("A Ayla precisa estar aberta e iniciada para a GUI funcionar.")

        self._build_main_app()

    # ══════════════════════════════════════════════════════
    #  SIDEBAR
    # ══════════════════════════════════════════════════════

    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=210, fg_color=C["sidebar"], corner_radius=0)
        sb.grid(row=0, column=0, rowspan=2, sticky="nsw")
        sb.grid_propagate(False)

        # Título com ícone
        tf = ctk.CTkFrame(sb, fg_color="transparent")
        tf.pack(fill="x", padx=18, pady=(22, 6))

        title_row = ctk.CTkFrame(tf, fg_color="transparent")
        title_row.pack(anchor="w")

        try:
            file_path = DISCORD_EMOJI_MAP.get("ayla_fofa")
            if file_path and Path(file_path).exists():
                _ico_sidebar = Image.open(file_path).resize((36, 36), Image.LANCZOS)
                _ico_sidebar = self._round_corners(_ico_sidebar, 8)
                self._sidebar_icon = ctk.CTkImage(
                    light_image=_ico_sidebar, dark_image=_ico_sidebar, size=(36, 36))
                ctk.CTkLabel(title_row, image=self._sidebar_icon, text=""
                             ).pack(side="left", padx=(0, 8))
            elif ICON_PATH.exists():
                _ico_sidebar = Image.open(ICON_PATH).resize((36, 36), Image.LANCZOS)
                self._sidebar_icon = ctk.CTkImage(
                    light_image=_ico_sidebar, dark_image=_ico_sidebar, size=(36, 36))
                ctk.CTkLabel(title_row, image=self._sidebar_icon, text=""
                             ).pack(side="left", padx=(0, 8))
        except Exception:
            pass

        ctk.CTkLabel(title_row, text="Ayla 🩵", font=(FONT_ROUND, 24, "bold"),
                     text_color=C["accent"]).pack(side="left")
        ctk.CTkLabel(tf, text="Painel de Controle", font=(FONT, 11),
                     text_color=C["text2"]).pack(anchor="w", pady=(2, 2))

        ctk.CTkFrame(sb, height=1, fg_color=C["border"]).pack(fill="x", padx=18, pady=(10, 14))

        # Navegação
        items = [
            ("config", "⚙️  Configurações"),
            ("models", "🤖  Modelos"),
            ("gallery", "🖼️  Galeria"),
            ("videos",  "📹  Vídeos"),
            ("memory", "📝  Memória"),
            ("permissions", "🔑  Permissões"),
            ("blocked", "🚫  Bloqueados"),
            ("status", "📊  Status"),
            ("console", "💻  Console"),
        ]
        for key, label in items:
            btn_frame = ctk.CTkFrame(sb, fg_color="transparent")
            btn_frame.pack(fill="x", padx=6, pady=2)
            
            # Indicador vertical
            ind = ctk.CTkFrame(btn_frame, width=4, height=36, fg_color="transparent", corner_radius=2)
            ind.pack(side="left", padx=(4, 0))
            self.nav_indicators[key] = ind
            
            btn = ctk.CTkButton(
                btn_frame, text=label, anchor="w", font=(FONT, 13),
                height=38, corner_radius=10,
                fg_color="transparent", text_color=C["text2"],
                hover_color=C["card_hover"],
                command=lambda k=key: self._show_page(k),
            )
            btn.pack(side="left", fill="x", expand=True, padx=(4, 6))
            self.nav_buttons[key] = btn
            btn.pack(side="left", fill="x", expand=True, padx=(4, 6))
            self.nav_buttons[key] = btn

        # Rodapé da sidebar
        sb.pack_propagate(False)
        ctk.CTkFrame(sb, fg_color="transparent").pack(fill="both", expand=True)
        ctk.CTkLabel(sb, text="Ayla GUI v1.1 • Feito com amor 🩵", font=(FONT, 10),
                     text_color=C["text3"]).pack(pady=(0, 14))

    def _show_page(self, key):
        for k, btn in self.nav_buttons.items():
            ind = self.nav_indicators[k]
            if k == key:
                btn.configure(fg_color=C["card_hover"], text_color=C["accent"],
                               font=(FONT_ROUND, 13, "bold"))
                ind.configure(fg_color=C["pink"])
            else:
                btn.configure(fg_color="transparent", text_color=C["text2"],
                               font=(FONT, 13))
                ind.configure(fg_color="transparent")
        for k, frame in self.pages.items():
            if k == key:
                frame.grid(row=0, column=1, sticky="nsew")
            else:
                frame.grid_forget()
        self.current_page = key
        # Refresh dinâmico
        if key == "config":
            self._reload_env()
        elif key == "gallery":
            self._refresh_gallery_grid()
        elif key == "memory":
            self._refresh_memory()
        elif key == "status":
            self._update_status()
        elif key == "permissions":
            self._refresh_permissions_ui()
        elif key == "blocked":
            self._refresh_blocked_ui()

    def _round_corners(self, image, radius):
        """Aplica cantos arredondados em uma imagem PIL."""
        mask = Image.new("L", image.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle((0, 0) + image.size, radius, fill=255)
        
        rounded = Image.new("RGBA", image.size, (0, 0, 0, 0))
        rounded.paste(image, (0, 0), mask=mask)
        return rounded

    # ══════════════════════════════════════════════════════
    #  PÁGINA — CONFIGURAÇÕES (.env)
    # ══════════════════════════════════════════════════════

    def _build_config_page(self):
        page = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        self.pages["config"] = page
        page.grid_rowconfigure(1, weight=1)
        page.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(page, height=52, fg_color=C["card"], corner_radius=0)
        hdr.grid(row=0, column=0, sticky="new")
        hdr.grid_propagate(False)
        ctk.CTkLabel(hdr, text="✨ ⚙️ Configurações (.env) 🌸", font=(FONT_ROUND, 16, "bold"),
                     text_color=C["text"]).pack(side="left", padx=20, pady=12)
        ctk.CTkButton(
            hdr, text="💾 Salvar", width=100,
            fg_color=C["accent"], hover_color=C["accent_hover"],
            text_color="#000", font=(FONT_ROUND, 12, "bold"), corner_radius=12,
            command=self._save_env,
        ).pack(side="right", padx=(0, 20), pady=12)
        ctk.CTkButton(
            hdr, text="🔄 Recarregar", width=110,
            fg_color=C["card_hover"], hover_color=C["border"],
            text_color=C["text"], font=(FONT, 11), corner_radius=12,
            command=self._reload_env,
        ).pack(side="right", padx=(0, 6), pady=12)
        ctk.CTkButton(
            hdr, text="➕ Adicionar", width=110,
            fg_color=C["pink"], hover_color=C["pink_hover"],
            text_color="#000", font=(FONT_ROUND, 11, "bold"), corner_radius=12,
            command=self._add_env_dialog,
        ).pack(side="right", padx=(0, 6), pady=12)

        # Container do scroll (será recriado no reload)
        self.config_scroll_container = ctk.CTkFrame(page, fg_color=C["bg"])
        self.config_scroll_container.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        self.config_scroll_container.grid_rowconfigure(0, weight=1)
        self.config_scroll_container.grid_columnconfigure(0, weight=1)

        self._reload_env()

    def _reload_env(self):
        """Relê o .env do disco e reconstrói toda a interface de edição."""
        # Limpa o container anterior
        for w in self.config_scroll_container.winfo_children():
            w.destroy()
        self.env_entries = {}

        scroll = ctk.CTkScrollableFrame(
            self.config_scroll_container, fg_color=C["bg"],
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["accent_dark"]
        )
        scroll.grid(row=0, column=0, sticky="nsew", padx=14, pady=(6, 14))
        scroll.grid_columnconfigure(1, weight=1)

        if not ENV_PATH.exists():
            ctk.CTkLabel(scroll, text="⚠️ .env não encontrado!",
                         text_color=C["red"]).pack()
            return

        raw = ENV_PATH.read_text(encoding="utf-8")
        lines = raw.splitlines()

        sensitive_words = ("API_KEY", "TOKEN", "SECRET")
        row = 0

        for line in lines:
            s = line.strip()

            # Comentários viram títulos de seção
            if s.startswith("#") and len(s) > 1:
                row += 1
                label_text = s.lstrip("# ").strip()
                if label_text:
                    ctk.CTkLabel(
                        scroll, text=f"── {label_text} ──",
                        font=(FONT, 12, "bold"), text_color=C["accent"],
                    ).grid(row=row, column=0, columnspan=4, sticky="w",
                           padx=8, pady=(18, 4))
                continue

            if "=" not in s or s.startswith("#"):
                continue

            # Separar comentário se existir no final da linha
            line_no_comment = s
            comment = ""
            if " #" in s:
                line_no_comment, _, comment = s.partition(" #")
                comment = " #" + comment

            key, _, value = line_no_comment.partition("=")
            key = key.strip()
            value = value.strip()
            
            # Remove aspas do valor se existirem
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            elif value.startswith("'") and value.endswith("'"):
                value = value[1:-1]

            row += 1

            # Label da chave
            ctk.CTkLabel(
                scroll, text=key, font=(FONT, 11), text_color=C["text2"],
                anchor="w",
            ).grid(row=row, column=0, sticky="w", padx=(8, 12), pady=1.5)

            # Entry do valor
            is_sens = any(w in key.upper() for w in sensitive_words)
            entry = ctk.CTkEntry(
                scroll, font=(FONT, 12), fg_color=C["input_bg"],
                border_color=C["input_border"], text_color=C["text"],
                corner_radius=6, height=26,
                show="•" if is_sens else "",
            )
            entry.insert(0, value)
            entry.grid(row=row, column=1, sticky="ew", padx=4, pady=1.5)
            entry.bind("<FocusIn>", lambda e, ent=entry: ent.configure(border_color=C["accent"]))
            entry.bind("<FocusOut>", lambda e, ent=entry: ent.configure(border_color=C["input_border"]))
            
            self.env_entries[key] = {"entry": entry, "sensitive": is_sens}

            # Botão revelar (para campos sensíveis)
            if is_sens:
                ctk.CTkButton(
                    scroll, text="👁", width=34, height=26,
                    fg_color=C["card"], hover_color=C["border"],
                    corner_radius=6, font=(FONT, 12),
                    command=lambda e=entry: e.configure(
                        show="" if e.cget("show") == "•" else "•"
                    ),
                ).grid(row=row, column=2, padx=2, pady=1.5)

            # Botão remover
            ctk.CTkButton(
                scroll, text="🗑", width=34, height=26,
                fg_color=C["red"], hover_color="#d63b3b",
                text_color="#fff", corner_radius=6, font=(FONT, 12),
                command=lambda k=key: self._remove_env_var(k),
            ).grid(row=row, column=3, padx=(2, 8), pady=1.5)

    def _save_env(self):
        """Salva o .env relendo o arquivo original e substituindo por nome de chave."""
        try:
            if not ENV_PATH.exists():
                # Arquivo não existe - cria do zero com as extras atuais
                new_lines = [f"{k}={info['entry'].get().strip()}"
                             for k, info in self.env_entries.items()]
                ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
                self._toast("✅ .env criado com sucesso!")
                self._hot_reload_api_keys()
                return

            # Relê o arquivo original para preservar comentários e ordem
            original = ENV_PATH.read_text(encoding="utf-8").splitlines()
            keys_written = set()
            new_lines = []

            for line in original:
                s = line.strip()
                if "=" in s and not s.startswith("#"):
                    # Extrair a chave e o comentário original
                    line_no_comment = s
                    comment = ""
                    if " #" in s:
                        line_no_comment, _, comment = s.partition(" #")
                        comment = " #" + comment
                    
                    key = line_no_comment.partition("=")[0].strip()
                    if key in self.env_entries:
                        val = self.env_entries[key]["entry"].get().strip()
                        new_lines.append(f"{key}={val}{comment}")
                        keys_written.add(key)
                else:
                    new_lines.append(line)

            # Adiciona variáveis novas que não existiam no arquivo original
            for key, info in self.env_entries.items():
                if key not in keys_written:
                    val = info["entry"].get().strip()
                    new_lines.append(f"{key}={val}")

            ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
            self._toast("✅ .env salvo! APIs recarregadas na memória.")
            self._hot_reload_api_keys()
        except Exception as e:
            self._toast(f"❌ Erro ao salvar: {e}")

    def _hot_reload_api_keys(self):
        """Recarrega as chaves na memória em tempo real sem precisar reiniciar o bot."""
        try:
            import dotenv
            dotenv.load_dotenv(ENV_PATH, override=True)
            import os
            keys = [os.getenv(f"GEMINI_API_KEY_{i}", "") for i in range(1, 7)]
            keys = [k for k in keys if k.strip()]
            if keys and hasattr(self.bot, "api_keys"):
                self.bot.api_keys = keys
                self.bot.idx_api_atual = 0
                from google import genai
                self.bot.genai_client = genai.Client(api_key=keys[0])
                print("🩵 [GUI] APIs recarregadas com sucesso na memória do bot!")
        except Exception as e:
            print(f"⚠️ Erro ao recarregar chaves na memória: {e}")

    def _remove_env_var(self, key):
        """Remove uma variável do editor (será removida do .env ao salvar)."""
        if key in self.env_entries:
            del self.env_entries[key]
        self._save_env()
        self._reload_env()
        self._toast(f"🗑 Variável '{key}' removida!")

    def _add_env_dialog(self):
        """Diálogo para adicionar uma nova variável ao .env."""
        dlg = ctk.CTkToplevel(self)
        dlg.title("➕ Adicionar Variável")
        dlg.geometry("420x220")
        dlg.configure(fg_color=C["bg"])
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(False, False)

        ctk.CTkLabel(dlg, text="Nome da variável:", font=(FONT, 12),
                     text_color=C["text"]).pack(padx=22, pady=(22, 4), anchor="w")
        k_entry = ctk.CTkEntry(dlg, fg_color=C["input_bg"],
                               border_color=C["input_border"],
                               font=(FONT, 12), corner_radius=6,
                               placeholder_text="EX: MINHA_API_KEY")
        k_entry.pack(fill="x", padx=22, pady=(0, 8))
        k_entry.bind("<FocusIn>", lambda e: k_entry.configure(border_color=C["accent"]))
        k_entry.bind("<FocusOut>", lambda e: k_entry.configure(border_color=C["input_border"]))

        ctk.CTkLabel(dlg, text="Valor:", font=(FONT, 12),
                     text_color=C["text"]).pack(padx=22, pady=(4, 4), anchor="w")
        v_entry = ctk.CTkEntry(dlg, fg_color=C["input_bg"],
                               border_color=C["input_border"],
                               font=(FONT, 12), corner_radius=6)
        v_entry.pack(fill="x", padx=22, pady=(0, 14))
        v_entry.bind("<FocusIn>", lambda e: v_entry.configure(border_color=C["accent"]))
        v_entry.bind("<FocusOut>", lambda e: v_entry.configure(border_color=C["input_border"]))

        def _save():
            k = k_entry.get().strip()
            v = v_entry.get().strip()
            if not k:
                return
            # Adiciona direto no arquivo
            try:
                current = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""
                if current and not current.endswith("\n"):
                    current += "\n"
                current += f"{k}={v}\n"
                ENV_PATH.write_text(current, encoding="utf-8")
                dlg.destroy()
                self._reload_env()
                self._toast(f"✅ Variável '{k}' adicionada!")
                self._hot_reload_api_keys()
            except Exception as e:
                self._toast(f"❌ Erro: {e}")

        ctk.CTkButton(
            dlg, text="💾 Salvar", fg_color=C["accent"],
            hover_color=C["accent_hover"], text_color="#000",
            font=(FONT, 13, "bold"), command=_save,
        ).pack(pady=(4, 22))

    # ══════════════════════════════════════════════════════
    #  PÁGINA — MODELOS
    # ══════════════════════════════════════════════════════

    def _load_models_config(self):
        if MODELS_PATH.exists():
            try:
                self.loaded_models = json.loads(MODELS_PATH.read_text(encoding="utf-8"))
                # Limpar chaves que eram do openrouter para manter limpo
                if "openrouter" in self.loaded_models:
                    del self.loaded_models["openrouter"]
                if "modo" in self.loaded_models:
                    del self.loaded_models["modo"]
                return
            except Exception as e:
                print(f"⚠️ Erro ao ler ayla_models.json: {e}")
        
        # Fallback padrão
        raciocinar_defaults = [
            {"name": "gemini-3.5-flash", "desc": "Multimodal, Raciocínio Ativo Superior", "tags": ["🩵 Principal", "🖼️ Multimodal", "🧠 Raciocínio"]},
            {"name": "gemini-3-flash-preview", "desc": "Modelo Flash experimental de alta velocidade", "tags": ["🧪 Experimental", "⚡ Rápido"]},
            {"name": "gemini-2.5-flash", "desc": "Modelo intermediário equilibrado em velocidade e qualidade", "tags": ["🖼️ Multimodal", "⚡ Rápido"]},
            {"name": "gemma-4-31b-it", "desc": "Modelo aberto do Google de alto desempenho (Dense)", "tags": ["💬 Texto", "🔓 Aberto"]}
        ]
        padrao_defaults = [
            {"name": "gemini-3.1-flash-lite", "desc": "Ultra-rápido e altamente eficiente", "tags": ["⚡ Rápido", "🪙 Econômico", "🖼️ Multimodal"]},
            {"name": "gemini-2.5-flash-lite", "desc": "Modelo compacto rápido e econômico", "tags": ["🪙 Econômico", "⚡ Rápido"]},
            {"name": "gemma-4-31b-it", "desc": "Modelo aberto do Google de alto desempenho (Dense)", "tags": ["💬 Texto", "🔓 Aberto"]},
            {"name": "gemma-4-26b-a4b-it", "desc": "Modelo aberto do Google otimizado (MoE)", "tags": ["💬 Texto", "🔓 Aberto"]}
        ]
        self.loaded_models = {
            "raciocinar": raciocinar_defaults,
            "padrao": padrao_defaults
        }
        self._save_models_config()

    def _save_models_config(self):
        try:
            # Limpar chaves antigas se existirem
            if "openrouter" in self.loaded_models:
                del self.loaded_models["openrouter"]
            if "modo" in self.loaded_models:
                del self.loaded_models["modo"]
            MODELS_PATH.write_text(json.dumps(self.loaded_models, indent=4, ensure_ascii=False), encoding="utf-8")
            if hasattr(self, "bot") and self.bot:
                self.bot.modelos_avancados = [m["name"] for m in self.loaded_models["raciocinar"]]
                self.bot.modelos_padrao = [m["name"] for m in self.loaded_models["padrao"]]
                self.bot.modelos_disponiveis = self.bot.modelos_avancados + self.bot.modelos_padrao
        except Exception as e:
            print(f"⚠️ Erro ao salvar ayla_models.json: {e}")

    def _build_models_page(self):
        page = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        self.pages["models"] = page
        page.grid_rowconfigure(1, weight=1)
        page.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(page, height=52, fg_color=C["card"], corner_radius=0)
        hdr.grid(row=0, column=0, sticky="new")
        hdr.grid_propagate(False)
        ctk.CTkLabel(hdr, text="✨ 🤖 Gerenciamento de Modelos 🪐", font=(FONT_ROUND, 16, "bold"),
                     text_color=C["text"]).pack(side="left", padx=20, pady=12)
        ctk.CTkButton(
            hdr, text="🧪 Testar Todos", width=130,
            fg_color=C["accent"], hover_color=C["accent_hover"],
            text_color="#000", font=(FONT_ROUND, 12, "bold"), corner_radius=12,
            command=self._test_models,
        ).pack(side="right", padx=20, pady=12)

        self.models_scroll = ctk.CTkScrollableFrame(page, fg_color=C["bg"])
        self.models_scroll.grid(row=1, column=0, sticky="nsew", padx=14, pady=(6, 14))
        self.models_scroll.grid_columnconfigure(0, weight=1)

        self._refresh_models_ui()

    def _refresh_models_ui(self):
        # Limpar widgets anteriores
        for w in self.models_scroll.winfo_children():
            w.destroy()

        # Modelo ativo
        act = ctk.CTkFrame(self.models_scroll, fg_color=C["card"], corner_radius=14,
                           border_width=2, border_color=C["pink"])
        act.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 10))
        self.lbl_active_model = ctk.CTkLabel(
            act, text=f"📡 Modelo ativo: {getattr(self.bot, 'modelo_atual', 'N/A')} ✨",
            font=(FONT_ROUND, 14, "bold"), text_color=C["accent"],
        )
        self.lbl_active_model.pack(padx=18, pady=12)

        # Seção unificada de modelos
        sections_frame = ctk.CTkFrame(self.models_scroll, fg_color="transparent")
        sections_frame.grid(row=1, column=0, sticky="ew", padx=6, pady=4)
        sections_frame.grid_columnconfigure(0, weight=1)

        self._model_section_v2(
            sections_frame, 0, "⚡ Lista de Modelos da Ayla (Fallback)", "padrao",
            self.loaded_models.get("padrao", [])
        )

        # Resultados de teste
        self.test_frame = ctk.CTkFrame(self.models_scroll, fg_color=C["card"], corner_radius=14, border_width=1, border_color=C["border"])
        self.test_frame.grid(row=2, column=0, sticky="ew", padx=6, pady=(10, 6))
        self.test_lbl = ctk.CTkLabel(
            self.test_frame,
            text="🧪 Clique em 'Testar Todos' para verificar disponibilidade",
            font=(FONT, 12), text_color=C["text2"], justify="left", anchor="w",
        )
        self.test_lbl.pack(padx=18, pady=12, anchor="w")

    def _model_section_v2(self, parent, col, title, group_key, models_data):
        fr = ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=14,
                           border_width=1, border_color=C["border"])
        fr.grid(row=0, column=col, sticky="nsew", padx=6, pady=4)
        fr.grid_columnconfigure(0, weight=1)
        
        # Title of section with Add Button
        hdr_row = ctk.CTkFrame(fr, fg_color="transparent")
        hdr_row.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 10))
        hdr_row.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(hdr_row, text=title, font=(FONT_ROUND, 13, "bold"),
                     text_color=C["accent"]).pack(side="left")
                     
        ctk.CTkButton(
            hdr_row, text="➕", width=26, height=22,
            fg_color=C["pink"], hover_color=C["pink_hover"],
            text_color="#000", font=(FONT_ROUND, 11, "bold"), corner_radius=6,
            command=lambda gk=group_key: self._add_model_dialog(gk)
        ).pack(side="right")
        
        for idx, m_info in enumerate(models_data):
            # Check model health status
            status_info = None
            if hasattr(self, "bot") and self.bot and hasattr(self.bot, "model_status"):
                status_info = self.bot.model_status.get(m_info["name"])
            if not status_info:
                status_info = self.model_status.get(m_info["name"])
                
            card_border = C["border"]
            card_border_w = 1
            status_lbl_text = ""
            status_lbl_color = C["text2"]
            
            if status_info:
                st = status_info.get("status")
                lat = status_info.get("latency", "")
                err = status_info.get("error", "")
                if st == "ok":
                    card_border = C["green"]
                    card_border_w = 2
                    status_lbl_text = f"✅ Ativo ({lat})"
                    status_lbl_color = C["green"]
                elif st == "slow":
                    card_border = C["yellow"]
                    card_border_w = 2
                    status_lbl_text = f"⚠️ Lento ({lat})"
                    status_lbl_color = C["yellow"]
                elif st == "error":
                    card_border = C["red"]
                    card_border_w = 2
                    status_lbl_text = f"❌ Erro: {err[:35]}" + ("..." if len(err) > 35 else "")
                    status_lbl_color = C["red"]

            # Inner card for each model
            m_frame = ctk.CTkFrame(fr, fg_color=C["input_bg"], corner_radius=10,
                                   border_width=card_border_w, border_color=card_border)
            m_frame.grid(row=idx + 1, column=0, sticky="ew", padx=10, pady=4)
            m_frame.grid_columnconfigure(0, weight=1)
            
            # Header line of model card: Name and tags
            hdr_f = ctk.CTkFrame(m_frame, fg_color="transparent")
            hdr_f.grid(row=0, column=0, sticky="ew", padx=10, pady=(6, 2))
            
            # Model Name
            is_active = (getattr(self.bot, 'modelo_atual', '') == m_info["name"])
            name_color = C["accent"] if is_active else C["text"]
            name_font = (FONT_ROUND, 12, "bold") if is_active else (FONT, 11, "bold")
            
            lbl_name = ctk.CTkLabel(hdr_f, text=m_info["name"], font=name_font, text_color=name_color)
            lbl_name.pack(side="left")
            
            # If active, add a cute badge
            if is_active:
                badge = ctk.CTkLabel(hdr_f, text=" ATIVO ✨", font=(FONT_ROUND, 9, "bold"), text_color=C["pink"])
                badge.pack(side="left", padx=4)
            
            # Tags or Status details
            tags_f = ctk.CTkFrame(hdr_f, fg_color="transparent")
            tags_f.pack(side="right")
            
            # Add status text if present, otherwise show tags
            if status_lbl_text:
                lbl_st = ctk.CTkLabel(tags_f, text=status_lbl_text, font=(FONT, 9, "bold"), text_color=status_lbl_color)
                lbl_st.pack(side="right", padx=2)
            else:
                for tag in m_info["tags"]:
                    tag_bg = C["border"]
                    tag_fg = C["text2"]
                    if "Principal" in tag or "ATIVO" in tag:
                        tag_bg = C["pink"]
                        tag_fg = "#000"
                    elif "Multimodal" in tag:
                        tag_bg = C["accent_dark"]
                        tag_fg = C["accent"]
                    
                    tag_lbl = ctk.CTkLabel(tags_f, text=f" {tag} ", font=(FONT, 9),
                                           fg_color=tag_bg, text_color=tag_fg, corner_radius=4)
                    tag_lbl.pack(side="right", padx=2)
            
            # Description row (middle)
            desc_row = ctk.CTkFrame(m_frame, fg_color="transparent")
            desc_row.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))
            desc_row.grid_columnconfigure(0, weight=1)
            
            lbl_desc = ctk.CTkLabel(desc_row, text=m_info["desc"], font=(FONT, 10),
                                    text_color=C["text2"], justify="left", anchor="w")
            lbl_desc.pack(side="left")
            
            # Action controls row (bottom)
            ctrl_row = ctk.CTkFrame(m_frame, fg_color="transparent")
            ctrl_row.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 6))
            
            # Reorder buttons
            if idx > 0:
                ctk.CTkButton(
                    ctrl_row, text="▲", width=22, height=18,
                    fg_color=C["card_hover"], hover_color=C["border"],
                    text_color=C["text"], font=(FONT, 8, "bold"), corner_radius=4,
                    command=lambda gk=group_key, i=idx: self._move_model(gk, i, -1)
                ).pack(side="left", padx=1)
                
            if idx < len(models_data) - 1:
                ctk.CTkButton(
                    ctrl_row, text="▼", width=22, height=18,
                    fg_color=C["card_hover"], hover_color=C["border"],
                    text_color=C["text"], font=(FONT, 8, "bold"), corner_radius=4,
                    command=lambda gk=group_key, i=idx: self._move_model(gk, i, 1)
                ).pack(side="left", padx=1)
                
            # Remove button
            ctk.CTkButton(
                ctrl_row, text="🗑", width=22, height=18,
                fg_color=C["red"], hover_color="#d63b3b",
                text_color="#fff", font=(FONT, 8), corner_radius=4,
                command=lambda gk=group_key, i=idx: self._remove_model(gk, i)
            ).pack(side="right", padx=1)

    def _move_model(self, group_key, idx, direction):
        target_idx = idx + direction
        models_list = self.loaded_models[group_key]
        if 0 <= target_idx < len(models_list):
            models_list[idx], models_list[target_idx] = models_list[target_idx], models_list[idx]
            self._save_models_config()
            self._refresh_models_ui()

    def _remove_model(self, group_key, idx):
        models_list = self.loaded_models[group_key]
        m_name = models_list[idx]["name"]
        del models_list[idx]
        self._save_models_config()
        self._refresh_models_ui()
        self._toast(f"🗑️ Modelo '{m_name}' removido!")

    def _add_model_dialog(self, group_key):
        dlg = ctk.CTkToplevel(self)
        dlg.title("➕ Adicionar Modelo")
        dlg.geometry("440x300")
        dlg.configure(fg_color=C["bg"])
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(False, False)

        # Title
        mode_name = "Modelos de Raciocínio" if group_key == "raciocinar" else "Modelos Padrão"
        ctk.CTkLabel(dlg, text=f"Adicionar ao grupo: {mode_name}", font=(FONT_ROUND, 13, "bold"),
                     text_color=C["accent"]).pack(pady=(16, 12))

        # Model name input
        ctk.CTkLabel(dlg, text="Nome do modelo (ID da API):", font=(FONT, 11),
                      text_color=C["text"]).pack(padx=22, pady=(4, 2), anchor="w")
        name_entry = ctk.CTkEntry(dlg, fg_color=C["input_bg"], border_color=C["input_border"],
                                  font=(FONT, 11), corner_radius=6, placeholder_text="EX: gemini-2.5-pro")
        name_entry.pack(fill="x", padx=22, pady=(0, 8))
        name_entry.bind("<FocusIn>", lambda e: name_entry.configure(border_color=C["accent"]))
        name_entry.bind("<FocusOut>", lambda e: name_entry.configure(border_color=C["input_border"]))

        # Description input
        ctk.CTkLabel(dlg, text="Descrição:", font=(FONT, 11),
                      text_color=C["text"]).pack(padx=22, pady=(4, 2), anchor="w")
        desc_entry = ctk.CTkEntry(dlg, fg_color=C["input_bg"], border_color=C["input_border"],
                                  font=(FONT, 11), corner_radius=6, placeholder_text="EX: Modelo Pro de alta precisão")
        desc_entry.pack(fill="x", padx=22, pady=(0, 8))
        desc_entry.bind("<FocusIn>", lambda e: desc_entry.configure(border_color=C["accent"]))
        desc_entry.bind("<FocusOut>", lambda e: desc_entry.configure(border_color=C["input_border"]))

        # Tags input
        ctk.CTkLabel(dlg, text="Tags (separadas por vírgula):", font=(FONT, 11),
                      text_color=C["text"]).pack(padx=22, pady=(4, 2), anchor="w")
        tags_entry = ctk.CTkEntry(dlg, fg_color=C["input_bg"], border_color=C["input_border"],
                                  font=(FONT, 11), corner_radius=6, placeholder_text="EX: 🧠 Raciocínio, 🖼️ Multimodal")
        tags_entry.pack(fill="x", padx=22, pady=(0, 14))
        tags_entry.bind("<FocusIn>", lambda e: tags_entry.configure(border_color=C["accent"]))
        tags_entry.bind("<FocusOut>", lambda e: tags_entry.configure(border_color=C["input_border"]))

        def _save():
            name = name_entry.get().strip()
            desc = desc_entry.get().strip()
            tags_raw = tags_entry.get().strip()
            
            if not name:
                self._toast("⚠️ O nome do modelo é obrigatório!")
                return
            
            tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
            new_model = {
                "name": name,
                "desc": desc or "Modelo Gemini customizado",
                "tags": tags if tags else ["Custom"]
            }
            
            self.loaded_models[group_key].append(new_model)
            self._save_models_config()
            self._refresh_models_ui()
            dlg.destroy()
            self._toast(f"✅ Modelo '{name}' adicionado com sucesso!")

        ctk.CTkButton(
            dlg, text="💾 Salvar", fg_color=C["accent"],
            hover_color=C["accent_hover"], text_color="#000",
            font=(FONT_ROUND, 12, "bold"), corner_radius=12,
            command=_save,
        ).pack(pady=(4, 16))

    def _test_models(self):
        if hasattr(self, "test_lbl"):
            self.test_lbl.configure(text="⏳ Testando modelos... aguarde...")

        def _run():
            from google import genai as tg
            models = []
            for group in self.loaded_models.values():
                for m in group:
                    models.append(m["name"])
            key = self.bot.api_keys[0] if (hasattr(self, "bot") and self.bot and self.bot.api_keys) else ""
            if not key:
                self.response_queue.put(("test", "❌ Nenhuma API key disponível"))
                return
            client = tg.Client(api_key=key)
            lines = []
            for m in models:
                try:
                    t0 = time.time()
                    client.models.generate_content(model=m, contents="Responda apenas OK")
                    dur = time.time() - t0
                    lines.append(f"✅  {m}  —  {dur:.1f}s")
                    self.response_queue.put(("model_status_update", m, "slow" if dur > 5.0 else "ok", f"{dur:.1f}s", ""))
                except Exception as e:
                    err_msg = str(e)[:60]
                    lines.append(f"❌  {m}  —  {err_msg}")
                    self.response_queue.put(("model_status_update", m, "error", "N/A", err_msg))
            self.response_queue.put(("test", "\n".join(lines)))

        threading.Thread(target=_run, daemon=True).start()

    # ══════════════════════════════════════════════════════
    #  PÁGINA — GALERIA
    # ══════════════════════════════════════════════════════

    def _build_gallery_page(self):
        page = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        self.pages["gallery"] = page
        page.grid_rowconfigure(1, weight=1)
        page.grid_columnconfigure(0, weight=1)

        # Cabeçalho
        hdr = ctk.CTkFrame(page, height=52, fg_color=C["card"], corner_radius=0)
        hdr.grid(row=0, column=0, sticky="new")
        hdr.grid_propagate(False)
        ctk.CTkLabel(hdr, text="✨ 🖼️ Galeria de Fotos da Ayla 🎀", font=(FONT_ROUND, 16, "bold"),
                     text_color=C["text"]).pack(side="left", padx=20, pady=12)

        # Botão para atualizar
        ctk.CTkButton(
            hdr, text="🔄 Atualizar", width=100,
            fg_color=C["accent"], hover_color=C["accent_hover"],
            text_color="#000", font=(FONT_ROUND, 12, "bold"), corner_radius=12,
            command=self._refresh_gallery_grid,
        ).pack(side="right", padx=20, pady=12)

        # Conteúdo principal dividido em duas colunas (Esquerda: Grid, Direita: Detalhes)
        content = ctk.CTkFrame(page, fg_color=C["bg"])
        content.grid(row=1, column=0, sticky="nsew", padx=14, pady=(6, 14))
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=3) # Grid de miniaturas pega mais espaço
        content.grid_columnconfigure(1, weight=2) # Painel de detalhes

        # Esquerda: Grid Scrollable
        self.gallery_scroll = ctk.CTkScrollableFrame(content, fg_color=C["card"], corner_radius=12)
        self.gallery_scroll.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        
        # Direita: Painel de Controle
        self.gallery_ctrl = ctk.CTkFrame(content, fg_color=C["card"], corner_radius=12)
        self.gallery_ctrl.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        self._build_gallery_details_placeholder()

        # Cache de miniaturas e controle de seleção
        self._thumbnail_cache = {}
        self._selected_img_path = None

    def _build_gallery_details_placeholder(self):
        # Limpa painel de controle
        for w in self.gallery_ctrl.winfo_children():
            w.destroy()
            
        self.gallery_ctrl.grid_rowconfigure(0, weight=1)
        self.gallery_ctrl.grid_columnconfigure(0, weight=1)
        
        lbl = ctk.CTkLabel(
            self.gallery_ctrl, 
            text="🖼️ Selecione uma imagem\nna galeria para ver detalhes", 
            font=(FONT, 13), text_color=C["text2"], justify="center"
        )
        lbl.grid(row=0, column=0, sticky="nsew")

    def _refresh_gallery_grid(self):
        # Limpa o grid anterior
        for w in self.gallery_scroll.winfo_children():
            w.destroy()
            
        # Define as pastas para escanear
        projeto_raiz = Path(__file__).resolve().parent
        pastas = [
            projeto_raiz / "Aylafotitos"
        ]
        
        imagens = []
        for p in pastas:
            if p.exists():
                for ext in ("*.png", "*.jpg", "*.jpeg"):
                    imagens.extend(list(p.glob(ext)))
                    
        # Ordenar por data de modificação decrescente (mais recente primeiro)
        # Remove duplicados caso o mesmo arquivo seja listado em ambas as pastas
        imagens = sorted(list(set(imagens)), key=lambda x: x.stat().st_mtime, reverse=True)
        
        if not imagens:
            ctk.CTkLabel(
                self.gallery_scroll, 
                text="Nenhuma imagem gerada ainda 😿", 
                font=(FONT, 14), text_color=C["text3"]
            ).pack(expand=True, pady=100)
            self._build_gallery_details_placeholder()
            return
            
        # Layout de Grid responsivo (3 colunas)
        cols = 3
        for i in range(cols):
            self.gallery_scroll.grid_columnconfigure(i, weight=1, minsize=110)
            
        for idx, img_path in enumerate(imagens):
            row = idx // cols
            col = idx % cols
            
            # Cria botão com miniatura
            btn = self._create_thumbnail_button(img_path)
            btn.grid(row=row, column=col, padx=4, pady=4, sticky="nsew")

    def _create_thumbnail_button(self, img_path: Path):
        # Carrega a miniatura (usa cache se disponível)
        cache_key = str(img_path)
        mtime = img_path.stat().st_mtime
        
        if cache_key in self._thumbnail_cache and self._thumbnail_cache[cache_key]["mtime"] == mtime:
            ctk_img = self._thumbnail_cache[cache_key]["img"]
        else:
            try:
                pil_img = Image.open(img_path)
                pil_img.thumbnail((100, 100))
                
                # Garante que seja quadrada ou centralizada
                square = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
                square.paste(pil_img, ((100 - pil_img.width) // 2, (100 - pil_img.height) // 2))
                
                ctk_img = ctk.CTkImage(light_image=square, dark_image=square, size=(100, 100))
                self._thumbnail_cache[cache_key] = {"img": ctk_img, "mtime": mtime}
            except Exception:
                # Caso a imagem esteja corrompida ou inacessível
                ctk_img = None
                
        btn = ctk.CTkButton(
            self.gallery_scroll,
            text="",
            image=ctk_img,
            width=100,
            height=100,
            fg_color=C["card_hover"],
            hover_color=C["accent"],
            corner_radius=8,
            command=lambda p=img_path: self._select_gallery_image(p)
        )
        return btn

    def _select_gallery_image(self, img_path: Path):
        self._selected_img_path = img_path
        
        for w in self.gallery_ctrl.winfo_children():
            w.destroy()
            
        self.gallery_ctrl.grid_rowconfigure(0, weight=0) # Preview
        self.gallery_ctrl.grid_rowconfigure(1, weight=0) # Info
        self.gallery_ctrl.grid_rowconfigure(2, weight=1) # Espaço
        self.gallery_ctrl.grid_rowconfigure(3, weight=0) # Botões
        self.gallery_ctrl.grid_columnconfigure(0, weight=1)
        
        # 1. Preview da Imagem (tamanho ampliado)
        try:
            pil_img = Image.open(img_path)
            # Redimensiona mantendo proporção para encaixar em 240x240
            w_original, h_original = pil_img.size
            pil_img.thumbnail((240, 240))
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(pil_img.width, pil_img.height))
            
            preview_lbl = ctk.CTkLabel(self.gallery_ctrl, image=ctk_img, text="")
            preview_lbl.grid(row=0, column=0, pady=(18, 10))
        except Exception:
            w_original, h_original = 0, 0
            ctk.CTkLabel(self.gallery_ctrl, text="❌ Erro ao carregar pré-visualização").grid(row=0, column=0, pady=20)
            
        # 2. Informações/Metadados
        nome = img_path.name
        tamanho_kb = img_path.stat().st_size / 1024
        tamanho_str = f"{tamanho_kb:.1f} KB" if tamanho_kb < 1024 else f"{(tamanho_kb/1024):.2f} MB"
        data_mod = datetime.fromtimestamp(img_path.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
        
        info_text = (
            f"📄 Nome: {nome}\n"
            f"📐 Resolução: {w_original}x{h_original}\n"
            f"💾 Tamanho: {tamanho_str}\n"
            f"📅 Criado em: {data_mod}"
        )
        
        info_lbl = ctk.CTkLabel(
            self.gallery_ctrl, text=info_text, font=(FONT, 12),
            text_color=C["text2"], justify="left", anchor="w"
        )
        info_lbl.grid(row=1, column=0, padx=18, pady=6, sticky="ew")
        
        # 3. Spacer
        ctk.CTkFrame(self.gallery_ctrl, fg_color="transparent", height=1).grid(row=2, column=0, sticky="nsew")
        
        # 4. Botões de Ação
        btn_container = ctk.CTkFrame(self.gallery_ctrl, fg_color="transparent")
        btn_container.grid(row=3, column=0, padx=18, pady=18, sticky="ew")
        btn_container.grid_columnconfigure(0, weight=1)
        
        # Botão Wallpaper
        ctk.CTkButton(
            btn_container, text="🖼️ Definir como Wallpaper", font=(FONT, 12, "bold"),
            fg_color=C["green"], hover_color="#2ea043", text_color="#000",
            height=36, command=self._set_wallpaper
        ).grid(row=0, column=0, pady=4, sticky="ew")
        
        # Botão Explorer
        ctk.CTkButton(
            btn_container, text="📁 Abrir no Explorer", font=(FONT, 12, "bold"),
            fg_color=C["card_hover"], hover_color=C["border"], text_color=C["text"],
            height=36, command=self._open_explorer
        ).grid(row=1, column=0, pady=4, sticky="ew")
        
        # Botão Deletar
        ctk.CTkButton(
            btn_container, text="🗑️ Excluir Foto", font=(FONT, 12, "bold"),
            fg_color=C["red"], hover_color="#d63b3b", text_color="#fff",
            height=36, command=self._delete_image
        ).grid(row=2, column=0, pady=4, sticky="ew")

    def _set_wallpaper(self):
        if not self._selected_img_path or not self._selected_img_path.is_file():
            self._toast("⚠️ Nenhuma imagem selecionada!")
            return
            
        try:
            # Chama a API do Windows nativamente via ctypes (SystemParametersInfoW)
            # 20 = SPI_SETDESKWALLPAPER
            # 3 = SPIF_UPDATEINIFILE | SPIF_SENDCHANGE
            res = ctypes.windll.user32.SystemParametersInfoW(20, 0, str(self._selected_img_path), 3)
            if res:
                self._toast("🖼️ Papel de parede alterado!")
            else:
                self._toast("❌ Erro ao definir papel de parede.")
        except Exception as e:
            self._toast(f"❌ Erro: {e}")

    def _open_explorer(self):
        if not self._selected_img_path or not self._selected_img_path.is_file():
            self._toast("⚠️ Nenhuma imagem selecionada!")
            return
            
        try:
            # Abre o Explorer selecionando o arquivo específico no Windows
            os.system(f'explorer /select,"{str(self._selected_img_path)}"')
        except Exception as e:
            self._toast(f"❌ Erro ao abrir pasta: {e}")

    def _delete_image(self):
        if not self._selected_img_path or not self._selected_img_path.is_file():
            self._toast("⚠️ Nenhuma imagem selecionada!")
            return
            
        try:
            # Remove o arquivo físico
            self._selected_img_path.unlink()
            self._toast("🗑️ Foto excluída com sucesso!")
            
            # Limpa seleção e atualiza
            self._selected_img_path = None
            self._build_gallery_details_placeholder()
            self._refresh_gallery_grid()
        except Exception as e:
            self._toast(f"❌ Erro ao deletar: {e}")

    # ══════════════════════════════════════════════════════
    #  PÁGINA — VÍDEOS BAIXADOS (GALERIA DE VÍDEOS) 📹
    # ══════════════════════════════════════════════════════

    # ══════════════════════════════════════════════════════
    #  PÁGINA — VÍDEOS BAIXADOS (GALERIA DE VÍDEOS) 📹
    # ══════════════════════════════════════════════════════
    

    def _build_videos_page(self):
        page = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        self.pages["videos"] = page
        page.grid_rowconfigure(1, weight=1)
        page.grid_columnconfigure(0, weight=1)

        # Cabeçalho
        hdr = ctk.CTkFrame(page, height=52, fg_color=C["card"], corner_radius=0)
        hdr.grid(row=0, column=0, sticky="new")
        hdr.grid_propagate(False)
        ctk.CTkLabel(hdr, text="✨ 📹 Galeria de Vídeos Baixados 🌸", font=(FONT_ROUND, 16, "bold"),
                     text_color=C["text"]).pack(side="left", padx=20, pady=12)

        # Botão para atualizar
        ctk.CTkButton(
            hdr, text="🔄 Atualizar", width=100,
            fg_color=C["accent"], hover_color=C["accent_hover"],
            text_color="#000", font=(FONT_ROUND, 12, "bold"), corner_radius=12,
            command=self._refresh_videos_grid,
        ).pack(side="right", padx=20, pady=12)

        # Conteúdo principal dividido em duas colunas (Esquerda: Grid, Direita: Detalhes)
        content = ctk.CTkFrame(page, fg_color=C["bg"])
        content.grid(row=1, column=0, sticky="nsew", padx=14, pady=(6, 14))
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=3) # Grid de miniaturas pega mais espaço
        content.grid_columnconfigure(1, weight=2) # Painel de detalhes

        # Esquerda: Grid Scrollable
        self.videos_scroll = ctk.CTkScrollableFrame(content, fg_color=C["card"], corner_radius=12)
        self.videos_scroll.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        
        # Direita: Painel de Controle
        self.videos_ctrl = ctk.CTkFrame(content, fg_color=C["card"], corner_radius=12)
        self.videos_ctrl.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        self._build_video_details_placeholder()

        # Cache de miniaturas de vídeo e controle de seleção
        self._video_thumbnail_cache = {}
        self._selected_video_path = None

    def _build_video_details_placeholder(self):
        # Limpa painel de controle
        for w in self.videos_ctrl.winfo_children():
            w.destroy()
            
        self.videos_ctrl.grid_rowconfigure(0, weight=1)
        self.videos_ctrl.grid_columnconfigure(0, weight=1)
        
        lbl = ctk.CTkLabel(
            self.videos_ctrl, 
            text="📹 Selecione um vídeo\nna galeria para ver detalhes", 
            font=(FONT, 13), text_color=C["text2"], justify="center"
        )
        lbl.grid(row=0, column=0, sticky="nsew")

    def _refresh_videos_grid(self):
        # Limpa o grid anterior
        for w in self.videos_scroll.winfo_children():
            w.destroy()
            
        # Pasta de vídeos
        pasta = Path(BASE_DIR) / "VideosBaixados"
        if not pasta.exists():
            pasta.mkdir(parents=True, exist_ok=True)
        
        videos = []
        for ext in ("*.mp4", "*.mkv", "*.avi", "*.mov", "*.webm"):
            videos.extend(list(pasta.glob(ext)))
                    
        # Ordenar por data de modificação decrescente (mais recente primeiro)
        videos = sorted(list(set(videos)), key=lambda x: x.stat().st_mtime, reverse=True)
        
        if not videos:
            ctk.CTkLabel(
                self.videos_scroll, 
                text="Nenhum vídeo baixado ainda 😿", 
                font=(FONT, 14), text_color=C["text3"]
            ).pack(expand=True, pady=100)
            self._build_video_details_placeholder()
            return
            
        # Layout de Grid responsivo (2 colunas para vídeos)
        cols = 2
        for i in range(cols):
            self.videos_scroll.grid_columnconfigure(i, weight=1, minsize=160)
            
        for idx, vid_path in enumerate(videos):
            row = idx // cols
            col = idx % cols
            
            # Cria botão com miniatura do vídeo
            btn = self._create_video_card(vid_path)
            btn.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")

    def _create_video_card(self, vid_path: Path):
        # Cria um card contendo uma miniatura fofa e o nome do arquivo abaixo
        card = ctk.CTkFrame(self.videos_scroll, fg_color=C["input_bg"], corner_radius=10, border_width=1, border_color=C["border"])
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=0)

        # Tentamos gerar/carregar uma miniatura fofa
        cache_key = str(vid_path)
        mtime = vid_path.stat().st_mtime
        
        ctk_img = None
        if cache_key in self._video_thumbnail_cache and self._video_thumbnail_cache[cache_key]["mtime"] == mtime:
            ctk_img = self._video_thumbnail_cache[cache_key]["img"]
        else:
            try:
                pil_img = self._get_video_thumbnail(vid_path, size=(160, 90))
                if pil_img:
                    ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(160, 90))
                    self._video_thumbnail_cache[cache_key] = {"img": ctk_img, "mtime": mtime}
                else:
                    ctk_img = None # Fallback para o caso de _get_video_thumbnail falhar completamente
            except Exception as e:
                print(f"Erro ao carregar ou gerar thumbnail (cache): {e}")
                ctk_img = None # Fallback para o caso de erro

        # Botão que engloba a miniatura
        btn_img = ctk.CTkButton(
            card,
            text="",
            image=ctk_img,
            width=160,
            height=90,
            fg_color="transparent",
            hover_color=C["card_hover"],
            corner_radius=8,
            command=lambda p=vid_path: self._select_gallery_video(p)
        )
        btn_img.grid(row=0, column=0, padx=6, pady=6, sticky="nsew")

        # Texto do nome do vídeo truncado
        nome_curto = vid_path.name
        if len(nome_curto) > 22:
            nome_curto = nome_curto[:20] + "..."
            
        btn_txt = ctk.CTkButton(
            card,
            text=nome_curto,
            font=(FONT, 11),
            text_color=C["text2"],
            fg_color="transparent",
            hover=False,
            command=lambda p=vid_path: self._select_gallery_video(p)
        )
        btn_txt.grid(row=1, column=0, padx=4, pady=(0, 6), sticky="ew")

        return card

    def _select_gallery_video(self, vid_path: Path):
        self._selected_video_path = vid_path
        
        for w in self.videos_ctrl.winfo_children():
            w.destroy()
            
        self.videos_ctrl.grid_rowconfigure(0, weight=0) # Capa fofa grande
        self.videos_ctrl.grid_rowconfigure(1, weight=0) # Info
        self.videos_ctrl.grid_rowconfigure(2, weight=1) # Espaço
        self.videos_ctrl.grid_rowconfigure(3, weight=0) # Botões
        self.videos_ctrl.grid_columnconfigure(0, weight=1)
        
        # 1. Preview Grande Estilizado (Capa fofa com o emoji atual da Ayla)
        try:
            capa_lrg = Image.new("RGBA", (260, 146), C["sidebar"])
            draw = ImageDraw.Draw(capa_lrg)
            draw.rounded_rectangle((2, 2, 258, 144), radius=10, fill=C["card"], outline=C["pink"], width=2)
            
            # Tentar colocar um emoji bem fofo no centro
            file_path = DISCORD_EMOJI_MAP.get("ayla_feliz") or DISCORD_EMOJI_MAP.get("ayla_fofa")
            if file_path and Path(file_path).exists():
                logo = Image.open(file_path).resize((64, 64), Image.LANCZOS)
                capa_lrg.paste(logo, (20, 41), logo if logo.mode == 'RGBA' else None)

            # Botão de play central-direito
            draw.polygon([(140, 53), (140, 93), (180, 73)], fill=C["pink"])
            
            ctk_img = ctk.CTkImage(light_image=capa_lrg, dark_image=capa_lrg, size=(260, 146))
            
            preview_lbl = ctk.CTkLabel(self.videos_ctrl, image=ctk_img, text="")
            preview_lbl.grid(row=0, column=0, pady=(18, 10))
        except Exception:
            ctk.CTkLabel(self.videos_ctrl, text="Video Selecionado").grid(row=0, column=0, pady=20)
            
        # 2. Informações/Metadados do Vídeo
        nome = vid_path.name
        tamanho_kb = vid_path.stat().st_size / 1024
        tamanho_str = f"{tamanho_kb:.1f} KB" if tamanho_kb < 1024 else f"{(tamanho_kb/1024):.2f} MB"
        data_mod = datetime.fromtimestamp(vid_path.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
        
        info_text = f"🎥 Nome: {nome}\n💾 Tamanho: {tamanho_str}\n📅 Baixado em: {data_mod}"
        
        info_lbl = ctk.CTkLabel(
            self.videos_ctrl, text=info_text, font=(FONT, 12),
            text_color=C["text2"], justify="left", anchor="w"
        )
        info_lbl.grid(row=1, column=0, padx=18, pady=6, sticky="ew")
        
        # 3. Spacer
        ctk.CTkFrame(self.videos_ctrl, fg_color="transparent", height=1).grid(row=2, column=0, sticky="nsew")
        
        # 4. Botões de Ação
        btn_container = ctk.CTkFrame(self.videos_ctrl, fg_color="transparent")
        btn_container.grid(row=3, column=0, padx=18, pady=18, sticky="ew")
        btn_container.grid_columnconfigure(0, weight=1)
        
        # Botão Reproduzir
        ctk.CTkButton(
            btn_container, text="▶️ Reproduzir Vídeo", font=(FONT, 12, "bold"),
            fg_color=C["green"], hover_color="#2ea043", text_color="#000",
            height=36, command=self._play_video
        ).grid(row=0, column=0, pady=4, sticky="ew")
        
        # Botão Explorer
        ctk.CTkButton(
            btn_container, text="📁 Abrir no Explorer", font=(FONT, 12, "bold"),
            fg_color=C["card_hover"], hover_color=C["border"], text_color=C["text"],
            height=36, command=self._open_video_explorer
        ).grid(row=1, column=0, pady=4, sticky="ew")
        
        # Botão Deletar
        ctk.CTkButton(
            btn_container, text="🗑️ Excluir Vídeo", font=(FONT, 12, "bold"),
            fg_color=C["red"], hover_color="#d63b3b", text_color="#fff",
            height=36, command=self._delete_video
        ).grid(row=2, column=0, pady=4, sticky="ew")

    def _play_video(self):
        if not self._selected_video_path or not self._selected_video_path.is_file():
            self._toast("⚠️ Nenhum vídeo selecionado!")
            return
            
        try:
            os.startfile(str(self._selected_video_path))
            self._toast("▶️ Vídeo aberto no player do sistema!")
        except Exception as e:
            self._toast(f"❌ Erro ao reproduzir: {e}")

    def _open_video_explorer(self):
        if not self._selected_video_path or not self._selected_video_path.is_file():
            self._toast("⚠️ Nenhum vídeo selecionado!")
            return
            
        try:
            os.system(f'explorer /select,"{str(self._selected_video_path)}"')
        except Exception as e:
            self._toast(f"❌ Erro ao abrir pasta: {e}")

    def _delete_video(self):
        if not self._selected_video_path or not self._selected_video_path.is_file():
            self._toast("⚠️ Nenhum vídeo selecionado!")
            return
            
        try:
            self._selected_video_path.unlink()
            self._toast("🗑️ Vídeo excluído com sucesso!")
            
            self._selected_video_path = None
            self._build_video_details_placeholder()
            self._refresh_videos_grid()
        except Exception as e:
            self._toast(f"❌ Erro ao deletar: {e}")


    def _get_video_thumbnail(self, video_path: Path, size=(160, 90)):
        """
        Extrai uma thumbnail de um vídeo usando OpenCV.
        Cria uma thumbnail em cache, aplica cantos arredondados e adiciona um ícone de play.
        """
        # Verificar se OpenCV está disponível antes de processar thumbnail
        if cv2 is None:
            # Logar aviso e usar placeholder genérico
            import logging
            logging.warning('OpenCV não está disponível; usando thumbnail padrão.')
            return None
        try:
            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                print(f"Erro: Não foi possível abrir o vídeo {video_path}")
                return None

            ret, frame = cap.read()
            if not ret:
                print(f"Erro: Não foi possível ler o frame do vídeo {video_path}")
                return None

            cap.release()

            # Converter de BGR para RGB para PIL
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(frame_rgb)
            # Redimensionar a imagem mantendo a proporção e preenchendo o restante com a cor do card
            original_width, original_height = pil_image.size
            target_width, target_height = size

            ratio = min(target_width / original_width, target_height / original_height)
            new_width = int(original_width * ratio)
            new_height = int(original_height * ratio)

            resized_image = pil_image.resize((new_width, new_height), Image.LANCZOS)

            # Criar uma imagem de fundo com a cor do card
            background = Image.new("RGBA", size, C["card"])
            
            # Colar a imagem redimensionada no centro do fundo
            paste_x = (target_width - new_width) // 2
            paste_y = (target_height - new_height) // 2
            background.paste(resized_image, (paste_x, paste_y))

            # Aplicar cantos arredondados
            thumbnail = self._round_corners(background, 8) # Usar a função existente

            # Adicionar um ícone de play sobre a thumbnail (opcional, para manter o estilo)
            draw = ImageDraw.Draw(thumbnail)
            # Triângulo do play
            play_size = 20
            play_x = (size[0] - play_size) // 2 + 5 # Ajuste para centralizar visualmente o triângulo
            play_y = (size[1] - play_size) // 2
            draw.polygon(
                [(play_x + 2, play_y), (play_x + 2, play_y + play_size), (play_x + 2 + play_size * 0.8, play_y + play_size / 2)],
                fill=C["accent"]
            )
            # Círculo externo do play
            draw.ellipse(
                (play_x - 10, play_y - 10, play_x + play_size + 10, play_y + play_size + 10),
                outline=C["accent"], width=2
            )

            return thumbnail

        except Exception as e:
            print(f"Erro ao gerar thumbnail para {video_path}: {e}")
            # Retorna uma thumbnail padrão em caso de erro
            capa = Image.new("RGBA", size, C["sidebar"])
            draw = ImageDraw.Draw(capa)
            draw.rounded_rectangle((2, 2, size[0]-2, size[1]-2), radius=6, fill=C["card"], outline=C["accent_dark"], width=1)
            
            file_path = DISCORD_EMOJI_MAP.get("ayla_fofa")
            if file_path and Path(file_path).exists():
                logo = Image.open(file_path).resize((32, 32), Image.LANCZOS)
                capa.paste(logo, (8, size[1] - 32 - 4), logo if logo.mode == 'RGBA' else None) # Ajusta posição
            
            draw.polygon([(70, 35), (70, 55), (90, 45)], fill=C["accent"])
            return capa

    def _build_memory_page(self):
        page = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        self.pages["memory"] = page
        page.grid_rowconfigure(1, weight=1)
        page.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(page, height=52, fg_color=C["card"], corner_radius=0)
        hdr.grid(row=0, column=0, sticky="new")
        hdr.grid_propagate(False)
        ctk.CTkLabel(hdr, text="✨ 📝 Memória da Ayla 💫", font=(FONT_ROUND, 16, "bold"),
                     text_color=C["text"]).pack(side="left", padx=20, pady=12)
        ctk.CTkButton(
            hdr, text="➕ Adicionar", width=110,
            fg_color=C["pink"], hover_color=C["pink_hover"],
            text_color="#000", font=(FONT_ROUND, 12, "bold"), corner_radius=12,
            command=self._add_memory_dialog,
        ).pack(side="right", padx=20, pady=12)
        
        # Filtro de busca na memória
        self.mem_search_entry = ctk.CTkEntry(
            hdr, width=180, placeholder_text="🔍 Buscar memória...",
            fg_color=C["input_bg"], border_color=C["input_border"],
            font=(FONT, 11), corner_radius=10
        )
        self.mem_search_entry.pack(side="right", padx=(0, 10), pady=12)
        self.mem_search_entry.bind("<KeyRelease>", lambda e: self._refresh_memory())
        self.mem_search_entry.bind("<FocusIn>", lambda e: self.mem_search_entry.configure(border_color=C["accent"]))
        self.mem_search_entry.bind("<FocusOut>", lambda e: self.mem_search_entry.configure(border_color=C["input_border"]))

        # Filtro de Categoria/Tags na memória
        self.mem_tag_filter = ctk.CTkOptionMenu(
            hdr, values=["Todas", "Favoritas", "Sentimentais", "Técnicas", "Gerais"],
            width=120, height=28,
            fg_color=C["input_bg"], button_color=C["border"],
            button_hover_color=C["accent"], text_color=C["text"],
            font=(FONT, 11), dropdown_font=(FONT, 11),
            command=lambda v: self._refresh_memory()
        )
        self.mem_tag_filter.pack(side="right", padx=(0, 10), pady=12)
        self.mem_tag_filter.set("Todas")

        self.mem_scroll = ctk.CTkScrollableFrame(
            page, fg_color=C["bg"],
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["accent_dark"]
        )
        self.mem_scroll.grid(row=1, column=0, sticky="nsew", padx=14, pady=(6, 14))
        self.mem_scroll.grid_columnconfigure(0, weight=1)

    def _load_mem(self):
        if MEMORIA_PATH.exists():
            try:
                return json.loads(MEMORIA_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_mem(self, data):
        MEMORIA_PATH.parent.mkdir(parents=True, exist_ok=True)
        MEMORIA_PATH.write_text(json.dumps(data, indent=4, ensure_ascii=False),
                                encoding="utf-8")

    def _refresh_memory(self):
        for w in self.mem_scroll.winfo_children():
            w.destroy()
        mem = self._load_mem()
        if not mem:
            ctk.CTkLabel(self.mem_scroll, text="Nenhuma memória salva ainda 📭",
                         font=(FONT, 13), text_color=C["text2"]).grid(row=0, pady=20)
            return

        search_query = self.mem_search_entry.get().strip().lower() if hasattr(self, "mem_search_entry") else ""
        selected_tag = self.mem_tag_filter.get() if hasattr(self, "mem_tag_filter") else "Todas"
        row_idx = 0

        for k, v in mem.items():
            if search_query and (search_query not in k.lower() and search_query not in str(v).lower()):
                continue

            # Extração da tag
            mem_tag = "Gerais"
            if isinstance(v, dict):
                mem_tag = v.get("tag", v.get("Tag", "Gerais"))

            if selected_tag != "Todas" and mem_tag.lower() != selected_tag.lower():
                continue

            fr = ctk.CTkFrame(self.mem_scroll, fg_color=C["card"], corner_radius=12,
                              border_width=1, border_color=C["border"])
            fr.grid(row=row_idx, column=0, sticky="ew", padx=4, pady=3)
            fr.grid_columnconfigure(1, weight=1)
            fr.grid_columnconfigure(2, weight=1)
            row_idx += 1

            ctk.CTkLabel(fr, text=f"🔑 {k}", font=(FONT, 12, "bold"),
                         text_color=C["accent"], anchor="w"
                         ).grid(row=0, column=0, sticky="w", padx=14, pady=(10, 0))

            # Badge da tag
            tag_colors = {
                "favoritas": C["pink"],
                "sentimentais": "#b388ff",
                "técnicas": "#80deea",
                "gerais": C["text3"]
            }
            tag_color = tag_colors.get(mem_tag.lower(), C["text3"])
            
            ctk.CTkLabel(fr, text=f"🏷️ {mem_tag}", font=(FONT, 10, "bold"),
                         text_color=tag_color, anchor="w"
                         ).grid(row=0, column=1, sticky="w", padx=4, pady=(10, 0))

            if isinstance(v, dict) and "Data e hora" in v and "Valor" in v:
                val_txt = v.get("Valor", "")
                dt_txt = v.get("Data e hora", "")
                lbl_val_txt = f"{val_txt}\n📅 Salvo em: {dt_txt}"
            elif isinstance(v, dict) and "valor" in v and "data_hora" in v:
                val_txt = v.get("valor", "")
                dt_txt = v.get("data_hora", "")
                lbl_val_txt = f"{val_txt}\n📅 Salvo em: {dt_txt}"
            elif isinstance(v, dict) and "Valor" in v:
                val_txt = v.get("Valor", "")
                dt_txt = v.get("Data e hora", "N/A")
                lbl_val_txt = f"{val_txt}\n📅 Salvo em: {dt_txt}"
            else:
                lbl_val_txt = str(v)

            ctk.CTkLabel(fr, text=lbl_val_txt, font=(FONT, 11), text_color=C["text"],
                         anchor="w", wraplength=480, justify="left"
                         ).grid(row=1, column=0, columnspan=3, sticky="w",
                                padx=14, pady=(2, 10))
            ctk.CTkButton(
                fr, text="🗑", width=34, height=28,
                fg_color=C["red"], hover_color="#d63b3b",
                text_color="#fff", corner_radius=6, font=(FONT, 12),
                command=lambda key=k: self._del_memory(key),
            ).grid(row=0, column=2, sticky="e", padx=14, pady=(10, 0))

    def _del_memory(self, key):
        mem = self._load_mem()
        mem.pop(key, None)
        self._save_mem(mem)
        self._refresh_memory()
        
        try:
            if self.bot and hasattr(self.bot, "atualizar_prompt_memoria"):
                self.bot.atualizar_prompt_memoria()
        except Exception as e:
            print(f"⚠️ Erro ao atualizar memórias do bot a partir da GUI: {e}")

        self._toast(f"🗑 Memória '{key}' deletada!")

    def _add_memory_dialog(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("➕ Adicionar Memória")
        dlg.geometry("420x300")
        dlg.configure(fg_color=C["bg"])
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(False, False)

        ctk.CTkLabel(dlg, text="Chave:", font=(FONT, 12),
                     text_color=C["text"]).pack(padx=22, pady=(22, 4), anchor="w")
        k_entry = ctk.CTkEntry(dlg, fg_color=C["input_bg"],
                               border_color=C["input_border"],
                               font=(FONT, 12), corner_radius=6)
        k_entry.pack(fill="x", padx=22, pady=(0, 8))
        k_entry.bind("<FocusIn>", lambda e: k_entry.configure(border_color=C["accent"]))
        k_entry.bind("<FocusOut>", lambda e: k_entry.configure(border_color=C["input_border"]))

        ctk.CTkLabel(dlg, text="Valor:", font=(FONT, 12),
                     text_color=C["text"]).pack(padx=22, pady=(4, 4), anchor="w")
        v_entry = ctk.CTkEntry(dlg, fg_color=C["input_bg"],
                               border_color=C["input_border"],
                               font=(FONT, 12), corner_radius=6)
        v_entry.pack(fill="x", padx=22, pady=(0, 8))
        v_entry.bind("<FocusIn>", lambda e: v_entry.configure(border_color=C["accent"]))
        v_entry.bind("<FocusOut>", lambda e: v_entry.configure(border_color=C["input_border"]))

        ctk.CTkLabel(dlg, text="Categoria/Tag:", font=(FONT, 12),
                     text_color=C["text"]).pack(padx=22, pady=(4, 4), anchor="w")
        tag_menu = ctk.CTkOptionMenu(
            dlg, values=["Favoritas", "Sentimentais", "Técnicas", "Gerais"],
            fg_color=C["input_bg"], button_color=C["border"],
            button_hover_color=C["accent"], text_color=C["text"],
            font=(FONT, 12), dropdown_font=(FONT, 12)
        )
        tag_menu.pack(fill="x", padx=22, pady=(0, 14))
        tag_menu.set("Gerais")

        def _save():
            k = k_entry.get().strip()
            v = v_entry.get().strip()
            t = tag_menu.get()
            if k and v:
                mem = self._load_mem()
                from datetime import datetime
                agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                mem[k] = {
                    "Data e hora": agora,
                    "Valor": v,
                    "tag": t
                }
                self._save_mem(mem)
                self._refresh_memory()
                
                try:
                    if self.bot and hasattr(self.bot, "atualizar_prompt_memoria"):
                        self.bot.atualizar_prompt_memoria()
                except Exception as e:
                    print(f"⚠️ Erro ao atualizar memórias do bot a partir da GUI: {e}")

                dlg.destroy()
                self._toast(f"✅ Memória '{k}' adicionada!")

        ctk.CTkButton(
            dlg, text="💾 Salvar", fg_color=C["accent"],
            hover_color=C["accent_hover"], text_color="#000",
            font=(FONT, 13, "bold"), command=_save,
        ).pack(pady=(4, 22))

    # ══════════════════════════════════════════════════════
    #  PÁGINA — STATUS
    # ══════════════════════════════════════════════════════

    def _is_startup_enabled(self):
        try:
            import winreg
            REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
            REG_NAME = "AylaGUI"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_READ)
            value, _ = winreg.QueryValueEx(key, REG_NAME)
            winreg.CloseKey(key)
            return True
        except Exception:
            return False

    def _toggle_startup(self):
        try:
            import winreg
            REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
            REG_NAME = "AylaGUI"
            
            currently_enabled = self._is_startup_enabled()
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY, 0, winreg.KEY_WRITE)
            
            if not currently_enabled:
                if getattr(sys, 'frozen', False):
                    cmd = f'"{sys.executable}"'
                else:
                    cmd = f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}"'
                winreg.SetValueEx(key, REG_NAME, 0, winreg.REG_SZ, cmd)
                self._toast("🚀 Iniciar com o Windows ativado!")
            else:
                try:
                    winreg.DeleteValue(key, REG_NAME)
                except WindowsError:
                    pass
                self._toast("💤 Iniciar com o Windows desativado!")
            
            winreg.CloseKey(key)
            self._update_status()
        except Exception as e:
            self._toast(f"❌ Erro ao configurar: {e}")

    def _build_status_page(self):
        page = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        self.pages["status"] = page
        page.grid_rowconfigure(1, weight=1)
        page.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(page, height=52, fg_color=C["card"], corner_radius=0)
        hdr.grid(row=0, column=0, sticky="new")
        hdr.grid_propagate(False)
        ctk.CTkLabel(hdr, text="✨ 📊 Status do Sistema 🍀", font=(FONT_ROUND, 16, "bold"),
                     text_color=C["text"]).pack(side="left", padx=20, pady=12)

        scroll = ctk.CTkScrollableFrame(page, fg_color=C["bg"])
        scroll.grid(row=1, column=0, sticky="nsew", padx=14, pady=(6, 14))
        scroll.grid_columnconfigure(0, weight=1)

        # Card de Inicialização com o Windows
        startup_card = ctk.CTkFrame(scroll, fg_color=C["card"], corner_radius=14,
                                    border_width=2, border_color=C["pink"])
        startup_card.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 10))
        startup_card.grid_columnconfigure(1, weight=1)

        left_startup_f = ctk.CTkFrame(startup_card, fg_color="transparent")
        left_startup_f.grid(row=0, column=0, sticky="w", padx=18, pady=14)

        ctk.CTkLabel(left_startup_f, text="🚀  Iniciar com o Windows", font=(FONT_ROUND, 13, "bold"),
                     text_color=C["accent"]).pack(anchor="w")
        ctk.CTkLabel(left_startup_f, text="Ative para a Ayla acordar junto com seu computador! ✨", 
                     font=(FONT, 11), text_color=C["text2"]).pack(anchor="w", pady=(2, 0))

        self.startup_var = ctk.BooleanVar(value=self._is_startup_enabled())
        self.startup_switch = ctk.CTkSwitch(
            startup_card, text="", variable=self.startup_var,
            command=self._toggle_startup,
            progress_color=C["pink"], fg_color=C["border"],
            button_color=C["accent"], button_hover_color=C["accent_hover"]
        )
        self.startup_switch.grid(row=0, column=1, sticky="e", padx=18, pady=14)

        items = [
            ("bot",     "🤖  Status do Bot Discord"),
            ("model",   "📡  Modelo Atual"),
            ("api_idx", "🔑  API Key Ativa"),
            ("keys",    "🔑  Total de API Keys"),
            ("mems",    "📝  Memórias Salvas"),
            ("msgs",    "💬  Mensagens nesta sessão"),
        ]
        for i, (key, label) in enumerate(items):
            card = ctk.CTkFrame(scroll, fg_color=C["card"], corner_radius=12,
                                border_width=1, border_color=C["border"])
            card.grid(row=i + 1, column=0, sticky="ew", padx=6, pady=4)
            card.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(card, text=label, font=(FONT, 13),
                         text_color=C["text2"]).grid(row=0, column=0, sticky="w",
                                                     padx=18, pady=14)
            vl = ctk.CTkLabel(card, text="...", font=(FONT, 13, "bold"),
                              text_color=C["text"])
            vl.grid(row=0, column=1, sticky="e", padx=18, pady=14)
            self.status_labels[key] = vl

    def _update_status(self):
        try:
            mm = sys.modules.get("__main__")
            ready = self.bot.is_ready() if hasattr(self.bot, "is_ready") else False
            launch_err = getattr(mm, "BOT_LAUNCH_ERROR", None) if mm else None

            if launch_err:
                self.status_labels["bot"].configure(
                    text="🔴 Erro de Login: Token Inválido!",
                    text_color=C["red"],
                )
            else:
                self.status_labels["bot"].configure(
                    text="🟢 Online" if ready else "🟡 Conectando...",
                    text_color=C["green"] if ready else C["yellow"],
                )
            self.status_labels["model"].configure(
                text=getattr(self.bot, "modelo_atual", "N/A"))
            idx = getattr(self.bot, "idx_api_atual", 0)
            self.status_labels["api_idx"].configure(text=f"Chave {idx + 1}")
            self.status_labels["keys"].configure(
                text=str(len(getattr(self.bot, "api_keys", []))))
            self.status_labels["mems"].configure(text=str(len(self._load_mem())))
            self.status_labels["msgs"].configure(text=str(self.msg_count))
            
            if hasattr(self, "startup_var"):
                self.startup_var.set(self._is_startup_enabled())
        except Exception:
            pass

    # ══════════════════════════════════════════════════════
    #  PÁGINA — PERMISSÕES DO MODO PÚBLICO 🔑
    # ══════════════════════════════════════════════════════

    def _get_available_tools(self):
        """Lê os nomes de todas as ferramentas disponíveis no diretório MODOS/."""
        pastas = [BASE_DIR / "MODOS"]
        tools = []
        for p in pastas:
            if p.exists():
                for arq in p.glob("*.py"):
                    tools.append(arq.stem)
        return sorted(list(set(tools)))

    def _load_permissions(self):
        """Carrega as permissões do arquivo ayla_permissions.json ou usa os padrões."""
        path = BASE_DIR / "ayla_permissions.json"
        defaults = {
            "public_mode": False,
            "allowed_tools": [
                "calcular",
                "jokenpo",
                "dado_rpg",
                "cara_ou_coroa",
                "sortear",
                "consultar_clima",
                "conversor_moeda",
                "conversor_unidades",
                "horario_mundial",
                "pesquisar_pokedex",
                "informacao_astronautas"
            ]
        }
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for k, v in defaults.items():
                        if k not in data:
                            data[k] = v
                    return data
            except Exception as e:
                print(f"⚠️ Erro ao ler ayla_permissions.json: {e}")
        return defaults

    def _save_permissions(self, data):
        """Salva as permissões no arquivo ayla_permissions.json e notifica o bot."""
        path = BASE_DIR / "ayla_permissions.json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            
            # Sincroniza em tempo real com o bot
            if self.bot and hasattr(self.bot, "carregar_permissoes"):
                self.bot.carregar_permissoes()
                print("🩵 [GUI] Permissões recarregadas na memória do bot com sucesso!")
        except Exception as e:
            print(f"⚠️ Erro ao salvar ayla_permissions.json: {e}")

    def _build_permissions_page(self):
        page = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        self.pages["permissions"] = page
        page.grid_rowconfigure(1, weight=1)
        page.grid_columnconfigure(0, weight=1)

        # Header
        hdr = ctk.CTkFrame(page, height=52, fg_color=C["card"], corner_radius=0)
        hdr.grid(row=0, column=0, sticky="new")
        hdr.grid_propagate(False)
        ctk.CTkLabel(hdr, text="✨ 🔑 Permissões do Modo Público 🎀", font=(FONT_ROUND, 16, "bold"),
                      text_color=C["text"]).pack(side="left", padx=20, pady=12)

        # Botão Salvar
        ctk.CTkButton(
            hdr, text="💾 Salvar", width=100,
            fg_color=C["accent"], hover_color=C["accent_hover"],
            text_color="#000", font=(FONT_ROUND, 12, "bold"), corner_radius=12,
            command=self._save_permissions_from_ui,
        ).pack(side="right", padx=20, pady=12)

        # Scroll area
        self.permissions_scroll = ctk.CTkScrollableFrame(
            page, fg_color=C["bg"],
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["accent_dark"]
        )
        self.permissions_scroll.grid(row=1, column=0, sticky="nsew", padx=14, pady=(6, 14))
        self.permissions_scroll.grid_columnconfigure(0, weight=1)

    def _refresh_permissions_ui(self):
        # Limpa widgets anteriores
        for w in self.permissions_scroll.winfo_children():
            w.destroy()

        data = self._load_permissions()

        # Master switch card
        master_card = ctk.CTkFrame(self.permissions_scroll, fg_color=C["card"], corner_radius=14,
                                    border_width=2, border_color=C["pink"])
        master_card.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 10))
        master_card.grid_columnconfigure(1, weight=1)

        left_f = ctk.CTkFrame(master_card, fg_color="transparent")
        left_f.grid(row=0, column=0, sticky="w", padx=18, pady=14)

        ctk.CTkLabel(left_f, text="🌐  Modo Público Ativado", font=(FONT_ROUND, 13, "bold"),
                     text_color=C["accent"]).pack(anchor="w")
        ctk.CTkLabel(left_f, text="Permite que outras pessoas interajam com a Ayla no Discord. Ferramentas não marcadas abaixo serão bloqueadas para outros usuários.", 
                     font=(FONT, 11), text_color=C["text2"]).pack(anchor="w", pady=(2, 0))

        self.public_mode_var = ctk.BooleanVar(value=data.get("public_mode", False))
        self.public_mode_switch = ctk.CTkSwitch(
            master_card, text="", variable=self.public_mode_var,
            progress_color=C["pink"], fg_color=C["border"],
            button_color=C["accent"], button_hover_color=C["accent_hover"]
        )
        self.public_mode_switch.grid(row=0, column=1, sticky="e", padx=18, pady=14)

        # Section title
        ctk.CTkLabel(
            self.permissions_scroll, text="🛠️  Ações Permitidas no Modo Público",
            font=(FONT_ROUND, 12, "bold"), text_color=C["accent"]
        ).grid(row=1, column=0, sticky="w", padx=8, pady=(12, 4))

        # List all tools with checkboxes and descriptions from function declarations
        tools = self._get_available_tools()
        self.tool_vars = {}

        tool_descriptions = {}
        if self.bot and hasattr(self.bot, "tools_config") and self.bot.tools_config:
            try:
                for tool in self.bot.tools_config:
                    if hasattr(tool, "function_declarations") and tool.function_declarations:
                        for fd in tool.function_declarations:
                            tool_descriptions[fd.name] = fd.description
            except Exception as e:
                print(f"⚠️ Erro ao obter descrições de ferramentas: {e}")

        allowed_set = set(data.get("allowed_tools", []))

        row_idx = 2
        for t_name in tools:
            card = ctk.CTkFrame(self.permissions_scroll, fg_color=C["card"], corner_radius=10,
                                border_width=1, border_color=C["border"])
            card.grid(row=row_idx, column=0, sticky="ew", padx=6, pady=3)
            card.grid_columnconfigure(0, weight=1)
            row_idx += 1

            t_var = ctk.BooleanVar(value=(t_name in allowed_set))
            self.tool_vars[t_name] = t_var

            desc = tool_descriptions.get(t_name, "Sem descrição disponível.")

            chk_frame = ctk.CTkFrame(card, fg_color="transparent")
            chk_frame.pack(fill="x", padx=14, pady=8)

            chk = ctk.CTkCheckBox(
                chk_frame, text=t_name, variable=t_var,
                font=(FONT_ROUND, 12, "bold"), text_color=C["text"],
                fg_color=C["pink"], hover_color=C["pink_hover"],
                border_color=C["border"], corner_radius=6
            )
            chk.pack(side="left", padx=(0, 10))

            lbl_desc = ctk.CTkLabel(
                chk_frame, text=f"—  {desc}", font=(FONT, 11),
                text_color=C["text2"], anchor="w", justify="left"
            )
            lbl_desc.pack(side="left", fill="x", expand=True)

    def _save_permissions_from_ui(self):
        allowed = []
        for t_name, var in self.tool_vars.items():
            if var.get():
                allowed.append(t_name)
        
        data = {
            "public_mode": self.public_mode_var.get(),
            "allowed_tools": allowed
        }
        self._save_permissions(data)
        self._toast("💾 Permissões salvas!")

    # ══════════════════════════════════════════════════════
    #  PÁGINA — LISTA DE BLOQUEADOS 🚫
    # ══════════════════════════════════════════════════════

    def _load_blocked_users(self) -> list:
        """Carrega a lista de IDs de usuários bloqueados do arquivo ayla_blocked_users.json."""
        path = BASE_DIR / "ayla_blocked_users.json"
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return [int(uid) for uid in data]
            except Exception as e:
                print(f"⚠️ Erro ao ler ayla_blocked_users.json: {e}")
        return []

    def _save_blocked_users(self, data: list):
        """Salva a lista de bloqueados no json e notifica o bot."""
        path = BASE_DIR / "ayla_blocked_users.json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            
            # Sincroniza em tempo real com o bot
            if self.bot and hasattr(self.bot, "carregar_bloqueados"):
                self.bot.carregar_bloqueados()
                print("🩵 [GUI] Lista de bloqueados sincronizada com o bot!")
        except Exception as e:
            print(f"⚠️ Erro ao salvar ayla_blocked_users.json: {e}")

    def _build_blocked_page(self):
        page = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        self.pages["blocked"] = page
        page.grid_rowconfigure(1, weight=1)
        page.grid_columnconfigure(0, weight=1)

        # Header
        hdr = ctk.CTkFrame(page, height=52, fg_color=C["card"], corner_radius=0)
        hdr.grid(row=0, column=0, sticky="new")
        hdr.grid_propagate(False)
        ctk.CTkLabel(hdr, text="✨ 🚫 Lista de Bloqueados (Discord) 🔒", font=(FONT_ROUND, 16, "bold"),
                      text_color=C["text"]).pack(side="left", padx=20, pady=12)

        # Adicionar novo ID
        add_f = ctk.CTkFrame(hdr, fg_color="transparent")
        add_f.pack(side="right", padx=20, pady=12)

        self.block_id_entry = ctk.CTkEntry(
            add_f, placeholder_text="ID do Discord (ex: 781299507056869379)",
            width=260, height=28, font=(FONT, 11),
            fg_color=C["input_bg"], border_color=C["input_border"],
            text_color=C["text"], corner_radius=6
        )
        self.block_id_entry.pack(side="left", padx=(0, 6))
        self.block_id_entry.bind("<FocusIn>", lambda e: self.block_id_entry.configure(border_color=C["accent"]))
        self.block_id_entry.bind("<FocusOut>", lambda e: self.block_id_entry.configure(border_color=C["input_border"]))

        ctk.CTkButton(
            add_f, text="➕ Bloquear", width=90, height=28,
            fg_color=C["red"], hover_color="#d63b3b",
            text_color="#fff", font=(FONT_ROUND, 11, "bold"), corner_radius=6,
            command=self._add_blocked_user,
        ).pack(side="left")

        # Container
        self.blocked_scroll = ctk.CTkScrollableFrame(
            page, fg_color=C["bg"],
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["accent_dark"]
        )
        self.blocked_scroll.grid(row=1, column=0, sticky="nsew", padx=14, pady=(6, 14))
        self.blocked_scroll.grid_columnconfigure(0, weight=1)

    def _refresh_blocked_ui(self):
        # Limpa widgets anteriores
        for w in self.blocked_scroll.winfo_children():
            w.destroy()

        blocked_list = self._load_blocked_users()

        if not blocked_list:
            ctk.CTkLabel(
                self.blocked_scroll, text="Nenhum usuário bloqueado no momento 😇",
                font=(FONT, 13), text_color=C["text2"]
            ).grid(row=0, column=0, pady=40, sticky="ew")
            return

        row_idx = 0
        for uid in blocked_list:
            card = ctk.CTkFrame(self.blocked_scroll, fg_color=C["card"], corner_radius=10,
                                 border_width=1, border_color=C["border"])
            card.grid(row=row_idx, column=0, sticky="ew", padx=6, pady=3)
            card.grid_columnconfigure(0, weight=1)
            row_idx += 1

            # Lado Esquerdo: ID e Informações
            left_f = ctk.CTkFrame(card, fg_color="transparent")
            left_f.pack(side="left", padx=14, pady=8)

            # Tenta resolver o nome do usuário a partir do bot se possível
            username = "Usuário Desconhecido"
            if self.bot and hasattr(self.bot, "get_user"):
                try:
                    user_obj = self.bot.get_user(uid)
                    if user_obj:
                        username = user_obj.display_name
                except Exception:
                    pass

            ctk.CTkLabel(
                left_f, text=f"🚫  ID: {uid}", font=(FONT_ROUND, 12, "bold"),
                text_color=C["red"]
            ).pack(anchor="w")

            ctk.CTkLabel(
                left_f, text=f"Nome Resolvido: {username}", font=(FONT, 10),
                text_color=C["text2"]
            ).pack(anchor="w", pady=(1, 0))

            # Lado Direito: Botão Desbloquear
            ctk.CTkButton(
                card, text="🗑 Desbloquear", width=110, height=26,
                fg_color=C["card_hover"], hover_color=C["border"],
                text_color=C["text"], font=(FONT_ROUND, 10, "bold"), corner_radius=6,
                command=lambda u=uid: self._remove_blocked_user(u)
            ).pack(side="right", padx=14, pady=8)

    def _add_blocked_user(self):
        raw_id = self.block_id_entry.get().strip()
        if not raw_id:
            self._toast("⚠️ Insira um ID válido!")
            return

        if not raw_id.isdigit():
            self._toast("⚠️ O ID do Discord deve conter apenas números!")
            return

        uid = int(raw_id)
        blocked_list = self._load_blocked_users()

        if uid in blocked_list:
            self._toast("⚠️ Esse usuário já está bloqueado!")
            return

        blocked_list.append(uid)
        self._save_blocked_users(blocked_list)
        self.block_id_entry.delete(0, "end")
        self._refresh_blocked_ui()
        self._toast(f"🚫 Usuário {uid} bloqueado com sucesso!")

    def _remove_blocked_user(self, uid: int):
        blocked_list = self._load_blocked_users()
        if uid in blocked_list:
            blocked_list.remove(uid)
            self._save_blocked_users(blocked_list)
            self._refresh_blocked_ui()
            self._toast(f"🔓 Usuário {uid} desbloqueado!")

    # ══════════════════════════════════════════════════════
    #  PÁGINA — CONSOLE / LOGS
    # ══════════════════════════════════════════════════════

    def _build_console_page(self):
        page = ctk.CTkFrame(self, fg_color=C["bg"], corner_radius=0)
        self.pages["console"] = page
        page.grid_rowconfigure(1, weight=1)
        page.grid_columnconfigure(0, weight=1)

        # Header
        hdr = ctk.CTkFrame(page, height=52, fg_color=C["card"], corner_radius=0)
        hdr.grid(row=0, column=0, sticky="new")
        hdr.grid_propagate(False)
        ctk.CTkLabel(hdr, text="✨ 💻 Console de Logs 🛠️", font=(FONT_ROUND, 16, "bold"),
                     text_color=C["text"]).pack(side="left", padx=20, pady=12)

        # Botão Limpar
        ctk.CTkButton(
            hdr, text="🗑️ Limpar Logs", width=110,
            fg_color=C["red"], hover_color="#d63b3b",
            text_color="#fff", font=(FONT_ROUND, 11, "bold"),
            corner_radius=12,
            command=self._clear_console_logs,
        ).pack(side="right", padx=20, pady=12)

        # Checkbox Auto-scroll
        self.console_autoscroll = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            hdr, text="Auto-scroll", variable=self.console_autoscroll,
            fg_color=C["pink"], hover_color=C["pink_hover"],
            border_color=C["border"], font=(FONT_ROUND, 11),
            corner_radius=6,
        ).pack(side="right", padx=5, pady=12)

        # Área de Texto do Console
        self.console_text_widget = ctk.CTkTextbox(
            page, fg_color=C["card"], border_color=C["border"], border_width=1,
            font=("Consolas", 11), text_color="#c5cdd8", corner_radius=10, wrap="word"
        )
        self.console_text_widget.grid(row=1, column=0, sticky="nsew", padx=14, pady=(6, 14))
        self.console_text_widget.configure(state="disabled")

    def _clear_console_logs(self):
        if hasattr(self, "console_text_widget"):
            try:
                self.console_text_widget.configure(state="normal")
                self.console_text_widget.delete("1.0", "end")
                self.console_text_widget.configure(state="disabled")
            except Exception:
                pass

    # ══════════════════════════════════════════════════════
    #  BARRA DE STATUS (RODAPÉ)
    # ══════════════════════════════════════════════════════

    def _get_context_tokens(self):
        if not self.bot or not getattr(self.bot, "chat_session", None):
            return 0
        try:
            history = self.bot.chat_session.get_history()
            total_chars = 0
            for content in history:
                if hasattr(content, "parts") and content.parts:
                    for part in content.parts:
                        if hasattr(part, "text") and part.text:
                            total_chars += len(part.text)
            # Estimativa de tokens para PT-BR/EN: ~4.5 caracteres por token
            estimated_tokens = int(total_chars / 4.5)
            return min(max(estimated_tokens, 0), 1000000)
        except Exception:
            return 0

    def _build_statusbar(self):
        bar = ctk.CTkFrame(self, height=32, fg_color=C["card"], corner_radius=0)
        bar.grid(row=1, column=0, columnspan=2, sticky="sew")
        bar.grid_propagate(False)

        self.sb_left = ctk.CTkLabel(bar, text="🟡 Conectando...",
                                    font=(FONT, 10), text_color=C["yellow"])
        self.sb_left.pack(side="left", padx=18)

        self.sb_middle = ctk.CTkLabel(bar, text="🧠 Uso de Tokens/Contexto: 0 / 1.000.000 (0.00%)",
                                      font=(FONT, 10), text_color=C["pink"])
        self.sb_middle.pack(side="left", expand=True, fill="x", padx=18)

        self.sb_right = ctk.CTkLabel(bar, text="", font=(FONT, 10),
                                     text_color=C["text3"])
        self.sb_right.pack(side="right", padx=18)

    def _update_statusbar(self):
        try:
            mm = sys.modules.get("__main__")
            ready = self.bot.is_ready() if hasattr(self.bot, "is_ready") else False
            launch_err = getattr(mm, "BOT_LAUNCH_ERROR", None) if mm else None

            if launch_err:
                self.sb_left.configure(text="🔴 Erro de Login no Discord!",
                                       text_color=C["red"])
            elif ready:
                name = self.bot.user.name if self.bot.user else "Ayla"
                self.sb_left.configure(text=f"🟢 {name} Online",
                                       text_color=C["green"])
            else:
                self.sb_left.configure(text="🟡 Conectando ao Discord...",
                                       text_color=C["yellow"])

            # Monitor dinâmico de tokens no rodapé
            tokens = self._get_context_tokens()
            pct = (tokens / 1000000.0) * 100.0
            self.sb_middle.configure(text=f"🧠 Uso de Tokens/Contexto: {tokens:,} / 1.000.000 ({pct:.2f}%)")

            model = getattr(self.bot, "modelo_atual", "")
            self.sb_right.configure(text=f"Modelo: {model}")
        except Exception:
            pass

    # ══════════════════════════════════════════════════════
    #  POLLING & TIMER
    # ══════════════════════════════════════════════════════

    def _poll_queue(self):
        try:
            while True:
                item = self.response_queue.get_nowait()
                kind = item[0]

                if kind == "test":
                    self.test_lbl.configure(text=item[1])
                elif kind == "model_status_update":
                    m_name = item[1]
                    status_val = item[2]
                    latency_val = item[3]
                    err_msg = item[4]
                    self.model_status[m_name] = {
                        "status": status_val,
                        "latency": latency_val,
                        "error": err_msg
                    }
                    if self.current_page == "models":
                        self._refresh_models_ui()
        except queue.Empty:
            pass

        # Processar logs do console
        try:
            log_text = ""
            while True:
                log_text += self.console_queue.get_nowait()
        except queue.Empty:
            pass

        if log_text and hasattr(self, "console_text_widget"):
            try:
                self.console_text_widget.configure(state="normal")
                self.console_text_widget.insert("end", log_text)
                # Limitar tamanho para evitar consumo excessivo de memória
                content_len = len(self.console_text_widget.get("1.0", "end"))
                if content_len > 120000:
                    self.console_text_widget.delete("1.0", "1.10000") # remove o início se passar de ~100k chars
                self.console_text_widget.configure(state="disabled")
                if self.console_autoscroll.get():
                    self.console_text_widget.see("end")
            except Exception:
                pass

        self.after(150, self._poll_queue)

    def _status_tick(self):
        self._update_statusbar()
        if hasattr(self, "lbl_active_model"):
            try:
                self.lbl_active_model.configure(
                    text=f"📡 Modelo ativo: {getattr(self.bot, 'modelo_atual', 'N/A')}"
                )
            except Exception:
                pass
        if self.current_page == "status":
            self._update_status()
        self.after(4000, self._status_tick)

    # ══════════════════════════════════════════════════════
    #  UTILITÁRIOS
    # ══════════════════════════════════════════════════════

    def _toast(self, msg, dur=3500):
        """Notificação flutuante temporária."""
        t = ctk.CTkFrame(self, fg_color=C["card"], border_color=C["pink"], border_width=1, corner_radius=14)
        t.place(relx=0.5, rely=0.94, anchor="center")
        ctk.CTkLabel(t, text=msg, font=(FONT, 12, "bold"),
                     text_color=C["accent"]).pack(padx=22, pady=10)
        self.after(dur, t.destroy)

    def _on_close(self):
        try:
            sys.stdout = self.stdout_redirector.original_stream
            sys.stderr = self.stderr_redirector.original_stream
        except Exception:
            pass
        self.destroy()
        os._exit(0)

    # ══════════════════════════════════════════════════════
    #  INICIALIZAÇÃO EM SEGUNDO PLANO (BACKGROUND LOADER)
    # ══════════════════════════════════════════════════════

    def _build_main_app(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_config_page()
        self._build_models_page()
        self._build_gallery_page()
        self._build_videos_page()
        self._build_memory_page()
        self._build_permissions_page()
        self._build_blocked_page()
        self._build_status_page()
        self._build_console_page()
        self._build_statusbar()

        self._show_page("config")
        self.after(3000, self._status_tick)


def abrir_gui(bot_instance):
    """Abre a interface gráfica (GUI) da Ayla de forma opcional, passando a própria instância da Ayla."""
    if bot_instance is None:
        raise ValueError("A Ayla precisa estar aberta e iniciada para a GUI funcionar.")

    gui = AylaGUI(bot_instance)
    gui.mainloop()



if __name__ == "__main__":
    try:
        # A GUI não abre a Ayla de forma independente.
        # Ela exige que o script principal (Ayla.py) seja executado.
        import tkinter.messagebox as messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Ayla Painel de Controle",
            "Esta interface gráfica só funciona se for iniciada através da Ayla (Ayla.py)!"
        )
        sys.exit(1)
    except Exception as e:
        print(f"⚠️ Erro ao abrir GUI diretamente: {e}")
