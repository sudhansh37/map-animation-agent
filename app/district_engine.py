"""District-by-district map reveal engine.

Reproduces the "UP districts" Short style: a dark, cinematic base map where
districts light up one after another, each with a vivid fill, a glowing
outline and a callout label box.

Everything is drawn locally with Pillow from a GeoJSON of polygons - no paid
map or video service.
"""
import json
import math
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .config import ROOT
from .utils import clamp, ease_in_out, load_font

# vivid, high-contrast fill colours cycled across districts
PALETTE = [
    (231, 76, 60),    # red
    (241, 196, 15),   # yellow
    (46, 204, 113),   # green
    (52, 152, 219),   # blue
    (155, 89, 182),   # purple
    (26, 188, 156),   # teal
    (230, 126, 34),   # orange
    (236, 64, 122),   # pink
    (0, 188, 212),    # cyan
    (139, 195, 74),   # lime
]


def _load_geojson(path):
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    districts = []
    for feature in data.get("features", []):
        props = feature.get("properties", {}) or {}
        name = (
            props.get("district")
            or props.get("DISTRICT")
            or props.get("NAME")
            or props.get("name")
            or "?"
        )
        geom = feature.get("geometry") or {}
        gtype = geom.get("type")
        coords = geom.get("coordinates") or []
        rings = []
        if gtype == "Polygon" and coords:
            rings = [coords[0]]
        elif gtype == "MultiPolygon":
            rings = [poly[0] for poly in coords if poly]
        if rings:
            districts.append({"name": str(name), "rings": rings})
    return districts


def _ring_centroid(ring):
    """Area-weighted centroid of a single ring (shoelace)."""
    a = cx = cy = 0.0
    n = len(ring)
    for i in range(n):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % n]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(a) < 1e-9:
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        return sum(xs) / n, sum(ys) / n
    a *= 0.5
    return cx / (6 * a), cy / (6 * a)


class DistrictEngine:
    def __init__(self, geojson_path, width, height, fps=30, state_name=None,
                 pad=0.07, intro=1.8, outro=0.8, fade=0.45, label_hold=2.2):
        self.W, self.H, self.fps = int(width), int(height), int(fps)
        self.pad = pad
        self.intro = intro
        self.outro = outro
        self.fade = fade
        self.label_hold = label_hold

        self.districts = _load_geojson(geojson_path)
        if not self.districts:
            raise ValueError("No polygon features found in the GeoJSON")

        self.geojson_path = geojson_path
        self.state_name = state_name or self._guess_state()
        self._project()
        self._fonts = {}
        self._bg = self._make_background()
        self._sprites = [self._make_sprite(d, i) for i, d in enumerate(self.districts)]

    # ------------------------------------------------------------------ setup
    def _guess_state(self):
        try:
            with open(self.geojson_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            props = data["features"][0].get("properties", {})
            return props.get("st_nm") or props.get("STATE") or "Districts"
        except Exception:  # noqa: BLE001
            return "Districts"

    def _project(self):
        lons, lats = [], []
        for d in self.districts:
            for ring in d["rings"]:
                for lon, lat in ring:
                    lons.append(lon)
                    lats.append(lat)
        lon0, lon1 = min(lons), max(lons)
        lat0, lat1 = min(lats), max(lats)
        k = math.cos(math.radians((lat0 + lat1) / 2.0))
        span_x = max(1e-6, (lon1 - lon0) * k)
        span_y = max(1e-6, (lat1 - lat0))
        avail_w = self.W * (1 - 2 * self.pad)
        avail_h = self.H * (1 - 2 * self.pad)
        scale = min(avail_w / span_x, avail_h / span_y)
        off_x = (self.W - span_x * scale) / 2.0
        off_y = (self.H - span_y * scale) / 2.0

        def proj(lon, lat):
            return (off_x + (lon - lon0) * k * scale, off_y + (lat1 - lat) * scale)

        for d in self.districts:
            d["px"] = [[proj(lon, lat) for lon, lat in ring] for ring in d["rings"]]
            biggest = max(d["px"], key=lambda r: abs(_poly_area(r)))
            d["centroid"] = _ring_centroid(biggest)

    # ------------------------------------------------------------- resources
    def font(self, size, text=""):
        return load_font(size, text)

    def _make_background(self):
        # dark cinematic gradient + faint district outlines
        bg = Image.new("RGB", (self.W, self.H), (6, 10, 18))
        draw = ImageDraw.Draw(bg, "RGBA")
        for y in range(self.H):
            f = y / self.H
            shade = int(16 - 10 * f)
            draw.line([(0, y), (self.W, y)], fill=(shade // 2, shade // 2, shade))
        outline = ImageDraw.Draw(bg, "RGBA")
        for d in self.districts:
            for ring in d["px"]:
                outline.line(list(ring) + [ring[0]], fill=(90, 110, 140, 90), width=max(1, int(self.W / 900)))
        return bg

    def _make_sprite(self, district, index):
        color = PALETTE[index % len(PALETTE)]
        xs = [p[0] for ring in district["px"] for p in ring]
        ys = [p[1] for ring in district["px"] for p in ring]
        margin = int(self.W * 0.02) + 6
        x0, y0 = int(min(xs)) - margin, int(min(ys)) - margin
        x1, y1 = int(max(xs)) + margin, int(max(ys)) + margin
        w, h = max(1, x1 - x0), max(1, y1 - y0)

        def local(ring):
            return [(p[0] - x0, p[1] - y0) for p in ring]

        glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        for ring in district["px"]:
            gd.polygon(local(ring), fill=color + (255,))
        glow = glow.filter(ImageFilter.GaussianBlur(int(self.W * 0.012)))

        sprite = glow
        sd = ImageDraw.Draw(sprite)
        for ring in district["px"]:
            sd.polygon(local(ring), fill=color + (235,))
        width = max(2, int(self.W / 420))
        for ring in district["px"]:
            sd.line(local(ring) + [local(ring)[0]], fill=(255, 255, 255, 235), width=width)
        return {"img": sprite, "pos": (x0, y0), "centroid": district["centroid"], "name": district["name"]}

    # ---------------------------------------------------------------- timing
    def reveal_times(self, duration):
        n = len(self.districts)
        start = self.intro
        end = max(start + 0.5, duration - self.outro)
        step = (end - start) / max(1, n)
        return [start + i * step for i in range(n)], step

    # ------------------------------------------------------------------ draw
    def _draw_label(self, frame, text, target, used_boxes):
        draw = ImageDraw.Draw(frame, "RGBA")
        unit = self.W / 1080.0
        font = self.font(int(40 * unit), text)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        pad = int(14 * unit)
        bw, bh = tw + 2 * pad, th + 2 * pad

        tx, ty = target
        # place the box above the district, nudged into the frame
        bx = clamp(tx - bw / 2, 8 * unit, self.W - bw - 8 * unit)
        by = ty - bh - 60 * unit
        if by < 8 * unit:
            by = ty + 60 * unit
        by = clamp(by, 8 * unit, self.H - bh - 8 * unit)

        # pointer line
        draw.line([(bx + bw / 2, by + bh), (tx, ty)], fill=(255, 255, 255, 220), width=max(2, int(3 * unit)))
        draw.ellipse([tx - 5 * unit, ty - 5 * unit, tx + 5 * unit, ty + 5 * unit], fill=(255, 255, 255, 255))
        # box
        draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=int(8 * unit), fill=(0, 0, 0, 235),
                               outline=(255, 255, 255, 180), width=max(1, int(2 * unit)))
        draw.text((bx + pad, by + pad - bbox[1]), text.upper(), font=font, fill=(255, 255, 255))

    def _draw_title(self, frame, alpha=255):
        draw = ImageDraw.Draw(frame, "RGBA")
        unit = self.W / 1080.0
        text = self.state_name.upper()
        font = self.font(int(64 * unit), text)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        x = (self.W - tw) / 2
        y = self.H * 0.045
        pad = int(18 * unit)
        draw.rounded_rectangle([x - pad, y - pad, x + tw + pad, y + (bbox[3] - bbox[1]) + pad],
                               radius=int(12 * unit), fill=(0, 0, 0, int(200 * alpha / 255)))
        draw.text((x, y - bbox[1]), text, font=font, fill=(255, 255, 255, alpha))

    # ----------------------------------------------------------------- public
    def frames(self, duration, show_labels=True):
        reveal, step = self.reveal_times(duration)
        total = int(round(duration * self.fps))
        acc = self._bg.copy()
        settled = 0  # districts already merged into acc

        for i in range(total):
            t = i / self.fps
            frame = acc.copy()

            # merge any district whose fade has finished
            while settled < len(self.districts) and reveal[settled] + self.fade <= t:
                s = self._sprites[settled]
                frame.paste(s["img"], s["pos"], s["img"])
                settled += 1
            acc = frame.copy()

            # draw districts currently fading in
            active = []
            for idx in range(settled, len(self.districts)):
                age = t - reveal[idx]
                if age < 0:
                    break
                if age <= self.fade:
                    alpha = int(255 * ease_in_out(age / self.fade))
                    sprite = self._sprites[idx]["img"].copy()
                    sprite.putalpha(sprite.getchannel("A").point(lambda a, a_=alpha: a * a_ // 255))
                    frame.paste(sprite, self._sprites[idx]["pos"], sprite)
                active.append(idx)

            # labels for the most recently revealed districts
            if show_labels:
                recent = [j for j in range(len(self.districts))
                          if 0 <= t - reveal[j] <= self.label_hold]
                for j in recent[-2:]:
                    self._draw_label(frame, self._sprites[j]["name"], self._sprites[j]["centroid"], [])

            title_alpha = 255 if t < self.intro + 1.5 else 0
            if title_alpha:
                self._draw_title(frame, title_alpha)

            yield frame.tobytes()


def _poly_area(ring):
    a = 0.0
    n = len(ring)
    for i in range(n):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return a * 0.5
