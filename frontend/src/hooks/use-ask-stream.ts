import { useCallback, useState } from 'react'
import type { FormEvent } from 'react'

import type { HealthPayload } from '@/lib/api/health'
import { consumeAskStream } from '@/lib/api/ask-stream'

export type StreamMeta = {
  embeddingFingerprint: string | null
  promptSha256: string | null
}

export function useAskStream(health: HealthPayload | undefined) {
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [streamMeta, setStreamMeta] = useState<StreamMeta | null>(null)

  const handleSubmit = useCallback(
    async (e: FormEvent) => {
      e.preventDefault()
      setError(null)
      setAnswer('')
      setStreamMeta(null)
      setLoading(true)
      try {
        let acc = ''
        await consumeAskStream(
          question,
          (meta) => {
            const ef =
              typeof meta.embeddingFingerprint === 'string'
                ? meta.embeddingFingerprint
                : null
            const ps =
              typeof meta.promptSha256 === 'string' ? meta.promptSha256 : null
            setStreamMeta({ embeddingFingerprint: ef, promptSha256: ps })
          },
          (text) => {
            acc += text
            setAnswer(acc)
          },
          {
            healthPromptSha256: health?.prompt_sha256,
            healthEmbeddingFingerprint: health?.embedding_fingerprint,
          },
        )
      } catch (err) {
        setError(err instanceof Error ? err.message : '網路錯誤，請稍後再試。')
      } finally {
        setLoading(false)
      }
    },
    [question, health],
  )

  return {
    question,
    setQuestion,
    answer,
    loading,
    error,
    streamMeta,
    handleSubmit,
  }
}
