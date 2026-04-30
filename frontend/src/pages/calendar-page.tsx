import type { FormEvent, KeyboardEvent, MouseEvent } from 'react'
import { useEffect, useRef, useState } from 'react'

import { useQueryClient } from '@tanstack/react-query'

import { AlertTriangle, CheckCircle2, MapPin } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { useCalendarEvents } from '@/hooks/use-calendar-events'
import { useCalendarStatus } from '@/hooks/use-calendar-status'
import { useHealth } from '@/hooks/use-health'
import {
  CalendarApiError,
  CALENDAR_EVENTS_QUERY_KEY,
  submitCalendarFromText,
  type CalendarFromTextPayload,
} from '@/lib/api/calendar'
import { formatCalendarInstant } from '@/lib/format-calendar'
import { cn } from '@/lib/utils'

const EXAMPLES = [
  '明天下午1點在朵頤牛排吃飯',
  '刪掉明天下午的朵頤',
  '下週五早上10點線上開會30分鐘',
] as const

function calendarErrorTitle(status: number): string {
  if (status === 409) return '找到多筆符合行程'
  if (status === 503) return '服務尚未就緒'
  if (status === 400) return '請求無法處理'
  if (status === 502) return 'Google 連線異常'
  return '行事曆'
}

function CalendarPage() {
  const queryClient = useQueryClient()
  const { data: health, isError, isFetching, refetch } = useHealth()
  const {
    data: calStatus,
    isFetching: calStatusFetching,
    refetch: refetchCalStatus,
  } = useCalendarStatus()
  const {
    data: upcoming,
    error: upcomingError,
    isFetching: upcomingFetching,
    refetch: refetchUpcoming,
  } = useCalendarEvents(calStatus?.configured === true)

  const healthError = isError
    ? '無法連線至後端（確認已執行 uvicorn 於 127.0.0.1:8000）。'
    : null

  const ready = health?.ready === true
  const calendarReady = calStatus?.configured === true
  const timezoneLabel = calStatus?.default_timezone ?? '—'

  const [calendarText, setCalendarText] = useState('')
  const [calendarLoading, setCalendarLoading] = useState(false)
  const [calendarError, setCalendarError] = useState<{ msg: string; status: number } | null>(
    null,
  )
  const [calendarLastOk, setCalendarLastOk] = useState<CalendarFromTextPayload | null>(null)
  const resultRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (calendarLastOk) resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [calendarLastOk])

  function onRefreshHealth(e: MouseEvent<HTMLButtonElement>) {
    e.preventDefault()
    void refetch()
    void refetchCalStatus()
    void refetchUpcoming()
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
      void queryClient.invalidateQueries({ queryKey: CALENDAR_EVENTS_QUERY_KEY })
    } catch (err) {
      if (err instanceof CalendarApiError) {
        setCalendarError({ msg: err.message, status: err.status })
      } else {
        setCalendarError({
          msg: err instanceof Error ? err.message : '無法處理事曆請求',
          status: 0,
        })
      }
    } finally {
      setCalendarLoading(false)
    }
  }

  function onCalTextKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key !== 'Enter' || !(e.metaKey || e.ctrlKey)) return
    e.preventDefault()
    if (calendarLoading || !calendarReady) return
    const form = e.currentTarget.form
    if (form) form.requestSubmit()
  }

  const err409 = calendarError?.status === 409

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
        {calStatus && (
          <p className="text-xs text-muted-foreground" role="status">
            解析與列表顯示時區：{timezoneLabel}
          </p>
        )}
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
            <AlertDescription className="whitespace-pre-wrap">{healthError}</AlertDescription>
          </Alert>
        )}
      </header>

      {calendarReady ? (
        <section
          className="flex flex-col gap-2 border-b border-border/60 pb-4"
          aria-labelledby="calendar-upcoming-heading"
        >
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2
              id="calendar-upcoming-heading"
              className="font-heading text-base font-medium text-card-foreground"
            >
              未來七天（primary）
            </h2>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-8 shrink-0 text-muted-foreground"
              disabled={upcomingFetching}
              onClick={() => void refetchUpcoming()}
            >
              {upcomingFetching ? '更新中…' : '重新整理'}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            刪除前可對照標題與時間；資料來自 Google，與 NLP 時區設定一致。
          </p>
          {upcomingError && (
            <p className="text-sm text-destructive">
              {upcomingError instanceof Error ? upcomingError.message : '無法載入行程'}
            </p>
          )}
          {!upcomingFetching && upcoming && upcoming.events.length === 0 ? (
            <p className="text-sm text-muted-foreground">此區間尚無行程。</p>
          ) : null}
          {upcoming && upcoming.events.length > 0 ? (
            <ul className="max-h-[min(22rem,50vh)] space-y-1.5 overflow-y-auto text-sm">
              {upcoming.events.map((row) => (
                <li
                  key={row.id || `${row.summary}-${row.start}`}
                  className="rounded-md border border-border/70 bg-muted/25 px-2.5 py-1.5"
                >
                  <div className="font-medium text-card-foreground">{row.summary}</div>
                  <div
                    className="text-xs text-muted-foreground"
                    title={`${row.start} — ${row.end}`}
                  >
                    {formatCalendarInstant(row.start, upcoming.timezone)}
                    {' — '}
                    {formatCalendarInstant(row.end, upcoming.timezone)}
                  </div>
                  {row.location?.trim() ? (
                    <div className="mt-0.5 flex items-start gap-1 text-xs text-muted-foreground">
                      <MapPin
                        className="mt-0.5 size-3 shrink-0 opacity-90"
                        aria-hidden
                      />
                      <span className="min-w-0 break-words">{row.location.trim()}</span>
                    </div>
                  ) : null}
                  {row.htmlLink ? (
                    <a
                      href={row.htmlLink}
                      target="_blank"
                      rel="noreferrer"
                      className="mt-1 inline-block text-xs text-primary underline underline-offset-2"
                    >
                      在 Google 開啟
                    </a>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}

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
            onFocus={() => setCalendarLastOk(null)}
            onKeyDown={onCalTextKeyDown}
            placeholder="建立：明天下午1點在朵頤牛排吃飯；刪除：刪掉明天下午的朵頤（⌘/Ctrl+Enter 送出）"
            disabled={calendarLoading || !calendarReady}
            className="min-h-[3.5rem] text-base md:text-sm"
          />
          <div className="flex flex-wrap gap-1.5" aria-label="範例（點擊填入）">
            {EXAMPLES.map((sample) => (
              <Button
                key={sample}
                type="button"
                variant="outline"
                size="sm"
                className="h-7 max-w-full rounded-full px-2.5 text-xs font-normal text-muted-foreground"
                title={sample}
                disabled={calendarLoading || !calendarReady}
                onClick={() => setCalendarText(sample)}
              >
                {sample.length > 20 ? `${sample.slice(0, 20)}…` : sample}
              </Button>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={calendarLoading || !calendarReady} size="lg">
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
          <Alert
            variant={err409 ? 'default' : 'destructive'}
            className={
              err409 ? 'border-amber-500/40 bg-amber-500/[0.07] [&_[data-slot=alert-description]]:text-card-foreground' : undefined
            }
          >
            <AlertTitle>{calendarErrorTitle(calendarError.status)}</AlertTitle>
            <AlertDescription className={cn(err409 ? 'text-pretty text-card-foreground/90' : '', 'whitespace-pre-wrap')}>
              {calendarError.msg}
            </AlertDescription>
          </Alert>
        )}
        <div ref={resultRef}>
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
            <p
              className="text-sm text-card-foreground"
              role="status"
              title={`${calendarLastOk.start} — ${calendarLastOk.end}`}
            >
              已刪除「{calendarLastOk.summary}」（
              {formatCalendarInstant(
                calendarLastOk.start,
                calStatus?.default_timezone ?? 'UTC',
              )}{' '}
              —{' '}
              {formatCalendarInstant(calendarLastOk.end, calStatus?.default_timezone ?? 'UTC')}
              ）。
            </p>
          )}
        </div>
      </section>
    </>
  )
}

export { CalendarPage }
