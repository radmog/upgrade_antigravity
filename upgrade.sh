#!/usr/bin/env bash

# Wrapper de compatibilidade. Toda a lógica reside na implementação Python.
set -o errexit
set -o nounset

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' "Erro: Python 3 é necessário para executar o Antigravity Updater." >&2
    exit 127
fi

exec python3 "$SCRIPT_DIR/upgrade.py" "$@"
