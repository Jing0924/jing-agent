"""POST /api/speech/transcribe and POST /api/speech/synthesize (Google Cloud REST + API key)."""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
import wave
from typing import Any, Literal

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from memoir_rag.config import google_api_key_value, google_cloud_api_key

logger = logging.getLogger(__name__)

router = APIRouter(tags=["speech"])

SPEECH_RECOGNIZE_URL = "https://speech.googleapis.com/v1/speech:recognize"
TTS_SYNTHESIZE_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
GEMINI_GENERATE_CONTENT_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
GEMINI_STREAM_GENERATE_CONTENT_URL = (
    "https://generativelanguage.googleapis.com/v1beta/"
    "models/{model}:streamGenerateContent?alt=sse"
)

DEFAULT_LANGUAGE = "zh-TW"
DEFAULT_SAMPLE_RATE = 48000
# 繁中 Wavenet，穩定可用；可改為 cmn-TW-Neural2-A 等
DEFAULT_TTS_VOICE_NAME = "cmn-TW-Wavenet-A"
TTS_MAX_CHARS = 4500
GEMINI_TTS_PCM_SAMPLE_RATE_HZ = 24000
DEFAULT_GEMINI_TTS_MODEL = "gemini-2.5-flash-preview-tts"
DEFAULT_GEMINI_TTS_VOICE = "Kore"


def _require_cloud_key() -> str:
    key = google_cloud_api_key()
    if not key:
        raise HTTPException(
            status_code=503,
            detail="語音服務未設定。請於後端設定 GOOGLE_CLOUD_API_KEY。",
        )
    return key


def _require_gemini_api_key() -> str:
    key = google_api_key_value()
    if not key:
        raise HTTPException(
            status_code=503,
            detail="Gemini 語音合成未設定。請於後端設定 GOOGLE_API_KEY。",
        )
    return key


def _gemini_tts_model_name() -> str:
    m = (os.environ.get("GEMINI_TTS_MODEL") or DEFAULT_GEMINI_TTS_MODEL).strip()
    return m or DEFAULT_GEMINI_TTS_MODEL


def _gemini_tts_voice_name() -> str:
    v = (os.environ.get("GEMINI_TTS_VOICE") or DEFAULT_GEMINI_TTS_VOICE).strip()
    return v or DEFAULT_GEMINI_TTS_VOICE


def _pcm_s16le_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def _extract_gemini_audio_b64(data: dict[str, Any]) -> str | None:
    cands = data.get("candidates") or []
    if not cands or not isinstance(cands[0], dict):
        return None
    content = cands[0].get("content") or {}
    parts = content.get("parts") or []
    if not parts or not isinstance(parts[0], dict):
        return None
    part = parts[0]
    inline = part.get("inlineData") or part.get("inline_data")
    if not isinstance(inline, dict):
        return None
    b64 = inline.get("data")
    return b64 if isinstance(b64, str) else None


def _gather_gemini_audio_pcm_from_chunk(data: dict[str, Any]) -> bytes | None:
    parts_pcm: list[bytes] = []
    for cand in data.get("candidates") or []:
        if not isinstance(cand, dict):
            continue
        content = cand.get("content") or {}
        parts = content.get("parts") or []
        for part in parts:
            if not isinstance(part, dict):
                continue
            inline = part.get("inlineData") or part.get("inline_data")
            if not isinstance(inline, dict):
                continue
            mime = str(
                inline.get("mimeType") or inline.get("mime_type") or "",
            ).lower()
            if mime.startswith("image/") or mime.startswith("video/"):
                continue
            b64 = inline.get("data")
            if not isinstance(b64, str):
                continue
            try:
                raw = base64.b64decode(b64)
            except Exception:
                continue
            if raw:
                parts_pcm.append(raw)
    if not parts_pcm:
        return None
    return b"".join(parts_pcm)


def _tts_sse_event(event: str, data_obj: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data_obj, ensure_ascii=False)}\n\n"


def _gemini_delta_pcm(prev_snap: bytes, chunk_full: bytes) -> tuple[bytes, bytes]:
    """Emit only new PCM: cumulative snapshots reuse startswith(prev); disjoint chunks replace anchor."""
    if not chunk_full:
        return b"", prev_snap
    if prev_snap and chunk_full.startswith(prev_snap):
        return chunk_full[len(prev_snap) :], chunk_full
    return chunk_full, chunk_full


_REFERER_BLOCKED_HINT = (
    "Google 拒絕此請求（空 Referer）。請在 Cloud Console「APIs 與服務 → 憑證」編輯 "
    "`GOOGLE_CLOUD_API_KEY` 對應的金鑰：「應用程式限制」勿設為 HTTP 參照網址（該類僅適合瀏覽器直連）；"
    "後端呼叫請改為 IP 位址或無（測試用），並以「API 限制」僅允許 Speech-to-Text／Text-to-Speech。"
)


def _google_http_error(exc: httpx.HTTPStatusError, upstream: str) -> HTTPException:
    status = exc.response.status_code
    detail = f"{upstream} 暫時無法使用，請稍後再試。"
    try:
        body = exc.response.json()
        err = body.get("error", {})
        msg = err.get("message")
        if isinstance(msg, str) and msg.strip():
            low = msg.lower()
            if "referer" in low and "blocked" in low:
                detail = _REFERER_BLOCKED_HINT
            else:
                # 不暴露金鑰；簡要帶過 Google 訊息
                detail = msg.strip()[:500]
    except Exception:
        pass
    code = 503 if status in (429, 500, 502, 503) else 502
    return HTTPException(status_code=code, detail=detail)


def _recognition_encoding_for_mime(content_type: str | None) -> str | None:
    if not content_type:
        return "WEBM_OPUS"
    ct = content_type.split(";")[0].strip().lower()
    if ct == "audio/webm":
        return "WEBM_OPUS"
    if ct in ("audio/ogg", "audio/opus"):
        return "OGG_OPUS"
    if ct == "audio/wav" or ct == "audio/x-wav":
        return "LINEAR16"
    if ct == "audio/flac":
        return "FLAC"
    if ct in ("audio/mpeg", "audio/mp3"):
        return "MP3"
    if ct == "audio/mp4" or ct == "audio/x-m4a":
        return None  # 第一版不支援，給明確錯誤
    return None


def strip_markdown_for_tts(text: str) -> str:
    """輕量 Markdown 降噪：程式碼塊、連結保留文字、常見標記。"""
    s = text.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"```[\s\S]*?```", " ", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"!?\[([^\]]*)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"^#{1,6}\s+", "", s, flags=re.MULTILINE)
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"__([^_]+)__", r"\1", s)
    s = re.sub(r"(?<!\*)\*(?!\*)([^*]+)\*(?!\*)", r"\1", s)
    s = re.sub(r"(?<!_)_(?!_)([^_]+)_(?!_)", r"\1", s)
    s = re.sub(r"^[ \t]*[-*+]\s+", "", s, flags=re.MULTILINE)
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


class SynthesizeBody(BaseModel):
    text: str = Field(..., min_length=1)
    voice_name: str | None = None
    language_code: str | None = None
    tts_engine: Literal["cloud", "gemini"] = "cloud"


@router.post("/api/speech/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    language_code: str | None = Form(default=None),
    sample_rate_hertz: int | None = Form(default=None),
):
    key = _require_cloud_key()
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="未收到音訊檔內容。")

    enc = _recognition_encoding_for_mime(file.content_type)
    if enc is None:
        ct = file.content_type or "（未知）"
        raise HTTPException(
            status_code=400,
            detail=(
                f"不支援的音訊格式（Content-Type: {ct}）。"
                "請使用 Chrome／Edge 錄製（WebM Opus），或上傳相容格式。"
            ),
        )

    lang = (language_code or DEFAULT_LANGUAGE).strip() or DEFAULT_LANGUAGE
    rate = int(sample_rate_hertz) if sample_rate_hertz is not None else DEFAULT_SAMPLE_RATE
    if rate < 8000 or rate > 48000:
        raise HTTPException(status_code=400, detail="sampleRateHertz 須介於 8000 與 48000。")

    b64 = base64.b64encode(raw).decode("ascii")
    payload: dict[str, Any] = {
        "config": {
            "encoding": enc,
            "sampleRateHertz": rate,
            "languageCode": lang,
            "enableAutomaticPunctuation": True,
        },
        "audio": {"content": b64},
    }

    try:
        with httpx.Client(timeout=60.0) as client:
            r = client.post(
                SPEECH_RECOGNIZE_URL,
                params={"key": key},
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPStatusError as e:
        raise _google_http_error(e, "語音辨識") from e
    except httpx.RequestError as e:
        logger.warning("Speech recognize request failed: %s", e)
        raise HTTPException(
            status_code=503,
            detail="無法連線至語音服務，請稍後再試。",
        ) from e
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=502, detail="語音服務回應異常。") from e

    results = data.get("results") or []
    parts: list[str] = []
    for item in results:
        alts = item.get("alternatives") or []
        if alts and isinstance(alts[0], dict):
            t = alts[0].get("transcript")
            if isinstance(t, str):
                parts.append(t)
    transcript = " ".join(parts).strip()
    return {"transcript": transcript}


def _gemini_tts_generation_payload(text: str) -> dict[str, Any]:
    voice = _gemini_tts_voice_name()
    return {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": voice},
                },
            },
        },
    }


def _synthesize_gemini_tts(text: str) -> Response:
    key = _require_gemini_api_key()
    model = _gemini_tts_model_name()
    url = GEMINI_GENERATE_CONTENT_URL.format(model=model)
    payload = _gemini_tts_generation_payload(text)
    try:
        with httpx.Client(timeout=120.0) as client:
            r = client.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": key,
                },
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPStatusError as e:
        raise _google_http_error(e, "Gemini 語音合成") from e
    except httpx.RequestError as e:
        logger.warning("Gemini TTS request failed: %s", e)
        raise HTTPException(
            status_code=503,
            detail="無法連線至 Gemini 語音合成服務，請稍後再試。",
        ) from e
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=502, detail="Gemini 語音合成回應異常。") from e

    audio_b64 = _extract_gemini_audio_b64(data)
    if not audio_b64:
        raise HTTPException(status_code=502, detail="Gemini 語音合成未回傳音訊資料。")
    try:
        pcm = base64.b64decode(audio_b64)
    except Exception as e:
        raise HTTPException(status_code=502, detail="語音資料解碼失敗。") from e
    if not pcm:
        raise HTTPException(status_code=502, detail="語音資料為空。")
    wav_bytes = _pcm_s16le_to_wav(pcm, GEMINI_TTS_PCM_SAMPLE_RATE_HZ)
    return Response(content=wav_bytes, media_type="audio/wav")


def _synthesize_cloud_tts(body: SynthesizeBody, text: str) -> Response:
    key = _require_cloud_key()
    voice_name = (body.voice_name or DEFAULT_TTS_VOICE_NAME).strip()
    lang = (body.language_code or "cmn-TW").strip() or "cmn-TW"

    payload = {
        "input": {"text": text},
        "voice": {"languageCode": lang, "name": voice_name},
        "audioConfig": {"audioEncoding": "MP3"},
    }

    try:
        with httpx.Client(timeout=60.0) as client:
            r = client.post(
                TTS_SYNTHESIZE_URL,
                params={"key": key},
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPStatusError as e:
        raise _google_http_error(e, "語音合成") from e
    except httpx.RequestError as e:
        logger.warning("TTS request failed: %s", e)
        raise HTTPException(
            status_code=503,
            detail="無法連線至語音合成服務，請稍後再試。",
        ) from e

    audio_b64 = data.get("audioContent")
    if not isinstance(audio_b64, str):
        raise HTTPException(status_code=502, detail="語音合成回應異常。")
    try:
        mp3 = base64.b64decode(audio_b64)
    except Exception as e:
        raise HTTPException(status_code=502, detail="語音資料解碼失敗。") from e

    return Response(content=mp3, media_type="audio/mpeg")


def _upstream_sse_block_to_obj(block: str) -> dict[str, Any] | None:
    data_parts: list[str] = []
    for raw in block.split("\n"):
        line = raw.rstrip("\r")
        if not line.strip() or line.startswith(":"):
            continue
        if line.startswith("data:"):
            data_parts.append(line[5:].lstrip())
    if not data_parts:
        return None
    joined = "".join(data_parts).strip()
    if not joined or joined == "[DONE]":
        return None
    try:
        obj = json.loads(joined)
    except json.JSONDecodeError:
        logger.warning("Gemini SSE chunk not JSON: %s", joined[:200])
        return None
    return obj if isinstance(obj, dict) else None


def _gemini_stream_error_message(obj: dict[str, Any]) -> str | None:
    err = obj.get("error")
    if isinstance(err, dict):
        msg = err.get("message")
        if isinstance(msg, str) and msg.strip():
            return msg.strip()[:500]
    return None


@router.post("/api/speech/synthesize-stream")
def synthesize_stream(body: SynthesizeBody):
    if body.tts_engine != "gemini":
        raise HTTPException(
            status_code=400,
            detail="串流語音合成僅支援 Gemini；Cloud TTS 請使用 /api/speech/synthesize。",
        )
    cleaned = strip_markdown_for_tts(body.text)
    if not cleaned:
        raise HTTPException(status_code=400, detail="去噪後無可朗讀文字。")
    text = cleaned[:TTS_MAX_CHARS]
    key = _require_gemini_api_key()
    model = _gemini_tts_model_name()
    url = GEMINI_STREAM_GENERATE_CONTENT_URL.format(model=model)
    payload = _gemini_tts_generation_payload(text)

    def generate():
        prev_snap = b""
        buf = ""
        saw_pcm = False
        try:
            with httpx.Client(timeout=120.0) as client:
                with client.stream(
                    "POST",
                    url,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "text/event-stream",
                        "x-goog-api-key": key,
                    },
                    json=payload,
                ) as r:
                    if r.status_code != 200:
                        msg = "Gemini 語音合成暫時無法使用，請稍後再試。"
                        try:
                            raw = r.read().decode("utf-8", errors="replace")
                            body_err = json.loads(raw)
                            if isinstance(body_err, dict):
                                gmsg = _gemini_stream_error_message(body_err)
                                if gmsg:
                                    msg = gmsg
                                low = msg.lower()
                                if "referer" in low and "blocked" in low:
                                    msg = _REFERER_BLOCKED_HINT
                        except Exception:
                            pass
                        yield _tts_sse_event("error", {"message": msg})
                        return
                    for line in r.iter_lines():
                        buf += line.rstrip("\r") + "\n"
                        while True:
                            sep = buf.find("\n\n")
                            if sep < 0:
                                break
                            block = buf[:sep]
                            buf = buf[sep + 2:]
                            obj = _upstream_sse_block_to_obj(block)
                            if not obj:
                                continue
                            errmsg = _gemini_stream_error_message(obj)
                            if errmsg:
                                yield _tts_sse_event("error", {"message": errmsg})
                                return
                            pcm_full = _gather_gemini_audio_pcm_from_chunk(obj)
                            if pcm_full:
                                delta, prev_snap = _gemini_delta_pcm(
                                    prev_snap, pcm_full,
                                )
                                if delta:
                                    saw_pcm = True
                                    pcm_b64 = base64.b64encode(delta).decode(
                                        "ascii",
                                    )
                                    yield _tts_sse_event(
                                        "pcm", {"pcm_b64": pcm_b64},
                                    )
                    if buf.strip():
                        tail = _upstream_sse_block_to_obj(buf)
                        if tail:
                            errmsg = _gemini_stream_error_message(tail)
                            if errmsg:
                                yield _tts_sse_event("error", {"message": errmsg})
                                return
                            pcm_full = _gather_gemini_audio_pcm_from_chunk(tail)
                            if pcm_full:
                                delta, prev_snap = _gemini_delta_pcm(
                                    prev_snap, pcm_full,
                                )
                                if delta:
                                    saw_pcm = True
                                    pcm_b64 = base64.b64encode(delta).decode(
                                        "ascii",
                                    )
                                    yield _tts_sse_event(
                                        "pcm", {"pcm_b64": pcm_b64},
                                    )
                    if not saw_pcm:
                        yield _tts_sse_event(
                            "error",
                            {
                                "message": (
                                    "Gemini 語音合成未回傳可串流之音訊資料。"
                                ),
                            },
                        )
                        return
                    yield _tts_sse_event("done", {})
        except httpx.RequestError as e:
            logger.warning("Gemini TTS stream failed: %s", e)
            yield _tts_sse_event(
                "error",
                {
                    "message": (
                        "無法連線至 Gemini 語音合成服務，請稍後再試。"
                    ),
                },
            )
        except Exception as e:
            logger.exception("Gemini TTS stream: %s", e)
            yield _tts_sse_event("error", {"message": "語音串流發生錯誤。"})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/speech/synthesize")
def synthesize(body: SynthesizeBody):
    cleaned = strip_markdown_for_tts(body.text)
    if not cleaned:
        raise HTTPException(status_code=400, detail="去噪後無可朗讀文字。")
    text = cleaned[:TTS_MAX_CHARS]

    if body.tts_engine == "gemini":
        return _synthesize_gemini_tts(text)
    return _synthesize_cloud_tts(body, text)
