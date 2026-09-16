"""Bodhan indic-speak TTS client.

Reads BODHAN_API_KEY from the environment (see .env, which is gitignored).
The hosted API allows 4 requests/minute on indic-speak, so speak() paces
itself and honours retry-after on 429.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = os.environ.get("BODHAN_BASE_URL", "https://api.bodhan.ai/v1")
RATE_LIMIT_RPM = 4

# Bujji's emotion tags -> Bodhan speaking styles.
# Bodhan offers: anger, disgust, fear, happy, sad, surprise (plus delivery
# registers we don't want). None means the voice's neutral reading.
EMOTION_TO_STYLE: dict[str, str | None] = {
    "neutral": None,
    "thinking": None,
    "happy": "happy",
    "excited": "happy",
    "affectionate": "happy",
    "worried": "fear",
    "annoyed": "anger",
    "sad": "sad",
    "surprised": "surprise",
}

# Telugu-recorded female voice. Any voice can read any language, so Sravani
# reading English gives Telugu-accented Indian English - the Hyderabad
# texture we want - and carries over unchanged when we add Telugu.
DEFAULT_VOICE = "Sravani"

_last_call = 0.0


def _api_key() -> str:
    key = os.environ.get("BODHAN_API_KEY")
    if not key:
        raise RuntimeError("BODHAN_API_KEY not set (source .env)")
    return key


def speak(
    text: str,
    *,
    emotion: str = "neutral",
    voice: str = DEFAULT_VOICE,
    lang: str = "en",
    out_path: str | Path | None = None,
) -> bytes:
    """Synthesise `text` and return WAV bytes (PCM16, 24 kHz, mono)."""
    global _last_call

    instructions: dict[str, str] = {"lang": lang}
    style = EMOTION_TO_STYLE.get(emotion)
    if style:
        instructions["style"] = style

    body = json.dumps({
        "model": "indic-speak",
        "input": text,
        "voice": voice,
        "instructions": json.dumps(instructions),
    }).encode()

    # Self-pace to stay inside the per-minute allowance.
    gap = 60.0 / RATE_LIMIT_RPM
    wait = gap - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)

    for attempt in range(4):
        req = urllib.request.Request(
            f"{BASE_URL}/audio/speech",
            data=body,
            headers={
                "Authorization": f"Bearer {_api_key()}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                audio = resp.read()
            _last_call = time.monotonic()
            break
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf8", "replace")[:300]
            if e.code == 429 and attempt < 3:
                delay = float(e.headers.get("retry-after") or gap)
                time.sleep(delay + 1)
                continue
            raise RuntimeError(f"bodhan {e.code}: {detail}") from None
    else:
        raise RuntimeError("bodhan: rate limited after retries")

    if out_path:
        Path(out_path).write_bytes(audio)
    return audio
