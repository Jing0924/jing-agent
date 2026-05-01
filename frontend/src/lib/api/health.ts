export type HealthPayload = {
  status: string
  ready: boolean
  error: string | null
  embedding_fingerprint?: string
  prompt_sha256?: string
  llm_model?: string
  speech_enabled?: boolean
}

export async function fetchHealth(): Promise<HealthPayload> {
  const res = await fetch('/api/health')
  if (!res.ok) throw new Error('Health check failed')
  return res.json() as Promise<HealthPayload>
}
