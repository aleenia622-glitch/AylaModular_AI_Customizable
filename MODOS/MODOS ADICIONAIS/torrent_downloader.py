"""Baixa torrents com qBittorrent, consulta downloads e interrompe processos de download."""
from ayla_paths import resolve_path
from ayla_paths import project_path
import os
import sys
import subprocess
import shutil
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

# Adiciona o diretório raiz ao sys.path para importações se necessário
DIR_RAIZ = Path(__file__).resolve().parent.parent.parent
if str(DIR_RAIZ) not in sys.path:
    sys.path.append(str(DIR_RAIZ))

try:
    import ayla_state
except ImportError:
    ayla_state = None

# Garante compatibilidade se o arquivo for executado/importado individualmente
if "TOOL_MAP" not in globals():
    TOOL_MAP = {}
if "FUNCTION_DECLARATIONS" not in globals():
    FUNCTION_DECLARATIONS = []

# Dicionário em memória para acompanhar processos de torrent em segundo plano
PROCESSOS_TORRENT = {}
PROCESSOS_LOCK = threading.Lock()

PASTA_PADRAO_DOWNLOAD = project_path('TorrentsBaixados')


def _encontrar_qbittorrent():
    executable = shutil.which('qbittorrent') or shutil.which('qbittorrent-nox')
    if executable:
        return executable
    if os.name == 'nt':
        for key in ('ProgramFiles', 'ProgramFiles(x86)', 'LOCALAPPDATA'):
            base = os.environ.get(key)
            if base:
                for relative in ('qBittorrent/qbittorrent.exe', 'Programs/qBittorrent/qbittorrent.exe'):
                    path = Path(base) / relative
                    if path.is_file():
                        return str(path)
    return None


def _extrair_nome_torrent(link_limpo: str) -> str:
    """Extrai um nome legível a partir do magnet link ou nome do arquivo/URL."""
    if link_limpo.startswith("magnet:?"):
        try:
            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(link_limpo).query)
            if "dn" in parsed and parsed["dn"]:
                return parsed["dn"][0]
            if "xt" in parsed and parsed["xt"]:
                return f"Torrent_{parsed['xt'][0][-8:]}"
        except Exception:
            pass
        return "Torrent Magnet"

    nome_arq = Path(link_limpo).name
    if nome_arq:
        return nome_arq
    return "Torrent"


def baixar_torrent(
    link_ou_magnet: str,
    pasta_destino: str = "",
    aguardar_fim: bool = False,
    tempo_limite_segundos: int = 300
) -> str:
    """
    Inicia o download de um arquivo torrent ou magnet link utilizando exclusivamente o qBittorrent.
    """
    if not link_ou_magnet or not link_ou_magnet.strip():
        return "⚠️ Por favor, forneça um magnet link (magnet:?xt=...) ou URL/caminho de um arquivo .torrent válido."

    link_limpo = link_ou_magnet.strip()

    # Validação simples de magnet / torrent
    is_magnet = link_limpo.startswith("magnet:?")
    is_torrent_file = link_limpo.endswith(".torrent") or os.path.exists(link_limpo)
    is_http_torrent = link_limpo.startswith("http://") or link_limpo.startswith("https://")

    if not (is_magnet or is_torrent_file or is_http_torrent):
        return "⚠️ O link fornecido não parece ser um magnet link nem um arquivo/URL .torrent válido."

    exe_qbit = _encontrar_qbittorrent()

    # Define a pasta de destino
    if pasta_destino and pasta_destino.strip():
        destino_path = resolve_path(pasta_destino.strip())
    else:
        destino_path = PASTA_PADRAO_DOWNLOAD

    try:
        destino_path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return f"❌ Erro ao criar diretório de destino `{destino_path}`: {e}"

    # Se for uma URL HTTP/HTTPS apontando para um .torrent, baixa o arquivo localmente primeiro
    alvo_download = link_limpo
    if is_http_torrent:
        try:
            temp_torrent = destino_path / f"temp_{int(time.time())}.torrent"
            urllib.request.urlretrieve(link_limpo, temp_torrent)
            alvo_download = str(temp_torrent)
        except Exception as e:
            return f"❌ Erro ao baixar o arquivo .torrent da URL fornecida: {e}"

    nome_torrent = _extrair_nome_torrent(link_limpo)

    if not exe_qbit:
        # Se não encontrar o executável direto, tenta via associação de arquivo do SO
        try:
            if sys.platform == "win32":
                os.startfile(alvo_download)
            else:
                subprocess.Popen(["xdg-open", alvo_download])
            return (
                f"🚀 **Download enviado para o qBittorrent via sistema padrão!**\n"
                f"• **Nome:** `{nome_torrent}`\n"
                f"• **Destino:** `{destino_path}`"
            )
        except Exception as e:
            return (
                f"❌ **qBittorrent não foi localizado no sistema!**\n\n"
                f"Certifique-se de que o qBittorrent está instalado. Você pode instalá-lo via terminal:\n"
                f"Instale qbittorrent pelo gerenciador de pacotes do sistema."
            )

    # Monta comando do qBittorrent
    comando = [exe_qbit, f"--save-path={destino_path}", alvo_download]

    try:
        if aguardar_fim:
            proc = subprocess.run(
                comando,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=tempo_limite_segundos
            )
            if proc.returncode == 0:
                return (
                    f"✅ **Download enviado ao qBittorrent com sucesso!**\n"
                    f"• **Nome:** `{nome_torrent}`\n"
                    f"• **Destino:** `{destino_path}`"
                )
            else:
                erro_msg = proc.stderr.strip() if proc.stderr else proc.stdout.strip()
                return f"⚠️ qBittorrent encerrou com código {proc.returncode}:\n```{erro_msg[:500]}```"
        else:
            proc = subprocess.Popen(
                comando,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
            )

            pid = proc.pid
            with PROCESSOS_LOCK:
                PROCESSOS_TORRENT[pid] = {
                    "processo": proc,
                    "nome": nome_torrent,
                    "link": link_limpo,
                    "destino": str(destino_path),
                    "inicio": time.strftime("%H:%M:%S")
                }

            return (
                f"🚀 **Download Torrent adicionado ao qBittorrent!**\n"
                f"• **PID do Processo:** `{pid}`\n"
                f"• **Nome:** `{nome_torrent}`\n"
                f"• **Pasta de Destino:** `{destino_path}`\n\n"
                f"💡 Você pode verificar o status dos downloads a qualquer momento com `status_downloads_torrent`."
            )

    except subprocess.TimeoutExpired:
        return f"⏳ O comando excedeu o tempo limite de {tempo_limite_segundos}s. O qBittorrent continua executando na pasta `{destino_path}`."
    except Exception as e:
        return f"❌ Falha ao iniciar o qBittorrent: {e}"


def status_downloads_torrent() -> str:
    """
    Retorna o status dos downloads de torrent rodando em segundo plano.
    """
    with PROCESSOS_LOCK:
        if not PROCESSOS_TORRENT:
            return "ℹ️ Nenhum download de torrent ativo no momento em segundo plano."

        linhas = ["📊 **Status dos Downloads no qBittorrent:**\n"]
        pids_finalizados = []

        for pid, info in list(PROCESSOS_TORRENT.items()):
            proc = info["processo"]
            ret = proc.poll()
            if ret is None:
                status_str = "🟢 Em andamento / Aberto no qBittorrent"
            else:
                status_str = f"🏁 Processo concluído (código {ret})"
                pids_finalizados.append(pid)

            nome = info.get("nome", "Torrent")
            linhas.append(
                f"• **PID:** `{pid}` | **Nome:** `{nome}`\n"
                f"  - **Status:** {status_str}\n"
                f"  - **Início:** {info['inicio']}\n"
                f"  - **Destino:** `{info['destino']}`"
            )

        for pid in pids_finalizados:
            del PROCESSOS_TORRENT[pid]

        return "\n\n".join(linhas)


def parar_downloads_torrent(pid: int = None) -> str:
    """
    Encerra um processo do qBittorrent ativo (pelo PID) ou todos os processos em segundo plano.
    """
    with PROCESSOS_LOCK:
        if not PROCESSOS_TORRENT:
            return "ℹ️ Não há nenhum processo do qBittorrent ativo para parar."

        if pid is not None:
            if pid in PROCESSOS_TORRENT:
                info = PROCESSOS_TORRENT.pop(pid)
                proc = info["processo"]
                try:
                    proc.terminate()
                    time.sleep(0.2)
                    if proc.poll() is None:
                        proc.kill()
                    return f"🛑 Processo do qBittorrent PID `{pid}` encerrado com sucesso!"
                except Exception as e:
                    return f"⚠️ Erro ao encerrar processo PID `{pid}`: {e}"
            else:
                return f"⚠️ Processo PID `{pid}` não encontrado na lista de downloads ativos."

        encerrados = 0
        for p_id, info in list(PROCESSOS_TORRENT.items()):
            try:
                proc = info["processo"]
                proc.terminate()
                time.sleep(0.1)
                if proc.poll() is None:
                    proc.kill()
                encerrados += 1
            except Exception:
                pass
        PROCESSOS_TORRENT.clear()
        return f"🛑 Todos os {encerrados} processos do qBittorrent foram encerrados!"


def register(tool_map: dict, function_declarations: list):
    """Registra as ferramentas do módulo nos dicionários da Ayla."""
    tool_map["baixar_torrent"] = baixar_torrent
    tool_map["status_downloads_torrent"] = status_downloads_torrent
    tool_map["parar_downloads_torrent"] = parar_downloads_torrent

    function_declarations.extend([
        {
            "name": "baixar_torrent",
            "description": (
                "Inicia o download de um arquivo torrent ou magnet link utilizando o qBittorrent. "
                "Permite definir a pasta de destino e rodar em segundo plano ou aguardar o término."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "link_ou_magnet": {
                        "type": "string",
                        "description": "O magnet link (magnet:?xt=...) ou URL / caminho local do arquivo .torrent."
                    },
                    "pasta_destino": {
                        "type": "string",
                        "description": "Caminho opcional do diretório onde os arquivos baixados serão salvos."
                    },
                    "aguardar_fim": {
                        "type": "boolean",
                        "description": "Se verdadeiro (True), aguarda a execução do comando. Se falso (False, padrão), executa em segundo plano."
                    },
                    "tempo_limite_segundos": {
                        "type": "integer",
                        "description": "Tempo limite em segundos para aguardar caso aguardar_fim seja True (padrão: 300 segundos)."
                    }
                },
                "required": ["link_ou_magnet"]
            }
        },
        {
            "name": "status_downloads_torrent",
            "description": "Exibe o status e a lista dos downloads de torrent acionados no qBittorrent.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        },
        {
            "name": "parar_downloads_torrent",
            "description": "Interrompe e encerra um processo do qBittorrent específico por PID ou todos em segundo plano.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pid": {
                        "type": "integer",
                        "description": "ID do processo (PID) a ser interrompido. Se omitido, interrompe todos os processos ativos."
                    }
                }
            }
        }
    ])


# Mapeamento e declarações no nível do módulo
TOOL_MAP["baixar_torrent"] = baixar_torrent
TOOL_MAP["status_downloads_torrent"] = status_downloads_torrent
TOOL_MAP["parar_downloads_torrent"] = parar_downloads_torrent

FUNCTION_DECLARATIONS.append({
    "name": "baixar_torrent",
    "description": (
        "Inicia o download de um arquivo torrent ou magnet link utilizando o qBittorrent. "
        "Permite definir a pasta de destino e rodar em segundo plano ou aguardar o término."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "link_ou_magnet": {
                "type": "string",
                "description": "O magnet link (magnet:?xt=...) ou URL / caminho local do arquivo .torrent."
            },
            "pasta_destino": {
                "type": "string",
                "description": "Caminho opcional do diretório onde os arquivos baixados serão salvos."
            },
            "aguardar_fim": {
                "type": "boolean",
                "description": "Se verdadeiro (True), aguarda a execução do comando. Se falso (False, padrão), executa em segundo plano."
            },
            "tempo_limite_segundos": {
                "type": "integer",
                "description": "Tempo limite em segundos para aguardar caso aguardar_fim seja True (padrão: 300 segundos)."
            }
        },
        "required": ["link_ou_magnet"]
    }
})

FUNCTION_DECLARATIONS.append({
    "name": "status_downloads_torrent",
    "description": "Exibe o status e a lista dos downloads de torrent acionados no qBittorrent.",
    "parameters": {
        "type": "object",
        "properties": {}
    }
})

FUNCTION_DECLARATIONS.append({
    "name": "parar_downloads_torrent",
    "description": "Interrompe e encerra um processo do qBittorrent específico por PID ou todos em segundo plano.",
    "parameters": {
        "type": "object",
        "properties": {
            "pid": {
                "type": "integer",
                "description": "ID do processo (PID) a ser interrompido. Se omitido, interrompe todos os processos ativos."
            }
        }
    }
})
