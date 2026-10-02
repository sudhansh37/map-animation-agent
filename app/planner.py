"""Validate and normalise the animation plan coming back from Gemini.

Everything downstream can then trust the shape of the plan: sorted,
gap-free scenes, clamped coordinates, sane zoom values.
"""
from .utils import clamp

_VALID_ACTIONS = {"full_map", "zoom", "pan", "zoom_pan", "route", "image"}


def _xy(value, default=(0.5, 0.5)):
    if not value or not isinstance(value, (list, tuple)) or len(value) < 2:
        return [float(default[0]), float(default[1])]
    try:
        return [clamp(float(value[0]), 0.0, 1.0), clamp(float(value[1]), 0.0, 1.0)]
    except (TypeError, ValueError):
        return [float(default[0]), float(default[1])]


def _points(items):
    out = []
    for item in items or []:
        if isinstance(item, dict):
            out.append({"name": str(item.get("name", "")), "xy": _xy(item.get("xy"))})
    return out


def normalize_plan(plan: dict, duration=None, language=None) -> dict:
    if not isinstance(plan, dict):
        raise ValueError("Plan must be a JSON object")
    scenes = plan.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("Plan has no scenes")

    total = float(plan.get("duration") or duration or 45)

    clean = []
    for sc in scenes:
        if not isinstance(sc, dict):
            continue
        start = float(sc.get("start", 0) or 0)
        end = float(sc.get("end", start + 1) or (start + 1))
        action = str(sc.get("action", "full_map")).lower()
        if action not in _VALID_ACTIONS:
            action = "zoom_pan"
        from_xy = _xy(sc.get("from_xy"))
        to_xy = _xy(sc.get("to_xy"), from_xy)
        zoom_from = clamp(float(sc.get("zoom_from", 1.0) or 1.0), 1.0, 6.0)
        zoom_to = clamp(float(sc.get("zoom_to", zoom_from) or zoom_from), 1.0, 6.0)
        clean.append(
            {
                "start": start,
                "end": end,
                "action": action,
                "from_xy": from_xy,
                "to_xy": to_xy,
                "zoom_from": zoom_from,
                "zoom_to": zoom_to,
                "highlight_xy": _xy(sc["highlight_xy"]) if sc.get("highlight_xy") else None,
                "markers": _points(sc.get("markers")),
                "route": _points(sc.get("route")),
                "labels": [str(x) for x in (sc.get("labels") or [])],
                "text": str(sc.get("text", "") or ""),
                "transition": str(sc.get("transition", "fade") or "fade"),
                "image_prompt": sc.get("image_prompt") or None,
            }
        )

    if not clean:
        raise ValueError("No usable scenes after normalisation")

    clean.sort(key=lambda s: s["start"])

    # Make the timeline contiguous and end exactly on the target duration.
    clean[0]["start"] = 0.0
    for i, scene in enumerate(clean):
        if i > 0:
            scene["start"] = clean[i - 1]["end"]
        if scene["end"] <= scene["start"]:
            scene["end"] = scene["start"] + 1.0
    if total > clean[-1]["start"]:
        clean[-1]["end"] = total
    else:
        total = clean[-1]["end"]

    return {
        "title": str(plan.get("title", "") or "Untitled"),
        "hook": str(plan.get("hook", "") or ""),
        "language": str(plan.get("language", "") or (language or "")),
        "duration": total,
        "music_mood": str(plan.get("music_mood", "cinematic") or "cinematic"),
        "narration": str(plan.get("narration", "") or ""),
        "scenes": clean,
    }
