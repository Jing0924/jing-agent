#!/usr/bin/env bash
# Export the single bundled Inori GLB for knowledge chat (motion preset 6 → inori-preset-07).
#
# Prerequisites: Blender on PATH; FBX + Textures under Inori-FBX-File-V1.1/
#
# Usage (repo root):
#   bash scripts/export_inori_presets.sh
#
# Outputs:
#   frontend/public/inori-preset-07.glb
#   frontend/public/inori-preset-07.shapekeys.json

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FBX="${ROOT}/Inori-FBX-File-V1.1/Inori_Unity.fbx"
TEXTURES="${ROOT}/Inori-FBX-File-V1.1/Textures"
OUT_DIR="${ROOT}/frontend/public"
PY="${ROOT}/scripts/blender_fbx_to_glb.py"
PRESET_INDEX=6

if ! command -v blender >/dev/null 2>&1; then
  echo "export_inori_presets.sh: blender not found in PATH" >&2
  exit 1
fi

blender --background --python "$PY" -- \
  "$FBX" "${OUT_DIR}/inori-preset-07.glb" \
  "$TEXTURES" costume1 "$PRESET_INDEX"

echo "export_inori_presets.sh: wrote ${OUT_DIR}/inori-preset-07.glb"
