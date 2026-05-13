/**
 * Bundled same-origin GLB: `final_character_-_blend_shapes.glb` (repo root)
 * copied to `public/final-character-blend-shapes.glb`. No outbound request on
 * first paint when using default.
 *
 * Override via `frontend/.env.local`:
 *
 *     VITE_AVATAR_GLB_URL=https://example.com/your-avatar.glb
 *
 * Bundled Inori FBX→glTF output for experiments (ARKit-style morph names):
 * put `public/inori-avatar.glb` in place and set `VITE_AVATAR_GLB_URL=/inori-avatar.glb`,
 * or re-export with `scripts/blender_fbx_to_glb.py`.
 *
 * For lip-sync and idle blink, the model needs blendshapes the app looks up
 * by name (`jawOpen`, `eyeBlinkLeft`, `eyeBlinkRight`). If the GLB was
 * exported without glTF morph targets (`primitives[].targets`), those
 * lookups find nothing — the avatar still renders; mouth/eye morphs are
 * skipped until you re-export with Shape Keys / ARKit-style visemes.
 */
export const BUNDLED_AVATAR_GLB_URL =
  '/final-character-blend-shapes.glb' as const

/** Same-origin Inori GLB under `public/` — knowledge chat answer avatar. */
export const INORI_AVATAR_GLB_URL = '/inori-avatar.glb' as const

const envOverride = import.meta.env.VITE_AVATAR_GLB_URL as
  | string
  | undefined

export const AVATAR_GLB_URL: string =
  envOverride && envOverride.trim().length > 0
    ? envOverride.trim()
    : BUNDLED_AVATAR_GLB_URL
