#!/usr/bin/env bash
set -euo pipefail
AYLA_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd -- "$AYLA_ROOT"
AYLA_INTERPRETER="${AYLA_PYTHON:-python3}"
if [[ -z "${AYLA_PYTHON:-}" && -x "$AYLA_ROOT/.venv/bin/python" ]]; then
    AYLA_INTERPRETER="$AYLA_ROOT/.venv/bin/python"
fi
if [[ $# -eq 0 ]]; then
    set -- --web
fi
exec "$AYLA_INTERPRETER" "$AYLA_ROOT/ayla_control_center.py" "$@"
