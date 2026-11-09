"""Aciona o Antigravity CLI para conversar, planejar e executar tarefas de código."""
import shutil
from ayla_platform import launch_terminal
# ══════════════════════════════════════════════════════════
#  MODO LAYKA ANTIGRAVITY (AGY) 🐾
#  Integração direta com o agy.exe + IPC Socket para Antigravity Window
# ══════════════════════════════════════════════════════════

from ayla_paths import project_path
import os
import sys
import json
import socket
import subprocess
import threading
import time
from pathlib import Path
from datetime import datetime

# Configurar encoding UTF-8 no stdout/stderr no Windows para suportar emojis
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# ── Configurações ─────────────────────────────────────────
_BASE_SEGURA = project_path().resolve()
_AGY_EXE_CUSTOM = os.environ.get("AYLA_AGY_EXECUTABLE", "").strip()
_TIMEOUT_PADRAO = 300
_PORTA_JANELA = 49153

# ── Estado da Sessão ─────────────────────────────────────
_sessao = {
    "ativo": False,
    "turnos": 0,
    "criado_em": None,
}

# ── Servidor IPC para Janela Visual (antigravity_window.py) ─────
_SERVER_SOCKET = None
_CLIENT_SOCKET = None
_PROCESSO_JANELA = None


def _exe() -> str:
    """Executável configurável ou descoberto no PATH, sem perfil de usuário fixo."""
    if _AGY_EXE_CUSTOM:
        path = Path(_AGY_EXE_CUSTOM).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
        raise FileNotFoundError('AYLA_AGY_EXECUTABLE não aponta para um executável válido.')
    executable = shutil.which('agy')
    if executable:
        return executable
    raise FileNotFoundError('CLI agy não encontrado. Instale uma versão Linux compatível ou configure AYLA_AGY_EXECUTABLE.')


def _safe_print(msg: str):
    """Print seguro para evitar erros de encodagem em consoles Windows."""
    try:
        print(msg)
    except Exception:
        pass


def _liberar_porta(porta: int):
    """Compatibilidade: uma porta ocupada é substituída por uma porta livre."""
    return None


def _iniciar_servidor_janela():
    """Inicia um servidor TCP local para se comunicar com a janela do Layka Antigravity."""
    global _SERVER_SOCKET, _CLIENT_SOCKET, _PORTA_JANELA
    if _SERVER_SOCKET is not None:
        return

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", _PORTA_JANELA))
        except OSError:
            s.bind(("127.0.0.1", 0))
            _PORTA_JANELA = s.getsockname()[1]

        s.listen(1)
        s.settimeout(0.5)
        _SERVER_SOCKET = s

        def _aceitar_conexao():
            global _CLIENT_SOCKET
            while _SERVER_SOCKET:
                try:
                    conn, _ = _SERVER_SOCKET.accept()
                    _CLIENT_SOCKET = conn
                except socket.timeout:
                    continue
                except Exception:
                    break

        t = threading.Thread(target=_aceitar_conexao, daemon=True)
        t.start()
    except Exception as e:
        _safe_print(f"[Layka Antigravity] Erro ao iniciar servidor TCP na porta {_PORTA_JANELA}: {e}")


def _garantir_janela_visual():
    """Garante que a janela visual (antigravity_window.py) esteja aberta e conectada via Socket."""
    global _PROCESSO_JANELA, _CLIENT_SOCKET
    _iniciar_servidor_janela()

    janela_viva = False
    if _PROCESSO_JANELA is not None:
        if _PROCESSO_JANELA.poll() is None:
            janela_viva = True

    if not janela_viva:
        _CLIENT_SOCKET = None
        script_window = _BASE_SEGURA / "MODOS" / "antigravity_window.py"
        if script_window.exists():
            try:
                python_exe = sys.executable or "python"
                _PROCESSO_JANELA = launch_terminal([python_exe, str(script_window), "--port", str(_PORTA_JANELA)], cwd=_BASE_SEGURA)
            except Exception as e:
                _safe_print(f"[Layka Antigravity] Erro ao abrir janela visual: {e}")

    # Aguarda a janela conectar via Socket (até 3 segundos)
    tentativas = 0
    while _CLIENT_SOCKET is None and tentativas < 30:
        time.sleep(0.1)
        tentativas += 1


def _enviar_evento_janela(evento: dict):
    """Envia um evento em formato JSON para a janela visual conectada."""
    global _CLIENT_SOCKET
    if _CLIENT_SOCKET is None:
        return
    try:
        data = json.dumps(evento, ensure_ascii=False) + "\n"
        _CLIENT_SOCKET.sendall(data.encode("utf-8"))
    except Exception:
        try:
            _CLIENT_SOCKET.close()
        except Exception:
            pass
        _CLIENT_SOCKET = None


# ── Execução Principal do AGY com Stream JSON ────────────

def _rodar_agy(args: list[str], timeout: int = _TIMEOUT_PADRAO) -> tuple[int, str]:
    """
    Roda o agy com --output-format stream-json:
    - Transmite eventos de pensamento, execução de ferramentas (tool_call) e resultados (tool_result) em tempo real
    - Mostra na janela visual exatamente o que o AGY está lendo/escrevendo
    """
    exe_path = _exe()
    cmd = [exe_path, "--dangerously-skip-permissions", "--output-format", "stream-json"] + args

    _enviar_evento_janela({"type": "status", "text": "🐾 Inicializando Modo Layka Antigravity (AGY)..."})

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(_BASE_SEGURA),
        )

        resposta_final = ""
        start_time = time.time()

        while True:
            linha = proc.stdout.readline()
            if not linha and proc.poll() is not None:
                break

            if linha:
                txt = linha.strip()
                if not txt:
                    continue

                if txt.startswith("{") and txt.endswith("}"):
                    try:
                        ev = json.loads(txt)
                        nome_evento = ev.get("event")

                        if nome_evento == "step_update":
                            step = ev.get("step_update", {})
                            stype = step.get("step_type")
                            sstate = step.get("state")

                            if stype == "tool":
                                t_info = step.get("tool_info", {})
                                t_name = step.get("tool_name") or t_info.get("name", "ferramenta")
                                t_args = t_info.get("parameters", {})

                                if sstate == "ACTIVE":
                                    _enviar_evento_janela({
                                        "type": "tool_call",
                                        "name": t_name,
                                        "args": t_args
                                    })
                                elif sstate == "DONE":
                                    dur = step.get("duration_seconds", 0)
                                    _enviar_evento_janela({
                                        "type": "tool_result",
                                        "name": t_name,
                                        "result": f"Concluído ({dur:.2f}s)" if dur else "Concluído"
                                    })

                            elif stype == "agent_response":
                                usage = step.get("usage", {})
                                thinking = usage.get("thinking_tokens")
                                if thinking:
                                    _enviar_evento_janela({
                                        "type": "status",
                                        "text": f"🧠 Raciocinando... ({thinking} tokens de pensamento)"
                                    })

                        elif nome_evento == "result":
                            res_obj = ev.get("result", {})
                            resposta_final = res_obj.get("response", "").strip()

                    except Exception:
                        pass
                else:
                    _enviar_evento_janela({"type": "status", "text": txt[:120]})

            if time.time() - start_time > timeout:
                proc.kill()
                msg = f"⏱️ O Layka Antigravity demorou mais de {timeout}s e foi interrompido."
                _enviar_evento_janela({"type": "status", "text": "⏱️ Timeout excedido."})
                return -1, msg

        rc = proc.poll() or 0

        if rc != 0 and not resposta_final:
            msg_erro = f"Código de saída {rc}"
            _enviar_evento_janela({"type": "status", "text": f"❌ Erro (código {rc})"})
            return rc, msg_erro

        res = resposta_final or "Instrução executada com sucesso."
        _enviar_evento_janela({"type": "response", "text": res, "model": "Layka Antigravity AGY"})
        return 0, res

    except FileNotFoundError:
        msg = f"❌ Executável do Antigravity CLI ('{exe_path}') não encontrado."
        _enviar_evento_janela({"type": "status", "text": "❌ Executável não encontrado."})
        return -1, msg
    except Exception as e:
        msg = f"❌ Erro ao executar Layka Antigravity CLI: {e}"
        _enviar_evento_janela({"type": "status", "text": f"❌ Erro: {e}"})
        return -1, msg


# ── Funções Públicas (Tools da Ayla & Layka) ─────────────────────

def abrir_antigravity(prompt_inicial: str = "") -> str:
    """Ativa a sessão do Modo Layka Antigravity CLI (agy) e abre a janela visual dedicada."""
    _sessao["ativo"] = True
    _sessao["turnos"] = 0
    _sessao["criado_em"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    _garantir_janela_visual()
    _enviar_evento_janela({"type": "status", "text": "Sessão Layka Antigravity iniciada."})

    if prompt_inicial and prompt_inicial.strip():
        return interagir_antigravity(prompt_inicial.strip())

    return "🚀 **Sessão do Modo Layka Antigravity CLI ativada!** Janela visual aberta."


def interagir_antigravity(mensagem: str) -> str:
    """Envia uma instrução para o Layka Antigravity CLI (agy) e retorna a resposta."""
    if not mensagem or not mensagem.strip():
        return "⚠️ Informe uma mensagem para enviar ao Layka Antigravity."

    _garantir_janela_visual()

    if not _sessao["ativo"]:
        _sessao["ativo"] = True
        _sessao["turnos"] = 0
        _sessao["criado_em"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    msg = mensagem.strip()

    _enviar_evento_janela({"type": "prompt", "text": msg})
    _enviar_evento_janela({"type": "model_start", "model": "Layka Antigravity AGY"})

    args = []
    if _sessao["turnos"] > 0:
        args.append("-c")
    args.extend(["-p", msg])

    rc, saida = _rodar_agy(args)
    _sessao["turnos"] += 1

    if rc != 0:
        return f"⚠️ Layka Antigravity retornou código {rc}:\n\n{saida}"

    return f"🐾 **Resposta do Layka Antigravity:**\n\n{saida}"


def modo_antigravity(prompt: str) -> str:
    """Alias principal — mesmo que interagir_antigravity."""
    return interagir_antigravity(prompt)


def modo_layka_antigravity(prompt: str) -> str:
    """Alias principal do Modo Layka Antigravity — mesmo que interagir_antigravity."""
    return interagir_antigravity(prompt)


def plano_antigravity(tarefa: str) -> str:
    """Pede ao Layka Antigravity CLI para criar um plano de implementação."""
    if not tarefa or not tarefa.strip():
        return "⚠️ Descreva a tarefa para criar o plano."

    _garantir_janela_visual()

    if not _sessao["ativo"]:
        _sessao["ativo"] = True
        _sessao["turnos"] = 0
        _sessao["criado_em"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    t = tarefa.strip()
    _enviar_evento_janela({"type": "prompt", "text": f"[GERAR PLANO] {t}"})
    _enviar_evento_janela({"type": "model_start", "model": "Layka Antigravity AGY (Plan Mode)"})

    args = ["--mode", "plan"]
    if _sessao["turnos"] > 0:
        args.append("-c")
    args.extend(["-p", t])

    rc, saida = _rodar_agy(args)
    _sessao["turnos"] += 1

    if rc != 0:
        return f"⚠️ Erro ao gerar plano (código {rc}):\n\n{saida}"

    return f"📋 **Plano do Layka Antigravity:**\n\n{saida}"


def aprovar_plano_antigravity() -> str:
    """Aprova o plano pendente no Layka Antigravity CLI."""
    if not _sessao["ativo"]:
        return "⚠️ Nenhuma sessão ativa. Crie um plano primeiro."

    _garantir_janela_visual()
    _enviar_evento_janela({"type": "prompt", "text": "[APROVAR PLANO]"})
    args = ["-c", "-p", "Approve and execute the plan."]
    rc, saida = _rodar_agy(args)
    _sessao["turnos"] += 1

    return f"✅ **Plano aprovado:**\n\n{saida}"


def rejeitar_plano_antigravity(motivo: str = "") -> str:
    """Rejeita o plano pendente no Layka Antigravity CLI."""
    if not _sessao["ativo"]:
        return "⚠️ Nenhuma sessão ativa."

    _garantir_janela_visual()
    msg = "Reject the plan."
    if motivo:
        msg += f" Reason: {motivo}"

    _enviar_evento_janela({"type": "prompt", "text": f"[REJEITAR PLANO] {motivo}"})
    args = ["-c", "-p", msg]
    rc, saida = _rodar_agy(args)
    _sessao["turnos"] += 1

    return f"❌ **Plano rejeitado:**\n\n{saida}"


def status_antigravity() -> str:
    """Retorna o status da sessão do Layka Antigravity CLI."""
    if _sessao["ativo"]:
        return (
            f"🟢 **Layka Antigravity CLI — Sessão ATIVA** 🐾\n"
            f"• Turnos: `{_sessao['turnos']}`\n"
            f"• Iniciada em: `{_sessao['criado_em']}`"
        )
    return "⚪ **Layka Antigravity CLI — Sessão inativa.**"


def fechar_antigravity() -> str:
    """Encerra a sessão do Layka Antigravity CLI."""
    _sessao["ativo"] = False
    _sessao["turnos"] = 0
    _sessao["criado_em"] = None
    _enviar_evento_janela({"type": "close", "text": "Sessão do Layka Antigravity encerrada."})
    return "🛑 **Sessão do Layka Antigravity CLI encerrada.**"


# ══════════════════════════════════════════════════════════
#  REGISTRO DE FERRAMENTAS
# ══════════════════════════════════════════════════════════

FERRAMENTAS_ANTIGRAVITY = {
    "modo_layka_antigravity": modo_layka_antigravity,
    "layka_antigravity": modo_layka_antigravity,
    "abrir_layka_antigravity": abrir_antigravity,
    "interagir_layka_antigravity": interagir_antigravity,
    "plano_layka_antigravity": plano_antigravity,
    "status_layka_antigravity": status_antigravity,
    "fechar_layka_antigravity": fechar_antigravity,
    "modo_antigravity": modo_antigravity,
    "abrir_antigravity": abrir_antigravity,
    "iniciar_antigravity": abrir_antigravity,
    "interagir_antigravity": interagir_antigravity,
    "enviar_antigravity": interagir_antigravity,
    "antigravity_cli": interagir_antigravity,
    "plano_antigravity": plano_antigravity,
    "aprovar_plano_antigravity": aprovar_plano_antigravity,
    "rejeitar_plano_antigravity": rejeitar_plano_antigravity,
    "status_antigravity": status_antigravity,
    "fechar_antigravity": fechar_antigravity,
    "parar_antigravity": fechar_antigravity,
    "cancelar_antigravity": fechar_antigravity,
}

_DECLARACOES = [
    {
        "name": "modo_layka_antigravity",
        "description": (
            "Invoca ou continua conversa com o Modo Layka Antigravity CLI (agy). 🐾 "
            "Abre a janela visual do terminal e retorna a resposta para a Ayla/Layka."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "A instrução, comando ou pergunta a enviar ao Layka Antigravity."
                }
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "layka_antigravity",
        "description": (
            "Alias para modo_layka_antigravity. Invoca o Modo Layka Antigravity CLI."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "A instrução, comando ou pergunta a enviar ao Layka Antigravity."
                }
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "modo_antigravity",
        "description": (
            "Invoca ou continua conversa com o Google Antigravity CLI (agy) / Modo Layka Antigravity. "
            "Abre a janela visual do terminal e retorna a resposta."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "A instrução, comando ou pergunta a enviar ao Antigravity."
                }
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "abrir_antigravity",
        "description": "Abre o Layka Antigravity CLI (agy) e inicializa a janela visual do terminal.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt_inicial": {
                    "type": "string",
                    "description": "Instrução inicial para o Layka Antigravity (opcional)."
                }
            }
        }
    },
    {
        "name": "interagir_antigravity",
        "description": "Envia uma instrução para o Layka Antigravity CLI (agy) e recebe a resposta.",
        "parameters": {
            "type": "object",
            "properties": {
                "mensagem": {
                    "type": "string",
                    "description": "A mensagem ou comando a enviar ao Antigravity."
                }
            },
            "required": ["mensagem"]
        }
    },
    {
        "name": "plano_antigravity",
        "description": "Cria um plano de implementação no Layka Antigravity CLI antes de alterar código.",
        "parameters": {
            "type": "object",
            "properties": {
                "tarefa": {
                    "type": "string",
                    "description": "A tarefa a ser planejada."
                }
            },
            "required": ["tarefa"]
        }
    },
    {
        "name": "aprovar_plano_antigravity",
        "description": "Aprova e executa o plano de implementação pendente no Layka Antigravity CLI.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "rejeitar_plano_antigravity",
        "description": "Rejeita e descarta o plano de implementação pendente no Layka Antigravity CLI.",
        "parameters": {
            "type": "object",
            "properties": {
                "motivo": {
                    "type": "string",
                    "description": "Motivo da rejeição (opcional)."
                }
            }
        }
    },
    {
        "name": "status_antigravity",
        "description": "Verifica se a sessão do Layka Antigravity CLI (agy) está ativa.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "fechar_antigravity",
        "description": "Encerra a sessão do Layka Antigravity CLI (agy).",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
]


def register(tool_map: dict, function_declarations: list):
    """Registra as ferramentas do Layka Antigravity no dicionário global de ferramentas da Ayla."""
    tool_map.update(FERRAMENTAS_ANTIGRAVITY)
    for dec in _DECLARACOES:
        if dec not in function_declarations:
            function_declarations.append(dec)


# Registro automático se importado diretamente
if "TOOL_MAP" in globals():
    TOOL_MAP.update(FERRAMENTAS_ANTIGRAVITY)
if "FUNCTION_DECLARATIONS" in globals():
    for _fd in _DECLARACOES:
        if _fd not in FUNCTION_DECLARATIONS:
            FUNCTION_DECLARATIONS.append(_fd)
