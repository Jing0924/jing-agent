"""
FBX → GLB via Blender CLI.

Assigns Base Color textures to `M_Inori_*` materials (Principled BSDF) from the
Inori PNG set, then exports GLB with morph targets.

Usage (from repo root):

  blender --background --python scripts/blender_fbx_to_glb.py -- \\
    Inori-FBX-File-V1.1/Inori_Unity.fbx frontend/public/inori-avatar.glb

Optional third/fourth arguments after the output path:

  [textures_dir] [body_variant]

  - textures_dir: folder containing Tex_Inori_*.png (default: <fbx_parent>/Textures)
  - body_variant: costume1 | costume2 | bodybase — which Tex_Inori_Body_*.png
    to use for M_Inori_Body (default: costume1)

Example with Costume2 body texture and explicit texture folder:

  blender --background --python scripts/blender_fbx_to_glb.py -- \\
    Inori-FBX-File-V1.1/Inori_Unity.fbx out.glb \\
    Inori-FBX-File-V1.1/Textures costume2
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy  # type: ignore

# Material base name (FBX slot) → fixed texture filename under textures_dir.
_MATERIAL_TEXTURE: dict[str, str] = {
    "M_Inori_Head": "Tex_Inori_Head.png",
    "M_Inori_Hair": "Tex_Inori_Hair.png",
    "M_Inori_Costume_A": "Tex_Inori_Costume_A.png",
    "M_Inori_Costume_B": "Tex_Inori_Costume_B.png",
    "M_Inori_CostumeExtra": "Tex_Inori_CostumeExtra.png",
    "M_Inori_Expressions": "Tex_Inori_Expressions.png",
}

_BODY_VARIANT_TO_FILE: dict[str, str] = {
    "costume1": "Tex_Inori_Body_Costume1.png",
    "costume2": "Tex_Inori_Body_Costume2.png",
    "bodybase": "Tex_Inori_BodyBase.png",
}

# Try in order for M_Inori_EyeAlpha (per asset notes).
_EYE_ALPHA_CANDIDATES: tuple[str, ...] = (
    "Tex_Inori_Head.png",
    "Tex_Inori_FaceMask.png",
)


def _argv_after_dd() -> list[str]:
    if "--" not in sys.argv:
        raise SystemExit("Usage: blender ... --python this.py -- input.fbx output.glb [textures_dir] [body_variant]")
    i = sys.argv.index("--") + 1
    return sys.argv[i:]


def _material_base_name(name: str) -> str:
    """Strip Blender duplicate suffix (e.g. M_Inori_Head.001)."""
    if "." in name:
        stem, suf = name.rsplit(".", 1)
        if suf.isdigit():
            return stem
    return name


def _reset_principled_tree(mat: bpy.types.Material) -> bpy.types.ShaderNodeBsdfPrincipled:
    mat.use_nodes = True
    nt = mat.node_tree
    if nt is None:
        raise RuntimeError(f"Material {mat.name} has no node tree")
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (340, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (40, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    mat.blend_method = "OPAQUE"
    return bsdf


def _load_png(textures_dir: Path, fname: str) -> bpy.types.Image:
    path = textures_dir / fname
    if not path.is_file():
        raise FileNotFoundError(f"Missing texture: {path}")
    # check_existing merges duplicate loads by path
    return bpy.data.images.load(str(path.resolve()), check_existing=True)


def _apply_image_base_color(mat: bpy.types.Material, image: bpy.types.Image, *, use_alpha_blend: bool) -> None:
    bsdf = _reset_principled_tree(mat)
    nt = mat.node_tree
    assert nt is not None
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.location = (-260, 0)
    tex.image = image
    tex.image.colorspace_settings.name = "sRGB"

    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    alpha_in = bsdf.inputs.get("Alpha")
    if use_alpha_blend and alpha_in is not None and "Alpha" in tex.outputs:
        nt.links.new(tex.outputs["Alpha"], alpha_in)
        mat.blend_method = "BLEND"
        if hasattr(mat, "shadow_method"):
            mat.shadow_method = "HASHED"


def _apply_glasses_principled(mat: bpy.types.Material) -> None:
    """No dedicated PNG; translucent lens-style Principled only."""
    bsdf = _reset_principled_tree(mat)
    inp_base = bsdf.inputs["Base Color"]
    inp_base.default_value = (0.92, 0.94, 0.96, 1.0)
    if "Metallic" in bsdf.inputs:
        bsdf.inputs["Metallic"].default_value = 0.0
    if "Roughness" in bsdf.inputs:
        bsdf.inputs["Roughness"].default_value = 0.08
    alpha_in = bsdf.inputs.get("Alpha")
    if alpha_in is not None:
        alpha_in.default_value = 0.12
    transmission = bsdf.inputs.get("Transmission Weight") or bsdf.inputs.get("Transmission")
    if transmission is not None:
        transmission.default_value = 0.92
    ior_in = bsdf.inputs.get("IOR")
    if ior_in is not None:
        ior_in.default_value = 1.45
    mat.blend_method = "BLEND"
    if hasattr(mat, "shadow_method"):
        mat.shadow_method = "HASHED"


def _apply_eye_alpha(mat: bpy.types.Material, textures_dir: Path) -> None:
    last_err: FileNotFoundError | None = None
    for fname in _EYE_ALPHA_CANDIDATES:
        try:
            img = _load_png(textures_dir, fname)
        except FileNotFoundError as e:
            last_err = e
            continue
        _apply_image_base_color(mat, img, use_alpha_blend=True)
        return
    assert last_err is not None
    raise last_err


def apply_inori_materials(textures_dir: Path, body_variant: str) -> None:
    variant_key = body_variant.lower().strip()
    if variant_key not in _BODY_VARIANT_TO_FILE:
        allowed = ", ".join(sorted(_BODY_VARIANT_TO_FILE))
        raise SystemExit(f"Unknown body_variant {body_variant!r}; use one of: {allowed}")

    body_file = _BODY_VARIANT_TO_FILE[variant_key]

    for mat in bpy.data.materials:
        base = _material_base_name(mat.name)

        try:
            if base == "M_Inori_Glasses":
                _apply_glasses_principled(mat)
            elif base == "M_Inori_EyeAlpha":
                _apply_eye_alpha(mat, textures_dir)
            elif base == "M_Inori_Body":
                img = _load_png(textures_dir, body_file)
                _apply_image_base_color(mat, img, use_alpha_blend=False)
            elif base in _MATERIAL_TEXTURE:
                fname = _MATERIAL_TEXTURE[base]
                img = _load_png(textures_dir, fname)
                _apply_image_base_color(mat, img, use_alpha_blend=False)
        except FileNotFoundError as e:
            print(f"[blender_fbx_to_glb] WARN: skipped {mat.name}: {e}", flush=True)


def main() -> None:
    args = _argv_after_dd()
    if len(args) < 2:
        raise SystemExit("Need input FBX and output GLB paths after --")
    fbx_path = Path(args[0]).expanduser().resolve()
    out_path = Path(args[1]).expanduser().resolve()
    if not fbx_path.is_file():
        raise SystemExit(f"Missing FBX: {fbx_path}")

    textures_dir = Path(args[2]).expanduser().resolve() if len(args) > 2 else (fbx_path.parent / "Textures")
    body_variant = args[3] if len(args) > 3 else "costume1"

    if not textures_dir.is_dir():
        raise SystemExit(f"Textures directory does not exist: {textures_dir}")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(fbx_path))

    apply_inori_materials(textures_dir, body_variant)

    report_path = out_path.with_name(f"{out_path.stem}.shapekeys.json")
    shapes: dict[str, list[str]] = {}
    for obj in bpy.data.objects:
        if obj.type != "MESH" or obj.data is None or obj.data.shape_keys is None:
            continue
        key_blocks = obj.data.shape_keys.key_blocks
        names = [kb.name for kb in key_blocks]
        if len(names) > 1 or (len(names) == 1 and names[0] != "Basis"):
            shapes[obj.name] = names

    report_path.write_text(json.dumps(shapes, ensure_ascii=False, indent=2), encoding="utf-8")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(out_path),
        export_format="GLB",
        use_visible=True,
        export_apply=True,
        export_morph=True,
        export_animations=True,
        export_materials="EXPORT",
    )


if __name__ == "__main__":
    main()
