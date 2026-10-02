"""Small shared helpers."""
import json
import math
import os
import re
import subprocess
from pathlib import Path

from .config import ROOT


def ffmpeg_bin() -> str:
    """Path to ffmpeg. Override with the FFMPEG_BIN env var if needed."""
    return os.getenv("FFMPEG_BIN", "ffmpeg")


# ---------------------------------------------------------------- filesystem
def ensure_dirs(*relative_names: str) -> None:
    for name in relative_names:
        (ROOT / name).mkdir(parents=True, exist_ok=True)


def read_json(path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path, obj) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------- JSON
def extract_json(text: str) -> dict:
    """Pull the first balanced JSON object out of a model response."""
    if not text:
        raise ValueError("Empty model response")
    text = text.strip()
    # strip markdown fences if present
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # fall back to the first balanced {...}
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found in response")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : i + 1])
    raise ValueError("Unbalanced JSON in response")


# --------------------------------------------------------------------- math
def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def ease_in_out(t: float) -> float:
    """Smoothstep easing for cinematic camera moves."""
    t = clamp(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def pulse(t: float, period: float = 1.2) -> float:
    """A 0..1 pulse that repeats, used for marker animations."""
    return 0.5 * (1.0 + math.sin(2.0 * math.pi * t / period))


# ------------------------------------------------------------------ process
def run_command(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command, raising with captured output on failure."""
    result = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(map(str, cmd))}\n"
            f"{result.stderr[-2000:]}"
        )
    return result


def human_time(seconds: float) -> str:
    seconds = int(round(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"
