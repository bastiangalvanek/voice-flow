#!/usr/bin/env bash
# Voice Flow starten (macOS). Ersetzt "Voice Flow.cmd" und run.ps1 vom PC.
#
#   ./voice-flow.sh              normal starten
#   ./voice-flow.sh --verbose    mit Debug-Ausgabe
#   ./voice-flow.sh --list-devices
#
# Beim ersten Start fragt macOS zweimal nach Rechten (Mikrofon, Bedienungshilfen).
# Ohne Bedienungshilfen bleibt die F8-Taste stumm — siehe README-MAC.md.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
  echo "Keine Umgebung gefunden. Einmalig anlegen:" >&2
  echo "  uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt" >&2
  exit 1
fi

export PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}"
exec .venv/bin/python -m voice_flow.cli "$@"
