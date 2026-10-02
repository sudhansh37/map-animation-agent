"""Offline smoke test: build a plan by hand, render a short video, no network."""
import sys, os
from pathlib import Path

ROOT = Path("/scratch/work/map-animation-agent")
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw
from app.planner import normalize_plan
from app.map_engine import MapEngine
from app.renderer import render_video, make_thumbnail

# 1. dummy map
os.makedirs(ROOT / "input", exist_ok=True)
map_path = ROOT / "input" / "test_map.png"
img = Image.new("RGB", (1600, 1000), (210, 225, 240))
d = ImageDraw.Draw(img)
for x in range(0, 1600, 100):
    d.line([(x, 0), (x, 1000)], fill=(180, 195, 215))
for y in range(0, 1000, 100):
    d.line([(0, y), (1600, y)], fill=(180, 195, 215))
d.ellipse([600, 350, 1000, 650], fill=(120, 170, 120))
d.rectangle([200, 200, 500, 450], fill=(200, 150, 120))
img.save(map_path)

# 2. hand-written plan
raw = {
    "title": "Test Map",
    "hook": "Testing",
    "language": "Hindi",
    "duration": 6,
    "music_mood": "cinematic",
    "narration": "यह एक परीक्षण है।",
    "scenes": [
        {"start": 0, "end": 2, "action": "full_map", "zoom_from": 1.0, "zoom_to": 1.0,
         "from_xy": [0.5, 0.5], "to_xy": [0.5, 0.5], "text": "भारत"},
        {"start": 2, "end": 4, "action": "zoom", "from_xy": [0.5, 0.5], "to_xy": [0.4, 0.4],
         "zoom_from": 1.0, "zoom_to": 2.5, "markers": [{"name": "दिल्ली", "xy": [0.4, 0.4]}],
         "text": "दिल्ली"},
        {"start": 4, "end": 6, "action": "route", "zoom_from": 1.8, "zoom_to": 1.8,
         "from_xy": [0.4, 0.4], "to_xy": [0.6, 0.6],
         "route": [{"name": "A", "xy": [0.4, 0.4]}, {"name": "B", "xy": [0.55, 0.5]},
                   {"name": "C", "xy": [0.6, 0.6]}]},
    ],
}
plan = normalize_plan(raw, duration=6, language="Hindi")
print("scenes:", [(s["start"], s["end"], s["action"]) for s in plan["scenes"]])

# 3. render
engine = MapEngine(map_path, 540, 960, 24)   # small + fast for the test
out = ROOT / "temp" / "test_video.mp4"
render_video(engine, plan, out)
print("video bytes:", out.stat().st_size if out.exists() else "MISSING")

make_thumbnail(map_path, plan["title"], ROOT / "temp" / "test_thumb.jpg")
print("thumb exists:", (ROOT / "temp" / "test_thumb.jpg").exists())
print("SMOKE_TEST_OK")
