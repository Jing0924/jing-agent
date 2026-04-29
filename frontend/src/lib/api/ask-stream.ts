function errorMessageFromResponse(res: Response, errText: string): string {
  let msg = `Request failed (${res.status})`
  try {
    const j = JSON.parse(errText) as { detail?: unknown }
    const d = j.detail
    if (typeof d === 'string') msg = d
  } catch {
    if (errText) msg = errText.slice(0, 200)
  }
  return msg
}

async function fetchAskJson(question: string): Promise<string> {
  const res = await fetch('/api/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
  const errText = await res.text().catch(() => '')
  if (!res.ok) {
    throw new Error(errorMessageFromResponse(res, errText))
  }
  try {
    const j = JSON.parse(errText) as { answer?: unknown }
    const a = j.answer
    return typeof a === 'string' ? a : a == null ? '' : String(a)
  } catch {
    throw new Error('Invalid JSON from /api/ask')
  }
}

function parseSseBlock(
  block: string,
  onMeta: (m: Record<string, unknown>) => void,
  onToken: (text: string) => void,
): void {
  if (!block.trim()) return
  let eventType: string | null = null
  let dataLine: string | null = null
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) eventType = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLine = line.slice(5).trimStart()
  }
  if (dataLine == null) return
  const data = JSON.parse(dataLine) as Record<string, unknown>
  if (eventType === 'meta') onMeta(data)
  else if (eventType === 'token' && typeof data.text === 'string') onToken(data.text)
  else if (eventType === 'error') {
    const m = typeof data.message === 'string' ? data.message : 'Stream error'
    throw new Error(m)
  }
}

export type AskStreamOptions = {
  healthPromptSha256?: string | null
  healthEmbeddingFingerprint?: string | null
}

export async function consumeAskStream(
  question: string,
  onMeta: (m: Record<string, unknown>) => void,
  onToken: (text: string) => void,
  options?: AskStreamOptions,
): Promise<void> {
  const res = await fetch('/api/ask/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
  if (res.status === 404) {
    const answer = await fetchAskJson(question)
    onMeta({
      embeddingFingerprint: options?.healthEmbeddingFingerprint ?? null,
      promptSha256: options?.healthPromptSha256 ?? null,
    })
    onToken(answer)
    return
  }
  if (!res.ok) {
    const errText = await res.text().catch(() => '')
    throw new Error(errorMessageFromResponse(res, errText))
  }
  const reader = res.body?.getReader()
  if (!reader) throw new Error('No response body')
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''
    for (const block of parts) {
      parseSseBlock(block, onMeta, onToken)
    }
  }
  buffer += decoder.decode()
  if (buffer.trim()) parseSseBlock(buffer, onMeta, onToken)
}
