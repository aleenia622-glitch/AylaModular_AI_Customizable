import asyncio
import importlib.util
import json
import random
import re
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.parse import quote, quote_plus


def _dummy_contexto() -> dict:
    contexto = {
        "TOOL_MAP": {},
        "FUNCTION_DECLARATIONS": [],
        "asyncio": asyncio,
        "json": json,
        "random": random,
        "re": re,
        "shutil": shutil,
        "subprocess": subprocess,
        "sys": sys,
        "time": time,
        "webbrowser": webbrowser,
        "Path": Path,
        "quote": quote,
        "quote_plus": quote_plus,
        "GEMINI_API_KEYS": ["dummy"],
        "DISCORD_OWNER_ID": 0,
        "ULTIMA_IMAGEM_GERADA": None,
        "ULTIMO_ANEXO_IMAGEM": None,
        "CONTEXTO_ATIVO": None,
        "BOT_LAUNCH_ERROR": None,
    }

    try:
        import requests
        contexto["requests"] = requests
    except Exception:
        pass
    try:
        import discord
        contexto["discord"] = discord
    except Exception:
        pass
    try:
        from google import genai
        from google.genai import types as genai_types
        contexto["genai"] = genai
        contexto["genai_types"] = genai_types
    except Exception:
        pass

    try:
        import pyautogui
        contexto["pyautogui"] = pyautogui
        contexto["PYAUTOGUI_OK"] = True
    except Exception:
        contexto["PYAUTOGUI_OK"] = False
    try:
        import psutil
        contexto["psutil"] = psutil
        contexto["PSUTIL_OK"] = True
    except Exception:
        contexto["PSUTIL_OK"] = False
    try:
        import pyperclip
        contexto["pyperclip"] = pyperclip
        contexto["PYPERCLIP_OK"] = True
    except Exception:
        contexto["PYPERCLIP_OK"] = False
    try:
        from send2trash import send2trash
        contexto["send2trash"] = send2trash
        contexto["SEND2TRASH_OK"] = True
    except Exception:
        contexto["SEND2TRASH_OK"] = False

    class DummyBot:
        loop = None
        chat_session = None
        genai_client = None

        def enviar_com_fallback(self, *args, **kwargs):
            return None

        def atualizar_prompt_memoria(self):
            return None

    class AylaBot:
        pass

    def carregar_memoria() -> dict:
        return {}

    def salvar_memoria(dados: dict):
        return None

    def gerar_audio_voicevox_bytes(texto: str, tom: str = "normal"):
        return None

    contexto["bot"] = DummyBot()
    contexto["AylaBot"] = AylaBot
    contexto["carregar_memoria"] = carregar_memoria
    contexto["salvar_memoria"] = salvar_memoria
    contexto["gerar_audio_voicevox_bytes"] = gerar_audio_voicevox_bytes
    contexto["gerar_audio_gemini_tts_bytes"] = gerar_audio_voicevox_bytes
    return contexto


def _testar_arquivo(arq_py: Path) -> tuple[bool, str, int, int]:
    nome_modulo = f"ayla_teste_modulo_{arq_py.stem}_{time.time_ns()}"
    contexto = _dummy_contexto()
    ferramentas_antes = len(contexto["TOOL_MAP"])
    declaracoes_antes = len(contexto["FUNCTION_DECLARATIONS"])

    try:
        spec = importlib.util.spec_from_file_location(nome_modulo, arq_py)
        if spec is None or spec.loader is None:
            return False, "spec de import invalida", 0, 0
        modulo = importlib.util.module_from_spec(spec)
        modulo.__dict__.update(contexto)
        sys.modules[nome_modulo] = modulo
        spec.loader.exec_module(modulo)

        register = getattr(modulo, "register", None)
        if callable(register):
            register(contexto["TOOL_MAP"], contexto["FUNCTION_DECLARATIONS"])

        novas_ferramentas = len(contexto["TOOL_MAP"]) - ferramentas_antes
        novas_declaracoes = len(contexto["FUNCTION_DECLARATIONS"]) - declaracoes_antes
        return True, "ok", novas_ferramentas, novas_declaracoes
    except Exception as e:
        return False, f"{type(e).__name__}: {e}", 0, 0
    finally:
        sys.modules.pop(nome_modulo, None)


def modo_teste_modulos() -> str:
    pasta = Path(__file__).resolve().parent
    resultados = []
    falhas = []

    for arq_py in sorted(pasta.glob("*.py")):
        ok, mensagem, qtd_tools, qtd_decl = _testar_arquivo(arq_py)
        if ok:
            resultados.append(f"OK {arq_py.name} ({qtd_tools} tool(s), {qtd_decl} declaracao(oes))")
        else:
            falhas.append(f"FALHA {arq_py.name}: {mensagem}")

    total = len(resultados) + len(falhas)
    partes = [
        "Teste isolado dos MODOS",
        f"Total: {total}",
        f"OK: {len(resultados)}",
        f"Falhas: {len(falhas)}",
        "",
    ]
    if falhas:
        partes.append("Falhas encontradas:")
        partes.extend(falhas)
        partes.append("")
    partes.append("Resumo OK:")
    partes.extend(resultados[:120])
    if len(resultados) > 120:
        partes.append(f"... mais {len(resultados) - 120} modulos OK ocultos.")
    return "\n".join(partes)


def register(tool_map, function_declarations):
    tool_map["modo_teste_modulos"] = modo_teste_modulos
    function_declarations.append({
        "name": "modo_teste_modulos",
        "description": "Importa cada arquivo de MODOS isoladamente com contexto falso e mostra quais carregam ou falham.",
        "parameters": {"type": "object", "properties": {}}
    })
