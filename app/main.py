"""Entry point.

MAP IMAGE -> GEMINI ANALYSIS -> PLAN -> NARRATION -> RENDER -> MP4 (+ upload)

Run locally:   python -m app.main --map input/india.png --topic "Mughal empire"
In Actions:    triggered by .github/workflows/generate.yml
"""
import argparse
from pathlib import Path

from . import analyzer, image_engine, planner, subtitles, tts, youtube
from .config import ROOT, SETTINGS, resolution
from .map_engine import MapEngine
from .renderer import make_thumbnail, render_video
from .utils import ensure_dirs, write_json

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")


def pick_map(explicit=None) -> Path:
    if explicit:
        path = Path(explicit)
        if not path.exists():
            raise SystemExit(f"Map not found: {path}")
        return path
    files = sorted(p for p in (ROOT / "input").glob("*") if p.suffix.lower() in IMAGE_SUFFIXES)
    if not files:
        sample = ROOT / "assets" / "sample_map.png"
        if sample.exists():
            print("[main] no map in input/, using the bundled sample map")
            return sample
        raise SystemExit("No map image found in input/. Put a PNG/JPG there.")
    return files[0]


def pick_music(mood) -> Path | None:
    music_dir = ROOT / "assets" / "music"
    if not music_dir.exists():
        return None
    files = sorted(
        p for p in music_dir.glob("*") if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".aac")
    )
    if not files:
        return None
    if mood:
        for f in files:
            if mood.lower() in f.name.lower():
                return f
    return files[0]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI Map Animation Shorts agent")
    parser.add_argument("--map", default=None, help="path to a map image")
    parser.add_argument("--topic", default="", help="optional topic / angle")
    parser.add_argument("--language", default=None)
    parser.add_argument("--duration", type=int, default=None)
    parser.add_argument("--style", default=None)
    parser.add_argument(
        "--resolution",
        default=None,
        choices=list(SETTINGS["resolution_presets"].keys()),
        help="720p | 1080p | 1440p | 2160p (4K)",
    )
    parser.add_argument("--no-tts", action="store_true")
    parser.add_argument("--no-music", action="store_true")
    parser.add_argument("--images", action="store_true", help="enable local text-to-image")
    parser.add_argument("--upload", action="store_true", help="upload to YouTube at the end")
    parser.add_argument("--privacy", default="private", choices=["public", "private", "unlisted"])
    return parser


def run(args) -> None:
    ensure_dirs("output", "temp", "assets/generated")

    if args.resolution:
        SETTINGS["video"]["resolution"] = args.resolution
    width, height = resolution(SETTINGS)
    fps = SETTINGS["video"]["fps"]

    map_path = pick_map(args.map)
    print(f"[main] map: {map_path}")

    print("[main] 1/6 analysing map with Gemini ...")
    raw_plan = analyzer.analyze_map(
        map_path,
        topic=args.topic,
        language=args.language,
        duration=args.duration,
        style=args.style,
    )
    plan = planner.normalize_plan(raw_plan, duration=args.duration, language=args.language)
    write_json(ROOT / "output" / "plan.json", plan)
    print(f"[main]     title: {plan['title']}  ({len(plan['scenes'])} scenes, {plan['duration']:.0f}s)")

    if args.images and image_engine.enabled():
        print("[main] 2/6 generating supporting images (local SD-Turbo) ...")
        for scene in plan["scenes"]:
            if scene["action"] == "image" and scene.get("image_prompt"):
                out = ROOT / "assets" / "generated" / f"scene_{int(scene['start'])}.png"
                generated = image_engine.generate(scene["image_prompt"], out)
                if generated:
                    scene["_image_path"] = generated
    else:
        print("[main] 2/6 supporting images: off")

    narration_path = ""
    if not args.no_tts and SETTINGS["features"]["tts"] and plan.get("narration"):
        print("[main] 3/6 generating narration (Gemini TTS) ...")
        narration_path = tts.synthesize_with_fallback(plan["narration"], ROOT / "temp" / "narration.wav")
        if narration_path:
            print(f"[main]     narration length: {tts.duration_of(narration_path):.1f}s")
    else:
        print("[main] 3/6 narration: off")

    music_path = None
    if not args.no_music and SETTINGS["features"]["background_music"]:
        music_path = pick_music(plan["music_mood"])
        print(f"[main] 4/6 music: {music_path.name if music_path else 'none'}")
    else:
        print("[main] 4/6 music: off")

    srt_path = None
    if SETTINGS["features"].get("captions"):
        srt_path = subtitles.write_srt(plan, ROOT / "temp" / "captions.srt")

    print(f"[main] 5/6 rendering {width}x{height} @ {fps}fps ...")
    engine = MapEngine(map_path, width, height, fps)
    out_video = ROOT / "output" / "video.mp4"
    render_video(engine, plan, out_video, narration=narration_path, music=music_path, srt=srt_path)
    print(f"[main]     video: {out_video}")

    print("[main] 6/6 thumbnail + metadata ...")
    make_thumbnail(map_path, plan["title"], ROOT / "output" / "thumbnail.jpg")
    try:
        metadata = analyzer.generate_metadata(
            args.topic, plan["title"], plan["hook"], plan["narration"], plan["language"]
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[main]     metadata via Gemini failed ({exc}); using plan values")
        metadata = {
            "title": plan["title"],
            "description": plan["hook"],
            "tags": [],
            "category_id": "27",
            "thumbnail_text": plan["title"],
        }
    write_json(ROOT / "output" / "metadata.json", metadata)

    if args.upload:
        print("[main] uploading to YouTube ...")
        try:
            response = youtube.upload(
                out_video,
                metadata.get("title", plan["title"]),
                metadata.get("description", ""),
                metadata.get("tags", []),
                metadata.get("category_id", "27"),
                args.privacy,
            )
            print(f"[main] uploaded: https://youtu.be/{response.get('id')}")
        except Exception as exc:  # noqa: BLE001 - keep the mp4 regardless
            print(f"[main] YouTube upload failed ({exc}). The MP4 is safe in output/.")

    print("[main] done.")


def main() -> None:
    run(build_parser().parse_args())


if __name__ == "__main__":
    main()
