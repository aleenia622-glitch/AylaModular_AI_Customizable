"""Envia uma imagem da aba de status da Ayla com os logs."""
from __future__ import annotations
import subprocess

import io
import json
import os
import sys
from pathlib import Path
from typing import Any

# Adiciona o diretório base ao sys.path para importações dos módulos centrais da Ayla
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    import ayla_state
except ImportError:
    ayla_state = None

from PIL import Image, ImageDraw, ImageFont

ENV_PATH = BASE_DIR / ".env"
MEMORIA_PATH = BASE_DIR / "Ayla_Memoria.json"
SETTINGS_PATH = BASE_DIR / "ayla_settings.json"


def _carregar_fonte(nome_fonte: str, tamanho: int):
    candidates = []
    if os.name == 'nt' and os.environ.get('WINDIR'):
        candidates.append(str(Path(os.environ['WINDIR']) / 'Fonts' / nome_fonte))
    else:
        try:
            family = 'sans:style=Bold' if 'bold' in nome_fonte.lower() or 'bd.' in nome_fonte.lower() else 'sans'
            result = subprocess.run(['fc-match', '-f', '%{file}', family], capture_output=True, text=True, timeout=3, check=True)
            candidates.append(result.stdout.strip())
        except (OSError, subprocess.SubprocessError):
            pass
    candidates += [nome_fonte, 'DejaVuSans.ttf']
    for candidate in candidates:
        if candidate:
            try:
                return ImageFont.truetype(candidate, tamanho)
            except OSError:
                pass
    return ImageFont.load_default(size=tamanho)


def obter_dados_status(
    bot: Any = None,
    gui: Any = None,
    logs: str | list[str] | None = None
) -> dict[str, Any]:
    """
    Coleta os dados de status REAIS da Ayla a partir dos objetos bot/gui ativos
    ou lê os arquivos do sistema (.env, Ayla_Memoria.json, ayla_settings.json).
    """
    # Se o bot não foi passado explicitamente, tenta localizar a instância ativa no sistema
    if bot is None:
        if "bot" in globals() and globals()["bot"] is not None:
            bot = globals()["bot"]
        else:
            main_mod = sys.modules.get("__main__")
            if main_mod and hasattr(main_mod, "bot") and main_mod.bot is not None:
                bot = main_mod.bot
            else:
                ayla_mod = sys.modules.get("Ayla") or sys.modules.get("ayla")
                if ayla_mod and hasattr(ayla_mod, "bot"):
                    bot = ayla_mod.bot

    # 1. Discord Status REAL
    ready = False
    if bot is not None:
        try:
            ready = bot.is_ready() if callable(getattr(bot, "is_ready", None)) else False
        except Exception:
            ready = False
    elif gui is not None and hasattr(gui, "bot") and gui.bot is not None:
        try:
            ready = gui.bot.is_ready() if callable(getattr(gui.bot, "is_ready", None)) else False
        except Exception:
            ready = False

    if ready:
        discord_status = "Online"
    elif bot is not None or (gui is not None and hasattr(gui, "bot")):
        discord_status = "Conectando"
    else:
        discord_status = "Offline"

    # 2. Modelo REAL
    modelo = None
    if bot is not None and hasattr(bot, "modelo_atual") and bot.modelo_atual:
        modelo = str(bot.modelo_atual)
    elif gui is not None and hasattr(gui, "bot") and hasattr(gui.bot, "modelo_atual") and gui.bot.modelo_atual:
        modelo = str(gui.bot.modelo_atual)

    if not modelo and SETTINGS_PATH.exists():
        try:
            cfg = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(cfg, dict) and "modelo_atual" in cfg:
                modelo = str(cfg["modelo_atual"])
        except Exception:
            pass

    if not modelo:
        modelo = "glm-5.3-flash"

    # 3. Chave API Atual REAL
    idx_chave = 0
    if bot is not None and hasattr(bot, "idx_api_atual"):
        idx_chave = getattr(bot, "idx_api_atual", 0)
    elif gui is not None and hasattr(gui, "bot") and hasattr(gui.bot, "idx_api_atual"):
        idx_chave = getattr(gui.bot, "idx_api_atual", 0)
    chave_api_str = str(idx_chave + 1)

    # 4. Total de APIs REAL
    total_apis = 0
    if bot is not None and hasattr(bot, "api_keys") and bot.api_keys:
        total_apis = len(bot.api_keys)
    elif gui is not None and hasattr(gui, "bot") and hasattr(gui.bot, "api_keys") and gui.bot.api_keys:
        total_apis = len(gui.bot.api_keys)
    else:
        if ENV_PATH.exists():
            try:
                for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("ZAI_API_KEY") and "=" in line:
                        val = line.split("=", 1)[1].strip()
                        if val:
                            total_apis += 1
            except Exception:
                pass

    # 5. Memórias REAIS
    total_memorias = 0
    if MEMORIA_PATH.exists():
        try:
            mem_data = json.loads(MEMORIA_PATH.read_text(encoding="utf-8"))
            if isinstance(mem_data, list):
                total_memorias = len(mem_data)
            elif isinstance(mem_data, dict):
                total_memorias = len(mem_data)
        except Exception:
            total_memorias = 0

    # 6. Contexto (Tokens) REAL
    tokens_count = 0
    if bot is not None and hasattr(bot, "chat_session") and bot.chat_session:
        try:
            total_chars = 0
            session = getattr(bot, "chat_session", None)
            if session:
                for content in session.get_history():
                    for part in getattr(content, "parts", []) or []:
                        texto = getattr(part, "text", None)
                        if texto:
                            total_chars += len(texto)
                        inline_data = getattr(part, "inline_data", None)
                        dados = getattr(inline_data, "data", None) if inline_data else None
                        if dados:
                            total_chars += min(len(dados), 100_000)
            tokens_count = int(total_chars / 4.5)
        except Exception:
            tokens_count = 0
    elif gui is not None and hasattr(gui, "_get_context_tokens"):
        try:
            tokens_count = gui._get_context_tokens()
        except Exception:
            tokens_count = 0

    if bot is not None and hasattr(bot,"obter_resumo_runtime"):
        tokens_count = bot.obter_resumo_runtime().get("tokens_estimados",0)
    contexto_str = f"{tokens_count:,} tokens estimados (sessões)"

    return {
        "Discord": discord_status,
        "Modelo": modelo,
        "Chave API": chave_api_str,
        "APIs": str(total_apis),
        "Memorias": str(total_memorias),
        "Contexto": contexto_str,
    }


def gerar_foto_status(
    bot: Any = None,
    gui: Any = None,
    logs: str | list[str] | None = None,
    output_path: str | Path | None = None,
) -> Image.Image:
    """
    Gera a imagem ('foto') representando a aba de status da Ayla.
    Sem os botões, sem 'Iniciar Windows' e sem 'Tempo de Resposta'.
    
    Retorna a imagem (PIL.Image.Image) e salva no `output_path` se especificado.
    """
    dados = obter_dados_status(bot=bot, gui=gui, logs=logs)

    width = 760
    card_cols = 2
    card_width = 350
    card_height = 80
    card_gap = 12
    padding = 24
    
    header_height = 50
    cards_section_height = 3 * (card_height + card_gap)
    total_height = padding + header_height + cards_section_height + padding

    img = Image.new("RGB", (width, total_height), color=(17, 19, 34))
    draw = ImageDraw.Draw(img)

    font_title = _carregar_fonte("segoeuib.ttf", 24)
    font_card_title = _carregar_fonte("segoeui.ttf", 13)
    font_card_value = _carregar_fonte("segoeuib.ttf", 18)

    # 1. Título "Status"
    draw.text((padding, padding), "Status", font=font_title, fill=(255, 255, 255))

    # 2. Renderização dos 6 Cards
    cards_data = [
        ("Discord", dados["Discord"]),
        ("Modelo", dados["Modelo"]),
        ("Chave API", dados["Chave API"]),
        ("APIs", dados["APIs"]),
        ("Memorias", dados["Memorias"]),
        ("Contexto", dados["Contexto"]),
    ]

    start_y = padding + header_height
    for idx, (label, val) in enumerate(cards_data):
        row = idx // card_cols
        col = idx % card_cols

        x1 = padding + col * (card_width + card_gap)
        y1 = start_y + row * (card_height + card_gap)
        x2 = x1 + card_width
        y2 = y1 + card_height

        draw.rounded_rectangle(
            [x1, y1, x2, y2],
            radius=8,
            fill=(29, 30, 54),
            outline=(46, 49, 84),
            width=1,
        )

        draw.text((x1 + 16, y1 + 14), label, font=font_card_title, fill=(143, 148, 178))
        draw.text((x1 + 16, y1 + 40), str(val), font=font_card_value, fill=(56, 189, 248))

    if output_path:
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_p, format="PNG")

    return img


def gerar_buffer_status(
    bot: Any = None,
    gui: Any = None,
    logs: str | list[str] | None = None,
    format: str = "PNG",
) -> io.BytesIO:
    """Gera a imagem de status em memória RAM (BytesIO). Não salva no PC."""
    img = gerar_foto_status(bot=bot, gui=gui, logs=logs, output_path=None)
    buffer = io.BytesIO()
    img.save(buffer, format=format)
    buffer.seek(0)
    return buffer


def gerar_bytes_status(
    bot: Any = None,
    gui: Any = None,
    logs: str | list[str] | None = None,
    format: str = "PNG",
) -> bytes:
    """Gera os bytes brutos da imagem de status em memória."""
    return gerar_buffer_status(bot=bot, gui=gui, logs=logs, format=format).getvalue()


def gerar_arquivo_discord(
    bot: Any = None,
    gui: Any = None,
    logs: str | list[str] | None = None,
    filename: str = "status_ayla.png",
) -> Any:
    """Cria um objeto discord.File a partir do buffer em memória BytesIO."""
    try:
        import discord
        buffer = gerar_buffer_status(bot=bot, gui=gui, logs=logs)
        return discord.File(fp=buffer, filename=filename)
    except ImportError:
        raise RuntimeError("A biblioteca 'discord.py' precisa estar instalada para gerar o objeto discord.File.")


# ══════════════════════════════════════════════════════════
#  REGISTRO DE FERRAMENTA DA AYLA (MODOS / TOOL_MAP)
# ══════════════════════════════════════════════════════════

def status_ayla() -> str:
    """Tira uma foto da aba de Status da Ayla e envia como anexo na resposta (idêntico ao gerar_imagem.py)."""
    try:
        pasta_saida = BASE_DIR / "Buffer de video"
        pasta_saida.mkdir(parents=True, exist_ok=True)
        caminho_final = pasta_saida / "status_ayla_temp.png"

        gerar_foto_status(output_path=caminho_final)

        # Atualiza a variável global para que o bot envie a imagem em anexo (exatamente como no gerar_imagem.py)
        if ayla_state is not None:
            ayla_state.ULTIMA_IMAGEM_GERADA.set(str(caminho_final))

        return (
            "📊 Foto da aba de status gerada com sucesso!\n"
            f"📁 Imagem: {caminho_final}\n"
            "🖼️ A foto da aba status será enviada em anexo junto com a resposta!"
        )
    except Exception as e:
        return f"Erro ao gerar foto de status: {e}"


# Registra a ferramenta no TOOL_MAP e FUNCTION_DECLARATIONS quando importado pelo sistema de MODOS da Ayla
if "TOOL_MAP" in globals() and "FUNCTION_DECLARATIONS" in globals():
    TOOL_MAP["status_ayla"] = status_ayla
    FUNCTION_DECLARATIONS.append({
        "name": "status_ayla",
        "description": "Gera uma foto da aba de status da Ayla com logs e anexa diretamente na resposta sem salvar no PC.",
        "parameters": {"type": "object", "properties": {}}
    })


if __name__ == "__main__":
    buf = gerar_buffer_status()
    print(f"[OK] Módulo status_ayla pronto na pasta MODOS! Buffer gerado com {len(buf.getvalue())} bytes (em memória).")
