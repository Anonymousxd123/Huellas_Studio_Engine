#!/usr/bin/env bash
set -euo pipefail

COMFYUI_DIR="${1:-$HOME/HuellasStudioAI/ComfyUI}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHECKPOINT="ltxv-2b-0.9.6-distilled-04-25.safetensors"
TEXT_ENCODER="t5xxl_fp16.safetensors"
CHECKPOINT_URL="https://huggingface.co/Lightricks/LTX-Video/resolve/main/$CHECKPOINT"
TEXT_ENCODER_URL="https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/$TEXT_ENCODER"
LICENSE_URL="https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltxv-2b-0.9.6-distilled-04-25.license.txt"

if [[ ! -f "$COMFYUI_DIR/main.py" ]]; then
  echo "[ERROR] No se encontró ComfyUI en: $COMFYUI_DIR"
  echo "Uso: bash scripts/setup_ltx_animation_macos.sh /ruta/a/ComfyUI"
  exit 1
fi

CHECKPOINT_DIR="$COMFYUI_DIR/models/checkpoints"
TEXT_DIR="$COMFYUI_DIR/models/text_encoders"
NODE_DIR="$COMFYUI_DIR/custom_nodes/HuellasLTXNodes"
mkdir -p "$CHECKPOINT_DIR" "$TEXT_DIR" "$NODE_DIR"

echo "========== HUELLAS STUDIO - LTX LOCAL ANIMATION =========="
echo "ComfyUI: $COMFYUI_DIR"

python3 - "$CHECKPOINT_DIR/$CHECKPOINT" "$TEXT_DIR/$TEXT_ENCODER" <<'PY'
import shutil
import sys
from pathlib import Path

targets = [Path(value) for value in sys.argv[1:]]
missing = [path for path in targets if not path.is_file() or path.stat().st_size < 1024]
if missing:
    required = sum(
        6_500_000_000 if "ltxv-" in path.name else 10_000_000_000
        for path in missing
    )
    free = shutil.disk_usage(missing[0].parent).free
    print(f"Espacio libre en disco: {free / 1e9:.1f} GB")
    print(f"Descarga pendiente estimada: {required / 1e9:.1f} GB")
    if free < required + 2_000_000_000:
        raise SystemExit(
            "[ERROR] No hay espacio suficiente. Libera espacio y vuelve a ejecutar."
        )
else:
    print("[OK] Ambos modelos ya están instalados; no se requiere espacio adicional.")
PY

download_if_missing() {
  local url="$1"
  local destination="$2"
  if [[ -s "$destination" ]]; then
    echo "[OK] Ya existe: $destination"
    return
  fi
  echo "[DOWNLOAD] $destination"
  curl -L --fail --retry 4 --retry-delay 3 -C - "$url" -o "$destination"
  if [[ ! -s "$destination" ]]; then
    echo "[ERROR] Descarga vacía: $destination"
    exit 1
  fi
}

download_if_missing "$CHECKPOINT_URL" "$CHECKPOINT_DIR/$CHECKPOINT"
download_if_missing "$TEXT_ENCODER_URL" "$TEXT_DIR/$TEXT_ENCODER"

if [[ ! -s "$COMFYUI_DIR/models/checkpoints/ltxv-2b-0.9.6-distilled-04-25.license.txt" ]]; then
  curl -L --fail --retry 3 "$LICENSE_URL" \
    -o "$COMFYUI_DIR/models/checkpoints/ltxv-2b-0.9.6-distilled-04-25.license.txt" || {
      echo "[WARN] No se pudo descargar el archivo de licencia automáticamente."
    }
fi

cp "$REPO_ROOT/comfyui_custom_nodes/HuellasLTXNodes/__init__.py" "$NODE_DIR/__init__.py"

echo ""
echo "[OK] Checkpoint LTX 2B distilled instalado."
echo "[OK] Encoder T5 XXL FP16 instalado."
echo "[OK] Nodos auxiliares mínimos instalados."
echo ""
echo "IMPORTANTE:"
echo "1. Detén ComfyUI si está ejecutándose (Ctrl+C en su Terminal)."
echo "2. Reinicia ComfyUI con tu comando habitual."
echo "3. Ejecuta desde Huellas_Studio_Engine:"
echo "   PYTHONPATH=src .venv/bin/python scripts/animate_scene.py --episode episode_001 --scene SC003"
