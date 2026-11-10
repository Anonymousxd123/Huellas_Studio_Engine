#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Este instalador está preparado para macOS."
  exit 1
fi

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew no está instalado. Instálalo desde https://brew.sh y vuelve a ejecutar."
  exit 1
fi

if ! command -v espeak-ng >/dev/null 2>&1; then
  echo "[1/3] Instalando espeak-ng..."
  brew install espeak-ng
else
  echo "[1/3] espeak-ng ya está instalado."
fi

if [[ ! -x ".venv/bin/python" ]]; then
  echo "[2/3] Creando entorno virtual .venv..."
  python3 -m venv .venv
else
  echo "[2/3] Reutilizando entorno .venv existente."
fi

echo "[3/3] Instalando Huellas Studio con Kokoro TTS..."
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e ".[tts]"

echo ""
echo "INSTALACIÓN TTS COMPLETADA"
echo "Prueba las voces con:"
echo ".venv/bin/python scripts/preview_voice_profiles.py --episode episode_001"
