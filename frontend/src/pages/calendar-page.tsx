import type { FormEvent, MouseEvent } from 'react'
import { useState } from 'react'

import { AlertTriangle, CheckCircle2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { useCalendarStatus } from '@/hooks/use-calendar-status'
import { useHealth } from '@/hooks/use-health'
import {
  submitCalendarFromText,
  type CalendarFromTextPayload,
} from '@/lib/api/calendar'
import { cn } from '@/lib/utils'

function CalendarPage() {
  const { data: health, isError, isFetching, refetch } = useHealth()
  const {
    data: calStatus,
    isFetching: calStatusFetching,
    refetch: refetchCalStatus,
  } = useCalendarStatus()
  const healthError = isError
    ? '無法連線至後端（確認已執行 uvicorn 於 127.0.0.1:8000）。'
    : null

  const ready = health?.ready === true
  const calendarReady = calStatus?.configured === true

  const [calendarText, setCalendarText] = useState('')
  const [calendarLoading, setCalendarLoading] = useState(false)
  const [calendarError, setCalendarError] = useState<string | null>(null)
  const [calendarLastOk, setCalendarLastOk] = useState<CalendarFromTextPayload | null>(null)

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
    setCalendarLastOk(null)
    try {
      const out = await submitCalendarFromText(t)
      setCalendarLastOk(out)
      setCalendarText('')
    } catch (err) {
      setCalendarError(err instanceof Error ? err.message : '無法處理事曆請求')
    } finally {
      setCalendarLoading(false)
    }
  }

  return (
    <>
      <header className="space-y-3">
        <h1 className="brand-heading-gradient font-heading text-3xl font-medium tracking-tight md:text-4xl">
          Google 行事曆
        </h1>
        <p className="text-[0.95rem] text-muted-foreground">
          用自然語言描述行程或刪除意圖（例如「刪掉明天下午的朵頤」），後端會解析並套用到你的
          primary 行事曆。
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
              ? '描述建立或刪除（取消／拿掉等）說法，後端會用 Gemini 解析並寫入或刪除 Google 行事曆（primary）中的符合行程。'
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
            placeholder="建立：明天下午1點在朵頤牛排吃飯；刪除：刪掉明天下午的朵頤"
            disabled={calendarLoading || !calendarReady}
            className="min-h-[3.5rem] text-base md:text-sm"
          />
          <div className="flex flex-wrap gap-2">
            <Button
              type="submit"
              disabled={calendarLoading || !calendarReady}
              size="lg"
            >
              {calendarLoading ? '處理中…' : '送出'}
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
        {calendarError && (
          <Alert variant="destructive">
            <AlertTitle>行事曆</AlertTitle>
            <AlertDescription>{calendarError}</AlertDescription>
          </Alert>
        )}
        {calendarLastOk?.result === 'created' && (
          <p className="text-sm text-card-foreground" role="status">
            已建立「{calendarLastOk.summary}」。
            {calendarLastOk.htmlLink ? (
              <>
                {' '}
                <a
                  href={calendarLastOk.htmlLink}
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
        {calendarLastOk?.result === 'deleted' && (
          <p className="text-sm text-card-foreground" role="status">
            已刪除「{calendarLastOk.summary}」（{calendarLastOk.start} — {calendarLastOk.end}
            ）。
          </p>
        )}
      </section>
    </>
  )
}

export { CalendarPage }
