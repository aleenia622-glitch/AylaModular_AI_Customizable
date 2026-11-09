"""Agente HTTP do host Oracle para a transferência confirmada da Ayla.

Ele deve ficar atrás de HTTPS (Caddy, Nginx ou túnel SSH privado) e separado do
processo da Ayla. Não expõe memória, chaves ou estado em endpoints sem token.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
import hmac
import json
import os
import shlex
import shutil
import subprocess
import threading
import time
import uuid

from ayla_handoff import (
    HandoffError,
    MAX_API_MESSAGE_BYTES,
    PROTOCOL_VERSION,
    STATE_SCHEMA_VERSION,
    TO_HOST_STATE_FILES,
    TO_LOCAL_STATE_FILES,
    _utc_now,
    host_api_token_from_environment,
    deployment_manifest,
    state_manifest,
)


@dataclass
class CommandProcessController:
    app_dir: Path
    start_command: str = ""
    health_command: str = ""
    drain_command: str = ""
    stopped_command: str = ""
    drain_timeout_seconds: int = 130
    start_timeout_seconds: int = 45
    dry_run: bool = False

    def _run(self, command: str, label: str) -> None:
        if self.dry_run:
            return
        if not command.strip():
            raise HandoffError(f"O host não tem um comando configurado para {label} a Ayla.")
        try:
            res = subprocess.run(
                shlex.split(command), cwd=self.app_dir, check=False, timeout=60,
                stdin=subprocess.DEVNULL, capture_output=True, text=True,
            )
            if res.returncode != 0:
                err_msg = (res.stderr or res.stdout or "").strip()
                raise HandoffError(f"O host falhou ao {label} a Ayla (código {res.returncode}): {err_msg[:200]}")
        except subprocess.TimeoutExpired as exc:
            raise HandoffError(f"O host esgotou o tempo limite ao tentar {label} a Ayla.") from exc
        except (OSError, subprocess.SubprocessError) as exc:
            raise HandoffError(f"O host não conseguiu {label} a Ayla.") from exc

    def is_active(self) -> bool:
        """Verifica de forma confiável se o serviço ayla.service está em execução."""
        if self.dry_run:
            return False
        try:
            res = subprocess.run(
                shlex.split("sudo -n systemctl is-active --quiet ayla.service"),
                cwd=self.app_dir, timeout=5,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return (res.returncode == 0)
        except Exception:
            return False

    def start(self) -> None:
        self._run(self.start_command, "iniciar")
        if not self.health_command.strip() or self.dry_run:
            return
        deadline = time.monotonic() + self.start_timeout_seconds
        while time.monotonic() < deadline:
            if self.is_active():
                return
            time.sleep(0.5)
        raise HandoffError("O host não confirmou a inicialização da Ayla dentro do prazo de segurança.")

    def force_stop(self) -> None:
        """Força a parada imediata da Ayla no host, eliminando qualquer processo travado."""
        if self.dry_run:
            return
        # 1. Tenta stop convencional com timeout curto
        try:
            subprocess.run(
                shlex.split("sudo -n systemctl stop ayla.service"),
                cwd=self.app_dir, timeout=8,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

        # 2. Se continuar ativa, envia SIGKILL direto para o cgroup do systemd
        if self.is_active():
            try:
                subprocess.run(
                    shlex.split("sudo -n systemctl kill -s SIGKILL ayla.service"),
                    cwd=self.app_dir, timeout=8,
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass
            time.sleep(0.5)

        # 3. Elimina eventuais processos órfãos de Ayla.py caso o systemd tenha se perdido
        # Com sudo: o serviço pode rodar como root e sem sudo o pkill não mata nada.
        try:
            subprocess.run(
                shlex.split("sudo -n pkill -9 -f 'python.*Ayla\\.py'"),
                cwd=self.app_dir, timeout=5,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

        # 4. Reseta o estado de falha da unidade para deixá-la limpa para próxima subida
        try:
            subprocess.run(
                shlex.split("sudo -n systemctl reset-failed ayla.service"),
                cwd=self.app_dir, timeout=5,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

        # 5. Confere que não restou processo zumbi de Ayla.py: liberar a posse
        # com um sobrevivente recriaria o conflito de claim.
        if self._ha_processo_ayla():
            raise HandoffError("Não foi possível forçar o encerramento da Ayla no host (processo sobrevivente ao SIGKILL).")

        if self.is_active():
            raise HandoffError("Não foi possível forçar o encerramento da Ayla no host.")

    def _ha_processo_ayla(self) -> bool:
        """Verifica com privilégios se algum processo Ayla.py sobreviveu.

        Combina o MainPID oficial do systemd com uma varredura via sudo
        (resistente a hidepid, onde pgrep sem sudo não vê processos alheios).
        """
        if self.dry_run:
            return False
        # 1. MainPID do systemd: a fonte oficial do processo do serviço
        try:
            res = subprocess.run(
                shlex.split("systemctl show ayla.service --property=MainPID --value"),
                cwd=self.app_dir, timeout=5,
                stdin=subprocess.DEVNULL, capture_output=True, text=True,
            )
            main_pid = (res.stdout or "").strip()
            if main_pid.isdigit() and main_pid != "0":
                return True
        except Exception:
            pass
        # 2. Varredura ampla com sudo (órfãos fora do cgroup; funciona com hidepid)
        try:
            res = subprocess.run(
                shlex.split("sudo -n pgrep -f 'python.*Ayla\\.py'"),
                cwd=self.app_dir, timeout=5,
                stdin=subprocess.DEVNULL, capture_output=True, text=True,
            )
            pids = [p for p in (res.stdout or "").split() if p.strip().isdigit()]
            return bool(pids)
        except Exception:
            return False

    def stop(self, force: bool = False) -> None:
        """Para o serviço da Ayla no host de forma limpa ou forçada."""
        if self.dry_run:
            return
        if force:
            self.force_stop()
            return
        # Usa systemctl stop para garantir parada limpa no systemd
        # sem disparar Restart=on-failure
        try:
            self._run("sudo -n systemctl stop ayla.service", "parar serviço da Ayla")
        except Exception:
            # Se nem o comando de parada funcionou, aciona parada forçada como salvaguarda
            self.force_stop()
            return

        deadline = time.monotonic() + self.drain_timeout_seconds
        while time.monotonic() < deadline:
            if not self.is_active():
                try:
                    subprocess.run(
                        shlex.split("sudo -n systemctl reset-failed ayla.service"),
                        cwd=self.app_dir, timeout=5,
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                except Exception:
                    pass
                return
            time.sleep(0.5)

        # Se o prazo expirou e a Ayla travou/não respondeu, força parada para não bloquear o sistema
        self.force_stop()


class HostCoordinator:
    """Máquina de estados persistida. Só uma Ayla pode ser dona por vez."""

    def __init__(self, app_dir: Path, data_dir: Path, code_dir: Path, controller: Any,
                 *, max_archive_bytes: int = 1024 * 1024):
        self.app_dir = Path(app_dir).resolve()
        self.data_dir = Path(data_dir).resolve()
        self.code_dir = Path(code_dir).resolve()
        self.controller = controller
        self.max_archive_bytes = max_archive_bytes
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.handoff_dir = self.data_dir / "handoffs"
        self.handoff_dir.mkdir(exist_ok=True)
        self.state_path = self.data_dir / "state.json"
        self.lock = threading.RLock()
        self.state = self._load_state()

    def _load_state(self) -> dict[str, Any]:
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            if state.get("owner") in {"none", "local", "host"}:
                return state
        except (OSError, ValueError, AttributeError):
            pass
        return {"owner": "none", "pending": None, "updated_at": _utc_now()}

    def _save_state(self) -> None:
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.state_path)

    def _new_pending(self, direction: str, device: str) -> dict[str, Any]:
        # Purga diretórios de handoffs anteriores que falharam no meio e nunca
        # foram limpos — evita acúmulo indefinido no servidor.
        for stale in self.handoff_dir.iterdir():
            if stale.is_dir():
                shutil.rmtree(stale, ignore_errors=True)
        handoff_id = uuid.uuid4().hex
        pending = {
            "id": handoff_id,
            "direction": direction,
            "device": device[:100],
            "phase": "prepared",
            "created_at": _utc_now(),
        }
        self.state["pending"] = pending
        self.state["updated_at"] = _utc_now()
        self._save_state()
        (self.handoff_dir / handoff_id).mkdir(parents=True, exist_ok=True)
        return pending

    def _pending(self, handoff_id: str, direction: str | None = None) -> dict[str, Any]:
        pending = self.state.get("pending")
        if not isinstance(pending, dict) or pending.get("id") != handoff_id:
            raise HandoffError("Esta transferência não está mais disponível.")
        if direction and pending.get("direction") != direction:
            raise HandoffError("A etapa solicitada não pertence a esta transferência.")
        return pending

    def status(self) -> dict[str, Any]:
        with self.lock:
            service_active = self.controller.is_active()
            owner = self.state.get("owner", "none")
            if service_active:
                owner = "host"
            elif owner == "host" and not service_active:
                owner = "none"
                # Auto-recuperação: se o serviço no host morreu, cura o estado persistido
                self.state["owner"] = "none"
                self.state["updated_at"] = _utc_now()
                self._save_state()

            pending = self.state.get("pending")
            return {
                "protocol": PROTOCOL_VERSION,
                "owner": owner,
                "service_active": service_active,
                "transition": pending.get("direction") if isinstance(pending, dict) else None,
                "updated_at": self.state.get("updated_at"),
            }

    def force_stop_host(self) -> dict[str, Any]:
        """Interrompe forçadamente qualquer instância da Ayla ativa no host e reseta o estado."""
        with self.lock:
            self.controller.force_stop()
            pending = self.state.get("pending")
            if isinstance(pending, dict):
                stale_id = str(pending.get("id", ""))
                if stale_id:
                    shutil.rmtree(self.handoff_dir / stale_id, ignore_errors=True)
            self.state = {"owner": "none", "pending": None, "updated_at": _utc_now()}
            self._save_state()
            return {"ok": True, "service_active": False, "owner": "none"}

    def reserve_to_host(self, device: str, force: bool = False) -> dict[str, Any]:
        with self.lock:
            service_active = self.controller.is_active()
            # Se o serviço não está ativo no host, cura estado obsoleto gravado
            if not service_active and self.state.get("owner") == "host":
                self.state["owner"] = "none"
                self.state["updated_at"] = _utc_now()
                self._save_state()

            # Se a Ayla estiver ativa ou registrada no host
            if self.state.get("owner") == "host" or service_active:
                if force:
                    # Força parada imediata para liberar a vaga e destravar
                    self.controller.force_stop()
                    self.state["owner"] = "none"
                    self.state["updated_at"] = _utc_now()
                    self._save_state()
                else:
                    raise HandoffError("A Ayla já está ativa no host; não é seguro iniciar uma segunda instância.")

            pending = self.state.get("pending")
            if pending:
                stale_id = str(pending.get("id", ""))
                if stale_id:
                    shutil.rmtree(self.handoff_dir / stale_id, ignore_errors=True)
            new_pending = self._new_pending("to-host", device)
            return {"handoff_id": new_pending["id"], "resumed": False}

    def prepare_host_state(self, handoff_id: str, body: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            pending = self._pending(handoff_id, "to-host")
            if body.get("schema") != STATE_SCHEMA_VERSION:
                raise HandoffError("O esquema de estado recebido é incompatível.")
            files_hash = str(body.get("files_hash", ""))
            if len(files_hash) != 64:
                raise HandoffError("O hash dos arquivos recebido é inválido.")
            pending["phase"] = "state-prepared"
            pending["files_hash"] = files_hash
            self.state["updated_at"] = _utc_now()
            self._save_state()
            return {"ok": True, "files_hash": files_hash}

    def assume_host(self, handoff_id: str) -> dict[str, Any]:
        with self.lock:
            pending = self._pending(handoff_id, "to-host")
            if pending.get("phase") != "state-prepared":
                raise HandoffError("O estado ainda não foi preparado para o host.")
            local_files = state_manifest(self.app_dir, file_list=TO_HOST_STATE_FILES, include_modos=True)
            if not hmac.compare_digest(local_files["sha256"], str(pending.get("files_hash", ""))):
                raise HandoffError(
                    f"O host não assumiu a Ayla: o hash dos arquivos recebidos não confere "
                    f"(host: {local_files['sha256'][:8]} != esperado: {str(pending.get('files_hash'))[:8]})."
                )
            self.controller.start()
            self.state = {"owner": "host", "pending": None, "updated_at": _utc_now()}
            self._save_state()
            stale_dir = self.handoff_dir / handoff_id
            shutil.rmtree(stale_dir, ignore_errors=True)
            return {"ok": True, "owner": "host"}

    def prepare_to_local(self, device: str, force: bool = False) -> dict[str, Any]:
        with self.lock:
            current_pending = self.state.get("pending")
            if isinstance(current_pending, dict):
                stale_id = str(current_pending.get("id", ""))
                if stale_id:
                    shutil.rmtree(self.handoff_dir / stale_id, ignore_errors=True)
                self.state["pending"] = None
                self._save_state()

            service_active = self.controller.is_active()
            if not service_active and self.state.get("owner") in {"none", "local"}:
                self.state = {"owner": "local", "pending": None, "updated_at": _utc_now()}
                self._save_state()
                return {"ok": True, "owner": "local", "already_local": True}

            # Se a Ayla estiver ativa no host (ou registrada como host), para ela no host de forma limpa ou forçada
            self.controller.stop(force=force)

            # Prepara os arquivos a devolver (somente histórico e memórias; sem env, sem embeddings)
            files = state_manifest(self.app_dir, file_list=TO_LOCAL_STATE_FILES, include_modos=False)
            pending = self._new_pending("to-local", device)
            pending["phase"] = "ready"
            pending["files_hash"] = files["sha256"]
            self.state["updated_at"] = _utc_now()
            self._save_state()
            return {"handoff_id": pending["id"], "files_hash": files["sha256"], "resumed": False}

    def acknowledge_local(self, handoff_id: str) -> dict[str, Any]:
        with self.lock:
            self._pending(handoff_id, "to-local")
            self.state = {"owner": "local", "pending": None, "updated_at": _utc_now()}
            self._save_state()
            shutil.rmtree(self.handoff_dir / handoff_id, ignore_errors=True)
            return {"ok": True, "owner": "local"}


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler, coordinator: HostCoordinator, token: str, max_body: int):
        super().__init__(address, handler)
        self.coordinator = coordinator
        self.token = token
        self.max_body = max_body


class HostRequestHandler(BaseHTTPRequestHandler):
    server: _Server
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args) -> None:
        return

    def _authorized(self) -> bool:
        header = self.headers.get("Authorization", "")
        expected = "Bearer " + self.server.token
        return hmac.compare_digest(header, expected)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_error(self, status: int, message: str) -> None:
        self._send_json(status, {"error": message})

    def _read_body(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError as exc:
            raise HandoffError("O tamanho da requisição é inválido.") from exc
        if length < 0 or length > self.server.max_body:
            raise HandoffError("A requisição excede o limite permitido.")
        body = self.rfile.read(length)
        if len(body) != length:
            raise HandoffError("A requisição foi interrompida antes de terminar.")
        return body

    def _read_json(self) -> dict[str, Any]:
        body = self._read_body()
        try:
            decoded = json.loads(body.decode("utf-8")) if body else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HandoffError("O corpo JSON da requisição é inválido.") from exc
        if not isinstance(decoded, dict):
            raise HandoffError("O corpo JSON da requisição é inválido.")
        return decoded

    def _route(self) -> tuple[str, list[str]]:
        path = self.path.split("?", 1)[0]
        return path, [part for part in path.split("/") if part]

    def _handle(self) -> None:
        if not self._authorized():
            self._send_error(HTTPStatus.UNAUTHORIZED, "Autenticação recusada.")
            return
        if self.headers.get("X-Ayla-Protocol") not in {None, str(PROTOCOL_VERSION)}:
            self._send_error(HTTPStatus.CONFLICT, "Versão de protocolo incompatível.")
            return
        path, pieces = self._route()
        try:
            if self.command == "GET" and path == "/v1/status":
                self._send_json(HTTPStatus.OK, self.server.coordinator.status())
                return
            if self.command == "POST" and path == "/v1/host/force-stop":
                self._send_json(HTTPStatus.OK, self.server.coordinator.force_stop_host())
                return
            if self.command == "GET" and path == "/v1/deployment-manifest":
                self._send_json(HTTPStatus.OK, {"manifest": deployment_manifest(self.server.coordinator.code_dir)})
                return
            if self.command == "POST" and path == "/v1/handoffs/to-host/reserve":
                body = self._read_json()
                self._send_json(
                    HTTPStatus.OK,
                    self.server.coordinator.reserve_to_host(str(body.get("source", "")), force=bool(body.get("force", False))),
                )
                return
            if self.command == "POST" and path == "/v1/handoffs/to-local/prepare":
                body = self._read_json()
                self._send_json(
                    HTTPStatus.OK,
                    self.server.coordinator.prepare_to_local(str(body.get("target", "")), force=bool(body.get("force", False))),
                )
                return
            if len(pieces) == 4 and pieces[:2] == ["v1", "handoffs"]:
                handoff_id = pieces[2]
                action = pieces[3]
                if self.command == "POST" and action == "prepare-state":
                    result = self.server.coordinator.prepare_host_state(handoff_id, self._read_json())
                    self._send_json(HTTPStatus.OK, result)
                    return
                if self.command == "POST" and action == "assume":
                    self._read_json()
                    self._send_json(HTTPStatus.OK, self.server.coordinator.assume_host(handoff_id))
                    return
                if self.command == "POST" and action == "ack-local":
                    self._read_json()
                    self._send_json(HTTPStatus.OK, self.server.coordinator.acknowledge_local(handoff_id))
                    return
            self._send_error(HTTPStatus.NOT_FOUND, "Endpoint inexistente.")
        except HandoffError as exc:
            self._send_error(HTTPStatus.CONFLICT, str(exc))
        except Exception as exc:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Erro interno no host: {exc}")

    def do_GET(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()

    def do_PUT(self) -> None:
        self._handle()


def create_server(bind: str, port: int, *, app_dir: Path, data_dir: Path, code_dir: Path,
                  token: str, controller: Any, max_archive_bytes: int = MAX_API_MESSAGE_BYTES) -> _Server:
    if len(token) < 32:
        raise ValueError("O token do agente do host precisa ter pelo menos 32 caracteres.")
    coordinator = HostCoordinator(app_dir, data_dir, code_dir, controller, max_archive_bytes=max_archive_bytes)
    return _Server((bind, port), HostRequestHandler, coordinator, token, max_archive_bytes)


def main() -> int:
    parser = argparse.ArgumentParser(description="Agente de transferência da Ayla hospedada")
    parser.add_argument("--bind", default=os.getenv("AYLA_HOST_BIND", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("AYLA_HOST_PORT", "8765")))
    parser.add_argument("--app-dir", default=os.getenv("AYLA_HOST_APP_DIR", str(Path(__file__).resolve().parents[1])))
    parser.add_argument("--data-dir", default=os.getenv("AYLA_HOST_DATA_DIR", str(Path(__file__).resolve().parent / "runtime")))
    args = parser.parse_args()
    token = host_api_token_from_environment()
    if len(token) < 32:
        raise SystemExit("Defina AYLA_HOST_TOKEN com pelo menos 32 caracteres aleatórios no ambiente do agente.")
    try:
        drain_timeout = max(15, min(900, int(os.getenv("AYLA_HOST_DRAIN_TIMEOUT_SECONDS", "130"))))
    except ValueError:
        drain_timeout = 130
    try:
        start_timeout = max(10, min(180, int(os.getenv("AYLA_HOST_START_TIMEOUT_SECONDS", "45"))))
    except ValueError:
        start_timeout = 45
    # Defaults seguros: se o .env do agente não definir os comandos, usa o systemd
    # diretamente. Isso evita que o assume falhe com "comando não configurado".
    controller = CommandProcessController(
        app_dir=Path(args.app_dir),
        start_command=os.getenv("AYLA_HOST_START_COMMAND", "sudo -n systemctl start ayla.service"),
        health_command=os.getenv("AYLA_HOST_HEALTH_COMMAND", "sudo -n systemctl is-active --quiet ayla.service"),
        drain_command=os.getenv("AYLA_HOST_DRAIN_COMMAND", ""),
        stopped_command=os.getenv("AYLA_HOST_STOPPED_COMMAND", ""),
        drain_timeout_seconds=drain_timeout,
        start_timeout_seconds=start_timeout,
        dry_run=os.getenv("AYLA_HOST_DRY_RUN", "").strip().lower() in {"1", "true", "yes", "sim"},
    )
    server = create_server(
        args.bind, args.port, app_dir=Path(args.app_dir), data_dir=Path(args.data_dir),
        code_dir=Path(__file__).resolve().parent, token=token, controller=controller,
    )
    print(f"Agente da Ayla escutando em http://{args.bind}:{args.port}")
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
