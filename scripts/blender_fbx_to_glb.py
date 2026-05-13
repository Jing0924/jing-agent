"""
FBX → GLB via Blender CLI.

Assigns Base Color textures to `M_Inori_*` materials (Principled BSDF) from the
Inori PNG set, then exports GLB with morph targets.

Usage (from repo root):

  blender --background --python scripts/blender_fbx_to_glb.py -- \\
    Inori-FBX-File-V1.1/Inori_Unity.fbx frontend/public/inori-preset-07.glb \\
    Inori-FBX-File-V1.1/Textures costume1 6

Optional arguments after the output path:

  [textures_dir] [body_variant] [preset_index|static]

  - textures_dir: folder containing Tex_Inori_*.png (default: <fbx_parent>/Textures)
  - body_variant: costume1 | costume2 | bodybase — which Tex_Inori_Body_*.png
    to use for M_Inori_Body (default: costume1). Overridden when a numeric preset_index
    is given (cycling); unchanged for static|relaxed|no_anim.
  - preset_index: integer 0–9 — selects skeletal loop recipe and cycles body_variant
    as costume1 → costume2 → bodybase by index % 3. Omit for legacy single export
    (motion preset 0, body_variant from previous arg).
  - static (aliases: relaxed, no_anim): no skeletal clips; strip imported actions and
    apply a relaxed arm pose in local space; body_variant stays from previous arg.

Example with Costume2 body texture and explicit texture folder:

  blender --background --python scripts/blender_fbx_to_glb.py -- \\
    Inori-FBX-File-V1.1/Inori_Unity.fbx out.glb \\
    Inori-FBX-File-V1.1/Textures costume2

Preset export (see scripts/export_inori_presets.sh — preset 6 → bundled knowledge-chat GLB):

  blender ... -- Inori_Unity.fbx frontend/public/inori-preset-07.glb \\
    Inori-FBX-File-V1.1/Textures costume1 6

Static relaxed arms, no animation (see scripts/export_inori_relaxed.sh):

  blender ... -- Inori_Unity.fbx frontend/public/inori-avatar-relaxed.glb \\
    Inori-FBX-File-V1.1/Textures costume1 static
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Literal

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

_BODY_CYCLE: tuple[str, str, str] = ("costume1", "costume2", "bodybase")

# Try in order for M_Inori_EyeAlpha (per asset notes).
_EYE_ALPHA_CANDIDATES: tuple[str, ...] = (
    "Tex_Inori_Head.png",
    "Tex_Inori_FaceMask.png",
)

# Optional explicit bone names (Blender pose bone names) for idle upper-arm swing.
# If empty, names are chosen by heuristic; if the rig does not match, add entries here.
_IDLE_UPPER_ARM_BONE_NAMES: tuple[str, ...] = ()

MAIN_ACTION_NAME = "Main"

BoneSubset = Literal["all", "left", "right"]
BoneLayer = Literal["upper_arm", "forearm"]

# Multiply all recipe limb swings after per-side scaling; reduce globally if clips clip cloth.
MOTION_SWING_GLOBAL_SCALE: float = 1.0

# Static relaxed arm pose: local-space Euler offsets (radians) after the import pose is cleared
# on upper-arm / forearm bones. X/Y/Z scale with _idle_arm_sign on X and Z for lateral mirror.
_RELAXED_UPPER_ARM_EULER_XYZ: tuple[float, float, float] = (0.38, -0.18, 0.06)
_RELAXED_FOREARM_EULER_XYZ: tuple[float, float, float] = (0.14, 0.02, 0.0)

_STATIC_MODE_ALIASES: frozenset[str] = frozenset({"static", "relaxed", "no_anim"})

# preset_index → timing, amplitude, local rotation axis (quaternion), bone subset.
# Each clip loops f0 → f1 → f2 with identical pose at f0 and f2.
# Optional: bone_layers (upper_arm ± forearm), torso_swing (rad on spine/chest heuristics),
# per_side_scale multiplies swing for left/right limbs (torso/mid uses 1.0).
_MOTION_PRESETS: list[dict[str, Any]] = [
    # 0 — calm roll on X (bust portrait–readable)
    {
        "fps": 60,
        "f0": 1,
        "f1": 90,
        "f2": 180,
        "swing": 0.15,
        "axis": (1.0, 0.0, 0.0),
        "bones": "all",
        "invert_right_phase": False,
        "bone_layers": ["upper_arm", "forearm"],
    },
    {
        "fps": 30,
        "f0": 1,
        "f1": 48,
        "f2": 96,
        "swing": 0.34,
        "axis": (0.0, 1.0, 0.0),
        "bones": "all",
        "invert_right_phase": False,
        "bone_layers": ["upper_arm", "forearm"],
    },
    {
        "fps": 60,
        "f0": 1,
        "f1": 52,
        "f2": 104,
        "swing": 0.16,
        "axis": (0.0, 0.0, 1.0),
        "bones": "all",
        "invert_right_phase": True,
        "bone_layers": ["upper_arm"],
        "per_side_scale": {"left": 1.15, "right": 0.35},
    },
    {
        "fps": 45,
        "f0": 1,
        "f1": 55,
        "f2": 110,
        "swing": 0.30,
        "axis": (1.0, 0.35, 0.1),
        "bones": "left",
        "invert_right_phase": False,
        "bone_layers": ["upper_arm", "forearm"],
    },
    {
        "fps": 45,
        "f0": 1,
        "f1": 56,
        "f2": 112,
        "swing": 0.30,
        "axis": (0.35, 1.0, 0.08),
        "bones": "right",
        "invert_right_phase": False,
        "bone_layers": ["upper_arm", "forearm"],
    },
    {
        "fps": 24,
        "f0": 1,
        "f1": 72,
        "f2": 144,
        "swing": 0.24,
        "axis": (0.55, 0.45, 0.12),
        "bones": "all",
        "invert_right_phase": False,
        "bone_layers": ["upper_arm", "forearm"],
        "torso_swing": 0.028,
    },
    {
        "fps": 60,
        "f0": 1,
        "f1": 34,
        "f2": 68,
        "swing": 0.36,
        "axis": (0.85, 0.2, 0.15),
        "bones": "all",
        "invert_right_phase": True,
        "bone_layers": ["upper_arm", "forearm"],
        "torso_swing": 0.038,
    },
    {
        "fps": 50,
        "f0": 1,
        "f1": 64,
        "f2": 128,
        "swing": 0.32,
        "axis": (0.25, 0.65, 0.45),
        "bones": "all",
        "invert_right_phase": False,
        "bone_layers": ["upper_arm", "forearm"],
    },
    {
        "fps": 40,
        "f0": 1,
        "f1": 50,
        "f2": 100,
        "swing": 0.20,
        "axis": (0.9, 0.15, 0.08),
        "bones": "all",
        "invert_right_phase": True,
        "bone_layers": ["upper_arm", "forearm"],
        "per_side_scale": {"left": 1.0, "right": 0.45},
    },
    {
        "fps": 36,
        "f0": 1,
        "f1": 80,
        "f2": 160,
        "swing": 0.40,
        "axis": (0.4, 0.75, 0.2),
        "bones": "all",
        "invert_right_phase": False,
        "bone_layers": ["upper_arm", "forearm"],
        "torso_swing": 0.032,
    },
]


def _argv_after_dd() -> list[str]:
    if "--" not in sys.argv:
        raise SystemExit(
            "Usage: blender ... --python this.py -- input.fbx output.glb "
            "[textures_dir] [body_variant] [preset_index|static]"
        )
    i = sys.argv.index("--") + 1
    return sys.argv[i:]


def preset_body_variant(preset_index: int) -> str:
    return _BODY_CYCLE[preset_index % 3]


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


def _pose_bones_upper_arm(arm_ob: bpy.types.Object) -> list[bpy.types.PoseBone]:
    if _IDLE_UPPER_ARM_BONE_NAMES:
        out: list[bpy.types.PoseBone] = []
        for name in _IDLE_UPPER_ARM_BONE_NAMES:
            pb = arm_ob.pose.bones.get(name)
            if pb is None:
                print(f"[blender_fbx_to_glb] WARN: idle bone {name!r} not found on armature", flush=True)
            else:
                out.append(pb)
        return out

    out = []
    for pb in arm_ob.pose.bones:
        n = pb.name.lower()
        if "twist" in n or "forearm" in n:
            continue
        if "upperarm" in n or "upper_arm" in n or "arm_stretch" in n:
            out.append(pb)
    return out


def _pose_bones_forearm(arm_ob: bpy.types.Object) -> list[bpy.types.PoseBone]:
    out: list[bpy.types.PoseBone] = []
    for pb in arm_ob.pose.bones:
        n = pb.name.lower()
        if "twist" in n:
            continue
        if any(
            k in n
            for k in (
                "forearm",
                "lower_arm",
                "lowerarm",
                "elbow",
            )
        ):
            out.append(pb)
    return out


def _pose_bones_torso_sway(arm_ob: bpy.types.Object) -> list[bpy.types.PoseBone]:
    out: list[bpy.types.PoseBone] = []
    for pb in arm_ob.pose.bones:
        n = pb.name.lower()
        if "twist" in n:
            continue
        if any(
            x in n
            for x in (
                "shoulder",
                "clavicle",
                "neck",
                "head",
                "hand",
                "wrist",
                "finger",
            )
        ):
            continue
        if "arm" in n or "leg" in n or "thigh" in n or "knee" in n:
            continue
        if any(k in n for k in ("spine", "chest", "upper_chest")):
            out.append(pb)
    return out


_LAYER_COLLECTORS: dict[BoneLayer, Any] = {
    "upper_arm": _pose_bones_upper_arm,
    "forearm": _pose_bones_forearm,
}


def _collect_bones_for_layers(
    arm_ob: bpy.types.Object,
    layers: list[str],
) -> list[bpy.types.PoseBone]:
    seen: set[str] = set()
    merged: list[bpy.types.PoseBone] = []
    for layer in layers:
        if layer not in _LAYER_COLLECTORS:
            print(f"[blender_fbx_to_glb] WARN: unknown bone_layer {layer!r}; skipping", flush=True)
            continue
        for pb in _LAYER_COLLECTORS[layer](arm_ob):
            if pb.name not in seen:
                seen.add(pb.name)
                merged.append(pb)
    return merged


def _idle_arm_sign(bone_name: str) -> float:
    """Flip swing direction for left vs right limbs (heuristic)."""
    n = bone_name.lower()
    if n.endswith(".l") or n.endswith("_l") or "left" in n:
        return -1.0
    if n.endswith(".r") or n.endswith("_r") or "right" in n:
        return 1.0
    return 1.0


def strip_armature_actions(arm_ob: bpy.types.Object) -> None:
    if arm_ob.type != "ARMATURE":
        return
    if arm_ob.animation_data is not None:
        arm_ob.animation_data_clear()


def strip_scene_object_actions() -> None:
    """Remove object-level animation data (armatures, meshes, empties, etc.) and orphan actions."""
    for ob in bpy.data.objects:
        if ob.type == "ARMATURE":
            strip_armature_actions(ob)
        elif ob.animation_data is not None:
            ob.animation_data_clear()
    for act in list(bpy.data.actions):
        if act.users == 0:
            bpy.data.actions.remove(act)


def _pose_bone_rotation_as_quaternion(pb: bpy.types.PoseBone) -> Any:
    from mathutils import Quaternion  # type: ignore

    if pb.rotation_mode == "QUATERNION":
        return pb.rotation_quaternion.copy()
    if pb.rotation_mode == "AXIS_ANGLE":
        return Quaternion(pb.rotation_axis, pb.rotation_angle).normalized()
    return pb.rotation_euler.to_quaternion()


def _apply_local_rotation_delta(pb: bpy.types.PoseBone, dx: float, dy: float, dz: float) -> None:
    from mathutils import Euler  # type: ignore

    delta = Euler((dx, dy, dz)).to_quaternion()
    base = _pose_bone_rotation_as_quaternion(pb)
    result = (base @ delta).normalized()
    mode = pb.rotation_mode
    if mode == "QUATERNION":
        pb.rotation_quaternion = result
    elif mode == "AXIS_ANGLE":
        axis, angle = result.to_axis_angle()
        pb.rotation_axis = axis
        pb.rotation_angle = angle
    else:
        pb.rotation_euler = result.to_euler(mode)


def apply_relaxed_arm_pose(arm_ob: bpy.types.Object) -> None:
    """Apply small local-space rotations on upper arms / forearms; rest pose for those bones first."""
    from mathutils import Matrix  # type: ignore

    upper = _pose_bones_upper_arm(arm_ob)
    fore = _pose_bones_forearm(arm_ob)

    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    arm_ob.select_set(True)
    bpy.context.view_layer.objects.active = arm_ob
    bpy.ops.object.mode_set(mode="POSE")

    seen_pose: set[str] = set()
    for pb in (*upper, *fore):
        if pb.name in seen_pose:
            continue
        seen_pose.add(pb.name)
        pb.matrix_basis = Matrix.Identity(4)

    def apply_layer(pbs: list[bpy.types.PoseBone], xyz: tuple[float, float, float]) -> None:
        for pb in pbs:
            sign = _idle_arm_sign(pb.name)
            dx, dy, dz = xyz[0] * sign, xyz[1], xyz[2] * sign
            _apply_local_rotation_delta(pb, dx, dy, dz)

    apply_layer(upper, _RELAXED_UPPER_ARM_EULER_XYZ)
    apply_layer(fore, _RELAXED_FOREARM_EULER_XYZ)

    bpy.ops.object.mode_set(mode="OBJECT")


def _bone_side(pb: bpy.types.PoseBone) -> Literal["left", "right", "mid"]:
    n = pb.name.lower()
    if "left" in n or n.endswith(".l") or n.endswith("_l"):
        return "left"
    if "right" in n or n.endswith(".r") or n.endswith("_r"):
        return "right"
    return "mid"


def _filter_by_subset(
    bones: list[bpy.types.PoseBone],
    subset: BoneSubset,
) -> list[bpy.types.PoseBone]:
    if subset == "all":
        return bones
    want = "left" if subset == "left" else "right"
    out = [pb for pb in bones if _bone_side(pb) == want]
    return out if out else bones


def _bezify_action(action: bpy.types.Action) -> None:
    curves = []
    legacy = getattr(action, "fcurves", None)
    if legacy:
        curves.extend(list(legacy))
    elif getattr(action, "is_action_layered", False):
        for layer in action.layers:
            for strip in layer.strips:
                if getattr(strip, "type", "") != "KEYFRAME":
                    continue
                for bag in strip.channelbags:
                    curves.extend(list(bag.fcurves))
    for fc in curves:
        for kp in fc.keyframe_points:
            kp.interpolation = "BEZIER"


def _euler_mid(base: Any, swing: float, sign: float, axis: tuple[float, float, float]) -> Any:
    from mathutils import Euler  # type: ignore

    ax, ay, az = axis
    return Euler(
        (
            base.x + sign * swing * (0.25 * ax + 0.2 * ay + 0.12 * az),
            base.y + sign * swing * (0.2 * ax + 0.65 * ay + 0.18 * az),
            base.z + sign * swing * (0.12 * ax + 0.18 * ay + 0.2 * az),
        ),
        order=base.order,
    )


def _effective_swing(
    pb: bpy.types.PoseBone,
    *,
    limb_swing: float,
    torso_swing: float | None,
    is_torso: bool,
    per_side_scale: dict[str, float] | None,
) -> float:
    scales = per_side_scale or {}
    side = _bone_side(pb)
    if is_torso:
        if torso_swing is None:
            return 0.0
        base = torso_swing
        side_mul = 1.0
    else:
        base = limb_swing
        if side == "left":
            side_mul = float(scales.get("left", 1.0))
        elif side == "right":
            side_mul = float(scales.get("right", 1.0))
        else:
            side_mul = 1.0
    return base * side_mul * MOTION_SWING_GLOBAL_SCALE


def ensure_skeleton_loop(preset_index: int = 0) -> None:
    """Create one looping skeletal clip: upper arms / forearms (recipe), optional torso sway."""
    from mathutils import Quaternion, Vector  # type: ignore

    if not (0 <= preset_index < len(_MOTION_PRESETS)):
        raise ValueError(f"preset_index must be 0..{len(_MOTION_PRESETS) - 1}")

    recipe = _MOTION_PRESETS[preset_index]
    fps = recipe["fps"]
    f0, f1, f2 = recipe["f0"], recipe["f1"], recipe["f2"]
    swing = float(recipe["swing"])
    axis_t = recipe["axis"]
    axis_vec = Vector(axis_t).normalized()
    subset: BoneSubset = recipe["bones"]
    invert_right_phase: bool = recipe["invert_right_phase"]
    bone_layers: list[str] = list(recipe.get("bone_layers") or ["upper_arm"])
    torso_swing = recipe.get("torso_swing")
    if torso_swing is not None:
        torso_swing = float(torso_swing)
    per_side: dict[str, float] | None = recipe.get("per_side_scale")

    arm_ob = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
    if arm_ob is None:
        print("[blender_fbx_to_glb] WARN: no armature found; skipping motion action", flush=True)
        return

    limb_candidates = _collect_bones_for_layers(arm_ob, bone_layers)
    limb_candidates = _filter_by_subset(limb_candidates, subset)

    torso_candidates: list[bpy.types.PoseBone] = []
    if torso_swing is not None and torso_swing > 0:
        torso_candidates = _pose_bones_torso_sway(arm_ob)
        torso_candidates = _filter_by_subset(torso_candidates, subset)

    work_items: list[tuple[bpy.types.PoseBone, bool]] = [
        *( (pb, False) for pb in limb_candidates ),
        *( (pb, True) for pb in torso_candidates ),
    ]

    if not work_items:
        sample = ", ".join(pb.name for pb in list(arm_ob.pose.bones)[:24])
        print(
            "[blender_fbx_to_glb] WARN: no bones matched motion recipe; skipping motion.",
            flush=True,
        )
        print(f"[blender_fbx_to_glb] WARN: first pose bones ({len(arm_ob.pose.bones)}): {sample}", flush=True)
        return

    bpy.context.scene.render.fps = fps
    bpy.context.scene.frame_start = f0
    bpy.context.scene.frame_end = f2

    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    arm_ob.select_set(True)
    bpy.context.view_layer.objects.active = arm_ob
    bpy.ops.object.mode_set(mode="POSE")
    bpy.ops.pose.select_all(action="DESELECT")

    if arm_ob.animation_data is None:
        arm_ob.animation_data_create()
    elif arm_ob.animation_data.action:
        old = arm_ob.animation_data.action
        arm_ob.animation_data.action = None
        if old and old.users == 0:
            bpy.data.actions.remove(old)

    for act in list(bpy.data.actions):
        if act.name == MAIN_ACTION_NAME and act.users == 0:
            bpy.data.actions.remove(act)

    action = bpy.data.actions.new(name=MAIN_ACTION_NAME)
    arm_ob.animation_data.action = action

    for pb, is_torso in work_items:
        eff = _effective_swing(
            pb,
            limb_swing=swing,
            torso_swing=torso_swing,
            is_torso=is_torso,
            per_side_scale=per_side,
        )
        if eff <= 0.0:
            continue

        base_sign = _idle_arm_sign(pb.name)
        side = _bone_side(pb)
        phase = base_sign
        if invert_right_phase and side == "right":
            phase *= -1.0

        if pb.rotation_mode == "QUATERNION":
            base = pb.rotation_quaternion.copy()
            mid = (base @ Quaternion(axis_vec, phase * eff)).normalized()
            pb.rotation_quaternion = base
            pb.keyframe_insert(data_path="rotation_quaternion", frame=f0)
            pb.rotation_quaternion = mid
            pb.keyframe_insert(data_path="rotation_quaternion", frame=f1)
            pb.rotation_quaternion = base
            pb.keyframe_insert(data_path="rotation_quaternion", frame=f2)
        else:
            base = pb.rotation_euler.copy()
            mid = _euler_mid(base, eff, phase, axis_t)
            pb.rotation_euler = base
            pb.keyframe_insert(data_path="rotation_euler", frame=f0)
            pb.rotation_euler = mid
            pb.keyframe_insert(data_path="rotation_euler", frame=f1)
            pb.rotation_euler = base
            pb.keyframe_insert(data_path="rotation_euler", frame=f2)

    _bezify_action(action)
    bpy.context.scene.frame_set(f0)
    bpy.ops.pose.select_all(action="SELECT")
    bpy.ops.pose.transforms_clear()
    bpy.ops.object.mode_set(mode="OBJECT")


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
    preset_index = 0
    static_export = False

    if len(args) > 4:
        fifth = args[4].strip().lower()
        if fifth in _STATIC_MODE_ALIASES:
            static_export = True
        else:
            try:
                preset_index = int(args[4].strip())
            except ValueError as e:
                raise SystemExit(
                    "5th argument must be an integer preset_index (0–9) or "
                    f"static|relaxed|no_anim, got {args[4]!r}"
                ) from e
            max_pi = len(_MOTION_PRESETS) - 1
            if not (0 <= preset_index <= max_pi):
                raise SystemExit(f"preset_index must be between 0 and {max_pi} inclusive")
            body_variant = preset_body_variant(preset_index)

    if not textures_dir.is_dir():
        raise SystemExit(f"Textures directory does not exist: {textures_dir}")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(fbx_path))

    apply_inori_materials(textures_dir, body_variant)
    if static_export:
        strip_scene_object_actions()
        arm_ob = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
        if arm_ob is None:
            print("[blender_fbx_to_glb] WARN: no armature; skipping relaxed pose", flush=True)
        else:
            apply_relaxed_arm_pose(arm_ob)
    else:
        ensure_skeleton_loop(preset_index)

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
        export_animations=not static_export,
        export_materials="EXPORT",
    )


if __name__ == "__main__":
    main()
