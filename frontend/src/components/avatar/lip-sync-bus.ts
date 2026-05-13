/**
 * Lightweight module-level bus shared between the page-level RAF loop
 * (which samples the TTS analyser) and the R3F `useFrame` consumer
 * inside the avatar.
 *
 * Plain mutable object — intentionally not React state to avoid a
 * 60Hz re-render of the entire page.
 */
export const lipSyncBus: {
  /** Normalised mouth-open value in [0, 1]. Reset when lip-sync stops. */
  mouth: number
} = {
  mouth: 0,
}
