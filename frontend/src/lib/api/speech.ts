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

export async function synthesizeSpeech(text: string): Promise<Blob> {
  const res = await fetch('/api/speech/synthesize', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
  if (!res.ok) throw new Error(await parseErrorDetail(res))
  const blob = await res.blob()
  if (!blob.size) throw new Error('語音合成未回傳音訊。')
  return blob
}
