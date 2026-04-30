import type { MouseEvent } from 'react'

import { AlertTriangle, CheckCircle2 } from 'lucide-react'

import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { AnswerMarkdown } from '@/components/markdown/answer-markdown'
import { useAskStream } from '@/hooks/use-ask-stream'
import { useHealth } from '@/hooks/use-health'
import { cn } from '@/lib/utils'

function KnowledgeChatPage() {
  const { data: health, isError, isFetching, refetch } = useHealth()
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

  function onRefreshHealth(e: MouseEvent<HTMLButtonElement>) {
    e.preventDefault()
    void refetch()
  }

  return (
    <>
      <header className="space-y-3">
        <h1 className="brand-heading-gradient font-heading text-3xl font-medium tracking-tight md:text-4xl">
          知識庫問答
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
              disabled={isFetching}
              size="lg"
              onClick={onRefreshHealth}
            >
              {isFetching ? '檢查中…' : '重新檢查服務'}
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
              <div aria-live="polite" className="min-h-[4.75rem]">
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
    </>
  )
}

export { KnowledgeChatPage }
