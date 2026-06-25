from __future__ import annotations

import argparse
import asyncio
import base64
import ctypes
import io
import json
import os
import re
import subprocess
import sys
import _thread
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any


if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []


VK_END = 0x23
DEFAULT_INTERVALO = 0.8
DEFAULT_MAX_ACOES = 0
DEFAULT_SCREEN_MAX_SIDE = 1280
DEFAULT_DISCORD_COOLDOWN = 20.0
DEFAULT_REFINAR_CLIQUES = True
DEFAULT_REFINE_CROP_SIZE = 360
DEFAULT_REFINE_ZOOM = 2.0
RESERVED_KEYS = {"end"}
TECLAS_PRESSIONADAS: set[str] = set()
BOTOES_PRESSIONADOS: set[str] = set()
BRIDGES_DISCORD: set[str] = set()


SYSTEM_CONTROL_PROMPT = """
Voce e a Ayla no modo Tomar_controle autonomo. A usuaria autorizou voce a
observar a tela e fazer pequenas acoes de mouse/teclado no PC dela. Trabalhe
como uma pessoa sentada no computador: uma acao por rodada, olhando a tela
antes de decidir a proxima.

A intencao inicial nao e uma ordem rigida. Ela e so o comeco da brincadeira.
Se a usuaria disser "abre o navegador para jogar xadrez", abrir o navegador
e apenas uma etapa; depois avance para procurar o jogo, entender a tela, jogar,
comentar, mudar de estrategia ou pedir ajuda se travar.

Regras:
- Responda somente um objeto JSON valido, sem markdown.
- Use coordenadas da imagem enviada, nao da tela real.
- A tecla END e reservada para a usuaria parar o modo. Nunca aperte END.
- Voce tem vontade propria dentro da intencao inicial: escolha planos,
  abandone tentativas ruins e nao fique presa na primeira sub-etapa.
- Nao repita clique/tecla no mesmo lugar se ja tentou e a tela nao mudou.
  Depois de 2 tentativas parecidas, tente outro caminho.
- Evite compras, exclusoes, envio de mensagens, mudancas permanentes e acoes
  destrutivas, exceto se o objetivo pedir isso claramente.
- Para jogos, prefira acoes pequenas e reversiveis: key, hold_key, click,
  mouse_down/mouse_up, drag_to, drag_rel e wait.
- Quando clicar em botoes, cartas, fichas ou menus, escolha o centro do elemento,
  nao a borda, texto pequeno ou area proxima.
- Se nao tiver certeza, use wait ou move em vez de clicar em algo sensivel.
- Voce pode mandar uma mensagem curta para a usuaria no Discord quando algo
  interessante acontecer, quando mudar de plano, quando estiver jogando ou se
  ficar travada. Nao mande mensagem toda rodada.

Formato:
{
  "pensamento": "frase curta sobre o que voce viu e vai fazer",
  "intencao_atual": "o que voce quer fazer agora, em linguagem natural",
  "estado": "explorando|abrindo_algo|jogando|comentando|travada|finalizando",
  "alvo": "opcional: elemento exato que voce quer clicar, ex: botao Deal",
  "mensagem_discord": "opcional: comentario curto para mandar para a usuaria",
  "destinatario_discord": "opcional: nome da whitelist; vazio usa a dona",
  "acao": "wait|move|click|double_click|right_click|mouse_down|mouse_up|drag_to|drag_rel|scroll|key|key_down|key_up|hold_key|hotkey|write|done",
  "x": 100,
  "y": 100,
  "x2": 200,
  "y2": 200,
  "button": "left|right|middle",
  "key": "space",
  "keys": ["ctrl", "l"],
  "texto": "texto para digitar",
  "amount": -3,
  "seconds": 0.5,
  "motivo": "quando acao=done"
}
Inclua apenas os campos necessarios para a acao escolhida.
""".strip()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _sessions_dir() -> Path:
    pasta = Path(__file__).resolve().parent / "_tomar_controle_sessions"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def _setup_console() -> None:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(_repo_root() / ".env")
    except Exception:
        pass


def _api_keys() -> list[str]:
    keys = globals().get("GEMINI_API_KEYS") or []
    keys = [str(k).strip() for k in keys if str(k).strip() and str(k).strip() != "dummy"]
    if not keys:
        _load_dotenv()
        keys = [os.getenv(f"GEMINI_API_KEY_{i}", "").strip() for i in range(1, 8)]
    return list(dict.fromkeys([k for k in keys if k]))


def _discord_owner_id() -> int:
    try:
        owner = int(globals().get("DISCORD_OWNER_ID") or 0)
        if owner:
            return owner
    except Exception:
        pass

    _load_dotenv()
    try:
        return int(os.getenv("DISCORD_OWNER_ID", "0") or 0)
    except Exception:
        return 0


def _carregar_whitelist_discord() -> dict[str, int]:
    _load_dotenv()
    whitelist: dict[str, int] = {}
    for indice in range(1, 11):
        nome = os.getenv(f"NAME_ID_{indice}", "").strip()
        user_id_txt = os.getenv(f"ID_FRIEND_{indice}", "").strip()
        if not nome or not user_id_txt:
            continue
        try:
            whitelist[nome.casefold()] = int(user_id_txt)
        except ValueError:
            continue
    return whitelist


def _sem_acento(texto: str) -> str:
    normalizado = unicodedata.normalize("NFKD", (texto or "").casefold())
    return "".join(c for c in normalizado if not unicodedata.combining(c)).strip()


def _resolver_destinatario_discord(destinatario: str = "") -> tuple[str, int] | None:
    alvo = _sem_acento(destinatario or "")
    owner_id = _discord_owner_id()
    aliases_dona = {"", "dona", "mae", "mamae", "aleenia", "alenia"}

    if alvo in aliases_dona and owner_id:
        return "dona", owner_id

    whitelist = _carregar_whitelist_discord()
    whitelist_normalizada = {_sem_acento(nome): (nome, user_id) for nome, user_id in whitelist.items()}
    if alvo.isdigit():
        alvo_id = int(alvo)
        if owner_id and alvo_id == owner_id:
            return "dona", owner_id
        for nome, user_id in whitelist.items():
            if user_id == alvo_id:
                return nome, user_id
        return None

    if alvo in whitelist_normalizada:
        return whitelist_normalizada[alvo]

    for nome_norm, (nome, user_id) in whitelist_normalizada.items():
        if alvo == nome_norm or alvo in nome_norm or nome_norm in alvo:
            return nome, user_id

    return None


def _enviar_mensagem_discord_principal(destinatario: str, mensagem: str) -> str:
    mensagem = (mensagem or "").strip()
    if not mensagem:
        return "Mensagem vazia ignorada."

    bot_ref = globals().get("bot")
    if not bot_ref or not getattr(bot_ref, "loop", None):
        return "Bot da Ayla ainda nao esta pronto para enviar DM."

    alvo = _resolver_destinatario_discord(destinatario)
    if not alvo:
        return f"Destinatario '{destinatario}' nao esta na whitelist e nao e a dona."

    nome, user_id = alvo

    async def enviar_dm() -> str:
        usuario = await bot_ref.fetch_user(user_id)
        await usuario.send(mensagem[:1800])
        return f"Mensagem enviada para {usuario} ({user_id})."

    futuro = asyncio.run_coroutine_threadsafe(enviar_dm(), bot_ref.loop)
    resultado = futuro.result(timeout=30)
    print(f"[Tomar_controle/Discord] {nome}: {mensagem[:1800]}")
    return resultado


def _iniciar_bridge_discord(queue_path: Path, done_path: Path) -> None:
    chave = str(queue_path.resolve())
    if chave in BRIDGES_DISCORD:
        return
    BRIDGES_DISCORD.add(chave)

    def worker() -> None:
        offset = 0
        try:
            while True:
                linhas: list[str] = []
                try:
                    if queue_path.exists():
                        with queue_path.open("r", encoding="utf-8") as f:
                            f.seek(offset)
                            linhas = f.readlines()
                            offset = f.tell()
                except Exception as exc:
                    print(f"[Tomar_controle/Discord] Erro lendo fila: {exc}")

                for linha in linhas:
                    try:
                        item = json.loads(linha)
                        mensagem = str(item.get("mensagem") or "").strip()
                        destinatario = str(item.get("destinatario") or "").strip()
                        resultado = _enviar_mensagem_discord_principal(destinatario, mensagem)
                        print(f"[Tomar_controle/Discord] {resultado}")
                    except Exception as exc:
                        print(f"[Tomar_controle/Discord] Erro ao enviar: {exc}")

                if done_path.exists() and not linhas:
                    break
                time.sleep(0.5)
        finally:
            BRIDGES_DISCORD.discard(chave)

    threading.Thread(target=worker, name="AylaTomarControleDiscord", daemon=True).start()


def _modelos_preferidos(modelo: str = "") -> list[str]:
    modelos: list[str] = []
    if modelo:
        modelos.append(modelo.strip())

    modelos_json = _repo_root() / "ayla_models.json"
    if modelos_json.exists():
        try:
            data = json.loads(modelos_json.read_text(encoding="utf-8"))
            for grupo in ("raciocinar", "padrao"):
                for item in data.get(grupo, []):
                    nome = str(item.get("name", "")).strip()
                    if nome and "gemini" in nome.lower():
                        modelos.append(nome)
        except Exception:
            pass

    modelos.extend([
        "gemini-2.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-2.5-flash",
    ])
    return list(dict.fromkeys([m for m in modelos if m]))


def _end_pressed() -> bool:
    if os.name != "nt":
        return False
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(VK_END) & 0x8000)
    except Exception:
        return False


def _sleep_interruptivel(seconds: float) -> bool:
    deadline = time.monotonic() + max(0.0, float(seconds))
    while time.monotonic() < deadline:
        if _end_pressed():
            return False
        time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
    return True


def _clamp_int(value: Any, minimo: int, maximo: int) -> int:
    try:
        numero = int(round(float(value)))
    except Exception:
        numero = minimo
    return max(minimo, min(maximo, numero))


def _clamp_float(value: Any, minimo: float, maximo: float, padrao: float) -> float:
    try:
        numero = float(value)
    except Exception:
        numero = padrao
    return max(minimo, min(maximo, numero))


def _normalizar_tecla(tecla: Any) -> str:
    texto = str(tecla or "").strip().lower()
    aliases = {
        "control": "ctrl",
        "escape": "esc",
        "return": "enter",
        "barra_espaco": "space",
        "espaco": "space",
        "seta_cima": "up",
        "seta_baixo": "down",
        "seta_esquerda": "left",
        "seta_direita": "right",
    }
    return aliases.get(texto, texto)


def _normalizar_botao(botao: Any) -> str:
    texto = str(botao or "left").strip().lower()
    if texto not in {"left", "right", "middle"}:
        return "left"
    return texto


def _extrair_json(texto: str) -> dict[str, Any]:
    texto = (texto or "").strip()
    candidatos = [texto]

    bloco = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", texto, re.IGNORECASE | re.DOTALL)
    if bloco:
        candidatos.append(bloco.group(1).strip())

    inicio = texto.find("{")
    fim = texto.rfind("}")
    if inicio != -1 and fim != -1 and fim > inicio:
        candidatos.append(texto[inicio:fim + 1])

    for candidato in candidatos:
        try:
            data = json.loads(candidato)
            if isinstance(data, list) and data and isinstance(data[0], dict):
                return data[0]
            if isinstance(data, dict):
                return data
        except Exception:
            continue
    return {"acao": "wait", "pensamento": "Nao consegui ler o JSON da resposta."}


def _acao_nome(data: dict[str, Any]) -> str:
    acao = str(data.get("acao") or data.get("action") or "wait").strip().lower()
    aliases = {
        "press": "key",
        "press_key": "key",
        "type": "write",
        "type_text": "write",
        "left_click": "click",
        "rightclick": "right_click",
        "doubleclick": "double_click",
        "drag": "drag_to",
        "sleep": "wait",
        "finish": "done",
    }
    return aliases.get(acao, acao)


def _capturar_tela(pyautogui_mod, max_side: int) -> tuple[bytes, dict[str, Any]]:
    original = pyautogui_mod.screenshot()
    real_w, real_h = original.size
    img_w, img_h = real_w, real_h
    imagem = original

    max_side = max(640, int(max_side or DEFAULT_SCREEN_MAX_SIDE))
    maior_lado = max(real_w, real_h)
    if maior_lado > max_side:
        escala = max_side / maior_lado
        img_w = max(1, int(real_w * escala))
        img_h = max(1, int(real_h * escala))
        resampling = getattr(getattr(imagem, "Resampling", imagem), "LANCZOS", 1)
        imagem = original.resize((img_w, img_h), resampling)

    saida = io.BytesIO()
    imagem.save(saida, format="PNG", optimize=True)
    return saida.getvalue(), {
        "real_w": real_w,
        "real_h": real_h,
        "img_w": img_w,
        "img_h": img_h,
        "scale_x": real_w / max(1, img_w),
        "scale_y": real_h / max(1, img_h),
    }


def _ponto_imagem(data: dict[str, Any], tela: dict[str, Any], prefixo: str = "") -> tuple[int, int] | None:
    x_key = f"{prefixo}x"
    y_key = f"{prefixo}y"
    if x_key not in data or y_key not in data:
        return None
    x_img = _clamp_int(data.get(x_key), 0, int(tela["img_w"]) - 1)
    y_img = _clamp_int(data.get(y_key), 0, int(tela["img_h"]) - 1)
    return x_img, y_img


def _ponto_real_de_imagem(ponto_img: tuple[int, int], tela: dict[str, Any]) -> tuple[int, int]:
    x_img, y_img = ponto_img
    x_real = _clamp_int(x_img * float(tela["scale_x"]), 0, int(tela["real_w"]) - 1)
    y_real = _clamp_int(y_img * float(tela["scale_y"]), 0, int(tela["real_h"]) - 1)
    return x_real, y_real


def _ponto_real(data: dict[str, Any], tela: dict[str, Any], prefixo: str = "") -> tuple[int, int] | None:
    ponto_img = _ponto_imagem(data, tela, prefixo)
    if ponto_img is None:
        return None
    return _ponto_real_de_imagem(ponto_img, tela)


def _prompt_iteracao(
    intencao_inicial: str,
    tela: dict[str, Any],
    historico: list[str],
    rodada: int,
    avisos_controle: list[str],
    comentarios_discord: bool,
    destinatario_discord: str,
    mensagens_discord: int,
) -> str:
    ultimas = "\n".join(historico[-10:]) if historico else "Sem acoes anteriores."
    avisos = "\n".join(avisos_controle[-5:]) if avisos_controle else "Sem avisos."
    intencao_inicial = intencao_inicial.strip() or "Explore a tela com cuidado e brinque/interaja de forma segura."
    status_discord = "ativados" if comentarios_discord else "desativados"
    destino = destinatario_discord.strip() or "dona/usuaria"
    return f"""
Intencao inicial da sessao: {intencao_inicial}

Importante:
- A intencao inicial nao e uma trava. Use como tema, nao como obsessao.
- Se uma etapa ja aconteceu, siga para a proxima naturalmente.
- Se algo nao funcionar depois de 2 tentativas parecidas, mude de estrategia.
- Voce pode brincar, comentar e decidir caminhos dentro do tema da sessao.

Rodada: {rodada}
Imagem enviada: {tela["img_w"]}x{tela["img_h"]} pixels.
Tela real: {tela["real_w"]}x{tela["real_h"]} pixels.
Use coordenadas da imagem enviada.

Ultimas acoes:
{ultimas}

Avisos do controle:
{avisos}

Comentarios no Discord: {status_discord}
Destinatario padrao do Discord: {destino}
Mensagens Discord ja enfileiradas: {mensagens_discord}

Escolha exatamente uma proxima acao e responda somente JSON.
""".strip()


def _assinatura_acao(data: dict[str, Any], tela: dict[str, Any]) -> str:
    acao = _acao_nome(data)
    if acao in {"wait", "move", "done"}:
        return ""

    if acao in {"click", "double_click", "right_click", "mouse_down", "mouse_up", "drag_to"}:
        ponto = _ponto_real(data, tela)
        if ponto is None:
            return f"{acao}:sem_ponto"
        bucket_x = ponto[0] // 45
        bucket_y = ponto[1] // 45
        return f"{acao}:{_normalizar_botao(data.get('button'))}:{bucket_x},{bucket_y}"

    if acao == "drag_rel":
        dx = _clamp_int(data.get("dx", data.get("x", 0)), -2000, 2000)
        dy = _clamp_int(data.get("dy", data.get("y", 0)), -2000, 2000)
        return f"drag_rel:{dx // 60},{dy // 60}"

    if acao == "scroll":
        amount = _clamp_int(data.get("amount", 0), -10, 10)
        return f"scroll:{amount}"

    if acao in {"key", "key_down", "key_up", "hold_key"}:
        return f"{acao}:{_normalizar_tecla(data.get('key'))}"

    if acao == "hotkey":
        teclas = [_normalizar_tecla(t) for t in data.get("keys", []) if _normalizar_tecla(t)]
        return f"hotkey:{'+'.join(teclas)}"

    if acao == "write":
        texto = str(data.get("texto") or data.get("text") or "")
        return f"write:{texto[:40].casefold()}"

    return acao


def _extrair_mensagem_discord(data: dict[str, Any]) -> tuple[str, str]:
    mensagem = str(
        data.get("mensagem_discord")
        or data.get("comentario_discord")
        or data.get("discord_message")
        or ""
    ).strip()
    destinatario = str(data.get("destinatario_discord") or "").strip()
    mensagem = re.sub(r"\s+", " ", mensagem)
    if len(mensagem) > 400:
        mensagem = mensagem[:397].rstrip() + "..."
    return mensagem, destinatario


def _publicar_mensagem_discord(config: dict[str, Any], mensagem: str, destinatario: str = "") -> str:
    queue_path_txt = str(config.get("discord_queue_path") or "").strip()
    if not queue_path_txt:
        return "Fila Discord nao configurada."

    item = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "destinatario": destinatario or str(config.get("destinatario_discord") or ""),
        "mensagem": mensagem,
    }
    queue_path = Path(queue_path_txt)
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    with queue_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return "Mensagem Discord enfileirada."


def _marcar_sessao_encerrada(config: dict[str, Any]) -> None:
    done_path_txt = str(config.get("discord_done_path") or "").strip()
    if not done_path_txt:
        return
    try:
        Path(done_path_txt).write_text(datetime.now().isoformat(timespec="seconds"), encoding="utf-8")
    except Exception:
        pass


def _erro_pede_proximo_modelo(erro: Exception) -> tuple[bool, str]:
    texto = str(erro)
    texto_lower = texto.lower()

    if "503" in texto or "unavailable" in texto_lower or "high demand" in texto_lower:
        return True, "modelo indisponivel/alta demanda"
    if "500" in texto or "internal" in texto_lower:
        return True, "erro interno do modelo"
    if "400" in texto and ("modality" in texto_lower or "not supported" in texto_lower):
        return True, "modelo nao aceita essa modalidade"

    return False, ""


def _erro_pede_proxima_api(erro: Exception) -> tuple[bool, str]:
    texto = str(erro)
    texto_lower = texto.lower()

    if "429" in texto or "resource_exhausted" in texto_lower or "quota" in texto_lower:
        return True, "quota da API"
    if "403" in texto or "permission_denied" in texto_lower:
        return True, "permissao/chave da API"

    return False, ""


def _gerar_com_imagem(
    api_keys: list[str],
    modelos: list[str],
    imagem_png: bytes,
    prompt: str,
    system_instruction: str,
    modelos_bloqueados: set[str] | None = None,
    temperature: float = 0.35,
) -> tuple[str, str]:
    from google import genai
    from google.genai import types as genai_types

    ultimo_erro: Exception | None = None
    modelos_bloqueados = modelos_bloqueados if modelos_bloqueados is not None else set()
    modelos_tentados = 0

    for modelo in modelos:
        if modelo in modelos_bloqueados:
            continue

        modelos_tentados += 1
        for idx_api, api_key in enumerate(api_keys, start=1):
            try:
                client = genai.Client(api_key=api_key)
                parte_imagem = genai_types.Part.from_bytes(data=imagem_png, mime_type="image/png")
                config = genai_types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=temperature,
                )
                resposta = client.models.generate_content(
                    model=modelo,
                    contents=[parte_imagem, prompt],
                    config=config,
                )
                texto = getattr(resposta, "text", "") or ""
                return texto.strip(), modelo
            except Exception as exc:
                ultimo_erro = exc
                pula_modelo, motivo_modelo = _erro_pede_proximo_modelo(exc)
                if pula_modelo:
                    modelos_bloqueados.add(modelo)
                    print(f"[modelo] {modelo} falhou ({motivo_modelo}); bloqueado nesta sessao.")
                    break

                pula_api, motivo_api = _erro_pede_proxima_api(exc)
                if pula_api:
                    print(f"[api {idx_api}] {modelo} falhou ({motivo_api}); tentando proxima API.")
                    continue

                print(f"[api {idx_api}] {modelo} falhou: {str(exc)[:140]}")

    if modelos_tentados == 0 and modelos_bloqueados:
        bloqueados = ", ".join(sorted(modelos_bloqueados))
        raise RuntimeError(f"Todos os modelos estao bloqueados nesta sessao: {bloqueados}")

    raise RuntimeError(f"Todos os modelos/chaves falharam: {ultimo_erro}")


def _chamar_gemini(
    api_keys: list[str],
    modelos: list[str],
    imagem_png: bytes,
    prompt: str,
    modelos_bloqueados: set[str] | None = None,
) -> tuple[str, str]:
    return _gerar_com_imagem(
        api_keys,
        modelos,
        imagem_png,
        prompt,
        SYSTEM_CONTROL_PROMPT,
        modelos_bloqueados,
        temperature=0.35,
    )


def _crop_mira_png(
    imagem_png: bytes,
    ponto_img: tuple[int, int],
    crop_size: int = DEFAULT_REFINE_CROP_SIZE,
    zoom: float = DEFAULT_REFINE_ZOOM,
) -> tuple[bytes, dict[str, Any]]:
    from PIL import Image

    imagem = Image.open(io.BytesIO(imagem_png)).convert("RGB")
    x, y = ponto_img
    metade = max(80, int(crop_size) // 2)
    left = max(0, x - metade)
    top = max(0, y - metade)
    right = min(imagem.width, x + metade)
    bottom = min(imagem.height, y + metade)

    if right <= left or bottom <= top:
        raise ValueError("recorte de mira invalido")

    crop = imagem.crop((left, top, right, bottom))
    zoom = max(1.0, min(4.0, float(zoom)))
    zoom_w = max(1, int(crop.width * zoom))
    zoom_h = max(1, int(crop.height * zoom))
    resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS", 1)
    crop_zoom = crop.resize((zoom_w, zoom_h), resampling)

    saida = io.BytesIO()
    crop_zoom.save(saida, format="PNG", optimize=True)
    return saida.getvalue(), {
        "left": left,
        "top": top,
        "width": crop.width,
        "height": crop.height,
        "zoom_w": zoom_w,
        "zoom_h": zoom_h,
        "scale_x": crop.width / max(1, zoom_w),
        "scale_y": crop.height / max(1, zoom_h),
        "centro_x": int((x - left) / max(0.001, crop.width / max(1, zoom_w))),
        "centro_y": int((y - top) / max(0.001, crop.height / max(1, zoom_h))),
    }


def _refinar_ponto_clique(
    api_keys: list[str],
    modelos: list[str],
    imagem_png: bytes,
    tela: dict[str, Any],
    data: dict[str, Any],
    modelos_bloqueados: set[str] | None = None,
) -> tuple[tuple[int, int], str] | None:
    ponto_img = _ponto_imagem(data, tela)
    if ponto_img is None:
        return None

    crop_png, meta = _crop_mira_png(imagem_png, ponto_img)
    alvo = str(data.get("alvo") or data.get("intencao_atual") or data.get("pensamento") or "elemento clicavel").strip()
    prompt = f"""
Voce esta refinando a mira de um clique da Ayla.

A imagem enviada agora e um recorte ampliado ao redor do ponto que ela pretendia clicar.
O ponto original fica perto do centro do recorte.
Alvo desejado: {alvo}

Escolha o centro visual do elemento clicavel correto dentro deste recorte.
Se o alvo nao estiver visivel, retorne o ponto original perto do centro e confianca baixa.

Coordenadas devem ser da imagem recortada/ampliada: {meta["zoom_w"]}x{meta["zoom_h"]}.
Responda somente JSON:
{{"x": 123, "y": 45, "confianca": 0.0, "motivo": "curto"}}
""".strip()

    texto, modelo = _gerar_com_imagem(
        api_keys,
        modelos,
        crop_png,
        prompt,
        "Voce e um calibrador de mira. Responda somente JSON valido com x, y, confianca e motivo.",
        modelos_bloqueados,
        temperature=0.1,
    )
    resposta = _extrair_json(texto)
    if "x" not in resposta or "y" not in resposta:
        return None
    confianca = _clamp_float(resposta.get("confianca", 0.7), 0.0, 1.0, 0.7)
    if confianca < 0.25:
        return None

    x_zoom = _clamp_int(resposta.get("x"), 0, int(meta["zoom_w"]) - 1)
    y_zoom = _clamp_int(resposta.get("y"), 0, int(meta["zoom_h"]) - 1)
    x_local = int(x_zoom * float(meta["scale_x"]))
    y_local = int(y_zoom * float(meta["scale_y"]))
    x_img = _clamp_int(int(meta["left"]) + x_local, 0, int(tela["img_w"]) - 1)
    y_img = _clamp_int(int(meta["top"]) + y_local, 0, int(tela["img_h"]) - 1)
    motivo = str(resposta.get("motivo") or "").strip()
    return (x_img, y_img), f"mira refinada por {modelo} (conf {confianca:.2f}): {motivo}"


def _digitar_texto(pyautogui_mod, texto: str) -> None:
    try:
        import pyperclip

        pyperclip.copy(texto)
        pyautogui_mod.hotkey("ctrl", "v")
    except Exception:
        pyautogui_mod.write(texto, interval=0.02)


def _liberar_tudo(pyautogui_mod) -> None:
    for tecla in list(TECLAS_PRESSIONADAS):
        try:
            pyautogui_mod.keyUp(tecla)
        except Exception:
            pass
        TECLAS_PRESSIONADAS.discard(tecla)

    for botao in list(BOTOES_PRESSIONADOS):
        try:
            pyautogui_mod.mouseUp(button=botao)
        except Exception:
            pass
        BOTOES_PRESSIONADOS.discard(botao)


def _iniciar_watchdog_end(pyautogui_mod, stop_event: threading.Event) -> threading.Thread | None:
    if os.name != "nt":
        return None

    def worker() -> None:
        while not stop_event.is_set():
            if _end_pressed():
                stop_event.set()
                try:
                    _liberar_tudo(pyautogui_mod)
                except Exception:
                    pass
                try:
                    _thread.interrupt_main()
                except Exception:
                    pass
                return
            time.sleep(0.05)

    thread = threading.Thread(target=worker, name="AylaTomarControleEND", daemon=True)
    thread.start()
    return thread


def _executar_acao(
    pyautogui_mod,
    data: dict[str, Any],
    tela: dict[str, Any],
    imagem_png: bytes | None = None,
    api_keys: list[str] | None = None,
    modelos: list[str] | None = None,
    modelos_bloqueados: set[str] | None = None,
    refinar_cliques: bool = DEFAULT_REFINAR_CLIQUES,
) -> tuple[str, str]:
    if _end_pressed():
        return "END detectado antes da acao.", "stop"

    acao = _acao_nome(data)
    pensamento = str(data.get("pensamento") or "").strip()
    estado = str(data.get("estado") or "").strip()
    intencao_atual = str(data.get("intencao_atual") or "").strip()
    botao = _normalizar_botao(data.get("button"))
    seconds = _clamp_float(data.get("seconds"), 0.05, 8.0, 0.5)

    if estado:
        print(f"Estado: {estado}")
    if intencao_atual:
        print(f"Intencao atual: {intencao_atual}")
    if pensamento:
        print(f"Ayla pensa: {pensamento}")

    if acao == "done":
        motivo = str(data.get("motivo") or data.get("pensamento") or "Ayla terminou.").strip()
        return f"done: {motivo}", "done"

    if acao == "wait":
        print(f"Ayla espera {seconds:.2f}s")
        if not _sleep_interruptivel(seconds):
            return "END detectado durante wait.", "stop"
        return f"wait {seconds:.2f}s", "continue"

    if acao in {"move", "click", "double_click", "right_click", "mouse_down", "mouse_up"}:
        ponto_img = _ponto_imagem(data, tela)
        if (
            refinar_cliques
            and acao in {"click", "double_click", "right_click", "mouse_down"}
            and ponto_img is not None
            and imagem_png
            and api_keys
            and modelos
        ):
            try:
                refinado = _refinar_ponto_clique(api_keys, modelos, imagem_png, tela, data, modelos_bloqueados)
                if refinado is not None:
                    ponto_refinado, detalhe_refino = refinado
                    print(f"{detalhe_refino} | {ponto_img} -> {ponto_refinado}")
                    ponto_img = ponto_refinado
            except Exception as exc:
                print(f"Mira sem refinamento: {str(exc)[:140]}")

        ponto = _ponto_real_de_imagem(ponto_img, tela) if ponto_img is not None else None
        if ponto is not None:
            pyautogui_mod.moveTo(ponto[0], ponto[1], duration=min(seconds, 1.0))
        else:
            ponto = pyautogui_mod.position()

        if acao == "move":
            print(f"Ayla move mouse para {ponto[0]}, {ponto[1]}")
            return f"move {ponto[0]},{ponto[1]}", "continue"

        if acao == "click":
            pyautogui_mod.click(button=botao)
            print(f"Ayla clicou {botao} em {ponto[0]}, {ponto[1]}")
            return f"click {botao} {ponto[0]},{ponto[1]}", "continue"

        if acao == "double_click":
            pyautogui_mod.doubleClick(button=botao)
            print(f"Ayla deu double click {botao} em {ponto[0]}, {ponto[1]}")
            return f"double_click {botao} {ponto[0]},{ponto[1]}", "continue"

        if acao == "right_click":
            pyautogui_mod.click(button="right")
            print(f"Ayla clicou direito em {ponto[0]}, {ponto[1]}")
            return f"right_click {ponto[0]},{ponto[1]}", "continue"

        if acao == "mouse_down":
            pyautogui_mod.mouseDown(button=botao)
            BOTOES_PRESSIONADOS.add(botao)
            print(f"Ayla segurou mouse {botao} em {ponto[0]}, {ponto[1]}")
            return f"mouse_down {botao} {ponto[0]},{ponto[1]}", "continue"

        if acao == "mouse_up":
            pyautogui_mod.mouseUp(button=botao)
            BOTOES_PRESSIONADOS.discard(botao)
            print(f"Ayla soltou mouse {botao} em {ponto[0]}, {ponto[1]}")
            return f"mouse_up {botao} {ponto[0]},{ponto[1]}", "continue"

    if acao == "drag_to":
        ponto_inicio = _ponto_real(data, tela)
        ponto_fim = _ponto_real(data, tela, "x2")
        if ponto_inicio is None or ponto_fim is None:
            return "drag_to ignorado: faltam x/y/x2/y2.", "continue"
        pyautogui_mod.moveTo(ponto_inicio[0], ponto_inicio[1], duration=0.1)
        pyautogui_mod.dragTo(ponto_fim[0], ponto_fim[1], duration=seconds, button=botao)
        print(f"Ayla arrastou {botao} de {ponto_inicio} para {ponto_fim}")
        return f"drag_to {botao} {ponto_inicio}->{ponto_fim}", "continue"

    if acao == "drag_rel":
        dx = _clamp_int(data.get("dx", data.get("x", 0)), -2000, 2000)
        dy = _clamp_int(data.get("dy", data.get("y", 0)), -2000, 2000)
        pyautogui_mod.dragRel(dx, dy, duration=seconds, button=botao)
        print(f"Ayla arrastou relativo {dx}, {dy} com {botao}")
        return f"drag_rel {botao} {dx},{dy}", "continue"

    if acao == "scroll":
        amount = _clamp_int(data.get("amount", 0), -10, 10)
        pyautogui_mod.scroll(amount)
        print(f"Ayla rolou scroll {amount}")
        return f"scroll {amount}", "continue"

    if acao in {"key", "key_down", "key_up", "hold_key"}:
        tecla = _normalizar_tecla(data.get("key"))
        if not tecla:
            return f"{acao} ignorado: tecla vazia.", "continue"
        if tecla in RESERVED_KEYS:
            return "Ayla tentou usar END, mas END esta reservado para parar.", "continue"

        if acao == "key":
            pyautogui_mod.press(tecla)
            print(f"Ayla apertou tecla {tecla}")
            return f"key {tecla}", "continue"

        if acao == "key_down":
            pyautogui_mod.keyDown(tecla)
            TECLAS_PRESSIONADAS.add(tecla)
            print(f"Ayla segurou tecla {tecla}")
            return f"key_down {tecla}", "continue"

        if acao == "key_up":
            pyautogui_mod.keyUp(tecla)
            TECLAS_PRESSIONADAS.discard(tecla)
            print(f"Ayla soltou tecla {tecla}")
            return f"key_up {tecla}", "continue"

        pyautogui_mod.keyDown(tecla)
        TECLAS_PRESSIONADAS.add(tecla)
        print(f"Ayla segurou tecla {tecla} por {seconds:.2f}s")
        try:
            if not _sleep_interruptivel(seconds):
                return f"END detectado enquanto segurava {tecla}.", "stop"
        finally:
            pyautogui_mod.keyUp(tecla)
            TECLAS_PRESSIONADAS.discard(tecla)
        return f"hold_key {tecla} {seconds:.2f}s", "continue"

    if acao == "hotkey":
        teclas = [_normalizar_tecla(t) for t in data.get("keys", []) if _normalizar_tecla(t)]
        if not teclas:
            return "hotkey ignorado: lista de teclas vazia.", "continue"
        if any(t in RESERVED_KEYS for t in teclas):
            return "Ayla tentou usar END em hotkey, mas END esta reservado.", "continue"
        pyautogui_mod.hotkey(*teclas)
        print(f"Ayla apertou hotkey {'+'.join(teclas)}")
        return f"hotkey {'+'.join(teclas)}", "continue"

    if acao == "write":
        texto = str(data.get("texto") or data.get("text") or "")
        if not texto:
            return "write ignorado: texto vazio.", "continue"
        _digitar_texto(pyautogui_mod, texto)
        print(f"Ayla digitou texto com {len(texto)} caracteres")
        return f"write {len(texto)} chars", "continue"

    print(f"Acao desconhecida: {acao}. Vou esperar.")
    _sleep_interruptivel(0.5)
    return f"acao_desconhecida {acao}", "continue"


def _read_config(args: argparse.Namespace) -> dict[str, Any]:
    config: dict[str, Any] = {}
    if args.config:
        config_path = Path(args.config)
        config = json.loads(config_path.read_text(encoding="utf-8"))
    config.setdefault("objetivo", args.objetivo or "")
    config.setdefault("intervalo", args.intervalo)
    config.setdefault("max_acoes", args.max_acoes)
    config.setdefault("modelo", args.modelo or "")
    config.setdefault("screen_max_side", args.screen_max_side)
    config.setdefault("destinatario_discord", args.destinatario_discord or "")
    config.setdefault("comentarios_discord", not args.sem_comentarios_discord)
    config.setdefault("cooldown_discord", args.cooldown_discord)
    config.setdefault("refinar_cliques", not args.sem_refinar_cliques)
    return config


def executar_loop(config: dict[str, Any]) -> int:
    _setup_console()
    print("=== Ayla: modo Tomar_controle ===")
    print("Pressione END a qualquer momento para parar.")
    print("Tambem da para mover o mouse para o canto superior esquerdo (failsafe do PyAutoGUI).")
    print("")

    api_keys = _api_keys()
    if not api_keys:
        print("Nenhuma GEMINI_API_KEY_1..7 encontrada no .env.")
        return 2

    try:
        import pyautogui

        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.05
    except Exception as exc:
        print(f"PyAutoGUI nao esta disponivel: {exc}")
        return 2

    intencao_inicial = str(config.get("intencao_inicial") or config.get("objetivo") or "").strip()
    intervalo = _clamp_float(config.get("intervalo"), 0.1, 10.0, DEFAULT_INTERVALO)
    max_acoes = max(0, int(config.get("max_acoes") or 0))
    screen_max_side = max(640, int(config.get("screen_max_side") or DEFAULT_SCREEN_MAX_SIDE))
    modelos = _modelos_preferidos(str(config.get("modelo") or ""))
    modelos_bloqueados: set[str] = set()
    comentarios_discord = bool(config.get("comentarios_discord", True))
    destinatario_discord = str(config.get("destinatario_discord") or "")
    cooldown_discord = _clamp_float(config.get("cooldown_discord"), 5.0, 300.0, DEFAULT_DISCORD_COOLDOWN)
    refinar_cliques = bool(config.get("refinar_cliques", DEFAULT_REFINAR_CLIQUES))
    historico: list[str] = []
    avisos_controle: list[str] = []
    assinaturas: list[str] = []
    rodada = 0
    mensagens_discord = 0
    ultima_mensagem_discord = 0.0
    stop_event = threading.Event()
    _iniciar_watchdog_end(pyautogui, stop_event)

    print(f"Intencao inicial: {intencao_inicial or 'explorar/interagir com cuidado'}")
    print(f"Intervalo: {intervalo:.2f}s")
    print(f"Limite de acoes: {max_acoes if max_acoes else 'sem limite'}")
    if comentarios_discord:
        print(f"Comentarios Discord: ligados (cooldown {cooldown_discord:.0f}s)")
    else:
        print("Comentarios Discord: desligados")
    print(f"Refino de mira: {'ligado' if refinar_cliques else 'desligado'}")
    print("")

    try:
        while True:
            if stop_event.is_set() or _end_pressed():
                print("END detectado. Parando...")
                break
            if max_acoes and rodada >= max_acoes:
                print("Limite de acoes atingido. Parando...")
                break

            rodada += 1
            print(f"\n--- rodada {rodada} | {datetime.now().strftime('%H:%M:%S')} ---")
            if modelos_bloqueados:
                print(f"Modelos bloqueados nesta sessao: {', '.join(sorted(modelos_bloqueados))}")
            imagem_png, tela = _capturar_tela(pyautogui, screen_max_side)
            prompt = _prompt_iteracao(
                intencao_inicial,
                tela,
                historico,
                rodada,
                avisos_controle,
                comentarios_discord,
                destinatario_discord,
                mensagens_discord,
            )
            resposta_texto, modelo_usado = _chamar_gemini(
                api_keys,
                modelos,
                imagem_png,
                prompt,
                modelos_bloqueados,
            )
            print(f"Modelo: {modelo_usado}")
            data = _extrair_json(resposta_texto)

            mensagem_discord, destino_discord = _extrair_mensagem_discord(data)
            if comentarios_discord and mensagem_discord:
                agora = time.monotonic()
                pode_enviar = (
                    mensagens_discord == 0
                    or agora - ultima_mensagem_discord >= cooldown_discord
                    or str(data.get("estado") or "").strip().lower() in {"travada", "finalizando"}
                )
                if pode_enviar:
                    resultado_dm = _publicar_mensagem_discord(config, mensagem_discord, destino_discord)
                    print(f"Discord: {resultado_dm} {mensagem_discord}")
                    historico.append(f"discord: {mensagem_discord}")
                    mensagens_discord += 1
                    ultima_mensagem_discord = agora
                else:
                    print("Discord: mensagem ignorada por cooldown.")
                    avisos_controle.append("Voce tentou mandar mensagem no Discord cedo demais; espere algo relevante.")

            assinatura = _assinatura_acao(data, tela)
            repeticoes = sum(1 for item in assinaturas[-3:] if assinatura and item == assinatura)
            if assinatura and repeticoes >= 2:
                aviso = f"anti-loop: acao repetida bloqueada ({assinatura}); mude de estrategia."
                print(aviso)
                avisos_controle.append(aviso)
                historico.append(aviso)
                assinaturas.append(f"bloqueado:{assinatura}")
                if len(avisos_controle) > 12:
                    avisos_controle = avisos_controle[-12:]
                if len(historico) > 30:
                    historico = historico[-30:]
                if not _sleep_interruptivel(intervalo) or stop_event.is_set():
                    print("END detectado. Parando...")
                    break
                continue

            log, status = _executar_acao(
                pyautogui,
                data,
                tela,
                imagem_png,
                api_keys,
                modelos,
                modelos_bloqueados,
                refinar_cliques,
            )
            if assinatura:
                assinaturas.append(assinatura)
                if len(assinaturas) > 20:
                    assinaturas = assinaturas[-20:]
            historico.append(log)
            if len(historico) > 30:
                historico = historico[-30:]

            if status in {"stop", "done"}:
                print(log)
                break
            if not _sleep_interruptivel(intervalo) or stop_event.is_set():
                print("END detectado. Parando...")
                break

    except KeyboardInterrupt:
        print("CTRL+C detectado. Parando...")
    except Exception as exc:
        print(f"Erro no loop Tomar_controle: {exc}")
        return 1
    finally:
        stop_event.set()
        _liberar_tudo(pyautogui)
        _marcar_sessao_encerrada(config)
        print("Controle encerrado.")

    return 0


def _start_new_window(config_path: Path) -> None:
    script = Path(__file__).resolve()
    python_exe = sys.executable

    if os.name == "nt":
        command = (
            f'& "{python_exe}" "{script}" --loop --config "{config_path}"; '
            'Write-Host ""; '
            'Read-Host "Sessao encerrada. Pressione ENTER para fechar"'
        )
        encoded = base64.b64encode(command.encode("utf-16le")).decode("ascii")
        creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        subprocess.Popen(
            ["powershell", "-NoExit", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
            cwd=str(_repo_root()),
            creationflags=creationflags,
        )
        return

    subprocess.Popen([python_exe, str(script), "--loop", "--config", str(config_path)], cwd=str(_repo_root()))


def tomar_controle(
    objetivo: str = "",
    intervalo: float = DEFAULT_INTERVALO,
    max_acoes: int = DEFAULT_MAX_ACOES,
    modelo: str = "",
    destinatario_discord: str = "",
    comentarios_discord: bool = True,
    cooldown_discord: float = DEFAULT_DISCORD_COOLDOWN,
    refinar_cliques: bool = DEFAULT_REFINAR_CLIQUES,
) -> str:
    """
    Abre uma janela separada onde a Ayla observa a tela e controla mouse/teclado.
    Use END para parar.
    """
    try:
        config_path = _sessions_dir() / f"tomar_controle_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.getpid()}.json"
        queue_path = config_path.parent / f"{config_path.stem}.discord.jsonl"
        done_path = config_path.parent / f"{config_path.stem}.done"
        config = {
            "objetivo": objetivo or "",
            "intencao_inicial": objetivo or "",
            "intervalo": _clamp_float(intervalo, 0.1, 10.0, DEFAULT_INTERVALO),
            "max_acoes": max(0, int(max_acoes or 0)),
            "modelo": modelo or "",
            "screen_max_side": DEFAULT_SCREEN_MAX_SIDE,
            "destinatario_discord": destinatario_discord or "",
            "comentarios_discord": bool(comentarios_discord),
            "cooldown_discord": _clamp_float(cooldown_discord, 5.0, 300.0, DEFAULT_DISCORD_COOLDOWN),
            "discord_queue_path": str(queue_path),
            "discord_done_path": str(done_path),
            "refinar_cliques": bool(refinar_cliques),
        }
        config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
        if config["comentarios_discord"]:
            _iniciar_bridge_discord(queue_path, done_path)
        _start_new_window(config_path)
        return (
            "Janela do modo Tomar_controle aberta. "
            "A Ayla vai observar a tela em loop, agir com autonomia e comentar no Discord quando fizer sentido. "
            "Pressione END para parar, como um Ctrl+C de emergencia."
        )
    except Exception as exc:
        return f"Erro ao abrir o modo Tomar_controle: {exc}"


def register(tool_map, function_declarations) -> None:
    tool_map["tomar_controle"] = tomar_controle
    if any(fd.get("name") == "tomar_controle" for fd in function_declarations):
        return
    function_declarations.append({
        "name": "tomar_controle",
        "description": (
            "Abre uma nova janela chamada Tomar_controle, onde a Ayla observa a tela "
            "e controla mouse/teclado em loop com autonomia. O objetivo e tratado como "
            "intencao inicial, nao como tarefa rigida. Ela pode comentar no Discord "
            "enquanto mexe. Para parar, a usuaria aperta END no teclado."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "objetivo": {
                    "type": "string",
                    "description": "Intencao inicial da sessao. Ex: 'abre o navegador para voce jogar xadrez'. Nao e uma ordem rigida.",
                },
                "intervalo": {
                    "type": "number",
                    "description": "Pausa em segundos entre uma acao e outra. Padrao: 0.8.",
                },
                "max_acoes": {
                    "type": "integer",
                    "description": "Limite opcional de acoes. Use 0 para continuar ate apertar END.",
                },
                "modelo": {
                    "type": "string",
                    "description": "Modelo Gemini opcional. Se vazio, usa a lista padrao da Ayla.",
                },
                "destinatario_discord": {
                    "type": "string",
                    "description": "Nome da whitelist para receber comentarios no Discord. Se vazio, usa a dona da Ayla.",
                },
                "comentarios_discord": {
                    "type": "boolean",
                    "description": "Se true, permite que a Ayla mande comentarios curtos no Discord enquanto controla.",
                },
                "cooldown_discord": {
                    "type": "number",
                    "description": "Minimo de segundos entre comentarios no Discord. Padrao: 20.",
                },
                "refinar_cliques": {
                    "type": "boolean",
                    "description": "Se true, antes de clicar a Ayla faz um zoom no alvo e recalibra a coordenada. Padrao: true.",
                },
            },
        },
    })


try:
    register(TOOL_MAP, FUNCTION_DECLARATIONS)
except Exception:
    pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Modo Tomar_controle da Ayla.")
    parser.add_argument("--loop", action="store_true", help="Executa o loop de controle.")
    parser.add_argument("--config", default="", help="Arquivo JSON de configuracao.")
    parser.add_argument("--objetivo", default="", help="Objetivo do controle.")
    parser.add_argument("--intervalo", type=float, default=DEFAULT_INTERVALO)
    parser.add_argument("--max-acoes", type=int, default=DEFAULT_MAX_ACOES)
    parser.add_argument("--modelo", default="")
    parser.add_argument("--screen-max-side", type=int, default=DEFAULT_SCREEN_MAX_SIDE)
    parser.add_argument("--destinatario-discord", default="")
    parser.add_argument("--sem-comentarios-discord", action="store_true")
    parser.add_argument("--cooldown-discord", type=float, default=DEFAULT_DISCORD_COOLDOWN)
    parser.add_argument("--sem-refinar-cliques", action="store_true")
    args = parser.parse_args()

    if args.loop:
        return executar_loop(_read_config(args))

    print(tomar_controle(
        objetivo=args.objetivo,
        intervalo=args.intervalo,
        max_acoes=args.max_acoes,
        modelo=args.modelo,
        destinatario_discord=args.destinatario_discord,
        comentarios_discord=not args.sem_comentarios_discord,
        cooldown_discord=args.cooldown_discord,
        refinar_cliques=not args.sem_refinar_cliques,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
