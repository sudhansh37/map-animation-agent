"""Render a district-reveal Short from a GeoJSON (the 'UP districts' style).

Example:
    python scripts/make_district_short.py \
        --geojson assets/geo/uttar-pradesh.geojson \
        --resolution 720p --duration 26 --out output/districts.mp4
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import SETTINGS  # noqa: E402
from app.district_engine import DistrictEngine  # noqa: E402
from app.renderer import make_district_thumbnail, render_stream  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="District-reveal map Short")
    parser.add_argument("--geojson", required=True)
    parser.add_argument("--out", default="output/districts.mp4")
    parser.add_argument("--resolution", default="720p", choices=list(SETTINGS["resolution_presets"]))
    parser.add_argument("--duration", type=float, default=26)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--state-name", default=None)
    parser.add_argument("--title", default=None)
    args = parser.parse_args()

    preset = SETTINGS["resolution_presets"][args.resolution]
    width, height = preset["width"], preset["height"]

    engine = DistrictEngine(args.geojson, width, height, args.fps, state_name=args.state_name)
    print(f"[districts] {len(engine.districts)} districts, state={engine.state_name}")

    render_stream(engine.frames(args.duration), args.out, width, height, args.fps, duration=args.duration)
    print(f"[districts] video: {args.out}")

    thumb_text = args.title or engine.state_name
    make_district_thumbnail(engine, thumb_text, str(Path(args.out).with_name("thumbnail.jpg")))
    print("[districts] done")


if __name__ == "__main__":
    main()
