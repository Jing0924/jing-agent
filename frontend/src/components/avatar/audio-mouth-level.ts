import { lipSyncBus } from './lip-sync-bus'

/**
 * Runs every animation frame: samples analyser time-domain audio and maps a
 * smoothed envelope to `lipSyncBus.mouth` in [0, 1].
 */
export function startLipSyncLoop(analyser: AnalyserNode): () => void {
  analyser.fftSize = 2048
  const bufferLength = analyser.fftSize
  const dataArray = new Uint8Array(bufferLength)

  let raf = 0
  let smoothed = 0

  const tick = () => {
    analyser.getByteTimeDomainData(dataArray)
    let sumSq = 0
    for (let i = 0; i < bufferLength; i++) {
      const centered = (dataArray[i]! - 128) / 128
      sumSq += centered * centered
    }
    const rms = Math.sqrt(sumSq / bufferLength)
    const boosted = Math.min(1, rms * 5)
    const shaped = Math.pow(boosted, 0.55)
    smoothed += (shaped - smoothed) * 0.35
    lipSyncBus.mouth = smoothed
    raf = requestAnimationFrame(tick)
  }

  raf = requestAnimationFrame(tick)

  return () => {
    cancelAnimationFrame(raf)
    lipSyncBus.mouth = 0
  }
}
