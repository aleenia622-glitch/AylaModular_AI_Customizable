# ══════════════════════════════════════════════════════════
#  MODO AGENTE DE CÓDIGO — Ayla Local Code Agent
#  Modelo primário: gemini-3.6-flash / gemini-3.5-flash
#  Fallbacks:       gemini-3-flash-preview → gemini-2.5-flash → gemma-4-31b-it → gemma-4-26b-a4b-it
#  Usa google-genai SDK com agentic loop manual
#  Fluxo Conversacional em Janela PowerShell Dedicada
# ══════════════════════════════════════════════════════════

import os
import sys
import re
import json
import socket
import subprocess
import threading
import asyncio
from pathlib import Path
from datetime import datetime

# ── Constantes ──────────────────────────────────────────
_TIMEOUT_COMANDO = 90           # segundos para comandos no terminal
_MAX_ITERACOES_LOOP = 25        # máximo de tool-calls antes de forçar parada
_MAX_LINHAS_LEITURA = 500       # max linhas por leitura de arquivo
_MAX_CHARS_RESULTADO = 12000    # truncar resultados muito grandes
_BASE_SEGURA = Path(__file__).resolve().parents[2]

_MODELOS_AGENTE = ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-3-flash-preview", "gemini-2.5-flash", "gemma-4-31b-it", "gemma-4-26b-a4b-it"]

_COMANDOS_BLOQUEADOS = [
    "format", "del /s", "del /q /s", "rm -rf /", "rm -rf /*",
    "rmdir /s /q c:\\", "shutdown", "restart", ":(){", "mkfs",
    "dd if=", "reg delete", "bcdedit",
]

# ── Estado Persistente da Sessão do Agente ──────────────
_SESSAO_AGENTE = {
    "ativo": False,
    "contents": [],
    "modelo_atual": None,
    "criado_em": None,
}

# ── Servidor IPC para Janela Dedicada do PowerShell ─────
_SERVER_SOCKET = None
_CLIENT_SOCKET = None
_PROCESSO_JANELA = None
_PORTA_JANELA = 49152

def _safe_print(msg: str):
    """Print seguro para evitar encoding errors em consoles Windows cp1252."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))

def _iniciar_servidor_janela():
    """Inicia um servidor TCP local para se comunicar com a janela do PowerShell."""
    global _SERVER_SOCKET, _CLIENT_SOCKET, _PORTA_JANELA
    if _SERVER_SOCKET is not None:
        return

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", _PORTA_JANELA))
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
        _safe_print(f"[Janela] Erro ao iniciar servidor TCP: {e}")

def _garantir_janela_powershell():
    """Garante que a janela externa do PowerShell do agente esteja aberta e conectada."""
    global _PROCESSO_JANELA
    _iniciar_servidor_janela()

    janela_viva = False
    if _PROCESSO_JANELA is not None:
        if _PROCESSO_JANELA.poll() is None:
            janela_viva = True

    if not janela_viva:
        try:
            cmd = [
                "powershell.exe",
                "-NoExit",
                "-ExecutionPolicy", "Bypass",
                "-Command",
                f"$host.UI.RawUI.WindowTitle = 'Ayla Code Agent - Modo Agente'; [Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [System.Text.Encoding]::UTF8; python MODOS/agente_window.py --port {_PORTA_JANELA}"
            ]
            _PROCESSO_JANELA = subprocess.Popen(cmd, cwd=str(_BASE_SEGURA))
            _safe_print("[Agente] Nova janela de PowerShell do Agente iniciada.")
        except Exception as e:
            _safe_print(f"[Agente] Erro ao abrir janela do PowerShell: {e}")

def _enviar_evento_janela(evento: dict):
    """Envia um evento formatado em JSON para a janela do PowerShell."""
    global _CLIENT_SOCKET
    if _CLIENT_SOCKET:
        try:
            msg = json.dumps(evento, ensure_ascii=False) + "\n"
            _CLIENT_SOCKET.sendall(msg.encode("utf-8"))
        except Exception:
            _CLIENT_SOCKET = None

def fechar_modo_agente() -> str:
    """Encerra a sessão ativa do Modo Agente, fecha a janela do PowerShell e limpa seu histórico de contexto."""
    global _SESSAO_AGENTE, _CLIENT_SOCKET, _PROCESSO_JANELA
    if not _SESSAO_AGENTE.get("ativo"):
        return "ℹ️ Nenhuma sessão do Modo Agente está ativa no momento."

    # Notificar janela do PowerShell para fechar
    _enviar_evento_janela({"type": "close", "text": "Sessão encerrada pela Ayla."})

    _SESSAO_AGENTE["ativo"] = False
    _SESSAO_AGENTE["contents"] = []
    _SESSAO_AGENTE["modelo_atual"] = None
    _SESSAO_AGENTE["criado_em"] = None

    if _CLIENT_SOCKET:
        try:
            _CLIENT_SOCKET.close()
        except Exception:
            pass
        _CLIENT_SOCKET = None

    if _PROCESSO_JANELA and _PROCESSO_JANELA.poll() is None:
        try:
            _PROCESSO_JANELA.terminate()
        except Exception:
            pass
        _PROCESSO_JANELA = None

    _safe_print("[Agente] Sessão encerrada e janela fechada pela Ayla.")
    return "🔒 Sessão do Modo Agente encerrada, histórico limpo e janela do PowerShell fechada com sucesso!"

def status_modo_agente() -> str:
    """Retorna o status da sessão ativa do Modo Agente."""
    if _SESSAO_AGENTE.get("ativo"):
        turnos = len(_SESSAO_AGENTE.get("contents", []))
        mod = _SESSAO_AGENTE.get("modelo_atual", "Desconhecido")
        iniciado = _SESSAO_AGENTE.get("criado_em", "Desconhecido")
        janela_status = "🟢 Aberta" if (_PROCESSO_JANELA and _PROCESSO_JANELA.poll() is None) else "🔴 Fechada"
        return (
            f"🟢 **Modo Agente está ATIVO e Conversacional!**\n"
            f"• Janela do PowerShell: `{janela_status}`\n"
            f"• Modelo atual: `{mod}`\n"
            f"• Mensagens no contexto: `{turnos}`\n"
            f"• Iniciado em: `{iniciado}`\n\n"
            f"O agente está pronto para continuar a conversa. Para encerrar a sessão quando tudo estiver certo, use `fechar_modo_agente`."
        )
    return "⚪ **Modo Agente está INATIVO.** Nenhuma sessão aberta no momento."


# ══════════════════════════════════════════════════════════
#  OBTENÇÃO DE API KEY
# ══════════════════════════════════════════════════════════

def _obter_api_key() -> str | None:
    """Busca a melhor API key disponível, na ordem:
    1. AGENT_KEY no env
    2. bot.api_keys[] (rodízio da Ayla)
    3. GEMINI_API_KEYS global
    """
    key = os.environ.get("AGENT_KEY", "").strip()
    if key:
        return key

    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
        key = os.environ.get("AGENT_KEY", "").strip()
        if key:
            return key
    except Exception:
        pass

    import builtins
    bot_ref = globals().get("bot") or getattr(builtins, "bot", None)
    if bot_ref and hasattr(bot_ref, "api_keys") and bot_ref.api_keys:
        idx = getattr(bot_ref, "idx_api_atual", 0)
        return bot_ref.api_keys[idx % len(bot_ref.api_keys)]

    chaves = globals().get("GEMINI_API_KEYS") or getattr(builtins, "GEMINI_API_KEYS", [])
    if chaves:
        return chaves[0]

    return None

def _obter_todas_api_keys() -> list[str]:
    """Retorna todas as API keys disponíveis para rodízio."""
    keys = []
    import builtins
    bot_ref = globals().get("bot") or getattr(builtins, "bot", None)
    if bot_ref and hasattr(bot_ref, "api_keys"):
        keys = list(bot_ref.api_keys)
    if not keys:
        chaves = globals().get("GEMINI_API_KEYS") or getattr(builtins, "GEMINI_API_KEYS", [])
        keys = list(chaves)
    agent_key = os.environ.get("AGENT_KEY", "").strip()
    if agent_key and agent_key not in keys:
        keys.insert(0, agent_key)
    return [k for k in keys if k.strip()]


# ══════════════════════════════════════════════════════════
#  VALIDAÇÃO DE CAMINHO SEGURO
# ══════════════════════════════════════════════════════════

def _caminho_seguro(caminho: str) -> bool:
    """Retorna True para qualquer caminho no sistema (acesso irrestrito a arquivos e pastas)."""
    try:
        Path(caminho).resolve()
        return True
    except Exception:
        return False


# ══════════════════════════════════════════════════════════
#  FERRAMENTAS DO AGENTE
# ══════════════════════════════════════════════════════════

def _tool_executar_comando(comando: str) -> str:
    """Executa um comando no PowerShell com timeout."""
    cmd_lower = comando.lower().strip()
    for bloqueado in _COMANDOS_BLOQUEADOS:
        if bloqueado in cmd_lower:
            return f"ERRO: Comando bloqueado por seguranca: '{bloqueado}'"

    _safe_print(f"  > {comando}")
    try:
        resultado = subprocess.run(
            ["powershell", "-NoProfile", "-Command", comando],
            capture_output=True, text=True, timeout=_TIMEOUT_COMANDO,
            encoding="utf-8", errors="replace",
            cwd=str(_BASE_SEGURA),
        )
        saida = ""
        if resultado.stdout and resultado.stdout.strip():
            saida += resultado.stdout.strip()
        if resultado.stderr and resultado.stderr.strip():
            if saida:
                saida += "\n"
            saida += f"[stderr]: {resultado.stderr.strip()}"
        if not saida:
            saida = "(comando executado sem saida)"
        if resultado.returncode != 0:
            saida += f"\n[exit code: {resultado.returncode}]"
        if len(saida) > _MAX_CHARS_RESULTADO:
            saida = saida[:_MAX_CHARS_RESULTADO] + "\n... [saida truncada]"
        return saida
    except subprocess.TimeoutExpired:
        return f"ERRO: Comando excedeu o timeout de {_TIMEOUT_COMANDO}s"
    except Exception as e:
        return f"ERRO ao executar comando: {e}"

def _tool_listar_pasta(caminho: str) -> str:
    """Lista o conteúdo de um diretório."""
    _safe_print(f"  Listando pasta {caminho}")
    try:
        p = Path(caminho).resolve()
        if not p.exists():
            return f"ERRO: Pasta nao encontrada: {caminho}"
        if not p.is_dir():
            return f"ERRO: '{caminho}' nao e um diretorio"

        itens = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        linhas = []
        for item in itens:
            if item.is_dir():
                try:
                    n_filhos = len(list(item.iterdir()))
                except PermissionError:
                    n_filhos = "?"
                linhas.append(f"  [DIR]  {item.name}/  ({n_filhos} itens)")
            else:
                tamanho = item.stat().st_size
                if tamanho < 1024:
                    tam_str = f"{tamanho} B"
                elif tamanho < 1024 * 1024:
                    tam_str = f"{tamanho / 1024:.1f} KB"
                else:
                    tam_str = f"{tamanho / (1024*1024):.1f} MB"
                linhas.append(f"  [ARQ]  {item.name}  ({tam_str})")

        if not linhas:
            return f"Pasta vazia: {caminho}"
        header = f"Conteudo de {p} ({len(itens)} itens):\n"
        return header + "\n".join(linhas)
    except PermissionError:
        return f"ERRO: Sem permissao para acessar: {caminho}"
    except Exception as e:
        return f"ERRO ao listar pasta: {e}"

def _tool_ver_info_arquivo(caminho: str) -> str:
    """Mostra informações detalhadas sobre um arquivo."""
    try:
        p = Path(caminho).resolve()
        if not p.exists():
            return f"ERRO: Arquivo nao encontrado: {caminho}"

        stat = p.stat()
        tamanho = stat.st_size
        if tamanho < 1024:
            tam_str = f"{tamanho} B"
        elif tamanho < 1024 * 1024:
            tam_str = f"{tamanho / 1024:.1f} KB"
        else:
            tam_str = f"{tamanho / (1024*1024):.1f} MB"

        info = f"Nome: {p.name}\n"
        info += f"Caminho: {p}\n"
        info += f"Extensao: {p.suffix or '(sem extensao)'}\n"
        info += f"Tamanho: {tam_str}\n"
        info += f"Tipo: {'Diretorio' if p.is_dir() else 'Arquivo'}\n"
        info += f"Modificado: {datetime.fromtimestamp(stat.st_mtime).strftime('%d/%m/%Y %H:%M:%S')}\n"
        info += f"Criado: {datetime.fromtimestamp(stat.st_ctime).strftime('%d/%m/%Y %H:%M:%S')}\n"

        if p.is_file():
            try:
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    num_linhas = sum(1 for _ in f)
                info += f"Linhas: {num_linhas}\n"
            except Exception:
                info += "Linhas: (nao foi possivel contar)\n"

        _safe_print(f"  Info: {p.name} ({tam_str})")
        return info
    except Exception as e:
        return f"ERRO ao obter info do arquivo: {e}"

def _tool_ler_arquivo(caminho: str, linha_inicio: int = 1, linha_fim: int = -1) -> str:
    """Lê um arquivo com seleção de linhas."""
    try:
        p = Path(caminho).resolve()
        if not p.exists():
            return f"ERRO: Arquivo nao encontrado: {caminho}"
        if not p.is_file():
            return f"ERRO: '{caminho}' nao e um arquivo"

        with open(p, "r", encoding="utf-8", errors="replace") as f:
            todas_linhas = f.readlines()

        total = len(todas_linhas)
        inicio = max(1, int(linha_inicio)) if linha_inicio else 1
        fim = int(linha_fim) if (linha_fim and int(linha_fim) > 0) else total
        inicio = max(1, min(inicio, total))
        fim = max(inicio, min(fim, total))

        qtd = fim - inicio + 1
        if qtd > _MAX_LINHAS_LEITURA:
            fim = inicio + _MAX_LINHAS_LEITURA - 1

        linhas_selecionadas = todas_linhas[inicio - 1:fim]
        conteudo = "".join(f"{i}: {linha}" for i, linha in enumerate(linhas_selecionadas, start=inicio))

        _safe_print(f"  {p.name} lido {inicio} | {fim}")
        header = f"Arquivo: {p.name} (linhas {inicio}-{fim} de {total} total)\n"
        return header + conteudo
    except Exception as e:
        return f"ERRO ao ler arquivo: {e}"

def _tool_escrever_arquivo(caminho: str, conteudo: str) -> str:
    """Escreve/reescreve o conteúdo de um arquivo existente ou novo."""
    try:
        p = Path(caminho).resolve()
        if not _caminho_seguro(str(p)):
            return f"ERRO: Caminho fora da area segura. Permitido apenas em: {_BASE_SEGURA}"

        linhas_antes = 0
        if p.exists() and p.is_file():
            try:
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    linhas_antes = sum(1 for _ in f)
            except Exception:
                pass

        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(conteudo)

        linhas_depois = conteudo.count("\n") + (1 if conteudo and not conteudo.endswith("\n") else 0)
        if linhas_antes > 0:
            diff_str = f"+{max(0, linhas_depois - linhas_antes)}|-{max(0, linhas_antes - linhas_depois)}"
            _safe_print(f"  {p.name} editado {diff_str}")
            return f"{p.name} editado com sucesso ({diff_str}). Total: {linhas_depois} linhas."
        else:
            _safe_print(f"  {p.name} criado ({linhas_depois} linhas)")
            return f"{p.name} criado com sucesso. Total: {linhas_depois} linhas."
    except Exception as e:
        return f"ERRO ao escrever arquivo: {e}"

def _tool_criar_arquivo(caminho: str, conteudo: str = "") -> str:
    """Cria um arquivo novo. Falha se já existir."""
    try:
        p = Path(caminho).resolve()
        if not _caminho_seguro(str(p)):
            return f"ERRO: Caminho fora da area segura. Permitido apenas em: {_BASE_SEGURA}"
        if p.exists():
            return f"ERRO: O arquivo '{p.name}' ja existe. Use escrever_arquivo para sobrescrever."

        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(conteudo)

        num_linhas = conteudo.count("\n") + (1 if conteudo and not conteudo.endswith("\n") else 0)
        _safe_print(f"  {p.name} criado ({num_linhas} linhas)")
        return f"{p.name} criado com sucesso. {num_linhas} linhas."
    except Exception as e:
        return f"ERRO ao criar arquivo: {e}"

def _tool_renomear_mover(caminho_origem: str, caminho_destino: str) -> str:
    """Renomeia ou move um arquivo/pasta."""
    try:
        origem = Path(caminho_origem).resolve()
        destino = Path(caminho_destino).resolve()

        if not _caminho_seguro(str(origem)):
            return f"ERRO: Origem fora da area segura: {origem}"
        if not _caminho_seguro(str(destino)):
            return f"ERRO: Destino fora da area segura: {destino}"
        if not origem.exists():
            return f"ERRO: Origem nao encontrada: {caminho_origem}"
        if destino.exists():
            return f"ERRO: Destino ja existe: {caminho_destino}"

        destino.parent.mkdir(parents=True, exist_ok=True)
        origem.rename(destino)

        _safe_print(f"  {origem.name} -> {destino.name}")
        return f"{origem.name} movido/renomeado para {destino.name} com sucesso."
    except Exception as e:
        return f"ERRO ao renomear/mover: {e}"

def _tool_deletar_arquivo(caminho: str) -> str:
    """Deleta um arquivo (não pastas)."""
    try:
        p = Path(caminho).resolve()
        if not _caminho_seguro(str(p)):
            return f"ERRO: Caminho fora da area segura: {p}"
        if not p.exists():
            return f"ERRO: Arquivo nao encontrado: {caminho}"
        if p.is_dir():
            return "ERRO: Nao e permitido deletar pastas inteiras por seguranca. Use executar_comando se necessario."

        nome = p.name
        p.unlink()
        _safe_print(f"  {nome} deletado")
        return f"{nome} deletado com sucesso."
    except Exception as e:
        return f"ERRO ao deletar arquivo: {e}"

def _tool_pesquisar_internet(consulta: str) -> str:
    """Pesquisa na internet via DuckDuckGo."""
    _safe_print(f"  pesquisando {consulta}")
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            try:
                from duckduckgo_search import DDGS
            except ImportError:
                return "ERRO: Nenhum modulo de busca instalado (ddgs ou duckduckgo_search). Instale com: pip install ddgs"

        resultados = []
        with DDGS() as ddgs:
            for r in ddgs.text(consulta, max_results=6):
                titulo = r.get("title", "")
                link = r.get("href", r.get("link", ""))
                corpo = r.get("body", r.get("snippet", ""))
                resultados.append(f"  - {titulo}\n    {link}\n    {corpo}")

        if not resultados:
            return f"Nenhum resultado encontrado para: {consulta}"

        return f"Resultados para '{consulta}':\n\n" + "\n\n".join(resultados)
    except Exception as e:
        return f"ERRO na pesquisa: {e}"


# ══════════════════════════════════════════════════════════
#  DECLARAÇÕES DE FERRAMENTAS (google-genai SDK)
# ══════════════════════════════════════════════════════════

_AGENT_TOOL_DECLARATIONS = [
    {
        "name": "executar_comando",
        "description": "Executa um comando no terminal PowerShell do Windows. Timeout de 90s. Use para instalar pacotes, rodar scripts, git, etc.",
        "parameters": {
            "type": "object",
            "properties": {
                "comando": {"type": "string", "description": "O comando a ser executado no PowerShell."}
            },
            "required": ["comando"]
        }
    },
    {
        "name": "listar_pasta",
        "description": "Lista todos os arquivos e subpastas de um diretorio, mostrando tamanhos e quantidade de itens.",
        "parameters": {
            "type": "object",
            "properties": {
                "caminho": {"type": "string", "description": "Caminho absoluto do diretorio a listar."}
            },
            "required": ["caminho"]
        }
    },
    {
        "name": "ver_info_arquivo",
        "description": "Mostra informacoes detalhadas de um arquivo: nome, caminho, extensao, tamanho, numero de linhas, datas de criacao e modificacao.",
        "parameters": {
            "type": "object",
            "properties": {
                "caminho": {"type": "string", "description": "Caminho absoluto do arquivo."}
            },
            "required": ["caminho"]
        }
    },
    {
        "name": "ler_arquivo",
        "description": "Le o conteudo de um arquivo de texto com selecao de linhas. Maximo de 500 linhas por leitura.",
        "parameters": {
            "type": "object",
            "properties": {
                "caminho": {"type": "string", "description": "Caminho absoluto do arquivo a ser lido."},
                "linha_inicio": {"type": "integer", "description": "Numero da primeira linha a ler (1-indexed). Padrao: 1."},
                "linha_fim": {"type": "integer", "description": "Numero da ultima linha a ler. Padrao: -1."}
            },
            "required": ["caminho"]
        }
    },
    {
        "name": "escrever_arquivo",
        "description": "Escreve ou reescreve o conteudo completo de um arquivo. Sempre inclua o conteudo COMPLETO do arquivo.",
        "parameters": {
            "type": "object",
            "properties": {
                "caminho": {"type": "string", "description": "Caminho absoluto do arquivo."},
                "conteudo": {"type": "string", "description": "O conteudo completo a ser escrito no arquivo."}
            },
            "required": ["caminho", "conteudo"]
        }
    },
    {
        "name": "criar_arquivo",
        "description": "Cria um arquivo novo. Falha se o arquivo ja existir.",
        "parameters": {
            "type": "object",
            "properties": {
                "caminho": {"type": "string", "description": "Caminho absoluto do novo arquivo."},
                "conteudo": {"type": "string", "description": "Conteudo inicial do arquivo. Pode ser vazio."}
            },
            "required": ["caminho"]
        }
    },
    {
        "name": "renomear_mover",
        "description": "Renomeia ou move um arquivo ou pasta para um novo caminho.",
        "parameters": {
            "type": "object",
            "properties": {
                "caminho_origem": {"type": "string", "description": "Caminho absoluto atual do arquivo/pasta."},
                "caminho_destino": {"type": "string", "description": "Novo caminho absoluto (destino)."}
            },
            "required": ["caminho_origem", "caminho_destino"]
        }
    },
    {
        "name": "deletar_arquivo",
        "description": "Deleta um arquivo. Nao permite deletar pastas inteiras por seguranca.",
        "parameters": {
            "type": "object",
            "properties": {
                "caminho": {"type": "string", "description": "Caminho absoluto do arquivo a deletar."}
            },
            "required": ["caminho"]
        }
    },
    {
        "name": "pesquisar_internet",
        "description": "Pesquisa informacoes na internet usando DuckDuckGo.",
        "parameters": {
            "type": "object",
            "properties": {
                "consulta": {"type": "string", "description": "O termo ou frase de busca."}
            },
            "required": ["consulta"]
        }
    },
]

_TOOL_DISPATCH = {
    "executar_comando":   lambda args: _tool_executar_comando(args["comando"]),
    "listar_pasta":       lambda args: _tool_listar_pasta(args["caminho"]),
    "ver_info_arquivo":   lambda args: _tool_ver_info_arquivo(args["caminho"]),
    "ler_arquivo":        lambda args: _tool_ler_arquivo(
                              args["caminho"],
                              args.get("linha_inicio", 1),
                              args.get("linha_fim", -1)
                          ),
    "escrever_arquivo":   lambda args: _tool_escrever_arquivo(args["caminho"], args["conteudo"]),
    "criar_arquivo":      lambda args: _tool_criar_arquivo(args["caminho"], args.get("conteudo", "")),
    "renomear_mover":     lambda args: _tool_renomear_mover(args["caminho_origem"], args["caminho_destino"]),
    "deletar_arquivo":    lambda args: _tool_deletar_arquivo(args["caminho"]),
    "pesquisar_internet": lambda args: _tool_pesquisar_internet(args["consulta"]),
    "fechar_modo_agente": lambda args: fechar_modo_agente(),
}


# ══════════════════════════════════════════════════════════
#  SYSTEM PROMPTS DO AGENTE CONVERSACIONAL
# ══════════════════════════════════════════════════════════

_SYSTEM_PROMPT_AGENTE = """Voce e o Agente de Codigo da Ayla, um assistente de programacao local especializado.
Voce roda diretamente na maquina do usuario (Windows 11) e tem acesso a ferramentas para manipular arquivos, executar comandos e pesquisar na internet.

ACESSO E PERMISSOES DO SISTEMA:
- Voce tem total liberdade e acesso irrestrito para ler, criar, editar, mover ou deletar arquivos e pastas em QUALQUER caminho do sistema do usuario (ex: C:\\, D:\\, pasta de usuario, etc.).

FLUXO CONVERSACIONAL DE MULTIPLOS TURNOS:
- Voce esta em uma CONVERSA CONTINUA com a Ayla.
- Nao feche nem encerre a sessao por conta propria!
- A cada turno, responda o que foi pedido ou o que foi ajustado, e permaneca receptivo a novos feedbacks, correcoes ou proximas instrucoes da Ayla.
- Se a Ayla informar um erro ou pedir uma alteracao no codigo que voce acabou de fazer, use o historico da conversa para entender o contexto, analise o problema e faca a correcao.

REGRAS CRITICAS DE RESPOSTA:
- Responda EXCLUSIVAMENTE em portugues brasileiro. NUNCA escreva em ingles.
- Seja DIRETA e CONCISA. Nao mostre seu raciocinio interno ou planejamento.
- NAO repita o conteudo das ferramentas na resposta. Resuma os resultados.
- Ao finalizar cada etapa, faca um resumo curto e claro do que foi feito.
- Seja fofa e prestativa, voce e a assistente do usuario!

REGRAS DE USO DE FERRAMENTAS:
1. SEMPRE use listar_pasta antes de editar arquivos para entender a estrutura do projeto.
2. SEMPRE use ler_arquivo com linha_inicio e linha_fim para ler trechos especificos. NAO leia arquivos inteiros de uma vez (max 500 linhas por leitura).
3. Ao editar codigo, use ler_arquivo primeiro para ver o estado atual, depois escrever_arquivo com o conteudo COMPLETO e updated.
4. Se um comando falhar, analise o erro e tente uma solucao alternativa.
5. Use pesquisar_internet quando precisar de documentacao ou solucoes que voce nao sabe de cabeca."""


_SYSTEM_PROMPT_PLANEJAMENTO = """Voce e o Agente de Codigo da Ayla, na fase de PLANEJAMENTO.
Voce esta analisando o projeto para criar um plano de implementacao ANTES de executar qualquer coisa.

ACESSO E PERMISSOES DO SISTEMA:
- Voce tem total liberdade para analisar e planejar mudancas em QUALQUER pasta ou arquivo do sistema.

FLUXO CONVERSACIONAL:
- Voce esta em uma conversa continua.
- Gere o plano de forma clara e objetiva para a Ayla apresentar ao usuario.
- A sessao permanecera ATIVA apos o envio do plano para aguardar a aprovacao ou pedidos de ajustes.

REGRAS ABSOLUTAS:
- Responda EXCLUSIVAMENTE em portugues brasileiro. NUNCA em ingles.
- Seja DIRETA e CONCISA. Nao mostre raciocinio interno.
- Voce so pode ANALISAR (ler arquivos, listar pastas, pesquisar). NAO execute comandos, NAO escreva arquivos, NAO crie nada.
- Use as ferramentas de leitura para entender o codigo atual e depois gere o plano.

FORMATO DO PLANO (siga EXATAMENTE este formato):

## Objetivo
(O que sera feito, em 1-2 frases)

## Arquivos Afetados
- [MODIFICAR] caminho/do/arquivo.py — o que muda
- [CRIAR] caminho/do/novo.py — o que faz
- [DELETAR] caminho/do/velho.py — por que deletar

## Passos
1. Primeiro passo
2. Segundo passo
3. ...

## Riscos
- Algum risco ou cuidado importante (se houver)

Seja fofa e prestativa, voce e a assistente do usuario!"""


# ══════════════════════════════════════════════════════════
#  AGENTIC LOOP (núcleo do agente conversacional)
# ══════════════════════════════════════════════════════════

def _converter_historico_para_texto(contents: list) -> list:
    """Converte o histórico de conversa com estruturas de FunctionCall e FunctionResponse
    em texto simples para evitar erros em retries e fallbacks."""
    try:
        from google.genai import types as genai_types
    except ImportError:
        return contents

    novos_contents = []
    for content in contents:
        novas_partes = []
        for part in content.parts:
            if hasattr(part, "text") and part.text:
                novas_partes.append(genai_types.Part(text=part.text))
            elif hasattr(part, "function_call") and part.function_call and part.function_call.name:
                fc = part.function_call
                args_str = str(dict(fc.args)) if fc.args else "{}"
                novas_partes.append(genai_types.Part(text=f"[Chamada de ferramenta: {fc.name} com args={args_str}]"))
            elif hasattr(part, "function_response") and part.function_response and part.function_response.name:
                fr = part.function_response
                res = fr.response
                res_str = str(res.get("result", res)) if isinstance(res, dict) else str(res)
                novas_partes.append(genai_types.Part(text=f"[Resultado da ferramenta {fr.name}]:\n{res_str}"))
        if novas_partes:
            novos_contents.append(genai_types.Content(
                role=content.role,
                parts=novas_partes
            ))
    return novos_contents


def _executar_agente(prompt: str, system_prompt: str = None, ferramentas_permitidas: list[str] = None) -> str:
    """Executa o agentic loop completo mantendo o contexto da conversa.
    Envia eventos em tempo real para a janela do PowerShell."""
    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError:
        return "ERRO: O pacote google-genai nao esta instalado. Rode: pip install google-genai"

    # ── Garantir que a janela do PowerShell está aberta ──
    _garantir_janela_powershell()
    _enviar_evento_janela({"type": "prompt", "text": prompt})

    # ── Obter API key ──
    api_key = _obter_api_key()
    if not api_key:
        return "ERRO: Nenhuma API key encontrada (AGENT_KEY, GEMINI_API_KEYS, etc.)"

    todas_keys = _obter_todas_api_keys()
    idx_key = todas_keys.index(api_key) if api_key in todas_keys else 0

    # ── Filtrar declarações de ferramentas se necessário ──
    decls_a_usar = _AGENT_TOOL_DECLARATIONS
    dispatch_a_usar = _TOOL_DISPATCH
    if ferramentas_permitidas:
        decls_a_usar = [td for td in _AGENT_TOOL_DECLARATIONS if td["name"] in ferramentas_permitidas]
        dispatch_a_usar = {k: v for k, v in _TOOL_DISPATCH.items() if k in ferramentas_permitidas}

    # ── Montar tool declarations para o SDK ──
    tool_declarations = []
    for td in decls_a_usar:
        props_schema = {}
        params_def = td.get("parameters", {})
        for prop_name, prop_def in params_def.get("properties", {}).items():
            schema_kwargs = {"type": prop_def["type"]}
            if "description" in prop_def:
                schema_kwargs["description"] = prop_def["description"]
            props_schema[prop_name] = genai_types.Schema(**schema_kwargs)

        param_schema = genai_types.Schema(
            type="object",
            properties=props_schema,
            required=params_def.get("required", []),
        )
        tool_declarations.append(genai_types.FunctionDeclaration(
            name=td["name"],
            description=td["description"],
            parameters=param_schema,
        ))

    tools = [genai_types.Tool(function_declarations=tool_declarations)]

    config = genai_types.GenerateContentConfig(
        system_instruction=system_prompt or _SYSTEM_PROMPT_AGENTE,
        tools=tools,
        automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True),
    )

    global _SESSAO_AGENTE

    # ── Histórico de conversa contínuo ──
    if _SESSAO_AGENTE.get("ativo") and _SESSAO_AGENTE.get("contents"):
        contents = list(_SESSAO_AGENTE["contents"])
        contents.append(genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=prompt)]
        ))
    else:
        contents = [genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=prompt)]
        )]
        _SESSAO_AGENTE["ativo"] = True
        _SESSAO_AGENTE["criado_em"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

    textos_finais = []
    ultimo_erro = None

    # ── Tentar cada modelo ──
    for modelo in _MODELOS_AGENTE:
        _enviar_evento_janela({"type": "model_start", "model": modelo})

        tentativas_key = 0
        max_tentativas_key = len(todas_keys)

        while tentativas_key < max_tentativas_key:
            current_key = todas_keys[idx_key % len(todas_keys)]

            try:
                _safe_print(f"[Agente] Iniciando com {modelo}...")
                client = genai.Client(
                    api_key=current_key,
                    http_options=genai_types.HttpOptions(timeout=120_000),
                )

                for iteracao in range(_MAX_ITERACOES_LOOP):
                    response = client.models.generate_content(
                        model=modelo,
                        contents=contents,
                        config=config,
                    )

                    if not response.candidates or not response.candidates[0].content:
                        break

                    resp_content = response.candidates[0].content
                    contents.append(resp_content)

                    fn_calls = []
                    for part in resp_content.parts:
                        if hasattr(part, "function_call") and part.function_call and part.function_call.name:
                            fn_calls.append(part)
                        elif hasattr(part, "text") and part.text and part.text.strip():
                            textos_finais.append(part.text.strip())

                    if not fn_calls:
                        break

                    fn_response_parts = []
                    for fc_part in fn_calls:
                        fc = fc_part.function_call
                        nome = fc.name
                        args = dict(fc.args) if fc.args else {}

                        _safe_print(f"[Agente] Ferramenta: {nome}")
                        _enviar_evento_janela({"type": "tool_call", "name": nome, "args": args})

                        executor = dispatch_a_usar.get(nome)
                        if executor:
                            try:
                                resultado = executor(args)
                            except Exception as e:
                                resultado = f"ERRO na ferramenta {nome}: {e}"
                                _safe_print(f"  ERRO em {nome}: {e}")
                        else:
                            resultado = f"ERRO: Ferramenta desconhecida: {nome}"
                            _safe_print(f"  ERRO: Ferramenta desconhecida: {nome}")

                        _enviar_evento_janela({"type": "tool_result", "name": nome, "result": str(resultado)})

                        if len(resultado) > _MAX_CHARS_RESULTADO:
                            resultado = resultado[:_MAX_CHARS_RESULTADO] + "\n... [resultado truncado]"

                        fn_response_parts.append(genai_types.Part(
                            function_response=genai_types.FunctionResponse(
                                name=nome,
                                response={"result": resultado},
                            )
                        ))

                    contents.append(genai_types.Content(
                        role="user",
                        parts=fn_response_parts,
                    ))

                # Preserva a sessão aberta com todo o histórico acumulado
                _SESSAO_AGENTE["contents"] = contents
                _SESSAO_AGENTE["modelo_atual"] = modelo
                _SESSAO_AGENTE["ativo"] = True

                resposta_final = "\n".join(textos_finais) if textos_finais else "(O agente executou as ferramentas mas nao gerou texto final.)"
                
                # Enviar resposta final para a janela do PowerShell
                _enviar_evento_janela({"type": "response", "text": resposta_final, "model": modelo})

                return f"[Agente | {modelo}]\n\n{resposta_final}\n\n🟢 *(Modo Agente mantido ATIVO. Diga o que achou ou peça ajustes. Quando terminar, use 'fechar_modo_agente').*"

            except Exception as e:
                ultimo_erro = e
                erro_str = str(e)
                _safe_print(f"[Agente] ERRO com {modelo} (key #{idx_key + 1}): {erro_str[:100]}")
                _enviar_evento_janela({"type": "status", "text": f"Erro no modelo {modelo}: {erro_str[:80]}"})

                is_quota = any(s in erro_str for s in ("429", "RESOURCE_EXHAUSTED", "limit", "quota"))
                is_modelo_sobrecarregado = any(s in erro_str for s in ("503", "UNAVAILABLE", "demand", "overloaded"))
                is_server_interno = any(s in erro_str for s in ("500", "INTERNAL"))

                if is_quota:
                    idx_key = (idx_key + 1) % len(todas_keys)
                    tentativas_key += 1
                    continue
                elif is_modelo_sobrecarregado:
                    break
                elif is_server_interno:
                    idx_key = (idx_key + 1) % len(todas_keys)
                    tentativas_key += 1
                    continue
                else:
                    break

        # Tentar converter conteúdo para texto antes de tentar o próximo modelo em fallback
        contents = _converter_historico_para_texto(contents)

    return f"ERRO: Todos os modelos falharam. Ultimo erro: {ultimo_erro}"


# ══════════════════════════════════════════════════════════
#  WRAPPER SÍNCRONO PARA A AYLA
# ══════════════════════════════════════════════════════════

def modo_agente(prompt: str) -> str:
    """Invoca ou continua a conversa com o agente de código local.
    A sessão permanece aberta e interativa em uma janela do PowerShell."""
    if not prompt or not prompt.strip():
        return "Por favor, diga o que voce quer que o agente faca!"

    _safe_print(f"\n{'='*50}")
    _safe_print(f"[Agente de Codigo] Mensagem recebida da Ayla")
    _safe_print(f"{'='*50}")

    resultado = _executar_agente(prompt.strip())

    _safe_print(f"{'='*50}")
    _safe_print(f"[Agente de Codigo] Resposta finalizada")
    _safe_print(f"{'='*50}\n")

    return resultado


# ══════════════════════════════════════════════════════════
#  PLANO DE IMPLEMENTAÇÃO (conversacional & pendente)
# ══════════════════════════════════════════════════════════

_ARQUIVO_PLANO = _BASE_SEGURA / "_plano_agente_atual.json"

_FERRAMENTAS_PLANEJAMENTO = [
    "listar_pasta", "ver_info_arquivo", "ler_arquivo", "pesquisar_internet"
]

def _salvar_plano(tarefa: str, plano: str):
    """Salva o plano em arquivo JSON."""
    dados = {
        "tarefa": tarefa,
        "plano": plano,
        "status": "pendente",
        "criado_em": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
    }
    with open(_ARQUIVO_PLANO, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

def _carregar_plano() -> dict | None:
    """Carrega o plano salvo, se existir."""
    if not _ARQUIVO_PLANO.exists():
        return None
    try:
        with open(_ARQUIVO_PLANO, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def _limpar_plano():
    """Remove o arquivo de plano."""
    try:
        if _ARQUIVO_PLANO.exists():
            _ARQUIVO_PLANO.unlink()
    except Exception:
        pass

def plano_de_implementacao(tarefa: str) -> str:
    """Cria um plano de implementação analisando o projeto com ferramentas de leitura.
    O plano é salvo e a sessão do agente é mantida aberta aguardando aprovação ou ajustes."""
    if not tarefa or not tarefa.strip():
        return "Por favor, descreva a tarefa para eu criar o plano!"

    plano_atual = _carregar_plano()
    if plano_atual and plano_atual.get("status") == "pendente":
        return (
            f"Ja existe um plano pendente de aprovacao!\n\n"
            f"Tarefa: {plano_atual['tarefa']}\n"
            f"Criado em: {plano_atual['criado_em']}\n\n"
            f"Plano atual:\n{plano_atual['plano']}\n\n"
            f"Use 'aprovar_plano' para executar, peça ajustes com 'modo_agente' ou descarte com 'rejeitar_plano'."
        )

    _safe_print(f"\n{'='*50}")
    _safe_print(f"[Plano] Analisando projeto para criar plano...")
    _safe_print(f"{'='*50}")

    prompt_planejamento = (
        f"TAREFA SOLICITADA PELO USUARIO: {tarefa.strip()}\n\n"
        f"Analise o projeto usando as ferramentas de leitura disponiveis e crie um plano "
        f"de implementacao detalhado seguindo o formato especificado. "
        f"NAO execute nada ainda, apenas planeje e envie para aprovacao."
    )

    resultado = _executar_agente(
        prompt=prompt_planejamento,
        system_prompt=_SYSTEM_PROMPT_PLANEJAMENTO,
        ferramentas_permitidas=_FERRAMENTAS_PLANEJAMENTO,
    )

    plano_texto = resultado
    if plano_texto.startswith("[Agente |"):
        linhas = plano_texto.split("\n", 2)
        if len(linhas) > 2:
            plano_texto = linhas[2]
        elif len(linhas) > 1:
            plano_texto = linhas[1]

    _salvar_plano(tarefa.strip(), plano_texto.strip())

    _safe_print(f"{'='*50}")
    _safe_print(f"[Plano] Plano criado e aguardando aprovacao")
    _safe_print(f"{'='*50}\n")

    return (
        f"Aqui esta o plano de implementacao:\n\n"
        f"{plano_texto.strip()}\n\n"
        f"---\n"
        f"O usuario precisa aprovar este plano antes de eu executar.\n"
        f"• Diga 'aprovar' para executar\n"
        f"• Se quiser alteracoes no plano, basta me dizer o que mudar!\n"
        f"• Diga 'rejeitar' para descartar."
    )

def aprovar_plano() -> str:
    """Aprova e executa o plano de implementação pendente mantendo a sessão conversacional ativa."""
    plano = _carregar_plano()
    if not plano:
        return "Nao existe nenhum plano pendente para aprovar. Use 'plano_de_implementacao' primeiro."

    if plano.get("status") != "pendente":
        return f"O plano atual ja foi {plano.get('status', 'processado')}. Crie um novo plano se necessario."

    tarefa = plano["tarefa"]
    plano_texto = plano["plano"]

    _safe_print(f"\n{'='*50}")
    _safe_print(f"[Plano] Aprovado! Executando no mesmo contexto conversacional...")
    _safe_print(f"{'='*50}")

    prompt_execucao = (
        f"PLANO APROVADO PELO USUARIO PARA A TAREFA: {tarefa}\n\n"
        f"Execute o plano aprovado passo a passo usando as ferramentas necessarias.\n"
        f"Ao finalizar, faça um resumo claro do que foi alterado e informe que a sessao continua aberta caso ela queira testes, ajustes ou correcoes."
    )

    resultado = _executar_agente(prompt=prompt_execucao)

    plano["status"] = "executado"
    plano["executado_em"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    with open(_ARQUIVO_PLANO, "w", encoding="utf-8") as f:
        json.dump(plano, f, ensure_ascii=False, indent=2)

    _safe_print(f"{'='*50}")
    _safe_print(f"[Plano] Execucao finalizada! Sessao mantida ativa.")
    _safe_print(f"{'='*50}\n")

    return resultado

def rejeitar_plano(motivo: str = "") -> str:
    """Rejeita e descarta o plano de implementação pendente."""
    plano = _carregar_plano()
    if not plano:
        return "Nao existe nenhum plano pendente para rejeitar."

    if plano.get("status") != "pendente":
        return f"O plano atual ja foi {plano.get('status', 'processado')}."

    tarefa = plano["tarefa"]
    _limpar_plano()

    _safe_print(f"[Plano] Rejeitado: {tarefa[:60]}")

    msg = f"Plano rejeitado e descartado."
    if motivo:
        msg += f"\nMotivo registrado: {motivo}\nVoce pode me pedir um novo plano com os ajustes desejados."
    return msg


# ══════════════════════════════════════════════════════════
#  REGISTRO NO SISTEMA DE MÓDULOS DA AYLA
# ══════════════════════════════════════════════════════════

if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

TOOL_MAP["modo_agente"] = modo_agente
FUNCTION_DECLARATIONS.append({
    "name": "modo_agente",
    "description": (
        "Invoca ou continua a conversa com o agente de codigo local. "
        "O agente mantem a sessao ATIVA e interativa em uma janela dedicada do PowerShell. "
        "Use esta ferramenta para dar instrucoes, relatar erros/problemas ou pedir ajustes incrementais. "
        "A conversa permanece aberta ate voce chamar 'fechar_modo_agente'."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "A instrucao, feedback ou relatorio de erro para o agente de codigo."
            }
        },
        "required": ["prompt"]
    }
})

TOOL_MAP["plano_de_implementacao"] = plano_de_implementacao
FUNCTION_DECLARATIONS.append({
    "name": "plano_de_implementacao",
    "description": (
        "Cria um plano de implementacao detalhado ANTES de executar qualquer mudanca no codigo. "
        "O agente analisa o projeto, gera o plano e mantem a sessao ATIVA em uma janela do PowerShell aguardando aprovacao ou ajustes."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "tarefa": {
                "type": "string",
                "description": "Descricao detalhada da tarefa/feature/mudanca a ser planejada."
            }
        },
        "required": ["tarefa"]
    }
})

TOOL_MAP["aprovar_plano"] = aprovar_plano
FUNCTION_DECLARATIONS.append({
    "name": "aprovar_plano",
    "description": (
        "Aprova e executa o plano de implementacao pendente. "
        "O agente executara o plano na janela do PowerShell e continuara ATIVO para receber ajustes ou correcoes se der algum problema."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
    }
})

TOOL_MAP["rejeitar_plano"] = rejeitar_plano
FUNCTION_DECLARATIONS.append({
    "name": "rejeitar_plano",
    "description": (
        "Rejeita e descarta o plano de implementacao pendente, mantendo a conversa aberta para um novo plano."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "motivo": {
                "type": "string",
                "description": "Motivo da rejeicao (opcional)."
            }
        },
    }
})

TOOL_MAP["fechar_modo_agente"] = fechar_modo_agente
FUNCTION_DECLARATIONS.append({
    "name": "fechar_modo_agente",
    "description": (
        "Encerra a sessao ativa do Modo Agente de codigo, fecha a janela do PowerShell e limpa todo o seu historico. "
        "Chame esta ferramenta APENAS quando todas as alteracoes estiverem concluidas com sucesso e o usuario confirmar que terminou."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
    }
})

TOOL_MAP["status_modo_agente"] = status_modo_agente
FUNCTION_DECLARATIONS.append({
    "name": "status_modo_agente",
    "description": "Verifica o status da sessao do Modo Agente e da janela do PowerShell.",
    "parameters": {
        "type": "object",
        "properties": {},
    }
})
