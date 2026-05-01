"""POST /api/speech/transcribe and POST /api/speech/synthesize (Google Cloud REST + API key)."""

from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from memoir_rag.config import google_cloud_api_key

logger = logging.getLogger(__name__)

router = APIRouter(tags=["speech"])

SPEECH_RECOGNIZE_URL = "https://speech.googleapis.com/v1/speech:recognize"
TTS_SYNTHESIZE_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"

DEFAULT_LANGUAGE = "zh-TW"
DEFAULT_SAMPLE_RATE = 48000
# 繁中 Wavenet，穩定可用；可改為 cmn-TW-Neural2-A 等
DEFAULT_TTS_VOICE_NAME = "cmn-TW-Wavenet-A"
TTS_MAX_CHARS = 4500


def _require_cloud_key() -> str:
    key = google_cloud_api_key()
    if not key:
        raise HTTPException(
            status_code=503,
            detail="語音服務未設定。請於後端設定 GOOGLE_CLOUD_API_KEY。",
        )
    return key


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


@router.post("/api/speech/synthesize")
def synthesize(body: SynthesizeBody):
    key = _require_cloud_key()
    cleaned = strip_markdown_for_tts(body.text)
    if not cleaned:
        raise HTTPException(status_code=400, detail="去噪後無可朗讀文字。")
    text = cleaned[:TTS_MAX_CHARS]

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
