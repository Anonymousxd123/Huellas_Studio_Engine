#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENGINE_DIR="$ROOT/engines/CosyVoice-MPS"
MODEL_DIR="$ENGINE_DIR/pretrained_models/Fun-CosyVoice3-0.5B"

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "Este instalador requiere macOS en Apple Silicon."
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "Falta Git. Instala las herramientas de línea de comandos de Xcode."
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "Falta uv. Instálalo con: brew install uv"
  exit 1
fi

if [[ ! -d "$ENGINE_DIR/.git" ]]; then
  mkdir -p "$(dirname "$ENGINE_DIR")"
  git clone --recursive https://github.com/ZoneTwelve/CosyVoice-MPS.git "$ENGINE_DIR"
else
  echo "[OK] CosyVoice-MPS ya está clonado."
  git -C "$ENGINE_DIR" submodule update --init --recursive
fi

cd "$ENGINE_DIR"
uv python install 3.10
if [[ ! -x ".venv/bin/python" ]]; then
  uv venv --python 3.10 .venv
fi

# The upstream requirements file includes CUDA-specific extra indexes.
# On Apple Silicon, use PyPI directly and omit those indexes so uv does not
# resolve macOS onnxruntime from Microsoft's CUDA package feed.
MAC_REQUIREMENTS="$(mktemp)"
trap 'rm -f "$MAC_REQUIREMENTS"' EXIT

# openai-whisper 20231117 uses pkg_resources from setuptools at build time,
# but its legacy setup.py does not declare that build dependency. New isolated
# build environments can therefore fail with "No module named pkg_resources".
# Install a compatible setuptools in this venv, install the remaining runtime
# requirements normally, then build this one legacy package without isolation.
grep -vE '^[[:space:]]*--extra-index-url([[:space:]]|=)|^[[:space:]]*openai-whisper==' \
  requirements.txt > "$MAC_REQUIREMENTS"

uv pip install \
  --python .venv/bin/python \
  --index-url https://pypi.org/simple \
  "setuptools<81" wheel

uv pip install \
  --python .venv/bin/python \
  --index-url https://pypi.org/simple \
  -r "$MAC_REQUIREMENTS"

uv pip install \
  --python .venv/bin/python \
  --index-url https://pypi.org/simple \
  --no-build-isolation \
  "openai-whisper==20231117"

uv pip install \
  --python .venv/bin/python \
  --index-url https://pypi.org/simple \
  huggingface_hub

echo ""
echo "ENTORNO COSYVOICE MPS INSTALADO"
.venv/bin/python - <<'PY'
import platform
import torch
print("Arquitectura:", platform.machine())
print("PyTorch:", torch.__version__)
print("MPS disponible:", torch.backends.mps.is_available())
if not torch.backends.mps.is_available():
    raise SystemExit("PyTorch no detecta MPS en este Mac.")
PY

if [[ -d "$MODEL_DIR" && -f "$MODEL_DIR/cosyvoice3.yaml" ]]; then
  echo "[OK] El modelo Fun-CosyVoice3 ya está descargado."
else
  echo ""
  echo "El modelo Fun-CosyVoice3-0.5B ocupa aproximadamente 9.75 GB."
  read -r -p "¿Descargar ahora el modelo? [y/N] " answer
  if [[ "$answer" =~ ^[Yy]$ ]]; then
    mkdir -p "$(dirname "$MODEL_DIR")"
    .venv/bin/python - "$MODEL_DIR" <<'PY'
import sys
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id="FunAudioLLM/Fun-CosyVoice3-0.5B-2512",
    local_dir=sys.argv[1]
)
PY
  else
    echo "Modelo no descargado. Ejecuta este instalador de nuevo cuando estés listo."
  fi
fi

echo ""
echo "CONFIGURACIÓN COSYVOICE FINALIZADA"
echo "Entorno: $ENGINE_DIR/.venv"
echo "Modelo:  $MODEL_DIR"
echo "Próximo paso: ejecutar las audiciones locales de Akira y Daniela desde Huellas Studio."
