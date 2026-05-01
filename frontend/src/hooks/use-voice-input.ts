import { useCallback, useRef, useState } from 'react'

export function useVoiceInput() {
  const [isRecording, setIsRecording] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const streamRef = useRef<MediaStream | null>(null)
  const stopResolverRef = useRef<((blob: Blob | null) => void) | null>(null)

  const startRecording = useCallback(async () => {
    setError(null)
    if (!navigator.mediaDevices?.getUserMedia) {
      setError('此瀏覽器不支援麥克風錄音。')
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
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
        const t = recorder.mimeType || mime || 'audio/webm'
        const blob =
          chunksRef.current.length > 0
            ? new Blob(chunksRef.current, { type: t })
            : null
        stream.getTracks().forEach((track) => track.stop())
        streamRef.current = null
        recorderRef.current = null
        setIsRecording(false)
        stopResolverRef.current?.(blob)
        stopResolverRef.current = null
      }

      recorder.start()
      setIsRecording(true)
    } catch {
      setError('無法取得麥克風權限或啟動錄音。')
      setIsRecording(false)
    }
  }, [])

  const stopRecording = useCallback((): Promise<Blob | null> => {
    return new Promise((resolve) => {
      const rec = recorderRef.current
      if (!rec || rec.state === 'inactive') {
        resolve(null)
        return
      }
      stopResolverRef.current = resolve
      rec.stop()
    })
  }, [])

  return { isRecording, error, startRecording, stopRecording }
}
