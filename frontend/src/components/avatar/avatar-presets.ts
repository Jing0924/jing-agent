/**
 * Inori GLB for the knowledge-chat avatar picker. Re-export with
 * `scripts/export_inori_presets.sh` (preset index 6 → `inori-preset-07.glb`).
 */
export type InoriAvatarPreset = {
  id: string
  label: string
  glbUrl: string
}

export const INORI_AVATAR_PRESETS: readonly InoriAvatarPreset[] = [
  { id: '07', label: '細碎顫動', glbUrl: '/inori-preset-07.glb' },
] as const

export const DEFAULT_INORI_PRESET_GLB_URL = INORI_AVATAR_PRESETS[0].glbUrl
