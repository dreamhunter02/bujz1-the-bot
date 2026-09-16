"""Generate Bujji voice samples across her emotional range.

Paced for the 4 req/min limit, so this takes ~15s per line.
    source .env && python3 voice/sample_bujji.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from bodhan import speak  # noqa: E402

OUT = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)

LINES = [
    ("neutral",   "Okay. Build's running. Give it a minute."),
    ("annoyed",   "Seriously? Third time today. Show me the logs."),
    ("worried",   "The disk is at ninety four percent. I don't like this."),
    ("happy",     "Tests passed. All of them. Don't look so surprised."),
    ("excited",   "Oh, that's clever. Wait, that's actually clever."),
    ("surprised", "You deleted what?"),
]

for emotion, text in LINES:
    path = OUT / f"bujji_{emotion}.wav"
    t0 = time.monotonic()
    try:
        audio = speak(text, emotion=emotion, out_path=path)
        dt = time.monotonic() - t0
        secs = (len(audio) - 44) / (24000 * 2)
        print(f"OK   {emotion:<10} {len(audio):>7}B  {secs:4.1f}s audio  {dt:4.1f}s call  \"{text}\"")
    except Exception as e:
        print(f"FAIL {emotion:<10} {e}")
