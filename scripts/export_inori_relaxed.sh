#!/usr/bin/env bash
# Export a single static Inori GLB (no skeletal clips) with relaxed arms.
#
# Prerequisites: Blender on PATH; FBX + Textures under Inori-FBX-File-V1.1/
#
# Usage (repo root):
#   bash scripts/export_inori_relaxed.sh
#
# Output:
#   frontend/public/inori-avatar-relaxed.glb
#   frontend/public/inori-avatar-relaxed.shapekeys.json

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FBX="${ROOT}/Inori-FBX-File-V1.1/Inori_Unity.fbx"
TEXTURES="${ROOT}/Inori-FBX-File-V1.1/Textures"
OUT="${ROOT}/frontend/public/inori-avatar-relaxed.glb"
PY="${ROOT}/scripts/blender_fbx_to_glb.py"

if ! command -v blender >/dev/null 2>&1; then
  echo "export_inori_relaxed.sh: blender not found in PATH" >&2
  exit 1
fi

blender --background --python "$PY" -- \
  "$FBX" "$OUT" \
  "$TEXTURES" costume1 static

echo "export_inori_relaxed.sh: wrote ${OUT}"
