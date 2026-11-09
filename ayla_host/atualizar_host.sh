#!/usr/bin/env bash
# Publica a Ayla no Oracle e valida a API por um túnel SSH privado.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/.env"
value() { sed -n "s/^$1=//p" "$ENV_FILE" | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//" | tail -n 1; }
TARGET="$(value AYLA_HOST_SSH_TARGET)"
KEY="$(value AYLA_HOST_SSH_KEY)"
[[ -n "$TARGET" && -n "$KEY" ]] || { echo "Configure o host no .env da Ayla." >&2; exit 1; }
[[ "$KEY" = /* ]] || KEY="$ROOT/$KEY"
[[ -f "$KEY" ]] || { echo "Chave SSH não encontrada: $KEY" >&2; exit 1; }
chmod 600 "$KEY"

SSH=(ssh -i "$KEY" -o BatchMode=yes -o StrictHostKeyChecking=yes "$TARGET")
RSYNC_SSH="ssh -i '$KEY' -o BatchMode=yes -o StrictHostKeyChecking=yes"

# Localiza o rsync mesmo dentro de sandboxes (ex.: VS Code Flatpak)
RSYNC="$(command -v rsync || true)"
if [[ -z "$RSYNC" ]]; then
    for c in /usr/bin/rsync /bin/rsync /usr/local/bin/rsync /run/host/usr/bin/rsync; do
        [[ -x "$c" ]] && RSYNC="$c" && break
    done
fi
[[ -n "$RSYNC" ]] || { echo "rsync não está instalado nesta máquina." >&2; exit 1; }

"${SSH[@]}" 'sudo install -d -m 0750 -o ubuntu -g ubuntu /opt/ayla'
_rsync() { "$RSYNC" -az "$@"; }
_rsync --delete --partial --inplace --checksum -e "$RSYNC_SSH" \
    --exclude='.git/' --exclude='.venv/' --exclude='__pycache__/' --exclude='*.pyc' \
    --exclude='chave SSH/' --exclude='ayla host/' --exclude='ayla_host/' --exclude='.ayla-host-outgoing/' --exclude='.ayla-host-incoming/' --exclude='.ayla-host-runtime/' \
    --exclude='Aylafotitos/' --exclude='VideosBaixados/' --exclude='Buffer de video/' \
    --exclude='audio_output/' --exclude='TorrentsBaixados/' \
    "$ROOT/" "$TARGET:/opt/ayla/"
_rsync --delete --partial --inplace --checksum -e "$RSYNC_SSH" \
    --exclude='runtime/' --exclude='data/' --exclude='__pycache__/' --exclude='*.pyc' \
    "$ROOT/ayla host/" "$TARGET:/opt/ayla/ayla_host/"

"${SSH[@]}" 'set -e; sudo cp /opt/ayla/ayla_host/systemd/ayla.service /etc/systemd/system/ayla.service; sudo cp /opt/ayla/ayla_host/systemd/ayla-host-agent.service /etc/systemd/system/ayla-host-agent.service; sudo systemctl daemon-reload; sudo systemctl enable --now ayla-host-agent.service; sudo systemctl restart ayla-host-agent.service; rm -rf "/opt/ayla/ayla host"; ln -sfn /opt/ayla/ayla_host "/opt/ayla/ayla host"; sudo apt-get update -qq; sudo apt-get install -y -qq python3-pip portaudio19-dev; sudo /usr/bin/python3 -m pip install --break-system-packages -q -r /opt/ayla/requirements.txt'

"$ROOT/ayla host/abrir_tunel_host.sh"
python3 - "$ROOT" <<'PY'
import sys
from pathlib import Path
root = Path(sys.argv[1])
from dotenv import load_dotenv
load_dotenv(root / '.env', override=True)
sys.path.insert(0, str(root / 'ayla host'))
from ayla_handoff import host_client_from_environment
client = host_client_from_environment(code_dir=root / 'ayla host')
print(client._request('GET', '/v1/status'))
PY

echo 'Host atualizado. A Ayla do host permanece parada até a primeira transferência confirmada.'
