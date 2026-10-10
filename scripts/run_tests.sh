#!/bin/bash
# Corre las pruebas del proyecto (unitarias + integración + e2e).
#
# CÓMO LO EJECUTA UN AGENTE (una sola orden, sin reintentos):
#   wsl -d Ubuntu -e bash /home/juanda/angie-nails/scripts/run_tests.sh
# El script se ubica solo en la raíz del repo y arregla el PATH por su
# cuenta: uv vive en ~/.local/bin y node/npx en ~/.nvm/versions/node/*,
# y nvm NO se carga en shells no interactivos. Sin el PATH de node, las
# pruebas de integración fallan todas al instante ("npx: command not
# found") y hay que reintentarlas; con este script eso no pasa.
# Darle tiempo: la suite completa tarda ~4 minutos.
#
# Args opcionales se pasan tal cual a pytest:
#   scripts/run_tests.sh tests/unit -q       # solo unitarias (rápido)
#   scripts/run_tests.sh tests/integration   # solo integración (~2-3 min)
#   scripts/run_tests.sh tests/e2e           # solo navegador (Edge)
#   scripts/run_tests.sh -m smoke            # humo contra producción
#   scripts/run_tests.sh tests/unit/test_admin_logic.py -q   # un archivo
# Sin args corre todo menos smoke (addopts de pyproject.toml).
#
# Notas: integración levanta wrangler dev con D1 local (puertos 8791/8792;
# conftest mata workerd huérfanos de corridas anteriores). e2e usa
# Microsoft Edge vía Playwright; si Edge no está, esas pruebas se saltan.

set -euo pipefail

export PATH="$HOME/.local/bin:$HOME/.nvm/versions/node/v24.21.0/bin:$PATH"

cd "$(dirname "$0")/.."

npm run build:assets --silent
exec uv run pytest "$@"
