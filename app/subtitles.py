"""Subtitle (SRT) generation.

Captions are OFF by default (config: features.captions = false). This module
exists so they can be switched on without touching the rest of the pipeline.
"""
import re
from pathlib import Path


def _fmt(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    hours, ms = divmod(ms, 3_600_000)
    minutes, ms = divmod(ms, 60_000)
    secs, ms = divmod(ms, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def build_srt(plan: dict) -> str:
    """Split the narration into sentences and time them across the video."""
    text = plan.get("narration", "").strip()
    sentences = [s for s in re.split(r"(?<=[।.!?])\s+", text) if s.strip()]
    if not sentences:
        return ""

    total = float(plan["duration"])
    total_chars = sum(len(s) for s in sentences) or 1
    blocks, cursor = [], 0.0
    for i, sentence in enumerate(sentences, start=1):
        span = total * len(sentence) / total_chars
        blocks.append(f"{i}\n{_fmt(cursor)} --> {_fmt(cursor + span)}\n{sentence}\n")
        cursor += span
    return "\n".join(blocks)


def write_srt(plan: dict, out_path) -> str:
    srt = build_srt(plan)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(srt, encoding="utf-8")
    return str(out_path)
