#!/usr/bin/env python3
"""yt2fb: YouTube URL to Facebook Page long-form post.

Commands:
  python yt2fb.py draft "https://youtu.be/VIDEO_ID"
  python yt2fb.py publish "https://youtu.be/VIDEO_ID" --confirm
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from openai import OpenAI
from youtube_transcript_api import NoTranscriptFound, TranscriptsDisabled, YouTubeTranscriptApi

try:
    import yt_dlp
except Exception:  # pragma: no cover
    yt_dlp = None

ROOT = Path(__file__).resolve().parent
PROMPT_PATH = ROOT / "prompts" / "system.md"
PREVIEW_PATH = ROOT / "preview.md"
RUN_PATH = ROOT / "run.json"

BANNED_PHRASES = [
    "不是",
    "而是",
    "值得注意的是",
    "需要指出的是",
    "總的來說",
    "總體而言",
    "不得不說",
    "毫無疑問",
    "顯而易見",
    "由此可見",
    "在這個背景下",
    "隨著",
]

END_MARKERS = [
    "掰掰",
    "我們下支影片見",
    "謝謝收看",
    "下次見",
    "see you next time",
    "thanks for watching",
]


@dataclass
class VideoMeta:
    video_id: str
    title: str
    channel: str
    url: str
    description: str = ""


def die(message: str, code: int = 1) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)


def extract_video_id(url: str) -> str:
    patterns = [
        r"youtu\.be/([A-Za-z0-9_-]{11})",
        r"youtube\.com/watch\?.*?v=([A-Za-z0-9_-]{11})",
        r"youtube\.com/shorts/([A-Za-z0-9_-]{11})",
        r"youtube\.com/embed/([A-Za-z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    die("找不到 YouTube video ID。請確認網址格式。")


def canonical_url(video_id: str) -> str:
    return f"https://youtu.be/{video_id}"


def get_video_metadata(video_url: str, video_id: str) -> VideoMeta:
    # First try yt-dlp for richer metadata.
    if yt_dlp is not None:
        try:
            opts = {"quiet": True, "skip_download": True, "nocheckcertificate": True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
            return VideoMeta(
                video_id=video_id,
                title=info.get("title") or "",
                channel=info.get("channel") or info.get("uploader") or "",
                description=info.get("description") or "",
                url=canonical_url(video_id),
            )
        except Exception:
            pass

    # Fallback to YouTube oEmbed.
    try:
        response = requests.get(
            "https://www.youtube.com/oembed",
            params={"url": video_url, "format": "json"},
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        return VideoMeta(
            video_id=video_id,
            title=data.get("title", ""),
            channel=data.get("author_name", ""),
            description="",
            url=canonical_url(video_id),
        )
    except Exception as exc:
        die(f"無法擷取 YouTube 影片資訊：{exc}")


def get_transcript(video_id: str) -> str:
    preferred_languages = ["zh-Hant", "zh-TW", "zh", "en", "ja"]
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=preferred_languages)
    except (NoTranscriptFound, TranscriptsDisabled):
        die("這部影片沒有可抓取的字幕或逐字稿。")
    except Exception as exc:
        die(f"擷取字幕失敗：{exc}")

    lines: list[str] = []
    previous = None
    for item in transcript:
        text = (item.get("text") or "").replace("\n", " ").strip()
        if not text or text == previous:
            continue
        lines.append(text)
        previous = text

    if not lines:
        die("字幕擷取結果為空。")

    return remove_possible_loop("\n".join(lines))


def remove_possible_loop(text: str) -> str:
    lowered = text.lower()
    for marker in END_MARKERS:
        idx = lowered.find(marker.lower())
        if idx != -1:
            return text[: idx + len(marker)].strip()
    return text.strip()


def load_system_prompt() -> str:
    if not PROMPT_PATH.exists():
        die(f"找不到 prompt：{PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8")


def generate_post(meta: VideoMeta, transcript: str) -> str:
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        die("缺少 OPENAI_API_KEY。")

    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    client = OpenAI(api_key=api_key)

    user_content = f"""
影片標題：{meta.title}
頻道：{meta.channel}
影片網址：{meta.url}
影片描述：{meta.description[:3000]}

逐字稿：
{transcript[:60000]}
""".strip()

    response = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": load_system_prompt()},
            {"role": "user", "content": user_content},
        ],
    )

    post = getattr(response, "output_text", "") or ""
    if not post.strip():
        die("OpenAI 回傳空白草稿。")
    return post.strip()


def check_banned_phrases(text: str) -> list[str]:
    return [phrase for phrase in BANNED_PHRASES if phrase in text]


def estimate_cjk_chars(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def build_preview(post: str, meta: VideoMeta) -> str:
    banned = check_banned_phrases(post)
    banned_text = "未發現明顯禁用詞" if not banned else "命中：" + "、".join(banned)
    count = estimate_cjk_chars(post)

    # Add safety diagnostics even if the model already produced them.
    return f"""{post}

─

▶ 原片：{meta.url}

─

【程式檢查】
中文字估算：{count}
禁用詞自查：{banned_text}
產生時間：{datetime.now(timezone.utc).isoformat()}
""".strip() + "\n"


def save_run(meta: VideoMeta, transcript: str, post: str) -> None:
    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "video": asdict(meta),
        "transcript_chars": len(transcript),
        "post_chars": len(post),
        "post_cjk_chars": estimate_cjk_chars(post),
        "banned_phrases": check_banned_phrases(post),
    }
    RUN_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_draft(url: str) -> None:
    video_id = extract_video_id(url)
    meta = get_video_metadata(url, video_id)
    transcript = get_transcript(video_id)
    post = generate_post(meta, transcript)
    preview = build_preview(post, meta)

    PREVIEW_PATH.write_text(preview, encoding="utf-8")
    save_run(meta, transcript, post)

    print(f"已產生 {PREVIEW_PATH.name} 與 {RUN_PATH.name}")
    print(f"影片：{meta.title}")
    print(f"中文字估算：{estimate_cjk_chars(post)}")
    banned = check_banned_phrases(post)
    if banned:
        print("禁用詞命中：" + "、".join(banned))
    else:
        print("禁用詞自查：未發現明顯禁用詞")


def publish_to_facebook(message: str, video_url: str) -> dict[str, Any]:
    load_dotenv()
    page_id = os.getenv("META_PAGE_ID")
    token = os.getenv("META_PAGE_ACCESS_TOKEN")
    version = os.getenv("META_GRAPH_VERSION", "v20.0")

    if not page_id:
        die("缺少 META_PAGE_ID。")
    if not token:
        die("缺少 META_PAGE_ACCESS_TOKEN。")

    endpoint = f"https://graph.facebook.com/{version}/{page_id}/feed"
    payload = {
        "message": message,
        "link": video_url,
        "access_token": token,
    }
    response = requests.post(endpoint, data=payload, timeout=30)
    try:
        data = response.json()
    except Exception:
        data = {"raw": response.text}

    if response.status_code >= 400:
        die(f"Facebook 發佈失敗：HTTP {response.status_code} {json.dumps(data, ensure_ascii=False)}")
    return data


def run_publish(url: str, confirm: bool) -> None:
    if not confirm:
        die("發佈需要人工確認。請在檢查 preview.md 後加上 --confirm。")
    if not PREVIEW_PATH.exists():
        die("找不到 preview.md。請先執行 draft。")

    video_id = extract_video_id(url)
    video_url = canonical_url(video_id)
    message = PREVIEW_PATH.read_text(encoding="utf-8").strip()
    result = publish_to_facebook(message, video_url)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="YouTube to Facebook Page long-form post automation")
    subparsers = parser.add_subparsers(dest="command", required=True)

    draft_parser = subparsers.add_parser("draft", help="Generate preview.md and run.json")
    draft_parser.add_argument("url", help="YouTube URL")

    publish_parser = subparsers.add_parser("publish", help="Publish preview.md to Facebook Page")
    publish_parser.add_argument("url", help="YouTube URL")
    publish_parser.add_argument("--confirm", action="store_true", help="Required safety confirmation")

    args = parser.parse_args()

    if args.command == "draft":
        run_draft(args.url)
    elif args.command == "publish":
        run_publish(args.url, args.confirm)
    else:  # pragma: no cover
        die("Unknown command")


if __name__ == "__main__":
    main()
