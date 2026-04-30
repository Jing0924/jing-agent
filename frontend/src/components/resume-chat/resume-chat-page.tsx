import type { FormEvent, MouseEvent } from 'react'
import { useState } from 'react'

import { AlertTriangle, CheckCircle2 } from 'lucide-react'

import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { AnswerMarkdown } from '@/components/markdown/answer-markdown'
import { useAskStream } from '@/hooks/use-ask-stream'
import { useCalendarStatus } from '@/hooks/use-calendar-status'
import { useHealth } from '@/hooks/use-health'
import { createCalendarEventFromText, type CalendarEventCreatedPayload } from '@/lib/api/calendar'
import { cn } from '@/lib/utils'

function ResumeChatPage() {
  const { data: health, isError, isFetching, refetch } = useHealth()
  const {
    data: calStatus,
    isFetching: calStatusFetching,
    refetch: refetchCalStatus,
  } = useCalendarStatus()
  const healthError = isError
    ? '無法連線至後端（確認已執行 uvicorn 於 127.0.0.1:8000）。'
    : null
  const {
    question,
    setQuestion,
    answer,
    loading,
    error,
    handleSubmit,
  } = useAskStream(health)

  const ready = health?.ready === true
  const calendarReady = calStatus?.configured === true

  const [calendarText, setCalendarText] = useState('')
  const [calendarLoading, setCalendarLoading] = useState(false)
  const [calendarError, setCalendarError] = useState<string | null>(null)
  const [calendarCreated, setCalendarCreated] =
    useState<CalendarEventCreatedPayload | null>(null)

  function onRefreshHealth(e: MouseEvent<HTMLButtonElement>) {
    e.preventDefault()
    void refetch()
    void refetchCalStatus()
  }

  async function handleCalendarSubmit(ev: FormEvent<HTMLFormElement>) {
    ev.preventDefault()
    setCalendarError(null)
    const t = calendarText.trim()
    if (!t || !calendarReady) return
    setCalendarLoading(true)
    setCalendarCreated(null)
    try {
      const created = await createCalendarEventFromText(t)
      setCalendarCreated(created)
      setCalendarText('')
    } catch (err) {
      setCalendarError(err instanceof Error ? err.message : '無法建立行程')
    } finally {
      setCalendarLoading(false)
    }
  }

  return (
    <main className="flex w-full max-w-2xl flex-1 flex-col gap-8 self-center px-6 py-8 text-left">
      <header className="space-y-3">
        <h1 className="brand-heading-gradient font-heading text-3xl font-medium tracking-tight md:text-4xl">
          Jing Memoir
        </h1>
        <p className="text-[0.95rem] text-muted-foreground">
          以經歷與備忘為本，透過後端 RAG 檢索回答關於履歷與經驗的問題。
        </p>
        {health && (
          <p
            className={cn(
              'flex items-start gap-2 rounded-md border px-3 py-2 text-sm leading-snug',
              ready
                ? 'border-primary/50 bg-primary/10 text-card-foreground'
                : 'border-amber-500/35 bg-amber-500/10 text-card-foreground',
            )}
            role="status"
          >
            {ready ? (
              <CheckCircle2
                className="mt-0.5 size-4 shrink-0 text-primary"
                aria-hidden
              />
            ) : (
              <AlertTriangle
                className="mt-0.5 size-4 shrink-0 text-amber-600 opacity-95"
                aria-hidden
              />
            )}
            <span>
              {ready ? '服務就緒' : '服務未就緒'}
              {!ready && health.error ? `：${health.error}` : null}
            </span>
          </p>
        )}
        {healthError && (
          <Alert variant="destructive">
            <AlertTitle>連線錯誤</AlertTitle>
            <AlertDescription>{healthError}</AlertDescription>
          </Alert>
        )}
      </header>

      <section
        className="flex flex-col gap-2"
        aria-labelledby="calendar-heading"
      >
        <h2
          id="calendar-heading"
          className="font-heading text-base font-medium text-card-foreground"
        >
          行程（自然語言）
        </h2>
        <p className="text-sm text-muted-foreground">
          {calStatusFetching && !calStatus
            ? '正在檢查 Google 行事曆設定…'
            : calendarReady
              ? '描述時間與內容，後端會用 Gemini 解析並寫入你的 Google 行事曆（primary）。'
              : '尚未連結 Google 行事曆：請在 Google Cloud 啟用 Calendar API、建立 OAuth 桌面應用程式憑證，執行 backend/scripts/oauth_google_calendar.py 取得 refresh token，並寫入 .env。'}
        </p>
        <form className="flex flex-col gap-2" onSubmit={handleCalendarSubmit}>
          <label className="text-sm font-medium text-card-foreground" htmlFor="cal-text">
            行程描述
          </label>
          <Textarea
            id="cal-text"
            rows={2}
            value={calendarText}
            onChange={(e) => setCalendarText(e.target.value)}
            placeholder="例如：明天下午1點在朵頤牛排吃飯"
            disabled={calendarLoading || !calendarReady}
            className="min-h-[3.5rem] text-base md:text-sm"
          />
          <Button
            type="submit"
            disabled={calendarLoading || !calendarReady}
            size="lg"
          >
            {calendarLoading ? '建立中…' : '建立行程'}
          </Button>
        </form>
        {calendarError && (
          <Alert variant="destructive">
            <AlertTitle>行事曆</AlertTitle>
            <AlertDescription>{calendarError}</AlertDescription>
          </Alert>
        )}
        {calendarCreated && (
          <p className="text-sm text-card-foreground" role="status">
            已建立「{calendarCreated.summary}」。
            {calendarCreated.htmlLink ? (
              <>
                {' '}
                <a
                  href={calendarCreated.htmlLink}
                  target="_blank"
                  rel="noreferrer"
                  className="text-primary underline underline-offset-2"
                >
                  在 Google 行事曆開啟
                </a>
              </>
            ) : null}
          </p>
        )}
      </section>

      <section
        className="flex flex-col gap-2"
        aria-labelledby="question-heading"
      >
        <h2 id="question-heading" className="sr-only">
          提問
        </h2>
        <form className="flex flex-col gap-2" onSubmit={handleSubmit}>
          <label className="text-sm font-medium text-card-foreground" htmlFor="q">
            問題
          </label>
          <Textarea
            id="q"
            rows={3}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="例如：請簡述最近一份工作的重點成果"
            disabled={loading || !ready}
            className="min-h-[4.5rem] text-base md:text-sm"
          />
          <div className="mt-1 flex flex-wrap gap-2">
            <Button type="submit" disabled={loading || !ready} size="lg">
              {loading ? '處理中…' : '送出'}
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={isFetching || calStatusFetching}
              size="lg"
              onClick={onRefreshHealth}
            >
              {isFetching || calStatusFetching ? '檢查中…' : '重新檢查服務'}
            </Button>
          </div>
        </form>
      </section>

      {error && (
        <Alert variant="destructive">
          <AlertTitle>發生錯誤</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {(answer || loading) && (
        <section aria-labelledby="answer-heading">
          <Card className="border-border bg-muted/40">
            <CardHeader className="pb-2">
              <h2
                id="answer-heading"
                className="font-heading text-base leading-snug font-medium"
              >
                回答
              </h2>
            </CardHeader>
            <CardContent className="pt-0">
              <div
                aria-live="polite"
                className="min-h-[4.75rem]"
              >
                {!answer && loading ? (
                  <p className="text-sm text-muted-foreground">
                    產生中，請稍候…
                  </p>
                ) : (
                  <AnswerMarkdown content={answer} />
                )}
              </div>
            </CardContent>
          </Card>
        </section>
      )}
    </main>
  )
}

export { ResumeChatPage }
