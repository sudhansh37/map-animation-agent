"""Video composition (FFmpeg) and thumbnail generation."""
import os
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .config import ROOT, SETTINGS
from .utils import ffmpeg_bin, load_font


def _load_font(size: int, text: str = ""):
    return load_font(size, text)


def _wrap(draw, text, font, max_width):
    words = text.split()
    lines, current = [], ""
    for word in words:
        candidate = (current + " " + word).strip()
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def render_stream(frames, out_path, width, height, fps, duration=None,
                  narration=None, music=None, srt=None) -> str:
    """Pipe an iterable of raw RGB24 frames into FFmpeg and mux audio."""
    crf = SETTINGS["video"]["crf"]
    preset = SETTINGS["video"]["preset"]
    volume = SETTINGS.get("music_volume", 0.12)

    cmd = [
        ffmpeg_bin(), "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
    ]

    index = 1
    narration_idx = music_idx = None
    if narration:
        cmd += ["-i", str(narration)]
        narration_idx = index
        index += 1
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(music)]
        music_idx = index
        index += 1

    filters, audio_map = [], None
    if narration_idx is not None and music_idx is not None:
        filters.append(f"[{narration_idx}:a]volume=1.0[na]")
        filters.append(f"[{music_idx}:a]volume={volume}[mu]")
        filters.append("[na][mu]amix=inputs=2:duration=longest:dropout_transition=0[aout]")
        audio_map = "[aout]"
    elif narration_idx is not None:
        audio_map = f"{narration_idx}:a"
    elif music_idx is not None:
        filters.append(f"[{music_idx}:a]volume={volume}[aout]")
        audio_map = "[aout]"

    vf = []
    if srt and Path(srt).exists():
        escaped = str(srt).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
        vf.append(f"subtitles='{escaped}':force_style='Fontsize=16,Alignment=2,MarginV=90'")

    cmd += ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p"]
    if vf:
        cmd += ["-vf", ",".join(vf)]
    if filters:
        cmd += ["-filter_complex", ";".join(filters)]
    cmd += ["-map", "0:v"]
    if audio_map:
        cmd += ["-map", audio_map, "-c:a", "aac", "-b:a", "192k"]
    # Cap the output at the intended duration instead of -shortest, so a short
    # narration does not truncate the video.
    if duration:
        cmd += ["-t", f"{float(duration):.3f}"]
    cmd += [str(out_path)]

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )
    try:
        for frame in frames:
            proc.stdin.write(frame)
        proc.stdin.close()
    except BrokenPipeError:
        pass
    stderr = proc.stderr.read().decode("utf-8", "ignore")
    if proc.wait() != 0:
        raise RuntimeError(f"FFmpeg failed:\n{stderr[-2000:]}")
    return str(out_path)


def render_video(engine, plan, out_path, narration=None, music=None, srt=None) -> str:
    """Render a MapEngine plan (kept for the image-map pipeline)."""
    return render_stream(
        engine.frames(plan),
        out_path,
        engine.W,
        engine.H,
        engine.fps,
        duration=plan.get("duration"),
        narration=narration,
        music=music,
        srt=srt,
    )


def make_thumbnail(map_path, text, out_path, width=1080, height=1920) -> str:
    """Simple, readable Shorts thumbnail from an image."""
    base = Image.open(map_path).convert("RGB")
    k = max(width / base.width, height / base.height)
    base = base.resize((int(base.width * k), int(base.height * k)), Image.LANCZOS)
    left = (base.width - width) // 2
    top = (base.height - height) // 2
    thumb = base.crop((left, top, left + width, top + height)).filter(ImageFilter.GaussianBlur(2))
    thumb = Image.blend(thumb, Image.new("RGB", (width, height), (0, 0, 0)), 0.4)

    draw = ImageDraw.Draw(thumb)
    font = _load_font(int(height * 0.075), text)
    lines = _wrap(draw, text, font, int(width * 0.85))
    line_h = int(height * 0.075 * 1.2)
    total_h = line_h * len(lines)
    y = (height - total_h) / 2
    for line in lines:
        w = draw.textlength(line, font=font)
        x = (width - w) / 2
        draw.text((x + 4, y + 4), line, font=font, fill=(0, 0, 0))
        draw.text((x, y), line, font=font, fill=(255, 255, 255))
        y += line_h

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    thumb.save(out_path, quality=92)
    return str(out_path)


def make_district_thumbnail(engine, text, out_path) -> str:
    """Thumbnail for the district engine: last frame + a title bar."""
    frame = None
    for frame_bytes in engine.frames(engine.intro + 0.1, show_labels=False):
        frame = frame_bytes
    img = Image.frombytes("RGB", (engine.W, engine.H), frame) if frame else engine._bg.copy()
    draw = ImageDraw.Draw(img, "RGBA")
    font = _load_font(int(engine.H * 0.06), text)
    lines = _wrap(draw, text, font, int(engine.W * 0.85))
    y = engine.H * 0.06
    for line in lines:
        w = draw.textlength(line, font=font)
        x = (engine.W - w) / 2
        draw.rectangle([x - 16, y - 10, x + w + 16, y + engine.H * 0.06 * 1.1], fill=(0, 0, 0, 200))
        draw.text((x, y), line, font=font, fill=(255, 255, 255))
        y += engine.H * 0.06 * 1.15
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, quality=92)
    return str(out_path)
