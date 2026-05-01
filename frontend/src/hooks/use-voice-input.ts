import { useCallback, useRef, useState } from 'react'

/** Tune for environment; linear RMS roughly 0–1 after normalization below. */
export type SilenceOptions = {
  /** Continuous below-threshold duration before stopping (ms). */
  silenceDurationMs?: number
  /** Minimum recording length before silence can end capture (ms). */
  minRecordingMs?: number
  /** Sample ambient noise at start of recording for this long (ms). */
  noiseCalibrationMs?: number
  /** Added to measured noise floor to form threshold (linear RMS). */
  rmsMargin?: number
}

const DEFAULT_SILENCE: Required<SilenceOptions> = {
  silenceDurationMs: 2000,
  minRecordingMs: 500,
  noiseCalibrationMs: 320,
  rmsMargin: 0.022,
}

function mergeSilence(opts?: SilenceOptions): Required<SilenceOptions> {
  return { ...DEFAULT_SILENCE, ...opts }
}

function computeRmsTimeDomain(data: Uint8Array): number {
  let sum = 0
  for (let i = 0; i < data.length; i++) {
    const v = (data[i] - 128) / 128
    sum += v * v
  }
  return Math.sqrt(sum / data.length)
}

export function useVoiceInput() {
  const [isRecording, setIsRecording] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const streamRef = useRef<MediaStream | null>(null)
  const blobResolveRef = useRef<((blob: Blob | null) => void) | null>(null)
  const blobPromiseRef = useRef<Promise<Blob | null> | null>(null)

  const vadStopRef = useRef<(() => void) | null>(null)

  const teardownVad = useCallback(() => {
    const end = vadStopRef.current
    vadStopRef.current = null
    end?.()
  }, [])

  const armBlobCompletion = useCallback(() => {
    blobPromiseRef.current = new Promise<Blob | null>((resolve) => {
      blobResolveRef.current = resolve
    })
    return blobPromiseRef.current
  }, [])

  const resolveBlobCompletion = useCallback((blob: Blob | null) => {
    blobResolveRef.current?.(blob)
    blobResolveRef.current = null
    blobPromiseRef.current = null
  }, [])

  const startSilenceWatcher = useCallback(
    (
      stream: MediaStream,
      recorder: MediaRecorder,
      silence: Required<SilenceOptions>,
      recordingStartedAt: number,
    ) => {
      let audioContext: AudioContext | null = null
      let rafId = 0
      let cancelled = false

      const stop = () => {
        if (cancelled) return
        cancelled = true
        cancelAnimationFrame(rafId)
        vadStopRef.current = null
        try {
          void audioContext?.close()
        } catch {
          /* ignore */
        }
        audioContext = null
      }
      vadStopRef.current = stop

      try {
        audioContext = new AudioContext()
      } catch {
        vadStopRef.current = null
        return
      }

      const source = audioContext.createMediaStreamSource(stream)
      const analyser = audioContext.createAnalyser()
      analyser.fftSize = 2048
      analyser.smoothingTimeConstant = 0.65
      source.connect(analyser)
      const data = new Uint8Array(analyser.fftSize)

      let calibrationSum = 0
      let calibrationCount = 0
      let silenceAccumMs = 0
      let lastTs = performance.now()

      const tick = (now: number) => {
        if (cancelled) return
        rafId = requestAnimationFrame(tick)

        const dt = Math.min(now - lastTs, 120)
        lastTs = now

        analyser.getByteTimeDomainData(data)
        const rms = computeRmsTimeDomain(data)

        const elapsedSinceStart = now - recordingStartedAt
        if (elapsedSinceStart < silence.noiseCalibrationMs) {
          calibrationSum += rms
          calibrationCount += 1
          return
        }

        const noiseFloor =
          calibrationCount > 0 ? calibrationSum / calibrationCount : rms
        const threshold = noiseFloor + silence.rmsMargin

        if (elapsedSinceStart < silence.minRecordingMs) {
          silenceAccumMs = 0
          return
        }

        if (rms < threshold) {
          silenceAccumMs += dt
          if (silenceAccumMs >= silence.silenceDurationMs) {
            stop()
            if (recorder.state === 'recording') {
              recorder.stop()
            }
            return
          }
        } else {
          silenceAccumMs = 0
        }
      }

      rafId = requestAnimationFrame(tick)
    },
    [],
  )

  const startRecording = useCallback(
    async (opts?: { endOnSilence?: SilenceOptions }) => {
      setError(null)
      teardownVad()

      if (!navigator.mediaDevices?.getUserMedia) {
        setError('此瀏覽器不支援麥克風錄音。')
        return
      }

      armBlobCompletion()

      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: true,
        })
        streamRef.current = stream
        chunksRef.current = []

        let mime = ''
        if (
          typeof MediaRecorder !== 'undefined' &&
          MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ) {
          mime = 'audio/webm;codecs=opus'
        } else if (
          typeof MediaRecorder !== 'undefined' &&
          MediaRecorder.isTypeSupported('audio/webm')
        ) {
          mime = 'audio/webm'
        }

        const recorder = mime
          ? new MediaRecorder(stream, { mimeType: mime })
          : new MediaRecorder(stream)
        recorderRef.current = recorder

        recorder.ondataavailable = (e) => {
          if (e.data.size > 0) chunksRef.current.push(e.data)
        }

        recorder.onstop = () => {
          teardownVad()
          const t = recorder.mimeType || mime || 'audio/webm'
          const blob =
            chunksRef.current.length > 0
              ? new Blob(chunksRef.current, { type: t })
              : null
          stream.getTracks().forEach((track) => track.stop())
          streamRef.current = null
          recorderRef.current = null
          setIsRecording(false)
          resolveBlobCompletion(blob)
        }

        const recordingStartedAt = performance.now()
        recorder.start()
        setIsRecording(true)

        if (opts?.endOnSilence) {
          startSilenceWatcher(
            stream,
            recorder,
            mergeSilence(opts.endOnSilence),
            recordingStartedAt,
          )
          return blobPromiseRef.current
        }

        return undefined
      } catch {
        setError('無法取得麥克風權限或啟動錄音。')
        setIsRecording(false)
        teardownVad()
        recorderRef.current = null
        streamRef.current?.getTracks().forEach((t) => t.stop())
        streamRef.current = null
        resolveBlobCompletion(null)
        return undefined
      }
    },
    [
      armBlobCompletion,
      resolveBlobCompletion,
      startSilenceWatcher,
      teardownVad,
    ],
  )

  const stopRecording = useCallback((): Promise<Blob | null> => {
    const rec = recorderRef.current
    if (!rec || rec.state === 'inactive') {
      return Promise.resolve(null)
    }
    const pending = blobPromiseRef.current
    teardownVad()
    rec.stop()
    return pending ?? Promise.resolve(null)
  }, [teardownVad])

  return { isRecording, error, startRecording, stopRecording }
}
