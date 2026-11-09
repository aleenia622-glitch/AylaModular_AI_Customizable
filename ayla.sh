#!/usr/bin/env bash
set -euo pipefail
AYLA_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd -- "$AYLA_ROOT"
if [[ -x "$AYLA_ROOT/ayla_host/abrir_tunel_host.sh" ]]; then
    "$AYLA_ROOT/ayla_host/abrir_tunel_host.sh"
elif [[ -x "$AYLA_ROOT/ayla host/abrir_tunel_host.sh" ]]; then
    "$AYLA_ROOT/ayla host/abrir_tunel_host.sh"
fi
if [[ -n "${AYLA_PYTHON:-}" ]]; then
    AYLA_INTERPRETER="$AYLA_PYTHON"
else
    AYLA_INTERPRETER=python3
fi
exec "$AYLA_INTERPRETER" Ayla.py "$@"
