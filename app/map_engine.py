"""Programmatic map animation engine (Pillow, no paid video APIs).

Camera model
------------
The map is placed on a 9:16 canvas with a "contain" fit, so zoom = 1.0 shows
the whole map (letterboxed over a blurred, darkened copy of itself). Higher
zoom scales the map up; the camera then keeps a chosen normalised point at
the centre of the frame. Panning is simply moving that centre point.
"""
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .config import ROOT
from .utils import clamp, ease_in_out, lerp, load_font, pulse


class MapEngine:
    def __init__(self, map_path, width, height, fps=30, max_zoom=4.0):
        self.W, self.H, self.fps = int(width), int(height), int(fps)
        self.base = Image.open(map_path).convert("RGB")
        self.base_w, self.base_h = self.base.size

        # scale at which the whole map is contained in the canvas
        self.contain = min(self.W / self.base_w, self.H / self.base_h)

        # a larger working copy keeps zoomed-in frames sharp
        self.max_zoom = max_zoom
        wf = self.contain * max_zoom
        ww, wh = self.base_w * wf, self.base_h * wf
        cap = 6000
        if max(ww, wh) > cap:
            k = cap / max(ww, wh)
            ww, wh = ww * k, wh * k
        self.work = self.base.resize((max(1, int(ww)), max(1, int(wh))), Image.LANCZOS)
        self.wf = self.work.width / self.base_w

        self.black = Image.new("RGB", (self.W, self.H), (0, 0, 0))
        self.bg = self._make_bg()
        self.vignette = self._make_vignette()
        self._fonts = {}

    # ------------------------------------------------------------- resources
    def _make_bg(self):
        k = max(self.W / self.base_w, self.H / self.base_h)
        bg = self.base.resize((max(1, int(self.base_w * k)), max(1, int(self.base_h * k))), Image.LANCZOS)
        left = (bg.width - self.W) // 2
        top = (bg.height - self.H) // 2
        bg = bg.crop((left, top, left + self.W, top + self.H))
        bg = bg.filter(ImageFilter.GaussianBlur(48))
        return Image.blend(bg, self.black, 0.45)

    def _make_vignette(self):
        try:
            import numpy as np
        except ImportError:
            return None
        ys, xs = np.ogrid[: self.H, : self.W]
        cx, cy = self.W / 2.0, self.H / 2.0
        dist = np.sqrt(((xs - cx) / cx) ** 2 + ((ys - cy) / cy) ** 2)
        alpha = np.clip((dist - 0.55) / 0.45, 0, 1) * 0.55 * 255
        return Image.fromarray(alpha.astype("uint8"), "L")

    def font(self, size, text=""):
        return load_font(size, text)

    # ---------------------------------------------------------------- camera
    def _scene_at(self, plan, t):
        scenes = plan["scenes"]
        for scene in scenes:
            if scene["start"] <= t < scene["end"]:
                span = max(1e-6, scene["end"] - scene["start"])
                return scene, clamp((t - scene["start"]) / span, 0.0, 1.0)
        return scenes[-1], 1.0

    def _camera(self, scene, progress):
        if scene["action"] == "full_map":
            return 0.5, 0.5, scene["zoom_from"]
        e = ease_in_out(progress)
        z = lerp(scene["zoom_from"], scene["zoom_to"], e)
        fx, fy = scene["from_xy"]
        tx, ty = scene["to_xy"]
        return lerp(fx, tx, e), lerp(fy, ty, e), z

    # ----------------------------------------------------------------- frames
    def _frame(self, plan, t, images, show_text):
        scene, progress = self._scene_at(plan, t)

        img_path = scene.get("_image_path")
        if scene["action"] == "image" and img_path:
            frame = self._image_frame(img_path, progress)
            return self._finish(frame, scene, t, show_text, None)

        cx, cy, z = self._camera(scene, progress)
        s = self.contain * z
        left = self.W / 2.0 - cx * self.base_w * s
        top = self.H / 2.0 - cy * self.base_h * s

        frame = self.bg.copy()

        wx0 = clamp((0 - left) * self.wf / s, 0, self.work.width)
        wy0 = clamp((0 - top) * self.wf / s, 0, self.work.height)
        wx1 = clamp((self.W - left) * self.wf / s, 0, self.work.width)
        wy1 = clamp((self.H - top) * self.wf / s, 0, self.work.height)

        if wx1 > wx0 and wy1 > wy0:
            crop = self.work.crop((int(wx0), int(wy0), int(wx1), int(wy1)))
            dx0 = left + wx0 / self.wf * s
            dy0 = top + wy0 / self.wf * s
            dx1 = left + wx1 / self.wf * s
            dy1 = top + wy1 / self.wf * s
            crop = crop.resize((max(1, int(dx1 - dx0)), max(1, int(dy1 - dy0))), Image.LANCZOS)
            frame.paste(crop, (int(dx0), int(dy0)))

        state = (left, top, s)
        return self._finish(frame, scene, t, show_text, state)

    def _image_frame(self, path, progress):
        try:
            img = Image.open(path).convert("RGB")
        except OSError:
            return self.bg.copy()
        k = max(self.W / img.width, self.H / img.height) * (1.0 + 0.12 * ease_in_out(progress))
        img = img.resize((max(1, int(img.width * k)), max(1, int(img.height * k))), Image.LANCZOS)
        left = (img.width - self.W) // 2
        top = (img.height - self.H) // 2
        return img.crop((left, top, left + self.W, top + self.H))

    def _finish(self, frame, scene, t, show_text, state):
        if state is not None:
            self._draw_overlays(frame, scene, t, state)
        if self.vignette is not None:
            frame = Image.composite(self.black, frame, self.vignette)
        if show_text and scene.get("text"):
            self._draw_title(frame, scene["text"])
        return frame

    # --------------------------------------------------------------- overlays
    def _to_canvas(self, xy, state):
        left, top, s = state
        return (left + xy[0] * self.base_w * s, top + xy[1] * self.base_h * s)

    def _draw_overlays(self, frame, scene, t, state):
        draw = ImageDraw.Draw(frame, "RGBA")
        unit = self.W / 1080.0

        if scene.get("highlight_xy"):
            x, y = self._to_canvas(scene["highlight_xy"], state)
            r = 130 * unit
            draw.ellipse([x - r, y - r, x + r, y + r], outline=(255, 210, 80), width=max(3, int(5 * unit)))

        route = scene.get("route") or []
        if len(route) >= 2:
            pts = [self._to_canvas(p["xy"], state) for p in route]
            progress = self._scene_at_progress(scene, t) * (len(pts) - 1)
            for i in range(len(pts) - 1):
                if progress <= i:
                    break
                frac = min(1.0, progress - i)
                a, b = pts[i], pts[i + 1]
                end = (a[0] + (b[0] - a[0]) * frac, a[1] + (b[1] - a[1]) * frac)
                draw.line([a, end], fill=(255, 90, 60), width=max(4, int(7 * unit)), joint="curve")

        for marker in scene.get("markers") or []:
            x, y = self._to_canvas(marker["xy"], state)
            base_r = 16 * unit
            pr = base_r * (1.4 + 1.1 * pulse(t))
            draw.ellipse([x - pr, y - pr, x + pr, y + pr], outline=(255, 80, 80), width=max(2, int(3 * unit)))
            draw.ellipse([x - base_r, y - base_r, x + base_r, y + base_r], fill=(255, 60, 60))
            if marker.get("name"):
                self._label(draw, frame, marker["name"], (x, y - base_r - 6 * unit))

        for label in scene.get("labels") or []:
            if label:
                self._label(draw, frame, label, (self.W * 0.5, self.H * 0.86), anchor_center=True)

    def _scene_at_progress(self, scene, t):
        span = max(1e-6, scene["end"] - scene["start"])
        return clamp((t - scene["start"]) / span, 0.0, 1.0)

    def _label(self, draw, frame, text, pos, anchor_center=False):
        unit = self.W / 1080.0
        font = self.font(int(40 * unit), text)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x, y = pos
        if anchor_center:
            x -= tw / 2
        pad = 10 * unit
        box = [x - pad, y - pad, x + tw + pad, y + th + pad]
        draw.rounded_rectangle(box, radius=int(10 * unit), fill=(0, 0, 0, 200))
        draw.text((x, y - bbox[1]), text, font=font, fill=(255, 255, 255))

    def _draw_title(self, frame, text):
        draw = ImageDraw.Draw(frame, "RGBA")
        unit = self.W / 1080.0
        font = self.font(int(58 * unit), text)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        x = (self.W - tw) / 2
        y = self.H * 0.06
        pad = 18 * unit
        draw.rounded_rectangle(
            [x - pad, y - pad, x + tw + pad, y + (bbox[3] - bbox[1]) + pad],
            radius=int(14 * unit),
            fill=(0, 0, 0, 170),
        )
        draw.text((x, y - bbox[1]), text, font=font, fill=(255, 255, 255))

    # ----------------------------------------------------------------- public
    def frames(self, plan, images=None, show_text=True):
        """Yield raw RGB24 frame bytes for the whole plan."""
        images = images or {}
        total = plan["duration"]
        count = int(round(total * self.fps))
        for i in range(count):
            t = i / self.fps
            frame = self._frame(plan, t, images, show_text)
            yield frame.tobytes()
