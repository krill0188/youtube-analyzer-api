"""
YouTube Video Analyzer API
FastAPI server — RapidAPI compatible
"""

from __future__ import annotations
import os
import time
import hashlib
from collections import defaultdict
from typing import Optional
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from analyzer import analyze_video

app = FastAPI(
    title="YouTube Video Analyzer API",
    description="AI-powered YouTube video analysis: summary + business opportunity scoring",
    version="1.0.0",
)

# ── API Key 관리 (환경변수로 주입) ──────────────────────────
VALID_API_KEYS = set(filter(None, os.getenv("API_KEYS", "").split(",")))

# ── Rate Limiting (메모리 기반, 서버 재시작 시 초기화) ────────
RATE_LIMIT = {
    "free":  {"calls": 10,   "window": 86400},   # 10회/일
    "basic": {"calls": 500,  "window": 86400},   # 500회/일
    "pro":   {"calls": 9999, "window": 86400},   # 무제한
}
_rate_store: "dict[str, list[float]]" = defaultdict(list)

def get_tier(api_key: str) -> str:
    """API 키 접두어로 티어 판별: free_ / basic_ / pro_"""
    if api_key.startswith("pro_"):
        return "pro"
    if api_key.startswith("basic_"):
        return "basic"
    return "free"

def check_rate_limit(api_key: str):
    tier = get_tier(api_key)
    limit = RATE_LIMIT[tier]
    now = time.time()
    window_start = now - limit["window"]

    calls = _rate_store[api_key]
    calls[:] = [t for t in calls if t > window_start]  # 오래된 기록 제거

    if len(calls) >= limit["calls"]:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "tier": tier,
                "limit": limit["calls"],
                "window_seconds": limit["window"],
                "retry_after": int(calls[0] + limit["window"] - now),
            }
        )
    calls.append(now)


# ── 요청/응답 모델 ────────────────────────────────────────────
class AnalyzeRequest(BaseModel):
    youtube_url: str
    language: str = "ko"   # ko | en


class AnalyzeResponse(BaseModel):
    video_id: str
    youtube_url: str
    source: str
    analysis: str
    tier: str
    calls_remaining: int


# ── 미들웨어: 인증 ────────────────────────────────────────────
def verify_api_key(x_rapidapi_key: Optional[str], x_api_key: Optional[str]) -> str:
    """RapidAPI 헤더 또는 직접 헤더 모두 허용"""
    key = x_rapidapi_key or x_api_key
    if not key:
        raise HTTPException(status_code=401, detail="API key required. Pass X-RapidAPI-Key or X-Api-Key header.")
    if VALID_API_KEYS and key not in VALID_API_KEYS:
        raise HTTPException(status_code=403, detail="Invalid API key.")
    return key


# ── 엔드포인트 ────────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "ok", "api": "YouTube Analyzer API v1.0"}


@app.get("/health")
def health():
    return {"status": "healthy", "timestamp": int(time.time())}


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    body: AnalyzeRequest,
    x_rapidapi_key: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None),
):
    api_key = verify_api_key(x_rapidapi_key, x_api_key)
    check_rate_limit(api_key)

    try:
        result = await analyze_video(body.youtube_url, body.language)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    tier = get_tier(api_key)
    limit = RATE_LIMIT[tier]
    calls_used = len(_rate_store[api_key])

    return AnalyzeResponse(
        video_id=result["video_id"],
        youtube_url=body.youtube_url,
        source=result["source"],
        analysis=result["analysis"],
        tier=tier,
        calls_remaining=max(0, limit["calls"] - calls_used),
    )
