/** Gemini streaming TTS PCM (s16le mono) nominal rate — must match backend. */
export const GEMINI_TTS_PCM_SAMPLE_RATE_HZ = 24000

async function parseErrorDetail(res: Response): Promise<string> {
  try {
    const j = (await res.json()) as { detail?: unknown }
    const d = j.detail
    if (typeof d === 'string') return d
    if (Array.isArray(d) && d.length > 0) {
      const first = d[0] as { msg?: string }
      if (typeof first?.msg === 'string') return first.msg
    }
  } catch {
    /* ignore */
  }
  return `請求失敗（HTTP ${res.status}）`
}

export async function uploadAudioForTranscript(
  blob: Blob,
): Promise<{ transcript: string }> {
  const fd = new FormData()
  const ext =
    blob.type.includes('webm') || blob.type.includes('opus')
      ? 'webm'
      : blob.type.includes('wav')
        ? 'wav'
        : 'audio'
  fd.append('file', blob, `recording.${ext}`)
  const res = await fetch('/api/speech/transcribe', {
    method: 'POST',
    body: fd,
  })
  if (!res.ok) throw new Error(await parseErrorDetail(res))
  return res.json() as Promise<{ transcript: string }>
}

export type TtsEngine = 'cloud' | 'gemini'

export async function synthesizeSpeech(
  text: string,
  opts?: { ttsEngine?: TtsEngine },
): Promise<Blob> {
  const tts_engine = opts?.ttsEngine ?? 'cloud'
  const res = await fetch('/api/speech/synthesize', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, tts_engine }),
  })
  if (!res.ok) throw new Error(await parseErrorDetail(res))
  const blob = await res.blob()
  if (!blob.size) throw new Error('語音合成未回傳音訊。')
  return blob
}

function decodeBase64ToArrayBuffer(b64: string): ArrayBuffer {
  const bin = atob(b64)
  const out = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i)
  return out.buffer
}

function parseGeminiTtsSseBlock(
  block: string,
  onPcm: (pcm: ArrayBuffer) => void,
): void {
  if (!block.trim()) return
  let eventType: string | null = null
  let dataLine: string | null = null
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) eventType = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLine = line.slice(5).trimStart()
  }
  if (!eventType || dataLine == null) return
  const data = JSON.parse(dataLine) as Record<string, unknown>
  if (eventType === 'pcm') {
    const b64 = data.pcm_b64
    if (typeof b64 !== 'string' || !b64) return
    const buf = decodeBase64ToArrayBuffer(b64)
    if (buf.byteLength > 0) onPcm(buf)
    return
  }
  if (eventType === 'done') return
  if (eventType === 'error') {
    const m =
      typeof data.message === 'string'
        ? data.message
        : '語音合成失敗。'
    throw new Error(m)
  }
}

/** Gemini only: SSE with `pcm` / `done` / `error` events. */
export async function synthesizeGeminiSpeechStream(
  text: string,
  handlers: { onPcm: (pcm: ArrayBuffer) => void; signal?: AbortSignal },
): Promise<void> {
  const res = await fetch('/api/speech/synthesize-stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify({ text, tts_engine: 'gemini' }),
    signal: handlers.signal,
  })
  if (!res.ok) throw new Error(await parseErrorDetail(res))
  const reader = res.body?.getReader()
  if (!reader) throw new Error('No response body')

  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split('\n\n')
      buffer = parts.pop() ?? ''
      for (const part of parts) {
        parseGeminiTtsSseBlock(part, handlers.onPcm)
      }
    }
    buffer += decoder.decode()
    if (buffer.trim()) parseGeminiTtsSseBlock(buffer, handlers.onPcm)
  } catch (e) {
    if (
      handlers.signal?.aborted ||
      (e instanceof DOMException && e.name === 'AbortError')
    ) {
      await reader.cancel().catch(() => {})
      throw e instanceof Error ? e : new DOMException('Aborted', 'AbortError')
    }
    throw e
  }
}
