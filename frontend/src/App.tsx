import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'

type HealthPayload = {
  status: string
  ready: boolean
  error: string | null
}

async function fetchHealth(): Promise<HealthPayload> {
  const res = await fetch('/api/health')
  if (!res.ok) throw new Error('Health check failed')
  return res.json() as Promise<HealthPayload>
}

function App() {
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [health, setHealth] = useState<HealthPayload | null>(null)
  const [healthError, setHealthError] = useState<string | null>(null)

  const refreshHealth = useCallback(async () => {
    setHealthError(null)
    try {
      setHealth(await fetchHealth())
    } catch {
      setHealthError('無法連線至後端（確認已執行 uvicorn 於 127.0.0.1:8000）。')
      setHealth(null)
    }
  }, [])

  useEffect(() => {
    void refreshHealth()
  }, [refreshHealth])

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setAnswer('')
    setLoading(true)
    try {
      const res = await fetch('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      })
      const data: unknown = await res.json().catch(() => ({}))
      if (!res.ok) {
        let msg = `Request failed (${res.status})`
        if (typeof data === 'object' && data !== null && 'detail' in data) {
          const d = (data as { detail: unknown }).detail
          if (typeof d === 'string') msg = d
          else if (Array.isArray(d) && d[0]?.msg) msg = String(d[0].msg)
        }
        setError(msg)
        return
      }
      const answerText =
        typeof data === 'object' &&
        data !== null &&
        'answer' in data &&
        typeof (data as { answer: unknown }).answer === 'string'
          ? (data as { answer: string }).answer
          : ''
      setAnswer(answerText)
    } catch {
      setError('網路錯誤，請稍後再試。')
    } finally {
      setLoading(false)
    }
  }

  const ready = health?.ready === true

  return (
    <main className="resume-chat">
      <header className="resume-chat__header">
        <h1>履歷問答</h1>
        <p className="resume-chat__subtitle">
          透過後端 RAG 檢索回答關於履歷的問題。
        </p>
        {health && (
          <p
            className={
              ready ? 'resume-chat__badge resume-chat__badge--ok' : 'resume-chat__badge resume-chat__badge--warn'
            }
            role="status"
          >
            {ready ? '服務就緒' : '服務未就緒'}
            {!ready && health.error ? `：${health.error}` : null}
          </p>
        )}
        {healthError && (
          <p className="resume-chat__badge resume-chat__badge--warn" role="alert">
            {healthError}
          </p>
        )}
      </header>

      <form className="resume-chat__form" onSubmit={onSubmit}>
        <label className="resume-chat__label" htmlFor="q">
          問題
        </label>
        <textarea
          id="q"
          className="resume-chat__input"
          rows={3}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="例如：請簡述最近一份工作的重點成果"
          disabled={loading || !ready}
        />
        <div className="resume-chat__actions">
          <button type="submit" disabled={loading || !ready}>
            {loading ? '處理中…' : '送出'}
          </button>
          <button type="button" className="secondary" onClick={() => void refreshHealth()}>
            重新檢查服務
          </button>
        </div>
      </form>

      {error && (
        <div className="resume-chat__panel resume-chat__panel--error" role="alert">
          {error}
        </div>
      )}

      {(answer || loading) && (
        <section className="resume-chat__panel" aria-live="polite">
          <h2>回答</h2>
          {loading ? <p className="resume-chat__muted">產生中…</p> : <p className="resume-chat__answer">{answer}</p>}
        </section>
      )}
    </main>
  )
}

export default App
