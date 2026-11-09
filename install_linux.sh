#!/usr/bin/env bash
# Instala dependências Python em ambiente isolado; pacotes do SO estão em LINUX.md.
set -euo pipefail
AYLA_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd -- "$AYLA_ROOT"
"${AYLA_PYTHON:-python3}" -m venv "$AYLA_ROOT/.venv"
"$AYLA_ROOT/.venv/bin/python" -m pip install --upgrade pip
"$AYLA_ROOT/.venv/bin/python" -m pip install -r "$AYLA_ROOT/requirements.txt" -r "$AYLA_ROOT/Lunar Menu's/requirements.txt"
printf '%s\n' 'Dependências Python instaladas. Inicie com ./ayla.sh (ou ./ayla.sh --with-menu).'
