"""Aciona um agente de código com IA para planejar e executar tarefas no computador."""
from ayla_paths import resolve_path
from ayla_platform import shell_command, launch_terminal
import platform
# ══════════════════════════════════════════════════════════
#  MODO AGENTE DE CÓDIGO — Ayla Local Code Agent
#  Modelo primário: openai/gpt-oss-120b (Groq)
#  Secundário:      qwen/qwen3.6-27b (Groq)
#  Fallback Z.ai:   glm-5.3-flash
#  Usa o endpoint pay-as-you-go da Z.ai e o SDK Groq com agentic loop manual
#  Fluxo Conversacional em Janela PowerShell Dedicada
# ══════════════════════════════════════════════════════════

from ayla_paths import project_path
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
_BASE_SEGURA = project_path().resolve()

_MODELOS_AGENTE = ["openai/gpt-oss-120b", "qwen/qwen3.6-27b", "glm-5.3-flash"]

_COMANDOS_BLOQUEADOS = [
    "format", "del /s", "del /q /s", "rm -rf /", "rm -rf /*",
    "rmdir /s /q c:\\", "shutdown", "restart", ":(){", "mkfs",
    "dd if=", "reg delete", "bcdedit",
]

# ── Estado Persistente da Sessão do Agente ──────────────
_SESSAO_AGENTE = {
    "ativo": False,
    "cancelar": False,
    "messages": [],
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
    """Inicia um servidor TCP local para se comunicar com a janela do terminal."""
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
    """Abre o monitor do agente no terminal disponível."""
    global _PROCESSO_JANELA
    _iniciar_servidor_janela()
    if _PROCESSO_JANELA is not None and _PROCESSO_JANELA.poll() is None:
        return
    try:
        _PROCESSO_JANELA = launch_terminal([sys.executable, _BASE_SEGURA / 'MODOS' / 'agente_window.py', '--port', str(_PORTA_JANELA)], cwd=_BASE_SEGURA)
    except Exception as exc:
        _safe_print(f'[Agente] Monitor externo indisponível: {exc}')


def _enviar_evento_janela(evento: dict):
    """Envia um evento formatado em JSON para a janela do terminal."""
    global _CLIENT_SOCKET
    if _CLIENT_SOCKET:
        try:
            msg = json.dumps(evento, ensure_ascii=False) + "\n"
            _CLIENT_SOCKET.sendall(msg.encode("utf-8"))
        except Exception:
            _CLIENT_SOCKET = None

def fechar_modo_agente() -> str:
    """Encerra e para imediatamente a sessão do Modo Agente, cancelando o loop, fechando a janela do terminal e limpando o contexto."""
    global _SESSAO_AGENTE, _CLIENT_SOCKET, _PROCESSO_JANELA

    _SESSAO_AGENTE["cancelar"] = True
    _SESSAO_AGENTE["ativo"] = False
    _SESSAO_AGENTE["messages"] = []
    _SESSAO_AGENTE["modelo_atual"] = None
    _SESSAO_AGENTE["criado_em"] = None

    try:
        _enviar_evento_janela({"type": "close", "text": "Sessão encerrada e parada a pedido do usuário."})
    except Exception:
        pass

    if _CLIENT_SOCKET:
        try:
            _CLIENT_SOCKET.close()
        except Exception:
            pass
        _CLIENT_SOCKET = None

    if _PROCESSO_JANELA:
        try:
            if _PROCESSO_JANELA.poll() is None:
                _PROCESSO_JANELA.terminate()
                _PROCESSO_JANELA.kill()
        except Exception:
            pass
        _PROCESSO_JANELA = None

    _safe_print("[Agente] Sessão encerrada, janela fechada e processo cancelado.")
    return "🛑 Sessão do Modo Agente interrompida e parada com sucesso! A janela do terminal foi fechada."

def parar_modo_agente() -> str:
    """Alias para fechar_modo_agente. Para o agente imediatamente."""
    return fechar_modo_agente()


def status_modo_agente() -> str:
    """Retorna o status da sessão ativa do Modo Agente."""
    if globals().get("_AGENT_RUN_LOCK") and _AGENT_RUN_LOCK.locked():
        return "O agente está executando uma tarefa. Você pode conversar com a Ayla, consultar o status ou solicitar cancelamento."
    if _SESSAO_AGENTE.get("ativo"):
        turnos = len(_SESSAO_AGENTE.get("messages", []))
        mod = _SESSAO_AGENTE.get("modelo_atual", "Desconhecido")
        iniciado = _SESSAO_AGENTE.get("criado_em", "Desconhecido")
        janela_status = "🟢 Aberta" if (_PROCESSO_JANELA and _PROCESSO_JANELA.poll() is None) else "🔴 Fechada"
        return (
            f"🟢 **Modo Agente está ATIVO e Conversacional!**\n"
            f"• Janela do terminal: `{janela_status}`\n"
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
    1. ZAI_API_KEY no env
    2. bot.api_keys[] (rodízio da Ayla)
    3. ZAI_API_KEYS global
    """
    key = os.environ.get("ZAI_API_KEY", "").strip()
    if key:
        return key

    try:
        from dotenv import load_dotenv
        load_dotenv(_BASE_SEGURA / ".env")
        key = os.environ.get("ZAI_API_KEY", "").strip()
        if key:
            return key
    except Exception:
        pass

    import builtins
    bot_ref = globals().get("bot") or getattr(builtins, "bot", None)
    if bot_ref and hasattr(bot_ref, "api_keys") and bot_ref.api_keys:
        idx = getattr(bot_ref, "idx_api_atual", 0)
        return bot_ref.api_keys[idx % len(bot_ref.api_keys)]

    chaves = globals().get("ZAI_API_KEYS") or getattr(builtins, "ZAI_API_KEYS", [])
    if chaves:
        return chaves[0]

    return None

def _obter_groq_key() -> str | None:
    """Busca a GROQ_API_KEY no env, no arquivo .env ou no objeto bot."""
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if key:
        return key

    try:
        from dotenv import load_dotenv
        env_path = _BASE_SEGURA / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        else:
            load_dotenv(Path(__file__).resolve().parents[2] / ".env")
        key = os.environ.get("GROQ_API_KEY", "").strip()
        if key:
            return key
    except Exception:
        pass

    import builtins
    bot_ref = globals().get("bot") or getattr(builtins, "bot", None)
    if bot_ref:
        groq_k = getattr(bot_ref, "groq_api_key", None)
        if groq_k and str(groq_k).strip():
            return str(groq_k).strip()

    return None

def _obter_todas_api_keys() -> list[str]:
    """Retorna todas as API keys disponíveis para rodízio."""
    keys = []
    import builtins
    bot_ref = globals().get("bot") or getattr(builtins, "bot", None)
    if bot_ref and hasattr(bot_ref, "api_keys"):
        keys = list(bot_ref.api_keys)
    if not keys:
        chaves = globals().get("ZAI_API_KEYS") or getattr(builtins, "ZAI_API_KEYS", [])
        keys = list(chaves)
    zai_key = os.environ.get("ZAI_API_KEY", "").strip()
    if zai_key and zai_key not in keys:
        keys.insert(0, zai_key)
    return [k for k in keys if k.strip()]


# ══════════════════════════════════════════════════════════
#  VALIDAÇÃO DE CAMINHO SEGURO
# ══════════════════════════════════════════════════════════

def _caminho_seguro(caminho: str) -> bool:
    """Retorna True para qualquer caminho no sistema (acesso irrestrito a arquivos e pastas)."""
    try:
        resolve_path(caminho)
        return True
    except Exception:
        return False


# ══════════════════════════════════════════════════════════
#  FERRAMENTAS DO AGENTE
# ══════════════════════════════════════════════════════════

def _tool_executar_comando(comando: str) -> str:
    """Executa um comando no shell do sistema com timeout."""
    cmd_lower = comando.lower().strip()
    for bloqueado in _COMANDOS_BLOQUEADOS:
        if bloqueado in cmd_lower:
            return f"ERRO: Comando bloqueado por seguranca: '{bloqueado}'"

    _safe_print(f"  > {comando}")
    try:
        resultado = subprocess.run(
            shell_command(comando),
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
        p = resolve_path(caminho)
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
        p = resolve_path(caminho)
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
        p = resolve_path(caminho)
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
        p = resolve_path(caminho)
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
        p = resolve_path(caminho)
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
        origem = resolve_path(caminho_origem)
        destino = resolve_path(caminho_destino)

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
        p = resolve_path(caminho)
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

def _obter_tavily_key() -> str | None:
    """Busca a TAVILY_API_KEY no env, no arquivo .env ou no objeto bot."""
    key = os.environ.get("TAVILY_API_KEY", "").strip()
    if key:
        return key

    try:
        from dotenv import load_dotenv
        env_path = _BASE_SEGURA / ".env"
        if env_path.exists():
            load_dotenv(env_path)
        else:
            load_dotenv(Path(__file__).resolve().parents[2] / ".env")
        key = os.environ.get("TAVILY_API_KEY", "").strip()
        if key:
            return key
    except Exception:
        pass

    import builtins
    bot_ref = globals().get("bot") or getattr(builtins, "bot", None)
    if bot_ref:
        tav_k = getattr(bot_ref, "tavily_api_key", None)
        if tav_k and str(tav_k).strip():
            return str(tav_k).strip()

    return None

_MAX_CHARS_PESQUISA = 5698  # Limite exato de caracteres obtido na pesquisa 'capivara' (5698 chars / 4242 letras)

def _tool_pesquisar_internet(consulta: str) -> str:
    """Pesquisa na internet usando Tavily (mecanismo principal igual ao pesquisar_na_internet.py da Ayla),
    com fallback para DuckDuckGo. Limite de retorno ajustado para 5698 caracteres."""
    _safe_print(f"  pesquisando {consulta}")

    # ── 1. Tentar reutilizar módulo pesquisar_na_internet se disponível ──
    try:
        sys_path = str(_BASE_SEGURA / "MODOS" / "MODOS ADICIONAIS")
        if sys_path not in sys.path:
            sys.path.append(sys_path)
        import pesquisar_na_internet
        if hasattr(pesquisar_na_internet, "_busca_tavily"):
            res_tavily = pesquisar_na_internet._busca_tavily(consulta, fontes=5, max_caracteres=1000)
            if res_tavily:
                if len(res_tavily) > _MAX_CHARS_PESQUISA:
                    res_tavily = res_tavily[:_MAX_CHARS_PESQUISA] + "\n... [resultado truncado]"
                return res_tavily
    except Exception:
        pass

    # ── 2. Tentar API direta da Tavily ──
    tavily_key = _obter_tavily_key()
    if tavily_key:
        try:
            import requests
            url_api = "https://api.tavily.com/search"
            payload = {
                "api_key": tavily_key,
                "query": consulta,
                "search_depth": "basic",
                "include_images": False,
                "max_results": 5
            }
            resp = requests.post(url_api, json=payload, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                search_results = data.get("results", [])
                if search_results:
                    blocos = []
                    fontes = []
                    for item in search_results:
                        url = item.get("url", "")
                        titulo = item.get("title", "")
                        snippet = item.get("content", "") or item.get("raw_content", "")
                        if url and (titulo or snippet):
                            blocos.append(f"🔍 **[{titulo}]({url})**\n{snippet}\n")
                            fontes.append(f"• [{titulo}]({url})")

                    corpo = "\n---\n".join(blocos)
                    resultado_final = f"📚 **Resultados da pesquisa (via Tavily)** — \"{consulta}\"\n\n{corpo}\n\n🔗 **Fontes:**\n" + "\n".join(fontes)
                    if len(resultado_final) > _MAX_CHARS_PESQUISA:
                        resultado_final = resultado_final[:_MAX_CHARS_PESQUISA] + "\n... [resultado truncado]"
                    return resultado_final
        except Exception as e:
            _safe_print(f"  ⚠️ Tavily API falhou: {e}. Usando DuckDuckGo fallback...")

    # ── 3. Fallback DuckDuckGo ──
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            try:
                from duckduckgo_search import DDGS
            except ImportError:
                return "ERRO: Nenhum modulo de busca instalado (tavily, ddgs ou duckduckgo_search)."

        resultados = []
        with DDGS() as ddgs:
            for r in ddgs.text(consulta, max_results=6):
                titulo = r.get("title", "")
                link = r.get("href", r.get("link", ""))
                corpo = r.get("body", r.get("snippet", ""))
                resultados.append(f"  - {titulo}\n    {link}\n    {corpo}")

        if not resultados:
            return f"Nenhum resultado encontrado para: {consulta}"

        res_str = f"Resultados para '{consulta}' (DuckDuckGo):\n\n" + "\n\n".join(resultados)
        if len(res_str) > _MAX_CHARS_PESQUISA:
            res_str = res_str[:_MAX_CHARS_PESQUISA] + "\n... [resultado truncado]"
        return res_str
    except Exception as e:
        return f"ERRO na pesquisa: {e}"


# ══════════════════════════════════════════════════════════
#  DECLARAÇÕES DE FERRAMENTAS (compatibilidade Z.ai/OpenAI)
# ══════════════════════════════════════════════════════════

_AGENT_TOOL_DECLARATIONS = [
    {
        "name": "executar_comando",
        "description": "Executa um comando no terminal Bash no Linux ou PowerShell no Windows. Timeout de 90s. Use para instalar pacotes, rodar scripts, git, etc.",
        "parameters": {
            "type": "object",
            "properties": {
                "comando": {"type": "string", "description": "O comando a ser executado em Bash no Linux ou PowerShell no Windows."}
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
    "parar_modo_agente":  lambda args: fechar_modo_agente(),
    "parar_agent":        lambda args: fechar_modo_agente(),
    "parar_agente":       lambda args: fechar_modo_agente(),
    "cancelar_agente":    lambda args: fechar_modo_agente(),
}



# ══════════════════════════════════════════════════════════
#  SYSTEM PROMPTS DO AGENTE CONVERSACIONAL
# ══════════════════════════════════════════════════════════

_SYSTEM_PROMPT_AGENTE = ""


_SYSTEM_PROMPT_PLANEJAMENTO = ""


# ══════════════════════════════════════════════════════════
#  AGENTIC LOOP (núcleo do agente conversacional)
# ══════════════════════════════════════════════════════════

import ayla_state
import threading as _agent_threading
_AGENT_RUN_LOCK = _agent_threading.Lock()
_PLAN_LOCK = _agent_threading.Lock()

def _executar_agente(prompt: str, system_prompt=None, ferramentas_permitidas=None):
    if not _AGENT_RUN_LOCK.acquire(blocking=False):
        return "ERRO: O agente já está executando uma tarefa. Você pode consultar o status ou pedir o cancelamento."
    try:
        return _executar_agente_impl(prompt, system_prompt, ferramentas_permitidas)
    finally:
        _AGENT_RUN_LOCK.release()


def _executar_agente_impl(prompt: str, system_prompt: str = None, ferramentas_permitidas: list[str] = None) -> str:
    """Executa o agentic loop completo mantendo o contexto da conversa.
    Envia eventos em tempo real para a janela do terminal."""
    try:
        from zai_provider import (
            ZaiChatConfig,
            ZaiClient,
            ZaiMessage,
            ZaiToolCall,
            ZaiToolResult,
        )
    except ImportError:
        return "ERRO: Dependencia Z.ai ausente. Rode: pip install openai>=1.0 httpx"

    houve_erro_ferramenta = False
    # ── Garantir que a janela do terminal está aberta ──
    _garantir_janela_powershell()
    _enviar_evento_janela({"type": "prompt", "text": prompt})

    # ── Obter API key ──
    api_key = _obter_api_key()
    if not api_key:
        return "ERRO: Nenhuma API key encontrada (ZAI_API_KEY)."

    todas_keys = _obter_todas_api_keys()
    idx_key = todas_keys.index(api_key) if api_key in todas_keys else 0

    # ── Filtrar declarações de ferramentas se necessário ──
    decls_a_usar = _AGENT_TOOL_DECLARATIONS
    dispatch_a_usar = _TOOL_DISPATCH
    if ferramentas_permitidas:
        decls_a_usar = [td for td in _AGENT_TOOL_DECLARATIONS if td["name"] in ferramentas_permitidas]
        dispatch_a_usar = {k: v for k, v in _TOOL_DISPATCH.items() if k in ferramentas_permitidas}

    tools = [
        {"type": "function", "function": td}
        for td in decls_a_usar
    ]

    generation_config = {
        'max_tokens': 65536,
        'top_p': 0.95,
        'thinking_level': 'low',
    }

    config = ZaiChatConfig(
        system_prompt=system_prompt or _SYSTEM_PROMPT_AGENTE,
        tools=tools,
        max_tokens=generation_config['max_tokens'],
        top_p=generation_config['top_p'],
        thinking_level=generation_config['thinking_level'],
    )

    global _SESSAO_AGENTE
    _SESSAO_AGENTE["cancelar"] = False

    # ── Histórico de conversa contínuo ──
    if _SESSAO_AGENTE.get("ativo") and _SESSAO_AGENTE.get("messages"):
        messages = list(_SESSAO_AGENTE["messages"])
        messages.append({"role": "user", "content": prompt})
    else:
        messages = [{"role": "user", "content": prompt}]
        _SESSAO_AGENTE["ativo"] = True
        _SESSAO_AGENTE["criado_em"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")


    textos_finais = []
    ultimo_erro = None

    # ── Tentar cada modelo ──
    for modelo in _MODELOS_AGENTE:
        _enviar_evento_janela({"type": "model_start", "model": modelo})

        # ── ROTA GROQ ──
        if any(k in modelo.lower() for k in ("openai", "groq", "gpt-oss", "qwen", "deepseek", "llama")):
            groq_key = _obter_groq_key()
            if not groq_key:
                _safe_print(f"[Agente] GROQ_API_KEY nao encontrada. Pulando modelo Groq ({modelo})...")
                continue

            try:
                from groq import Groq
                groq_client = Groq(api_key=groq_key)
            except ImportError:
                _safe_print("[Agente] Modulo 'groq' nao instalado. Pulando modelo Groq...")
                continue

            groq_tools = [
                {
                    "type": "function",
                    "function": td
                }
                for td in decls_a_usar
            ]

            sys_msg = system_prompt or _SYSTEM_PROMPT_AGENTE
            groq_messages = [{"role": "system", "content": sys_msg}]

            # Converter histórico da sessão para formato Groq
            for item in messages:
                if isinstance(item, dict) and "role" in item:
                    groq_messages.append(item)
                elif isinstance(item, ZaiMessage):
                    converted = {"role": item.role, "content": item.text or ""}
                    if item.tool_call_id:
                        converted["tool_call_id"] = item.tool_call_id
                    if item.name:
                        converted["name"] = item.name
                    if item.tool_calls:
                        converted["tool_calls"] = [
                            {
                                "id": call.id,
                                "type": "function",
                                "function": {
                                    "name": call.name,
                                    "arguments": json.dumps(call.arguments, ensure_ascii=False),
                                },
                            }
                            for call in item.tool_calls
                        ]
                    groq_messages.append(converted)

            try:
                _safe_print(f"[Agente] Iniciando com {modelo} (Groq)...")
                textos_finais_groq = []

                concluiu = False
                for iteracao in range(_MAX_ITERACOES_LOOP):
                    if _SESSAO_AGENTE.get("cancelar") or not _SESSAO_AGENTE.get("ativo"):
                        _safe_print("[Agente] Loop cancelado a pedido do usuario.")
                        fechar_modo_agente()
                        return "🛑 O Modo Agente foi interrompido e parado com sucesso a seu pedido."

                    resp = groq_client.chat.completions.create(

                        model=modelo,
                        messages=groq_messages,
                        tools=groq_tools,
                        tool_choice="auto"
                    )

                    if not resp.choices:
                        break

                    choice = resp.choices[0].message
                    if choice.tool_calls:
                        groq_messages.append({
                            "role": "assistant",
                            "content": choice.content,
                            "tool_calls": [
                                {
                                    "id": tc.id,
                                    "type": "function",
                                    "function": {
                                        "name": tc.function.name,
                                        "arguments": tc.function.arguments
                                    }
                                } for tc in choice.tool_calls
                            ]
                        })
                        if choice.content and choice.content.strip():
                            textos_finais_groq.append(choice.content.strip())

                        for tc in choice.tool_calls:
                            if _SESSAO_AGENTE.get("cancelar") or not _SESSAO_AGENTE.get("ativo"):
                                _safe_print("[Agente] Interrompido antes da ferramenta.")
                                fechar_modo_agente()
                                return "🛑 O Modo Agente foi interrompido e parado com sucesso a seu pedido."

                            nome = tc.function.name

                            raw_args = tc.function.arguments
                            if isinstance(raw_args, str):
                                try:
                                    args = json.loads(raw_args)
                                except Exception:
                                    args = {"comando": raw_args}
                            else:
                                args = raw_args or {}

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

                            if not ayla_state.resultado_sucesso(resultado): houve_erro_ferramenta = True
                            _enviar_evento_janela({"type": "tool_result", "name": nome, "result": str(resultado)})

                            if len(str(resultado)) > _MAX_CHARS_RESULTADO:
                                resultado = str(resultado)[:_MAX_CHARS_RESULTADO] + "\n... [resultado truncado]"

                            groq_messages.append({
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "name": nome,
                                "content": str(resultado)
                            })
                    else:
                        if choice.content and choice.content.strip():
                            textos_finais_groq.append(choice.content.strip())
                            groq_messages.append({"role": "assistant", "content": choice.content.strip()})
                            concluiu = True
                        break

                conversa_guardada = [m for m in groq_messages if m.get("role") != "system"]
                _SESSAO_AGENTE["messages"] = conversa_guardada
                _SESSAO_AGENTE["modelo_atual"] = f"{modelo} (Groq)"
                _SESSAO_AGENTE["ativo"] = True

                resposta_final = "\n".join(textos_finais_groq) if textos_finais_groq else "(O agente executou as ferramentas mas nao gerou texto final.)"
                _enviar_evento_janela({"type": "response", "text": resposta_final, "model": modelo})

                if houve_erro_ferramenta:
                    return "ERRO: Uma ou mais ferramentas falharam. " + resposta_final
                if not concluiu:
                    return "ERRO: Limite de iterações atingido; execução não confirmada. " + resposta_final
                return f"[Agente | {modelo} (Groq)]\n\n{resposta_final}\n\n🟢 *(Modo Agente mantido ATIVO. Diga o que achou ou peça ajustes. Quando terminar, use 'fechar_modo_agente').*"

            except Exception as e:
                ultimo_erro = e
                erro_str = str(e)
                _safe_print(f"[Agente] ERRO com {modelo} (Groq): {erro_str[:100]}")
                _enviar_evento_janela({"type": "status", "text": f"Erro no modelo {modelo}: {erro_str[:80]}"})
                continue

        # ── ROTA Z.AI (FALLBACK) ──
        zai_messages = []
        for item in messages:
            if isinstance(item, ZaiMessage):
                zai_messages.append(item)
                continue
            if not isinstance(item, dict):
                zai_messages.append(ZaiMessage.user(str(item)))
                continue
            role = item.get("role", "user")
            text = str(item.get("content") or "")
            if role == "assistant":
                tool_calls = []
                for raw_call in item.get("tool_calls", []) or []:
                    fn = raw_call.get("function", {})
                    raw_args = fn.get("arguments", {})
                    if isinstance(raw_args, str):
                        try:
                            raw_args = json.loads(raw_args)
                        except Exception:
                            raw_args = {"_invalid_arguments": raw_args}
                    tool_calls.append(ZaiToolCall(
                        name=fn.get("name", ""),
                        arguments=raw_args or {},
                        id=raw_call.get("id"),
                    ))
                zai_messages.append(ZaiMessage.assistant(text, tool_calls))
            elif role == "tool":
                zai_messages.append(ZaiMessage.tool(ZaiToolResult(
                    name=item.get("name", ""),
                    result=text,
                    call_id=item.get("tool_call_id", ""),
                )))
            elif role == "system":
                continue
            else:
                zai_messages.append(ZaiMessage.user(text))

        tentativas_key = 0
        max_tentativas_key = len(todas_keys)

        while tentativas_key < max_tentativas_key:
            current_key = todas_keys[idx_key % len(todas_keys)]

            try:
                _safe_print(f"[Agente] Iniciando com {modelo}...")
                client = ZaiClient(api_key=current_key, timeout=120.0)

                concluiu = False
                for iteracao in range(_MAX_ITERACOES_LOOP):
                    if _SESSAO_AGENTE.get("cancelar") or not _SESSAO_AGENTE.get("ativo"):
                        _safe_print("[Agente] Loop cancelado a pedido do usuario.")
                        fechar_modo_agente()
                        return "🛑 O Modo Agente foi interrompido e parado com sucesso a seu pedido."

                    response = client.complete(
                        model=modelo,
                        messages=zai_messages,
                        config=config,
                    )

                    if not response.text and not response.tool_calls:
                        break

                    zai_messages.append(ZaiMessage.assistant(response.text, response.tool_calls))
                    fn_calls = list(response.tool_calls or [])
                    if response.text and response.text.strip():
                        textos_finais.append(response.text.strip())

                    if not fn_calls:
                        concluiu = bool(textos_finais)
                        break

                    fn_results = []
                    for fc in fn_calls:
                        if _SESSAO_AGENTE.get("cancelar") or not _SESSAO_AGENTE.get("ativo"):
                            _safe_print("[Agente] Interrompido antes da ferramenta.")
                            fechar_modo_agente()
                            return "🛑 O Modo Agente foi interrompido e parado com sucesso a seu pedido."

                        nome = fc.name
                        args = dict(fc.arguments) if fc.arguments else {}

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

                        if not ayla_state.resultado_sucesso(resultado): houve_erro_ferramenta = True
                        _enviar_evento_janela({"type": "tool_result", "name": nome, "result": str(resultado)})

                        if len(str(resultado)) > _MAX_CHARS_RESULTADO:
                            resultado = str(resultado)[:_MAX_CHARS_RESULTADO] + "\n... [resultado truncado]"

                        fn_results.append(ZaiToolResult(
                            name=nome,
                            result={"result": resultado},
                            call_id=fc.id,
                        ))

                    zai_messages.extend(ZaiMessage.tool(result) for result in fn_results)

                # Preserva a sessão aberta com todo o histórico acumulado
                _SESSAO_AGENTE["messages"] = zai_messages
                _SESSAO_AGENTE["modelo_atual"] = modelo
                _SESSAO_AGENTE["ativo"] = True

                resposta_final = "\n".join(textos_finais) if textos_finais else "(O agente executou as ferramentas mas nao gerou texto final.)"
                
                # Enviar resposta final para a janela do terminal
                _enviar_evento_janela({"type": "response", "text": resposta_final, "model": modelo})

                if houve_erro_ferramenta:
                    return "ERRO: Uma ou mais ferramentas falharam. " + resposta_final
                if not concluiu:
                    return "ERRO: Limite de iterações atingido; execução não confirmada. " + resposta_final
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

    return f"ERRO: Todos os modelos falharam. Ultimo erro: {ultimo_erro}"


# ══════════════════════════════════════════════════════════
#  WRAPPER SÍNCRONO PARA A AYLA
# ══════════════════════════════════════════════════════════

def modo_agente(prompt: str) -> str:
    """Invoca ou continua a conversa com o agente de código local.
    A sessão permanece aberta e interativa em uma janela do terminal."""
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
        ""
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
        f"A Usuario precisa aprovar este plano antes de eu executar.\n"
        f"• Diga 'aprovar' para executar\n"
        f"• Se quiser alteracoes no plano, basta me dizer o que mudar!\n"
        f"• Diga 'rejeitar' para descartar."
    )

def aprovar_plano() -> str:
    if not _PLAN_LOCK.acquire(blocking=False):
        return "ERRO: A aprovação deste plano já está em execução."
    try:
        return _aprovar_plano_impl()
    finally:
        _PLAN_LOCK.release()


def _aprovar_plano_impl() -> str:
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
        ""
    )

    resultado = _executar_agente(prompt=prompt_execucao)

    from ayla_state import resultado_sucesso
    plano["status"] = ("cancelado" if "🛑" in str(resultado) else ("executado" if resultado_sucesso(resultado) else "falhou"))
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
    "description": "Invoca ou continua conversa interativa com o agente de código no terminal.",
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
    "description": "Gera um plano de implementação detalhado antes de alterar código.",
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
        "O agente executara o plano na janela do terminal e continuara ATIVO para receber ajustes ou correcoes se der algum problema."
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
TOOL_MAP["parar_modo_agente"] = fechar_modo_agente
TOOL_MAP["parar_agent"] = fechar_modo_agente
TOOL_MAP["parar_agente"] = fechar_modo_agente
TOOL_MAP["cancelar_agente"] = fechar_modo_agente

FUNCTION_DECLARATIONS.append({
    "name": "fechar_modo_agente",
    "description": "Encerra a sessão ativa do Modo Agente de código no terminal.",
    "parameters": {
        "type": "object",
        "properties": {},
    }
})

FUNCTION_DECLARATIONS.append({
    "name": "parar_modo_agente",
    "description": (
        "Para e interrompe a execução do Modo Agente imediatamente. "
        "Chame esta ferramenta quando o usuário disser 'parar agent', 'parar agente', 'stop agent', 'cancela agente', etc."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
    }
})

TOOL_MAP["status_modo_agente"] = status_modo_agente
FUNCTION_DECLARATIONS.append({
    "name": "status_modo_agente",
    "description": "Verifica o status da sessao do Modo Agente e da janela do terminal.",
    "parameters": {
        "type": "object",
        "properties": {},
    }
})

