import type { MouseEvent } from 'react'
import { useCallback, useEffect, useRef, useState } from 'react'

import { AlertTriangle, CheckCircle2, Mic, Square, Volume2 } from 'lucide-react'

import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { AnswerMarkdown } from '@/components/markdown/answer-markdown'
import { useAskStream } from '@/hooks/use-ask-stream'
import { useHealth } from '@/hooks/use-health'
import { useVoiceInput } from '@/hooks/use-voice-input'
import { uploadAudioForTranscript, synthesizeSpeech } from '@/lib/api/speech'
import { cn } from '@/lib/utils'

const INTERVIEW_QUICK_QUESTIONS = [
  '請用一小段話自我介紹（背景與目前狀態）。',
  '最近一份工作／現職主要職責與成果？',
  '印象最深或最有代表性的專案？',
  '熟悉的技術、工具或證照？',
  '學歷與相關訓練？',
] as const

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
    askWithText,
  } = useAskStream(health)

  const ready = health?.ready === true
  const speechUsable = ready && health?.speech_enabled === true

  const voiceInput = useVoiceInput()
  const [voiceBusy, setVoiceBusy] = useState(false)
  const [voiceError, setVoiceError] = useState<string | null>(null)
  const [ttsBusy, setTtsBusy] = useState(false)
  const [ttsPlaying, setTtsPlaying] = useState(false)
  const [ttsError, setTtsError] = useState<string | null>(null)
  const ttsUrlRef = useRef<string | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  const stopTts = useCallback(() => {
    const a = audioRef.current
    if (a) {
      a.pause()
      audioRef.current = null
    }
    if (ttsUrlRef.current) {
      URL.revokeObjectURL(ttsUrlRef.current)
      ttsUrlRef.current = null
    }
    setTtsPlaying(false)
  }, [])

  useEffect(() => {
    return () => {
      const a = audioRef.current
      if (a) a.pause()
      if (ttsUrlRef.current) URL.revokeObjectURL(ttsUrlRef.current)
    }
  }, [])

  useEffect(() => {
    stopTts()
    setTtsError(null)
  }, [answer, stopTts])

  const onMicClick = async () => {
    if (!speechUsable || voiceBusy || loading) return
    setVoiceError(null)
    if (voiceInput.isRecording) {
      setVoiceBusy(true)
      try {
        const blob = await voiceInput.stopRecording()
        if (blob && blob.size > 0) {
          const { transcript } = await uploadAudioForTranscript(blob)
          setQuestion(transcript.trim())
        }
      } catch (e) {
        setVoiceError(e instanceof Error ? e.message : '語音轉文字失敗。')
      } finally {
        setVoiceBusy(false)
      }
    } else {
      setVoiceBusy(true)
      try {
        await voiceInput.startRecording()
      } finally {
        setVoiceBusy(false)
      }
    }
  }

  const onReadAloudClick = async () => {
    if (!speechUsable || !answer.trim() || loading) return
    setTtsError(null)
    if (ttsPlaying || (audioRef.current && !audioRef.current.paused)) {
      stopTts()
      return
    }
    setTtsBusy(true)
    try {
      const mp3 = await synthesizeSpeech(answer)
      stopTts()
      const url = URL.createObjectURL(mp3)
      ttsUrlRef.current = url
      const audio = new Audio(url)
      audioRef.current = audio
      audio.onended = () => {
        setTtsPlaying(false)
        stopTts()
      }
      audio.onerror = () => {
        setTtsError('無法播放語音。')
        stopTts()
      }
      setTtsPlaying(true)
      await audio.play()
    } catch (e) {
      setTtsError(e instanceof Error ? e.message : '語音合成失敗。')
    } finally {
      setTtsBusy(false)
    }
  }

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
              {ready && health.speech_enabled !== true ? (
                <span className="mt-1 block text-xs font-normal text-muted-foreground">
                  後端未設定 GOOGLE_CLOUD_API_KEY 時，語音輸入與朗讀不可用。
                </span>
              ) : null}
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
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <Button type="submit" disabled={loading || !ready} size="lg">
              {loading ? '處理中…' : '送出'}
            </Button>
            {speechUsable ? (
              <Button
                type="button"
                variant={voiceInput.isRecording ? 'secondary' : 'outline'}
                size="lg"
                disabled={loading || voiceBusy}
                aria-label={
                  voiceInput.isRecording ? '停止錄音並轉成文字' : '開始語音輸入'
                }
                aria-pressed={voiceInput.isRecording}
                onClick={() => void onMicClick()}
                className="gap-2"
              >
                {voiceInput.isRecording ? (
                  <Square className="size-4" aria-hidden />
                ) : (
                  <Mic className="size-4" aria-hidden />
                )}
                {voiceBusy
                  ? voiceInput.isRecording
                    ? '辨識中…'
                    : '啟動中…'
                  : voiceInput.isRecording
                    ? '停止'
                    : '語音輸入'}
              </Button>
            ) : null}
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
          {speechUsable ? (
            <p className="text-xs text-muted-foreground">
              語音輸入建議使用 Chrome／Edge（WebM
              Opus）。Safari 錄音格式可能無法辨識。
            </p>
          ) : null}
        </form>
        {voiceInput.error ? (
          <p className="text-sm text-destructive" role="alert">
            {voiceInput.error}
          </p>
        ) : null}
        {voiceError ? (
          <p className="text-sm text-destructive" role="alert">
            {voiceError}
          </p>
        ) : null}
      </section>

      <section
        className="space-y-2"
        aria-labelledby="interview-quick-heading"
      >
        <div>
          <h2
            id="interview-quick-heading"
            className="font-heading text-base font-medium text-card-foreground"
          >
            常見問題
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            點一下即送出；回答僅依知識庫內容，未收錄的項目會如實說明。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {INTERVIEW_QUICK_QUESTIONS.map((qPreset) => (
            <Button
              key={qPreset}
              type="button"
              variant="outline"
              size="sm"
              className="h-auto max-w-full shrink-0 whitespace-normal py-2 text-left text-sm leading-snug"
              disabled={loading || !ready}
              aria-label={qPreset}
              onClick={() => askWithText(qPreset)}
            >
              {qPreset}
            </Button>
          ))}
        </div>
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
              <div className="flex flex-wrap items-start justify-between gap-2">
                <h2
                  id="answer-heading"
                  className="font-heading text-base leading-snug font-medium"
                >
                  回答
                </h2>
                {speechUsable && answer && !loading ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={ttsBusy}
                    aria-label={ttsPlaying ? '停止朗讀' : '朗讀回答'}
                    aria-pressed={ttsPlaying}
                    onClick={() => void onReadAloudClick()}
                    className="shrink-0 gap-1.5"
                  >
                    <Volume2 className="size-3.5" aria-hidden />
                    {ttsBusy ? '合成中…' : ttsPlaying ? '停止' : '朗讀'}
                  </Button>
                ) : null}
              </div>
            </CardHeader>
            <CardContent className="pt-0">
              {ttsError ? (
                <p className="mb-2 text-sm text-destructive" role="alert">
                  {ttsError}
                </p>
              ) : null}
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
