"""Transferência confirmada de estado entre a Ayla local e a Ayla hospedada.

Este módulo não conhece nem chama provedores de IA. Ele movimenta, valida e
aplica o código e os arquivos persistentes que compõem o estado da Ayla.
O mesmo arquivo é usado pelo cliente local e pelo agente HTTP instalado no host.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
import hashlib
import hmac
import json
import os
import re
import shlex
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


PROTOCOL_VERSION = 2
STATE_SCHEMA_VERSION = 2
DEFAULT_TIMEOUT_SECONDS = 45
MAX_API_MEMORY_BYTES = 1024 * 1024
MAX_API_MESSAGE_BYTES = MAX_API_MEMORY_BYTES + 64 * 1024

# Arquivos enviados da máquina local para o host quando a Ayla local fecha.
# Inclui env, históricos, modelos, memórias e memórias de embedding.
TO_HOST_STATE_FILES = (
    ".env",
    "Ayla_Memoria.json",
    "Ayla_Memoria.json.bak",
    "Ayla_Memoria_lixeira.json",
    "Ayla_Memoria_lixeira.json.bak",
    "Ayla_Memoria_historico.jsonl",
    "ayla_memorias_automaticas.jsonl",
    "ayla_memorias_automaticas.jsonl.bak",
    "ayla_stopwords.json",
    "ayla_settings.json",
    "ayla_settings.json.bak",
    "ayla_models.json",
    "ayla_models.json.bak",
    "ayla_ultima_sessao.json",
    "ayla_conversa_ativa.json",
    "ayla_interaction_history.jsonl",
    "ayla_media.json",
    "ayla_media.json.bak",
    "ayla_embeddings.sqlite3",
    "ayla_publico.sqlite3",
    "ayla_metrics.json",
    "ayla_consumo_deepseek.json",
    "ayla_consumo_zai.json",
    "moltbook_credentials.json",
    "benchmark_models.json",
    "full_benchmark_results.json",
)

# Arquivos devolvidos pelo host para o computador local ao reabrir a Ayla local.
# O host devolve históricos atualizados e memórias.
# Não devolve o .env nem as memórias embedding (sqlite3 grande).
TO_LOCAL_STATE_FILES = (
    "Ayla_Memoria.json",
    "Ayla_Memoria.json.bak",
    "Ayla_Memoria_lixeira.json",
    "Ayla_Memoria_lixeira.json.bak",
    "Ayla_Memoria_historico.jsonl",
    "ayla_memorias_automaticas.jsonl",
    "ayla_memorias_automaticas.jsonl.bak",
    "ayla_stopwords.json",
    "ayla_settings.json",
    "ayla_settings.json.bak",
    "ayla_ultima_sessao.json",
    "ayla_conversa_ativa.json",
    "ayla_interaction_history.jsonl",
    "ayla_media.json",
    "ayla_media.json.bak",
    "ayla_metrics.json",
    "ayla_consumo_deepseek.json",
    "ayla_consumo_zai.json",
)

SQLITE_STATE_FILES = {"ayla_embeddings.sqlite3", "ayla_publico.sqlite3"}
API_MEMORY_FILE = "Ayla_Memoria.json"
STATE_FILES = TO_HOST_STATE_FILES
SSH_STATE_FILES = TO_HOST_STATE_FILES
_DEPLOYMENT_EXCLUDED_PARTS = {"__pycache__", "runtime", "data", ".pytest_cache"}


class HandoffError(RuntimeError):
    """Erro esperado de protocolo, sem conter segredos no texto."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "sim", "on"}


def _rsync_binary() -> str:
    """Localiza o rsync mesmo executando dentro de sandboxes (ex.: VS Code Flatpak).

    Dentro de sandboxes o PATH não inclui o sistema real; procura em caminhos
    conhecidos do host para que a transferência não falhe no meio.
    """
    found = shutil.which("rsync")
    if found:
        return found
    for candidate in ("/usr/bin/rsync", "/bin/rsync", "/usr/local/bin/rsync", "/run/host/usr/bin/rsync"):
        try:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        except OSError:
            continue
    return ""


def _rsync_works(binary: str) -> bool:
    """Confere se o binário rsync consegue executar (libs presentes)."""
    if not binary:
        return False
    try:
        probe = subprocess.run([binary, "--version"], capture_output=True, timeout=10)
        return probe.returncode == 0
    except Exception:
        return False


def _split_remote(path: str) -> tuple[str | None, str]:
    if ":" in path:
        host_part, remote = path.split(":", 1)
        return host_part, remote.rstrip("/")
    return None, path.rstrip("/")


def _tar_stream_fallback(args: list[str], *, error_message: str, timeout: int) -> None:
    """Fallback tar+ssh quando o rsync não funciona (ex.: sandbox sem libpopt).

    Interpreta os argumentos do rsync (transporte -e, excludes, includes,
    --delete, origem e destino) e executa uma sincronização equivalente via tar,
    com prazo de tempo imposto e stderr sempre drenado (evita deadlock de PIPE).
    """
    transport = ""
    excludes: list[str] = []
    includes: list[str] = []
    positional: list[str] = []
    delete_requested = False
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "-e":
            transport = args[i + 1]
            i += 2
            continue
        if arg.startswith("--exclude="):
            excludes.append(arg.split("=", 1)[1].rstrip("/"))
            i += 1
            continue
        if arg == "--exclude":
            excludes.append(args[i + 1].rstrip("/"))
            i += 2
            continue
        if arg == "--include":
            includes.append(args[i + 1])
            i += 2
            continue
        if arg == "--include=":
            includes.append(arg.split("=", 1)[1])
            i += 1
            continue
        if arg == "--delete":
            delete_requested = True
            i += 1
            continue
        positional.append(arg)
        i += 1
    # O tar casa padrões contra o nome completo ("./caminho"); prefixa com "*"
    # para equivaler ao comportamento de casamento em qualquer nível do rsync.
    padroes_tar = []
    for e in excludes:
        if "*" in e or e.startswith("./") or "/" in e.rstrip("*"):
            padroes_tar.append(f"--exclude={e}")
        else:
            padroes_tar.append(f"--exclude=*{e}")
    if len(positional) < 2:
        raise HandoffError(error_message)
    src, dst = positional[-2], positional[-1]
    src_host, src_path = _split_remote(src)
    dst_host, dst_path = _split_remote(dst)
    ssh_cmd = shlex.split(transport) if transport else ["ssh"]
    prazo = time.monotonic() + max(15, timeout)

    def _drain(pipe) -> list[str]:
        """Lê um PIPE em thread própria para nunca travar o tar por buffer cheio."""
        linhas: list[str] = []
        if pipe is None:
            return linhas

        def _ler():
            try:
                for chunk in iter(lambda: pipe.readline(), b""):
                    linhas.append(chunk.decode("utf-8", "replace").rstrip())
            except Exception:
                pass
            finally:
                try:
                    pipe.close()
                except Exception:
                    pass
        threading.Thread(target=_ler, daemon=True).start()
        return linhas

    def _matar_todos(*processos: subprocess.Popen) -> None:
        """Mata todos os processos do pipeline, sem órfãos vivos."""
        for p in processos:
            try:
                if p.poll() is None:
                    p.kill()
            except Exception:
                pass

    def _wait_com_prazo(*processos: subprocess.Popen) -> list[int]:
        """Espera todos com prazo único; se estourar, mata todos e falha."""
        restante = prazo - time.monotonic()
        if restante <= 0:
            _matar_todos(*processos)
            raise HandoffError(f"{error_message} (fallback tar: tempo limite de {timeout}s esgotado).")
        try:
            return [p.wait(timeout=restante) for p in processos]
        except subprocess.TimeoutExpired:
            _matar_todos(*processos)
            raise HandoffError(f"{error_message} (fallback tar: tempo limite de {timeout}s esgotado).") from None

    recv_rc = send_rc = 0
    send_err: list[str] = []
    recv_err: list[str] = []
    try:
        if src_host is None and dst_host is not None:
            # Push: PC -> host
            tar_send = subprocess.Popen(
                ["tar", "-C", src_path, "-czf", "-", *padroes_tar, "."],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            tar_recv = subprocess.Popen(
                ssh_cmd + [dst_host, "tar -C " + shlex.quote(dst_path) + " -xzf -"],
                stdin=tar_send.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            )
            tar_send.stdout.close()
            send_err = _drain(tar_send.stderr)
            recv_err = _drain(tar_recv.stderr)
            recv_rc, send_rc = _wait_com_prazo(tar_recv, tar_send)
            if delete_requested and recv_rc == 0 and send_rc == 0:
                _propagar_exclusoes_push(ssh_cmd, dst_host, dst_path, src_path, excludes, error_message)
        elif src_host is not None and dst_host is None:
            # Pull: host -> PC (não propaga --delete para nunca apagar arquivos
            # locais que não vieram do host).
            # Arquivos ausentes no host são tolerados como no rsync: pede a
            # lista real via find antes de montar o tar, saindo rc=0 sempre
            # que ao menos um arquivo existir.
            # ATENÇÃO: excludes do rsync (ex.: "--exclude *") são filtro de
            # transferência; no tar, --exclude='*' excluiria até os arquivos
            # nomeados. Com lista explícita de includes, o tar não recebe
            # excludes — a própria lista já é o filtro.
            usar_excludes = not includes
            files = includes if includes else ["."]
            if includes:
                # Descobre quais arquivos pedidos existem de fato no host.
                # O loop retorna rc≠0 quando o último arquivo testado não
                # existe, então não se usa check=True: stdout válido manda.
                script_find = "cd " + shlex.quote(src_path) + " && for f in " + " ".join(shlex.quote(f) for f in files) + '; do [ -e "$f" ] && printf \'%s\\n\' "$f"; done'
                try:
                    resp_find = subprocess.run(
                        ssh_cmd + [src_host, script_find],
                        capture_output=True, text=True, timeout=min(30, max(10, timeout // 2)),
                    )
                    existentes = [l.strip() for l in resp_find.stdout.splitlines() if l.strip()]
                    if not existentes and resp_find.returncode not in (0, 1):
                        raise RuntimeError(f"find remoto rc={resp_find.returncode}: {(resp_find.stderr or '')[:150]}")
                except Exception:
                    existentes = list(files)  # conservador: tenta todos como antes
                if not existentes:
                    # Nada existe no host: nada a baixar, sucesso vazio
                    return
                files = existentes
            remoto = "tar -C " + shlex.quote(src_path) + " -czf - " + (" ".join(shlex.quote(p) for p in padroes_tar) + " " if usar_excludes else "") + " ".join(shlex.quote(f) for f in files)
            tar_send = subprocess.Popen(
                ssh_cmd + [src_host, remoto],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            tar_recv = subprocess.Popen(
                ["tar", "-C", dst_path, "-xzf", "-"],
                stdin=tar_send.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            )
            tar_send.stdout.close()
            send_err = _drain(tar_send.stderr)
            recv_err = _drain(tar_recv.stderr)
            recv_rc, send_rc = _wait_com_prazo(tar_recv, tar_send)
        else:
            raise HandoffError(error_message)
        if recv_rc != 0 or send_rc != 0:
            detalhe = "\n".join([*(send_err or []), *(recv_err or [])]).strip()
            detalhe = detalhe or f"tar rc={recv_rc}/{send_rc}"
            raise HandoffError(f"{error_message} (fallback tar: {detalhe[:300]})")
    except HandoffError:
        raise
    except Exception as exc:
        raise HandoffError(f"{error_message} (fallback tar: {exc})") from exc


def _caminho_casa_padrao(caminho_rel: str, padroes: list[str]) -> bool:
    """Verifica se um caminho relativo casa com um padrão estilo rsync.

    Preserva nomes iniciados por ponto (.env não pode virar "env").
    """
    from fnmatch import fnmatch
    nome = caminho_rel[2:] if caminho_rel.startswith("./") else caminho_rel
    partes = nome.split("/")
    for padrao in padroes:
        p = padrao.lstrip("*").rstrip("/")
        if not p:
            continue
        if fnmatch(nome, padrao) or fnmatch(nome, p) or fnmatch(nome, p + "/*") or nome == p:
            return True
        # Padrão simples sem barra nem curinga casa com qualquer segmento (MODOS)
        if "/" not in padrao.rstrip("/") and "*" not in padrao and "." not in padrao:
            if any(part == padrao.rstrip("/") for part in partes):
                return True
        # Sufixo de arquivo em qualquer profundidade (Ayla_Memoria*.json*)
        if fnmatch(os.path.basename(nome), padrao):
            return True
    return False


def _propagar_exclusoes_push(ssh_cmd: list[str], dst_host: str, dst_path: str,
                             src_path: str, excludes: list[str],
                             error_message: str) -> None:
    """Apaga no host arquivos de código que não existem mais no PC (--delete).

    Protege os arquivos excluídos (estado, .env, sqlite etc.), igual ao rsync.
    Só caminhos relativos simples; nunca apaga fora do diretório de destino.
    """
    try:
        listagem = subprocess.run(
            ssh_cmd + [dst_host, "cd " + shlex.quote(dst_path) + " && find . -type f"],
            check=True, capture_output=True, text=True, timeout=30,
        )
    except Exception as exc:
        raise HandoffError(f"{error_message} (fallback --delete: falha ao listar arquivos no host: {exc})") from exc
    remotos = {l.strip() for l in listagem.stdout.splitlines() if l.strip()}

    locais: set[str] = set()
    for base, _, arquivos in os.walk(src_path):
        for nome in arquivos:
            rel = os.path.relpath(os.path.join(base, nome), src_path).replace(os.sep, "/")
            locais.add("./" + rel)

    a_apagar = []
    for caminho in remotos:
        rel_sem_ponto = caminho[2:] if caminho.startswith("./") else caminho
        if _caminho_casa_padrao(rel_sem_ponto, excludes):
            continue  # protegido (estado, .env, sqlite etc.)
        if caminho not in locais and not os.path.exists(os.path.join(src_path, rel_sem_ponto)):
            a_apagar.append(rel_sem_ponto)
    a_apagar = [c for c in a_apagar if c and not c.startswith("/") and ".." not in Path(c).parts]
    if not a_apagar:
        return
    # Remove em lotes para não estourar limite de comando, sem truncar nada
    LOTE = 200
    for inicio_lote in range(0, len(a_apagar), LOTE):
        pedaco = a_apagar[inicio_lote:inicio_lote + LOTE]
        comando_rm = "cd " + shlex.quote(dst_path) + " && rm -f -- " + " ".join(shlex.quote(c) for c in pedaco)
        try:
            subprocess.run(ssh_cmd + [dst_host, comando_rm], check=True, capture_output=True, text=True, timeout=30)
        except Exception as exc:
            apagados_ate_agora = inicio_lote
            raise HandoffError(
                f"{error_message} (fallback --delete: falha ao remover arquivo(s) órfão(s) "
                f"após {apagados_ate_agora} de {len(a_apagar)}: {exc})"
            ) from exc


def run_rsync(command: list[str], *, error_message: str, timeout: int) -> None:
    """Executa rsync; se o binário não funcionar, usa fallback tar+ssh transparente."""
    binary = command[0]
    if _rsync_works(binary):
        try:
            subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=timeout)
            return
        except subprocess.TimeoutExpired as exc:
            raise HandoffError(f"{error_message} (tempo limite esgotado).") from exc
        except Exception as exc:
            raise HandoffError(f"{error_message}: {exc}") from exc
    # rsync indisponível ou quebrado: degrada com elegância em vez de falhar
    _tar_stream_fallback(command[1:], error_message=error_message, timeout=timeout)


def host_api_token_from_environment() -> str:
    """Usa token próprio configurado no .env."""
    explicit = os.getenv("AYLA_HOST_TOKEN", "").strip()
    if explicit:
        return explicit
    discord_token = os.getenv("DISCORD_TOKEN", "").strip()
    if not discord_token:
        return ""
    return hashlib.sha256(("ayla-host-api-v1:\0" + discord_token).encode("utf-8")).hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def read_small_memory(app_dir: Path) -> dict[str, Any]:
    """Lê a memória JSON primária."""
    source = Path(app_dir) / API_MEMORY_FILE
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HandoffError("Não foi possível ler a memória JSON da Ayla.") from exc
    if not isinstance(value, (dict, list)):
        raise HandoffError("A memória JSON da Ayla tem um formato inválido.")
    encoded = _canonical_json_bytes(value)
    if len(encoded) > MAX_API_MEMORY_BYTES:
        raise HandoffError("A memória JSON está grande demais para a API.")
    return {"schema": STATE_SCHEMA_VERSION, "value": value, "sha256": _sha256_bytes(encoded), "size": len(encoded)}


def write_small_memory(app_dir: Path, payload: dict[str, Any]) -> None:
    if not isinstance(payload, dict) or payload.get("schema") != STATE_SCHEMA_VERSION:
        raise HandoffError("A memória recebida usa um esquema incompatível.")
    value = payload.get("value")
    if not isinstance(value, (dict, list)):
        raise HandoffError("A memória recebida é inválida.")
    encoded = _canonical_json_bytes(value)
    if len(encoded) > MAX_API_MEMORY_BYTES or not hmac.compare_digest(_sha256_bytes(encoded), str(payload.get("sha256", ""))):
        raise HandoffError("O hash da memória recebida não confere.")
    destination = Path(app_dir) / API_MEMORY_FILE
    temporary = destination.with_name(destination.name + ".handoff.tmp")
    with temporary.open("wb") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, destination)


def state_manifest(
    root: Path,
    file_list: tuple[str, ...] = TO_HOST_STATE_FILES,
    include_modos: bool = True,
) -> dict[str, Any]:
    """Calcula hash seguro e canônico dos arquivos de estado."""
    root = Path(root).resolve()
    files: dict[str, dict[str, Any]] = {}
    for name in file_list:
        source = root / name
        if source.exists() and source.is_file() and not source.is_symlink():
            files[name] = {"sha256": _sha256_file(source), "size": source.stat().st_size}
    if include_modos:
        modes = root / "MODOS"
        if modes.is_dir() and not modes.is_symlink():
            for source in sorted(modes.rglob("*")):
                if source.is_file() and not source.is_symlink():
                    name = source.relative_to(root).as_posix()
                    files[name] = {"sha256": _sha256_file(source), "size": source.stat().st_size}
    payload = {"schema": STATE_SCHEMA_VERSION, "files": files}
    payload["sha256"] = _sha256_bytes(_canonical_json_bytes(payload))
    return payload


def _vacuum_sqlite_into(source: Path, destination: Path) -> None:
    """Checkpoint + VACUUM INTO: gera snapshot SQLite 100% íntegro e autossuficiente."""
    destination.unlink(missing_ok=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        try:
            connection = sqlite3.connect(source, timeout=15)
            try:
                connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                connection.execute("VACUUM INTO ?", (str(destination),))
                return
            finally:
                connection.close()
        except sqlite3.Error as exc:
            if attempt == 2:
                raise HandoffError(f"Não foi possível criar snapshot íntegro de {source.name}.") from exc
            time.sleep(1)


def prepare_ssh_state(
    app_dir: Path,
    stage_dir: Path,
    *,
    file_list: tuple[str, ...] = TO_HOST_STATE_FILES,
    include_modos: bool = True,
    vacuum_sqlite: bool = True,
) -> dict[str, Any]:
    """Prepara a pasta de stage antes da transferência."""
    app_dir = Path(app_dir).resolve()
    stage_dir = Path(stage_dir)
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)

    for name in file_list:
        source = app_dir / name
        if not source.exists():
            continue
        if not source.is_file() or source.is_symlink():
            continue
        destination = stage_dir / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if vacuum_sqlite and name in SQLITE_STATE_FILES:
            _vacuum_sqlite_into(source, destination)
        else:
            shutil.copy2(source, destination)

    if include_modos:
        source_modes = app_dir / "MODOS"
        if source_modes.exists() and source_modes.is_dir() and not source_modes.is_symlink():
            shutil.copytree(source_modes, stage_dir / "MODOS", symlinks=False)

    manifest = state_manifest(stage_dir, file_list=file_list, include_modos=include_modos)
    saved_manifest = stage_dir / "state-manifest.json"
    saved_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def apply_ssh_state(
    app_dir: Path,
    stage_dir: Path,
    expected_hash: str,
    *,
    file_list: tuple[str, ...] = TO_LOCAL_STATE_FILES,
    include_modos: bool = False,
) -> dict[str, Any]:
    """Aplica os arquivos recebidos apenas após conferência estrita de hash."""
    app_dir = Path(app_dir).resolve()
    stage_dir = Path(stage_dir).resolve()
    manifest = state_manifest(stage_dir, file_list=file_list, include_modos=include_modos)
    if not hmac.compare_digest(manifest["sha256"], expected_hash):
        raise HandoffError(
            f"Os arquivos recebidos não conferem com o hash esperado "
            f"(recebido: {manifest['sha256'][:8]} != esperado: {expected_hash[:8]})."
        )

    for name in file_list:
        source = stage_dir / name
        if not source.exists():
            continue
        destination = app_dir / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        tmp = destination.with_suffix(destination.suffix + ".claim.tmp")
        shutil.copy2(source, tmp)
        os.replace(tmp, destination)

    if include_modos:
        source_modes = stage_dir / "MODOS"
        destination_modes = app_dir / "MODOS"
        if source_modes.exists():
            if destination_modes.exists():
                shutil.rmtree(destination_modes)
            shutil.copytree(source_modes, destination_modes)

    return manifest


def deployment_manifest(code_dir: Path) -> dict[str, Any]:
    code_dir = Path(code_dir).resolve()
    files: dict[str, dict[str, Any]] = {}
    for path in sorted(code_dir.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(code_dir).as_posix()
        if any(part in _DEPLOYMENT_EXCLUDED_PARTS for part in PurePosixPath(relative).parts):
            continue
        if path.suffix in {".pyc", ".sqlite", ".zip"} or path.name.endswith(".sqlite3"):
            continue
        files[relative] = {"sha256": _sha256_file(path), "size": path.stat().st_size}
    return {"protocol": PROTOCOL_VERSION, "files": files}


def compare_deployment_manifests(local: dict[str, Any], remote: dict[str, Any]) -> list[str]:
    local_files = local.get("files") if isinstance(local.get("files"), dict) else {}
    remote_files = remote.get("files") if isinstance(remote.get("files"), dict) else {}
    differences: list[str] = []
    for name in sorted(set(local_files) | set(remote_files)):
        if name not in local_files:
            differences.append(f"só no host: {name}")
        elif name not in remote_files:
            differences.append(f"só local: {name}")
        elif local_files[name] != remote_files[name]:
            differences.append(f"conteúdo diferente: {name}")
    return differences


def _ensure_env_loaded() -> None:
    if not os.getenv("AYLA_HOST_URL"):
        env_path = Path(__file__).resolve().parents[1] / ".env"
        if env_path.is_file():
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
            except Exception:
                pass


@dataclass(frozen=True)
class HostConfig:
    url: str
    token: str
    timeout: int = DEFAULT_TIMEOUT_SECONDS
    allow_http: bool = False
    device_id: str = ""

    @classmethod
    def from_environment(cls) -> "HostConfig | None":
        _ensure_env_loaded()
        url = os.getenv("AYLA_HOST_URL", "").strip().rstrip("/")
        token = host_api_token_from_environment()
        if not url and not token:
            return None
        if not url or not token:
            raise HandoffError("Configure AYLA_HOST_URL e AYLA_HOST_TOKEN juntos.")
        parsed = urllib.parse.urlsplit(url)
        allow_http = _truthy(os.getenv("AYLA_HOST_ALLOW_HTTP"))
        if parsed.scheme not in {"https", "http"} or not parsed.netloc:
            raise HandoffError("AYLA_HOST_URL precisa ser uma URL HTTPS válida.")
        if parsed.scheme != "https" and not allow_http:
            raise HandoffError("A transferência exige HTTPS (ou AYLA_HOST_ALLOW_HTTP=1 para teste/túnel local).")
        try:
            timeout = max(5, min(180, int(os.getenv("AYLA_HOST_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))))
        except ValueError:
            timeout = DEFAULT_TIMEOUT_SECONDS
        device = os.getenv("AYLA_HOST_DEVICE_ID", "").strip() or (os.uname().nodename if hasattr(os, "uname") else "ayla-local")
        return cls(url=url, token=token, timeout=timeout, allow_http=allow_http, device_id=device[:100])


@dataclass(frozen=True)
class SSHDeploymentConfig:
    target: str
    remote_code_dir: str
    remote_app_dir: str
    identity_file: str = ""
    port: int = 22
    timeout: int = 45

    @classmethod
    def from_environment(cls, *, required: bool = False) -> "SSHDeploymentConfig | None":
        target = os.getenv("AYLA_HOST_SSH_TARGET", "").strip()
        remote_code_dir = os.getenv("AYLA_HOST_SSH_CODE_DIR", "").strip()
        remote_app_dir = os.getenv("AYLA_HOST_SSH_APP_DIR", "").strip()
        if not target and not remote_code_dir and not remote_app_dir and not required:
            return None
        if not target or not remote_code_dir or not remote_app_dir:
            raise HandoffError("Configure AYLA_HOST_SSH_TARGET, AYLA_HOST_SSH_CODE_DIR e AYLA_HOST_SSH_APP_DIR.")
        if not re.fullmatch(r"[A-Za-z0-9_.@:-]+", target):
            raise HandoffError("AYLA_HOST_SSH_TARGET contém caracteres inválidos.")
        if not remote_code_dir.startswith("/") or not remote_app_dir.startswith("/"):
            raise HandoffError("Os caminhos SSH remotos precisam ser absolutos.")
        try:
            port = int(os.getenv("AYLA_HOST_SSH_PORT", "22"))
        except ValueError as exc:
            raise HandoffError("AYLA_HOST_SSH_PORT é inválida.") from exc
        try:
            timeout = int(os.getenv("AYLA_HOST_SSH_TIMEOUT", "90"))
        except ValueError:
            timeout = 90
        timeout = max(15, min(600, timeout))
        key = os.getenv("AYLA_HOST_SSH_KEY", "").strip()
        if key:
            key_path = Path(key).expanduser()
            if not key_path.is_absolute():
                module_dir = Path(__file__).resolve().parent
                candidates = [
                    module_dir.parent / key_path,
                    module_dir / key_path,
                    Path.cwd() / key_path,
                ]
                key_path = next((p for p in candidates if p.is_file()), candidates[0])
            if not key_path.is_file():
                raise HandoffError(f"AYLA_HOST_SSH_KEY não aponta para chave acessível: {key_path}")
            key = str(key_path.resolve())
        return cls(target=target, remote_code_dir=remote_code_dir, remote_app_dir=remote_app_dir, identity_file=key, port=port, timeout=timeout)


class SSHDeploymentSync:
    """Sincroniza o código do pacote ayla_host e reinicia o serviço do agente quando alterado."""

    def __init__(self, config: SSHDeploymentConfig, local_code_dir: Path):
        self.config = config
        self.local_code_dir = Path(local_code_dir).resolve()

    def _ssh(self, remote_command: str) -> subprocess.CompletedProcess[str]:
        command = ["ssh", "-p", str(self.config.port), "-o", "BatchMode=yes"]
        if self.config.identity_file:
            command.extend(["-i", self.config.identity_file])
        command.extend([self.config.target, remote_command])
        try:
            return subprocess.run(command, check=True, capture_output=True, text=True, timeout=self.config.timeout)
        except Exception as exc:
            raise HandoffError(f"Falha na conexão SSH com {self.config.target}: {exc}") from exc

    def _remote_manifest(self) -> dict[str, Any]:
        cmd = (
            f"python3 -c \"import sys; sys.path.insert(0, {self.config.remote_code_dir!r}); "
            f"from ayla_handoff import deployment_manifest; from pathlib import Path; import json; "
            f"print(json.dumps(deployment_manifest(Path({self.config.remote_code_dir!r}))))\""
        )
        try:
            res = self._ssh(cmd)
            return json.loads(res.stdout)
        except Exception:
            return {"protocol": PROTOCOL_VERSION, "files": {}}

    def sync_and_verify(self) -> dict[str, Any]:
        before = self._remote_manifest()
        local = deployment_manifest(self.local_code_dir)
        differences = compare_deployment_manifests(local, before)
        if not differences:
            return {"changed": False, "differences": []}

        self._ssh("mkdir -p " + shlex.quote(self.config.remote_code_dir))
        transport = f"ssh -p {self.config.port} -o BatchMode=yes"
        if self.config.identity_file:
            transport += f" -i {shlex.quote(self.config.identity_file)}"

        rsync_cmd = [
            _rsync_binary(), "-az", "--delete", "--partial", "--inplace", "--checksum",
            "--exclude=__pycache__/", "--exclude=*.pyc",
            "-e", transport,
            str(self.local_code_dir) + "/",
            f"{self.config.target}:{shlex.quote(self.config.remote_code_dir + '/')}",
        ]
        run_rsync(rsync_cmd, error_message="Falha ao sincronizar o pacote ayla host", timeout=self.config.timeout)

        # Reinicia o agente no servidor para carregar o código novo
        try:
            self._ssh("sudo -n systemctl restart ayla-host-agent.service")
            time.sleep(1)
        except Exception:
            pass

        return {"changed": True, "differences": differences}


class SSHStateSync:
    """Move código do projeto e arquivos de estado com integridade por SSH e rsync."""

    def __init__(self, config: SSHDeploymentConfig):
        self.config = config

    def _remote(self, command: str) -> subprocess.CompletedProcess[str]:
        args = ["ssh", "-p", str(self.config.port), "-o", "BatchMode=yes"]
        if self.config.identity_file:
            args.extend(["-i", self.config.identity_file])
        args.extend([self.config.target, command])
        try:
            return subprocess.run(args, check=True, capture_output=True, text=True, timeout=self.config.timeout)
        except Exception as exc:
            raise HandoffError(f"Falha no comando remoto SSH: {exc}") from exc

    def _transport(self) -> str:
        transport = f"ssh -p {self.config.port} -o BatchMode=yes"
        if self.config.identity_file:
            transport += f" -i {shlex.quote(self.config.identity_file)}"
        return transport

    def sync_code(self, app_dir: Path) -> dict[str, Any]:
        """Sincroniza alterações de código do projeto para o host."""
        app_dir = Path(app_dir).resolve()
        self._remote("mkdir -p " + shlex.quote(self.config.remote_app_dir))

        excludes = self._code_excludes()

        cmd = [
            _rsync_binary(), "-az", "--delete", "--partial", "--inplace", "--checksum",
            "-e", self._transport(),
        ] + excludes + [
            str(app_dir) + "/",
            f"{self.config.target}:{shlex.quote(self.config.remote_app_dir + '/')}",
        ]
        try:
            run_rsync(cmd, error_message="Falha ao enviar alterações de código para o host", timeout=self.config.timeout)
        except HandoffError:
            raise

        # Sincroniza a pasta MODOS com --delete para manter modos sincronizados com o código
        modos_dir = app_dir / "MODOS"
        if modos_dir.is_dir():
            cmd_modos = [
                _rsync_binary(), "-az", "--delete", "--partial", "--inplace", "--checksum",
                "-e", self._transport(),
                str(modos_dir) + "/",
                f"{self.config.target}:{shlex.quote(self.config.remote_app_dir + '/MODOS/')}",
            ]
            run_rsync(cmd_modos, error_message="Falha ao sincronizar MODOS para o host", timeout=self.config.timeout)

        # Sincroniza a pasta 'ayla host' para remote_code_dir
        code_dir = app_dir / "ayla host"
        if code_dir.is_dir():
            cmd_host = [
                _rsync_binary(), "-az", "--delete", "--partial", "--inplace", "--checksum",
                "--exclude=__pycache__/", "--exclude=*.pyc",
                "-e", self._transport(),
                str(code_dir) + "/",
                f"{self.config.target}:{shlex.quote(self.config.remote_code_dir + '/')}",
            ]
            run_rsync(cmd_host, error_message="Falha ao sincronizar 'ayla host'", timeout=self.config.timeout)

        return {"ok": True}

    def pull_code_back(self, app_dir: Path) -> dict[str, Any]:
        """Resync do código modificado pela Ayla no host de volta ao PC.

        Executado quando o PC solicita assumir (claim_local), garantindo que
        auto-modificações feitas no servidor não se percam. Usa os mesmos
        excludes de sync_code, sem --delete para nunca apagar arquivos locais.
        """
        app_dir = Path(app_dir).resolve()
        cmd = [
            _rsync_binary(), "-az", "--partial", "--inplace", "--checksum",
            "-e", self._transport(),
        ] + self._code_excludes() + [
            f"{self.config.target}:{shlex.quote(self.config.remote_app_dir + '/')}",
            str(app_dir) + "/",
        ]
        run_rsync(cmd, error_message="Falha ao trazer o código modificado no host de volta ao PC", timeout=self.config.timeout)
        return {"ok": True}

    def _code_excludes(self) -> list[str]:
        return [
            "--exclude=.git/",
            "--exclude=.venv/",
            "--exclude=__pycache__/",
            "--exclude=*.pyc",
            "--exclude=chave SSH/",
            "--exclude=ayla host/",
            "--exclude=ayla_host/",
            "--exclude=.ayla-host-outgoing/",
            "--exclude=.ayla-host-incoming/",
            "--exclude=.ayla-host-runtime/",
            "--exclude=.ayla_live.py.kate-swp",
            "--exclude=Aylafotitos/",
            "--exclude=VideosBaixados/",
            "--exclude=Buffer de video/",
            "--exclude=audio_output/",
            "--exclude=TorrentsBaixados/",
            "--exclude=MODOS/",
            # Exclui arquivos de estado para que o snapshot stage trate de forma consistente
            "--exclude=*.sqlite3",
            "--exclude=*.sqlite3-wal",
            "--exclude=*.sqlite3-shm",
            "--exclude=.env*",
            "--exclude=Ayla_Memoria*.json*",
            "--exclude=ayla_memorias_automaticas*.jsonl*",
            "--exclude=ayla_interaction_history.jsonl",
            "--exclude=ayla_ultima_sessao.json",
            "--exclude=ayla_conversa_ativa.json",
            "--exclude=ayla_metrics.json",
            "--exclude=ayla_consumo_*.json",
            "--exclude=moltbook_credentials.json",
            "--exclude=benchmark_models.json",
            "--exclude=full_benchmark_results.json",
            "--exclude=ayla_stopwords.json",
            "--exclude=ayla_settings*.json",
            "--exclude=ayla_models*.json",
            "--exclude=ayla_media*.json",
        ]

    def _remote_state_manifest(self, file_list: tuple[str, ...], include_modos: bool) -> dict[str, Any]:
        """Calcula o manifesto remoto usando exatamente a mesma função state_manifest."""
        files_json = json.dumps(list(file_list))
        script = (
            f"import sys; sys.path.insert(0, {self.config.remote_code_dir!r}); "
            f"from ayla_handoff import state_manifest; from pathlib import Path; import json; "
            f"print(json.dumps(state_manifest(Path({self.config.remote_app_dir!r}), "
            f"file_list=tuple(json.loads({files_json!r})), "
            f"include_modos={include_modos!r})))"
        )
        res = self._remote("python3 -c " + shlex.quote(script))
        try:
            manifest = json.loads(res.stdout)
            if not isinstance(manifest, dict) or manifest.get("schema") != STATE_SCHEMA_VERSION:
                raise ValueError("Manifesto com esquema inválido")
            return manifest
        except Exception as exc:
            raise HandoffError(f"Host não retornou manifesto válido: {res.stderr or res.stdout}") from exc

    def push(self, app_dir: Path, handoff_id: str) -> dict[str, Any]:
        """Prepara, fotografa com vacuum e envia todos os arquivos de estado para o host."""
        stage = Path(app_dir) / ".ayla-host-outgoing" / handoff_id
        manifest = prepare_ssh_state(app_dir, stage, file_list=TO_HOST_STATE_FILES, include_modos=True, vacuum_sqlite=True)
        self._remote("mkdir -p " + shlex.quote(self.config.remote_app_dir))

        # Remove do host arquivos rastreados da lista de estado que não existem localmente
        missing_state_files = [name for name in TO_HOST_STATE_FILES if not (stage / name).exists()]
        if missing_state_files:
            rm_args = " ".join(shlex.quote(f"{self.config.remote_app_dir}/{name}") for name in missing_state_files)
            try:
                self._remote(f"rm -f {rm_args}")
            except Exception:
                pass

        cmd = [
            _rsync_binary(), "-az", "--partial", "--inplace", "--checksum",
            "--exclude=state-manifest.json",
            "--exclude=MODOS/",
            "-e", self._transport(),
            str(stage) + "/",
            f"{self.config.target}:{shlex.quote(self.config.remote_app_dir + '/')}",
        ]
        run_rsync(cmd, error_message="Falha na sincronização dos arquivos de estado para o host", timeout=self.config.timeout)

        stage_modos = stage / "MODOS"
        if stage_modos.is_dir():
            cmd_modos = [
                _rsync_binary(), "-az", "--delete", "--partial", "--inplace", "--checksum",
                "-e", self._transport(),
                str(stage_modos) + "/",
                f"{self.config.target}:{shlex.quote(self.config.remote_app_dir + '/MODOS/')}",
            ]
            run_rsync(cmd_modos, error_message="Falha na sincronização dos MODOS para o host", timeout=self.config.timeout)

        remote_manifest = self._remote_state_manifest(TO_HOST_STATE_FILES, include_modos=True)
        if not hmac.compare_digest(manifest["sha256"], str(remote_manifest.get("sha256", ""))):
            raise HandoffError(
                f"O hash dos arquivos no host não confere após rsync "
                f"(local: {manifest['sha256'][:8]} != host: {str(remote_manifest.get('sha256'))[:8]})."
            )
        return manifest

    def pull(self, app_dir: Path, handoff_id: str, expected_hash: str) -> dict[str, Any]:
        """Puxa apenas históricos e memórias do host (sem env, sem embeddings)."""
        stage = Path(app_dir) / ".ayla-host-incoming" / handoff_id
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir(parents=True, exist_ok=True)

        remote_manifest = self._remote_state_manifest(TO_LOCAL_STATE_FILES, include_modos=False)
        if not hmac.compare_digest(str(remote_manifest.get("sha256", "")), expected_hash):
            raise HandoffError("O estado no host divergiu antes de iniciar a devolução.")

        includes = []
        for name in TO_LOCAL_STATE_FILES:
            includes.extend(["--include", name])
        includes.extend(["--exclude", "*"])

        cmd = [
            _rsync_binary(), "-az", "--partial", "--inplace", "--checksum",
            "-e", self._transport(),
        ] + includes + [
            f"{self.config.target}:{shlex.quote(self.config.remote_app_dir + '/')}",
            str(stage) + "/",
        ]
        run_rsync(cmd, error_message="Falha ao baixar histórico e memórias do host", timeout=self.config.timeout)

        return apply_ssh_state(app_dir, stage, expected_hash, file_list=TO_LOCAL_STATE_FILES, include_modos=False)


class HandoffClient:
    """Cliente local de orquestração com a Ayla no host."""

    def __init__(
        self,
        config: HostConfig,
        *,
        code_dir: Path | None = None,
        deployment_sync: SSHDeploymentSync | Any | None = None,
        state_sync: SSHStateSync | Any | None = None,
    ):
        self.config = config
        self.code_dir = Path(code_dir or Path(__file__).resolve().parent)
        self.deployment_sync = deployment_sync
        self.state_sync = state_sync

    def ensure_tunnel(self) -> None:
        """Garante que o túnel SSH local para a API do host está aberto e ativo."""
        parsed = urllib.parse.urlsplit(self.config.url)
        if parsed.hostname in {"127.0.0.1", "localhost"}:
            port = parsed.port or 18765
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            try:
                if sock.connect_ex(("127.0.0.1", port)) == 0:
                    sock.close()
                    return
            except Exception:
                pass
            finally:
                try:
                    sock.close()
                except Exception:
                    pass

            tunnel_script = self.code_dir / "abrir_tunel_host.sh"
            if tunnel_script.is_file():
                try:
                    subprocess.run(["bash", str(tunnel_script)], check=True, timeout=15)
                except Exception as exc:
                    raise HandoffError(f"Não foi possível abrir o túnel SSH para o host: {exc}") from exc
                deadline = time.monotonic() + 3.0
                while time.monotonic() < deadline:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(0.3)
                    try:
                        if s.connect_ex(("127.0.0.1", port)) == 0:
                            s.close()
                            return
                    except Exception:
                        pass
                    finally:
                        try:
                            s.close()
                        except Exception:
                            pass
                    time.sleep(0.2)

    def _request(
        self,
        method: str,
        route: str,
        *,
        payload: dict[str, Any] | None = None,
        raw_body: bytes | None = None,
        binary_response: bool = False,
    ) -> Any:
        self.ensure_tunnel()
        if payload is not None and raw_body is not None:
            raise ValueError("Use apenas um tipo de corpo por requisição.")
        data = raw_body
        headers = {
            "Authorization": "Bearer " + self.config.token,
            "X-Ayla-Protocol": str(PROTOCOL_VERSION),
            "X-Ayla-Device": self.config.device_id,
        }
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"

        request = urllib.request.Request(self.config.url + route, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                body = response.read(MAX_API_MESSAGE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            try:
                details = json.loads(exc.read().decode("utf-8"))
                message = details.get("error", "O host recusou a requisição.")
            except Exception:
                message = "O host recusou a requisição."
            finally:
                exc.close()
            raise HandoffError(str(message)) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise HandoffError(f"Não foi possível conectar ao host da Ayla ({exc}).") from exc

        if len(body) > MAX_API_MESSAGE_BYTES:
            raise HandoffError("A resposta do host excede o limite permitido.")
        if binary_response:
            return body
        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HandoffError("O host retornou uma resposta inválida.") from exc
        if not isinstance(decoded, dict):
            raise HandoffError("O host retornou uma resposta inválida.")
        return decoded

    def status(self) -> dict[str, Any]:
        return self._request("GET", "/v1/status")

    def _state_sync(self) -> SSHStateSync:
        if self.state_sync is None:
            raise HandoffError("A sincronização SSH não está configurada.")
        return self.state_sync

    def force_stop_host(self) -> dict[str, Any]:
        """Força o encerramento da Ayla no host via API HTTP ou diretamente via SSH de emergência."""
        print("⚠️ [Host Handoff] Solicitando parada forçada da Ayla no host...")
        # 1. Tenta pela API HTTP do agente do host
        try:
            self.ensure_tunnel()
            res = self._request("POST", "/v1/host/force-stop", payload={})
            if isinstance(res, dict) and res.get("ok"):
                print("🩵 [Host Handoff] Encerramento forçado confirmado pela API do host.")
                return res
        except Exception as erro:
            print(f"ℹ️ [Host Handoff] Parada via API HTTP não respondeu ({erro}). Acionando intervenção direta via SSH...")

        # 2. Intervenção direta via SSH caso a API esteja inacessível ou travada
        if self.state_sync is not None:
            try:
                cmd = (
                    "sudo -n systemctl kill -s SIGKILL ayla.service 2>/dev/null || true; "
                    "sudo -n systemctl stop ayla.service 2>/dev/null || true; "
                    "sudo -n pkill -9 -f 'python.*Ayla\\.py' 2>/dev/null || true; "
                    "sudo -n systemctl reset-failed ayla.service 2>/dev/null || true; "
                    "python3 -c 'import json, pathlib; p = pathlib.Path(\"/opt/ayla/.ayla-host-runtime/state.json\"); "
                    "p.parent.mkdir(parents=True, exist_ok=True); "
                    "p.write_text(json.dumps({\"owner\": \"none\", \"pending\": None}))' 2>/dev/null || true"
                )
                self.state_sync._remote(cmd)
                print("🩵 [Host Handoff] Comandos de parada forçada e reset executados via SSH com sucesso.")
                return {"ok": True, "service_active": False, "owner": "none"}
            except Exception as ssh_err:
                print(f"❌ [Host Handoff] Falha crítica ao forçar parada via SSH: {ssh_err}")
                raise HandoffError(f"Não foi possível forçar a parada da Ayla no host: {ssh_err}") from ssh_err

        raise HandoffError("Não foi possível forçar a parada da Ayla no host.")

    def transfer_to_host(self, app_dir: Path, on_progress: Any | None = None) -> dict[str, Any]:
        """Sincroniza alterações de código, histórico, modelos, env, memórias e embeddings para o host, iniciando a Ayla lá."""
        app_dir = Path(app_dir).resolve()

        def report(pct: int, msg: str):
            if callable(on_progress):
                try:
                    on_progress(pct, msg)
                except Exception:
                    pass
            print(f"🩵 [{pct:3d}%] {msg}")

        # Remove estágios abandonados de transferências anteriores que falharam no meio
        shutil.rmtree(app_dir / ".ayla-host-outgoing", ignore_errors=True)

        report(5, "Verificando conexão e túnel SSH com o host...")
        self.ensure_tunnel()

        # 1. Reserva transferência no host
        report(15, "Reservando transferência no host...")
        try:
            reserved = self._request(
                "POST", "/v1/handoffs/to-host/reserve",
                payload={"source": self.config.device_id, "force": True},
            )
        except HandoffError as erro:
            if any(k in str(erro).lower() for k in ("já está ativa", "não é seguro", "conflito")):
                report(18, "Ayla presa no host detectada. Forçando liberação no servidor...")
                self.force_stop_host()
                time.sleep(1.0)
                reserved = self._request(
                    "POST", "/v1/handoffs/to-host/reserve",
                    payload={"source": self.config.device_id, "force": True},
                )
            else:
                raise

        handoff_id = str(reserved.get("handoff_id", ""))
        if not handoff_id:
            raise HandoffError("O host não reservou uma transferência válida.")

        # 2. Sincroniza todas as alterações de código do projeto
        report(30, "Sincronizando alterações de código do projeto...")
        self._state_sync().sync_code(app_dir)

        # 3. Snapshot com VACUUM dos SQLite e rsync de todos os arquivos de estado
        report(55, "Criando snapshot das memórias e banco SQLite...")
        files = self._state_sync().push(app_dir, handoff_id)
        report(75, "Arquivos de estado enviados para o host via SSH/rsync.")

        # 4. Host valida arquivos e prepara estado
        report(85, "Host validando integridade dos arquivos...")
        prepared = self._request(
            "POST", f"/v1/handoffs/{urllib.parse.quote(handoff_id)}/prepare-state",
            payload={"schema": STATE_SCHEMA_VERSION, "files_hash": files["sha256"]},
        )
        if prepared.get("files_hash") != files["sha256"]:
            raise HandoffError("O host recusou o hash dos arquivos transferidos.")

        # 5. Host assume a Ayla e inicia o serviço no servidor
        report(95, "Iniciando Ayla no servidor e verificando serviço...")
        assumed = self._request("POST", f"/v1/handoffs/{urllib.parse.quote(handoff_id)}/assume", payload={})
        if assumed.get("owner") != "host":
            raise HandoffError("O host não confirmou a inicialização da Ayla no servidor.")

        # 6. Limpa stage de saída local
        report(100, "Ayla ativa no servidor com sucesso! Encerrando localmente.")
        shutil.rmtree(app_dir / ".ayla-host-outgoing" / handoff_id, ignore_errors=True)
        return assumed

    def claim_local(self, app_dir: Path, on_progress: Any | None = None) -> dict[str, Any]:
        """Para a Ayla no host e devolve históricos atualizados e memórias (sem env, sem embeddings)."""
        app_dir = Path(app_dir).resolve()

        def report(pct: int, msg: str):
            if callable(on_progress):
                try:
                    on_progress(pct, msg)
                except Exception:
                    pass
            print(f"🩵 [{pct:3d}%] {msg}")

        # Remove estágios abandonados de devoluções anteriores que falharam no meio
        shutil.rmtree(app_dir / ".ayla-host-incoming", ignore_errors=True)

        report(10, "Verificando conexão e status do host...")
        self.ensure_tunnel()

        # 1. Solicita ao host parar a Ayla e fotografar os dados a devolver
        report(25, "Solicitando parada segura e drenagem de turnos no servidor...")
        try:
            prepared = self._request("POST", "/v1/handoffs/to-local/prepare", payload={"target": self.config.device_id, "force": False})
        except HandoffError as erro:
            report(28, f"Host demorou ou falhou ao encerrar ({erro}). Forçando parada imediata no servidor...")
            self.force_stop_host()
            time.sleep(1.0)
            prepared = self._request("POST", "/v1/handoffs/to-local/prepare", payload={"target": self.config.device_id, "force": True})

        if prepared.get("already_local") and prepared.get("owner") == "local":
            report(100, "Ayla já está no modo local.")
            return prepared

        handoff_id = str(prepared.get("handoff_id", ""))
        if not handoff_id:
            raise HandoffError("O host não preparou a devolução dos dados.")
        expected_hash = str(prepared.get("files_hash", ""))
        if not expected_hash:
            raise HandoffError("O host não forneceu o hash dos dados a devolver.")

        # 2. Resync do código: auto-modificações feitas pela Ayla no host voltam ao PC
        report(40, "Sincronizando código modificado pela Ayla no host de volta ao PC...")
        try:
            self._state_sync().pull_code_back(app_dir)
        except HandoffError as erro:
            report(50, f"Aviso: código do host não pôde ser resincronizado ({erro}). Continuando com os dados.")

        # 3. Baixa apenas históricos atualizados e memórias por SSH/rsync
        report(65, "Baixando histórico atualizado e memórias do host por SSH...")
        manifest = self._state_sync().pull(app_dir, handoff_id, expected_hash)
        arquivos = list(manifest.get("files", {}).keys())
        principais = [f for f in arquivos if any(k in f for k in ("historico", "sessao", "Memoria", "consumo"))]
        report(80, f"Histórico e memórias aplicados ({len(principais)} arquivos principais sincronizados).")

        # 4. Confirma devolução ao host
        report(90, "Confirmando devolução com o servidor...")
        acknowledged = self._request("POST", f"/v1/handoffs/{urllib.parse.quote(handoff_id)}/ack-local", payload={})
        if acknowledged.get("owner") != "local":
            raise HandoffError("O host não confirmou a devolução da Ayla para este computador.")

        # 5. Limpa stage de entrada local
        report(100, "Histórico e memórias sincronizados com sucesso!")
        shutil.rmtree(app_dir / ".ayla-host-incoming" / handoff_id, ignore_errors=True)
        return acknowledged


def host_client_from_environment(*, code_dir: Path | None = None) -> HandoffClient | None:
    config = HostConfig.from_environment()
    if not config:
        return None
    ssh_config = SSHDeploymentConfig.from_environment(required=True)
    deployment = SSHDeploymentSync(ssh_config, Path(code_dir or Path(__file__).resolve().parent))
    return HandoffClient(config, code_dir=code_dir, deployment_sync=deployment, state_sync=SSHStateSync(ssh_config))
