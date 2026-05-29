"""
YouTube 분석 핵심 로직 — Claude CLI subprocess 호출
"""

import os
import asyncio
import subprocess
from urllib.parse import urlparse, parse_qs

CLAUDE_CANDIDATES = [
    os.path.expanduser("~/.npm-global/bin/claude"),
    "/usr/local/bin/claude",
    os.path.expanduser("~/.local/bin/claude"),
]

def find_claude_bin() -> str:
    for c in CLAUDE_CANDIDATES:
        if os.path.exists(c):
            return c
    return "claude"

PROMPT_TEMPLATE = """You are an expert business analyst. Analyze this YouTube video and provide structured insights.

Video: https://youtu.be/{video_id}
Content source: {source_label}

{body}

---

Respond in {language}. Use this exact structure with emoji headers only (no # markdown headers):

📺 [Video Title]
🔗 https://youtu.be/{video_id}

📌 Key Summary
(3-5 lines covering the core content)

💡 Main Points
• Point 1
• Point 2
• Point 3
• Point 4

━━━━━━━━━━━━━━━━━━━
🎯 Business Replication Analysis
━━━━━━━━━━━━━━━━━━━

✅ Replication Potential: [Possible / Conditional / Not Possible] — (one-line rationale)

🛠 Required Tools & Stack
• SW: (specific libraries/frameworks/APIs)
• HW: (if any)
• External services: (APIs needed, paid or free)

💰 Estimated Cost & Timeline
• Initial cost: ($USD)
• MVP timeline: (X days/weeks)
• Technical difficulty: Beginner / Intermediate / Advanced
• Monthly operating cost: ($USD)

🏷️ Keywords: (5-8 tags)
"""


def extract_video_id(url: str) -> str:
    if "youtu.be" in url:
        return url.split("youtu.be/")[1].split("?")[0].split("&")[0]
    if "youtube.com" in url:
        parsed = urlparse(url)
        v = parse_qs(parsed.query).get("v")
        if v:
            return v[0]
        if "/shorts/" in url:
            return url.split("/shorts/")[1].split("?")[0].split("&")[0]
    raise ValueError(f"Invalid YouTube URL: {url}")


def get_transcript(video_id: str):
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return None

    api = YouTubeTranscriptApi()

    for lang in ["ko", "en"]:
        try:
            fetched = api.fetch(video_id, languages=[lang])
            text = " ".join([s.text for s in fetched.snippets])
            return text, lang, "manual"
        except Exception:
            continue

    try:
        for t in api.list(video_id):
            try:
                fetched = t.fetch()
                text = " ".join([s.text for s in fetched.snippets])
                src = "auto" if getattr(t, "is_generated", False) else "manual"
                return text, t.language, src
            except Exception:
                continue
    except Exception:
        pass

    return None


def get_metadata(url: str) -> dict:
    import subprocess, json
    result = subprocess.run(
        ["yt-dlp", "--skip-download", "--dump-single-json", "--no-warnings", url],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError("Failed to fetch video metadata")
    data = json.loads(result.stdout)
    return {
        "title": data.get("title", ""),
        "channel": data.get("channel") or data.get("uploader", ""),
        "duration": data.get("duration", 0),
        "description": (data.get("description") or "")[:3000],
        "tags": data.get("tags") or [],
        "view_count": data.get("view_count", 0),
    }


async def analyze_video(url: str, language: str = "ko") -> dict:
    video_id = extract_video_id(url)
    lang_label = "Korean" if language == "ko" else "English"

    transcript_result = get_transcript(video_id)

    if transcript_result:
        text, lang, src = transcript_result
        truncated = text[:8000]
        source_label = f"{lang} subtitles ({'manual' if src == 'manual' else 'auto-generated'})"
        body = f"Subtitles ({len(truncated)} chars):\n\n{truncated}"
    else:
        meta = get_metadata(url)
        duration_min = meta["duration"] // 60 if meta["duration"] else 0
        tags_str = ", ".join(meta["tags"][:15]) if meta["tags"] else "(none)"
        source_label = "metadata only (no subtitles)"
        body = (
            f"Video metadata (no subtitles available):\n\n"
            f"Title: {meta['title']}\n"
            f"Channel: {meta['channel']}\n"
            f"Duration: {duration_min} min\n"
            f"Views: {meta['view_count']:,}\n"
            f"Tags: {tags_str}\n\n"
            f"Description:\n{meta['description']}\n\n"
            f"⚠️ No subtitles. Analyze based on metadata only."
        )

    prompt = PROMPT_TEMPLATE.format(
        video_id=video_id,
        source_label=source_label,
        body=body,
        language=lang_label,
    )

    def run_claude(p: str) -> str:
        claude_bin = find_claude_bin()
        result = subprocess.run(
            [claude_bin, "--print", "--dangerously-skip-permissions"],
            input=p, capture_output=True, text=True,
            timeout=120, cwd=os.path.expanduser("~"),
        )
        if result.returncode != 0 or not result.stdout.strip():
            raise RuntimeError(f"Claude CLI 실패: {result.stderr[:300]}")
        return result.stdout.strip()

    analysis = await asyncio.to_thread(run_claude, prompt)

    return {
        "video_id": video_id,
        "source": source_label,
        "analysis": analysis,
    }
