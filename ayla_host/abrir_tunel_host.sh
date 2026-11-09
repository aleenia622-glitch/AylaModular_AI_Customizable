#!/usr/bin/env bash
# Mantém a API privada no host e cria o canal SSH local usado pela Ayla.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/.env"
value() { sed -n "s/^$1=//p" "$ENV_FILE" | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//" | tail -n 1; }

TARGET="$(value AYLA_HOST_SSH_TARGET)"
KEY="$(value AYLA_HOST_SSH_KEY)"
URL="$(value AYLA_HOST_URL)"
PORT="${URL##*:}"
PORT="${PORT%%/*}"

[[ -n "$TARGET" && -n "$KEY" && "$URL" == http://127.0.0.1:* ]] || exit 0
[[ "$KEY" = /* ]] || KEY="$ROOT/$KEY"
[[ -f "$KEY" ]] || { echo "Chave SSH da Ayla não encontrada." >&2; exit 1; }

if ss -ltn "sport = :$PORT" 2>/dev/null | grep -q LISTEN; then
    exit 0
fi
ssh -fN -i "$KEY" -o BatchMode=yes -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
    -L "127.0.0.1:$PORT:127.0.0.1:8765" "$TARGET"
