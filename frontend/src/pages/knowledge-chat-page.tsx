import type { FormEvent, MouseEvent } from 'react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import {
  AlertTriangle,
  CheckCircle2,
  MessageCircle,
  Mic,
  Square,
  Volume2,
} from 'lucide-react'

import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { AnswerMarkdown } from '@/components/markdown/answer-markdown'
import { useAskStream } from '@/hooks/use-ask-stream'
import { useHealth } from '@/hooks/use-health'
import { useVoiceInput } from '@/hooks/use-voice-input'
import {
  GEMINI_TTS_PCM_SAMPLE_RATE_HZ,
  synthesizeGeminiSpeechStream,
  synthesizeSpeech,
  uploadAudioForTranscript,
  type TtsEngine,
} from '@/lib/api/speech'
import { cn } from '@/lib/utils'

const VOICE_CONVERSATION_STORAGE_KEY = 'knowledge-chat-voice-conversation'
const TTS_ENGINE_STORAGE_KEY = 'knowledge-chat-tts-engine'

function readTtsEnginePref(): TtsEngine {
  try {
    const v = localStorage.getItem(TTS_ENGINE_STORAGE_KEY)
    if (v === 'gemini' || v === 'cloud') return v
  } catch {
    /* ignore */
  }
  return 'cloud'
}

function readVoiceConversationPref(): boolean {
  try {
    return localStorage.getItem(VOICE_CONVERSATION_STORAGE_KEY) === 'true'
  } catch {
    return false
  }
}

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
  const cloudTts = health?.speech_enabled === true
  const geminiTts = health?.gemini_tts_available === true
  const micUsable = ready && cloudTts
  const ttsUsable = ready && (cloudTts || geminiTts)

  const [ttsEngine, setTtsEngine] = useState<TtsEngine>(readTtsEnginePref)

  const effectiveTtsEngine = useMemo((): TtsEngine => {
    if (ttsEngine === 'cloud' && cloudTts) return 'cloud'
    if (ttsEngine === 'gemini' && geminiTts) return 'gemini'
    if (cloudTts) return 'cloud'
    if (geminiTts) return 'gemini'
    return 'cloud'
  }, [ttsEngine, cloudTts, geminiTts])

  useEffect(() => {
    if (!health || !ready) return
    setTtsEngine((prev) => {
      const prevOk =
        (prev === 'cloud' && cloudTts) || (prev === 'gemini' && geminiTts)
      if (prevOk) return prev
      if (cloudTts) return 'cloud'
      if (geminiTts) return 'gemini'
      return prev
    })
  }, [health, ready, cloudTts, geminiTts])

  const voiceInput = useVoiceInput()
  const [voiceConversationMode, setVoiceConversationMode] = useState(
    readVoiceConversationPref,
  )
  const voiceConversationModeRef = useRef(voiceConversationMode)
  const [conversationListeningActive, setConversationListeningActive] =
    useState(false)
  const conversationListeningActiveRef = useRef(false)
  const segmentLoopInFlightRef = useRef(false)
  const expectAutoTtsRef = useRef(false)
  const prevLoadingRef = useRef(false)
  const [voiceBusy, setVoiceBusy] = useState(false)
  const voiceBusyRef = useRef(false)
  const [voiceError, setVoiceError] = useState<string | null>(null)
  const [ttsBusy, setTtsBusy] = useState(false)
  const [ttsPlaying, setTtsPlaying] = useState(false)
  const [ttsError, setTtsError] = useState<string | null>(null)
  const ttsUrlRef = useRef<string | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  const geminiStreamAbortRef = useRef<AbortController | null>(null)
  const geminiCtxRef = useRef<AudioContext | null>(null)
  const geminiSourcesRef = useRef<AudioBufferSourceNode[]>([])
  const geminiNextScheduleRef = useRef(0)
  const geminiPlaybackPendingRef = useRef(0)
  const geminiStreamDoneRef = useRef(false)

  const getGeminiAudioContext = useCallback(() => {
    if (!geminiCtxRef.current) {
      try {
        geminiCtxRef.current = new AudioContext({
          sampleRate: GEMINI_TTS_PCM_SAMPLE_RATE_HZ,
        })
      } catch {
        geminiCtxRef.current = new AudioContext()
      }
    }
    return geminiCtxRef.current
  }, [])

  const stopTts = useCallback(() => {
    geminiStreamAbortRef.current?.abort()
    geminiStreamAbortRef.current = null
    geminiStreamDoneRef.current = false
    geminiNextScheduleRef.current = 0
    geminiPlaybackPendingRef.current = 0
    for (const s of geminiSourcesRef.current) {
      try {
        s.stop(0)
      } catch {
        /* already stopped or not started */
      }
    }
    geminiSourcesRef.current = []

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
      geminiStreamAbortRef.current?.abort()
      for (const s of geminiSourcesRef.current) {
        try {
          s.stop(0)
        } catch {
          /* ignore */
        }
      }
      geminiSourcesRef.current = []
      void geminiCtxRef.current?.close().catch(() => {})
      geminiCtxRef.current = null
      const a = audioRef.current
      if (a) a.pause()
      if (ttsUrlRef.current) URL.revokeObjectURL(ttsUrlRef.current)
    }
  }, [])

  useEffect(() => {
    stopTts()
    setTtsError(null)
  }, [answer, stopTts])

  useEffect(() => {
    voiceConversationModeRef.current = voiceConversationMode
  }, [voiceConversationMode])

  const processVoiceBlob = useCallback(
    async (blob: Blob | null) => {
      if (!blob || blob.size <= 0) return
      try {
        const { transcript } = await uploadAudioForTranscript(blob)
        const trimmed = transcript.trim()
        if (!trimmed) {
          setVoiceError('未辨識到語音內容，請再試一次。')
          return
        }
        expectAutoTtsRef.current = voiceConversationMode
        askWithText(trimmed)
      } catch (e) {
        setVoiceError(e instanceof Error ? e.message : '語音轉文字失敗。')
      }
    },
    [askWithText, voiceConversationMode],
  )

  const playAnswerTts = useCallback(
    async (text: string) => {
      if (!ttsUsable || !text.trim()) return
      setTtsError(null)
      stopTts()
      setTtsBusy(true)

      if (effectiveTtsEngine !== 'gemini') {
        try {
          const audioBlob = await synthesizeSpeech(text, {
            ttsEngine: effectiveTtsEngine,
          })
          stopTts()
          const url = URL.createObjectURL(audioBlob)
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
          await audio.play()
          setTtsPlaying(true)
        } catch (e) {
          stopTts()
          setTtsError(e instanceof Error ? e.message : '語音合成失敗。')
        } finally {
          setTtsBusy(false)
        }
        return
      }

      geminiStreamDoneRef.current = false
      const ac = new AbortController()
      geminiStreamAbortRef.current = ac
      geminiPlaybackPendingRef.current = 0

      let heardPcm = false
      try {
        const ctx = getGeminiAudioContext()
        await ctx.resume()

        geminiNextScheduleRef.current = ctx.currentTime

        await synthesizeGeminiSpeechStream(text, {
          signal: ac.signal,
          onPcm: (pcm) => {
            if (pcm.byteLength === 0) return
            if (!heardPcm) {
              heardPcm = true
              setTtsBusy(false)
              setTtsPlaying(true)
            }

            const int16 = new Int16Array(pcm)
            const frames = int16.length
            if (!frames) return

            const abuf = ctx.createBuffer(
              1,
              frames,
              GEMINI_TTS_PCM_SAMPLE_RATE_HZ,
            )
            const channel = abuf.getChannelData(0)
            for (let i = 0; i < frames; i++) channel[i] = int16[i] / 32768

            const src = ctx.createBufferSource()
            src.buffer = abuf
            src.connect(ctx.destination)

            const scheduleFrom = Math.max(
              geminiNextScheduleRef.current,
              ctx.currentTime,
            )

            geminiPlaybackPendingRef.current += 1
            try {
              src.start(scheduleFrom)
            } catch {
              geminiPlaybackPendingRef.current -= 1
              return
            }

            geminiNextScheduleRef.current = scheduleFrom + abuf.duration
            geminiSourcesRef.current.push(src)

            src.onended = () => {
              geminiPlaybackPendingRef.current -= 1
              if (
                geminiStreamDoneRef.current &&
                geminiPlaybackPendingRef.current <= 0
              ) {
                setTtsPlaying(false)
              }
            }
          },
        })

        geminiStreamDoneRef.current = true
        if (geminiPlaybackPendingRef.current <= 0 && heardPcm)
          setTtsPlaying(false)
      } catch (e) {
        const aborted =
          ac.signal.aborted ||
          (e instanceof DOMException && e.name === 'AbortError') ||
          (e instanceof Error &&
            (e.name === 'AbortError' ||
              /aborted|canceled|cancell?ed/i.test(e.message)))
        if (!aborted) {
          stopTts()
          setTtsError(
            e instanceof Error ? e.message : '語音合成失敗。',
          )
        }
      } finally {
        if (geminiStreamAbortRef.current === ac)
          geminiStreamAbortRef.current = null
        if (!heardPcm) setTtsBusy(false)
      }
    },
    [ttsUsable, effectiveTtsEngine, stopTts, getGeminiAudioContext],
  )

  useEffect(() => {
    const wasLoading = prevLoadingRef.current
    prevLoadingRef.current = loading
    if (!voiceConversationMode || !wasLoading || loading) return
    if (!expectAutoTtsRef.current) return
    expectAutoTtsRef.current = false
    if (error || !answer.trim()) return
    void playAnswerTts(answer)
  }, [
    voiceConversationMode,
    loading,
    answer,
    error,
    playAnswerTts,
  ])

  useEffect(() => {
    voiceBusyRef.current = voiceBusy
  }, [voiceBusy])

  /* eslint-disable react-hooks/exhaustive-deps -- omit isRecording and voiceBusy: they flip when startRecording/setVoiceBusy run and would cleanup this effect, cancelling the in-flight segment and looping setVoiceBusy. Guard busy via voiceBusyRef.current instead. */
  useEffect(() => {
    if (
      !conversationListeningActive ||
      !voiceConversationMode ||
      !micUsable
    ) {
      return
    }
    if (
      voiceInput.isRecording ||
      voiceBusyRef.current ||
      loading ||
      ttsBusy ||
      geminiPlaybackPendingRef.current > 0 ||
      ttsPlaying
    ) {
      return
    }
    if (segmentLoopInFlightRef.current) return

    segmentLoopInFlightRef.current = true
    let cancelled = false

    void (async () => {
      try {
        setVoiceBusy(true)
        const blob = await voiceInput.startRecording({ endOnSilence: {} })
        if (
          cancelled ||
          !conversationListeningActiveRef.current ||
          !voiceConversationModeRef.current
        ) {
          if (voiceInput.isRecording) {
            await voiceInput.stopRecording()
          }
          return
        }
        await processVoiceBlob(blob ?? null)
      } catch (e) {
        if (!cancelled) {
          setVoiceError(e instanceof Error ? e.message : '語音輸入失敗。')
          conversationListeningActiveRef.current = false
          setConversationListeningActive(false)
        }
      } finally {
        setVoiceBusy(false)
        segmentLoopInFlightRef.current = false
      }
    })()

    return () => {
      cancelled = true
    }
  }, [
    conversationListeningActive,
    voiceConversationMode,
    micUsable,
    loading,
    ttsBusy,
    ttsPlaying,
    voiceInput.startRecording,
    voiceInput.stopRecording,
    processVoiceBlob,
  ])
  /* eslint-enable react-hooks/exhaustive-deps */

  const onMicClick = async () => {
    if (!micUsable || voiceBusy) return

    const canStopWhileLoading =
      voiceConversationMode &&
      conversationListeningActive &&
      voiceInput.isRecording

    if (loading && !canStopWhileLoading) return

    setVoiceError(null)
    if (voiceInput.isRecording) {
      setVoiceBusy(true)
      try {
        if (voiceConversationMode) {
          conversationListeningActiveRef.current = false
          setConversationListeningActive(false)
        }
        const blob = await voiceInput.stopRecording()
        await processVoiceBlob(blob)
      } catch (e) {
        setVoiceError(e instanceof Error ? e.message : '語音轉文字失敗。')
      } finally {
        setVoiceBusy(false)
      }
    } else {
      setVoiceBusy(true)
      try {
        if (voiceConversationMode) {
          conversationListeningActiveRef.current = true
          setConversationListeningActive(true)
          try {
            const blob = await voiceInput.startRecording({ endOnSilence: {} })
            if (
              !conversationListeningActiveRef.current ||
              !voiceConversationModeRef.current
            ) {
              if (voiceInput.isRecording) {
                await voiceInput.stopRecording()
              }
              return
            }
            await processVoiceBlob(blob ?? null)
          } catch (e) {
            conversationListeningActiveRef.current = false
            setConversationListeningActive(false)
            throw e
          }
        } else {
          await voiceInput.startRecording()
        }
      } catch (e) {
        setVoiceError(e instanceof Error ? e.message : '語音輸入失敗。')
      } finally {
        setVoiceBusy(false)
      }
    }
  }

  const onReadAloudClick = async () => {
    if (!ttsUsable || !answer.trim() || loading) return
    if (
      ttsBusy ||
      ttsPlaying ||
      geminiPlaybackPendingRef.current > 0 ||
      (audioRef.current && !audioRef.current.paused)
    ) {
      stopTts()
      return
    }
    await playAnswerTts(answer)
  }

  const toggleVoiceConversationMode = () => {
    setVoiceConversationMode((prev) => {
      const next = !prev
      try {
        localStorage.setItem(
          VOICE_CONVERSATION_STORAGE_KEY,
          next ? 'true' : 'false',
        )
      } catch {
        /* ignore */
      }
      if (!next) {
        expectAutoTtsRef.current = false
        conversationListeningActiveRef.current = false
        setConversationListeningActive(false)
        void (async () => {
          if (!voiceInput.isRecording) return
          setVoiceBusy(true)
          try {
            const blob = await voiceInput.stopRecording()
            await processVoiceBlob(blob)
          } catch (e) {
            setVoiceError(
              e instanceof Error ? e.message : '語音轉文字失敗。',
            )
          } finally {
            setVoiceBusy(false)
          }
        })()
      }
      return next
    })
  }

  const onQuestionSubmit = (e: FormEvent<HTMLFormElement>) => {
    expectAutoTtsRef.current = false
    void handleSubmit(e)
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
        <p className="text-pretty text-[0.95rem] text-muted-foreground">
          以經歷與備忘為本，透過後端 RAG 檢索回答關於履歷與經驗的問題。
          朗讀可選 Google Cloud TTS 或 Gemini TTS；語音轉寫仍需 Cloud 金鑰。
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
              {ready && !cloudTts ? (
                <span className="mt-1 block text-xs font-normal text-muted-foreground">
                  {geminiTts
                    ? '未設定 GOOGLE_CLOUD_API_KEY：無法使用語音轉寫與 Cloud 朗讀；回答區可選 Gemini 朗讀。'
                    : '後端未設定 GOOGLE_CLOUD_API_KEY（轉寫）或 GOOGLE_API_KEY（Gemini 朗讀）時，語音相關功能不可用。'}
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
        <form className="flex flex-col gap-2" onSubmit={onQuestionSubmit}>
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
          <div className="mt-1 flex flex-col gap-2 sm:flex sm:flex-row sm:flex-wrap sm:items-center">
            <Button
              type="submit"
              disabled={loading || !ready}
              size="lg"
              className="min-h-11 w-full sm:min-h-0 sm:w-auto"
            >
              {loading ? '處理中…' : '送出'}
            </Button>
            <div className="grid grid-cols-2 gap-2 sm:contents sm:gap-0">
              {ttsUsable && cloudTts && geminiTts && ready ? (
                <label className="col-span-2 flex min-h-11 items-center gap-1.5 text-sm text-muted-foreground sm:min-h-0">
                  <span className="sr-only">語音合成引擎</span>
                  <select
                    id="tts-engine"
                    value={effectiveTtsEngine}
                    disabled={loading}
                    onChange={(e) => {
                      const v = e.target.value as TtsEngine
                      setTtsEngine(v)
                      try {
                        localStorage.setItem(TTS_ENGINE_STORAGE_KEY, v)
                      } catch {
                        /* ignore */
                      }
                    }}
                    className="h-10 min-h-10 w-full max-w-[11rem] rounded-md border border-input bg-background px-2 py-1 text-sm text-card-foreground disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <option value="cloud">Cloud TTS</option>
                    <option value="gemini">Gemini TTS</option>
                  </select>
                </label>
              ) : null}
              {micUsable ? (
                <>
                  <Button
                    type="button"
                    variant={voiceInput.isRecording ? 'secondary' : 'outline'}
                    size="lg"
                    disabled={
                      voiceBusy ||
                      (loading &&
                        !(
                          voiceConversationMode &&
                          conversationListeningActive &&
                          voiceInput.isRecording
                        ))
                    }
                    aria-label={
                      voiceConversationMode && conversationListeningActive
                        ? voiceInput.isRecording
                          ? '結束監聽並送出目前這一段'
                          : '開始語音監聽會話'
                        : voiceInput.isRecording
                          ? '停止錄音並送出問題'
                          : '開始語音輸入'
                    }
                    aria-pressed={voiceInput.isRecording}
                    onClick={() => void onMicClick()}
                    className="min-h-11 gap-2 sm:min-h-0"
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
                        ? voiceConversationMode && conversationListeningActive
                          ? '結束監聽'
                          : '停止並送出'
                        : '語音輸入'}
                  </Button>
                  <Button
                    type="button"
                    variant={voiceConversationMode ? 'secondary' : 'outline'}
                    size="lg"
                    disabled={voiceBusy}
                    aria-label={
                      voiceConversationMode ? '關閉對話模式' : '開啟對話模式'
                    }
                    aria-pressed={voiceConversationMode}
                    onClick={toggleVoiceConversationMode}
                    className="min-h-11 gap-2 sm:min-h-0"
                  >
                    <MessageCircle className="size-4" aria-hidden />
                    對話模式
                  </Button>
                </>
              ) : null}
              <Button
                type="button"
                variant="outline"
                disabled={isFetching}
                size="lg"
                onClick={onRefreshHealth}
                className="min-h-11 max-sm:col-span-2 sm:min-h-0"
              >
                {isFetching ? '檢查中…' : '重新檢查服務'}
              </Button>
            </div>
          </div>
          {micUsable ? (
            <>
              <details className="rounded-md border border-border/60 bg-muted/15 sm:hidden">
                <summary className="cursor-pointer list-none px-2 py-2 text-xs font-medium text-muted-foreground [&::-webkit-details-marker]:hidden">
                  語音使用說明
                </summary>
                <p className="px-2 pb-2 text-xs text-muted-foreground">
                  {voiceConversationMode ? (
                    <>
                      對話模式：點「語音輸入」開始監聽；停頓約一秒後自動送出並續錄下一輪。
                      再次點語音輸入可結束監聽（錄音中會送出目前這一段）；關閉對話模式亦會結束監聽。
                      語音成功送出後，回答結束將自動朗讀，朗讀完畢後才會再開麥克風以避免回音。
                      語音輸入建議 Chrome／Edge（WebM Opus）；Safari 錄音格式可能無法辨識。
                    </>
                  ) : (
                    <>
                      停止錄音後會自動送出問題；回答需按「朗讀」。語音輸入建議使用
                      Chrome／Edge（WebM Opus）。Safari 錄音格式可能無法辨識。
                    </>
                  )}
                </p>
              </details>
              <p className="hidden text-xs text-muted-foreground sm:block">
                {voiceConversationMode ? (
                  <>
                    對話模式：點「語音輸入」開始監聽；停頓約一秒後自動送出並續錄下一輪。
                    再次點語音輸入可結束監聽（錄音中會送出目前這一段）；關閉對話模式亦會結束監聽。
                    語音成功送出後，回答結束將自動朗讀，朗讀完畢後才會再開麥克風以避免回音。
                    語音輸入建議 Chrome／Edge（WebM Opus）；Safari 錄音格式可能無法辨識。
                  </>
                ) : (
                  <>
                    停止錄音後會自動送出問題；回答需按「朗讀」。語音輸入建議使用
                    Chrome／Edge（WebM Opus）。Safari 錄音格式可能無法辨識。
                  </>
                )}
              </p>
            </>
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
              onClick={() => {
                expectAutoTtsRef.current = false
                askWithText(qPreset)
              }}
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
                {ttsUsable && answer && !loading ? (
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
