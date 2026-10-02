"""Gemini is the 'brain': it analyses the map and writes the animation plan
and the YouTube metadata. Actual animation is done locally (see map_engine).
"""
import mimetypes
from pathlib import Path

from .config import ROOT, SECRETS, SETTINGS
from .utils import extract_json


def _client():
    from google import genai  # imported lazily so the module loads without the SDK

    if not SECRETS.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return genai.Client(api_key=SECRETS.gemini_api_key)


def _mime(path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "image/jpeg"


def _fill(template: str, mapping: dict) -> str:
    for key, value in mapping.items():
        template = template.replace(f"__{key}__", str(value))
    return template


def analyze_map(image_path, topic="", language=None, duration=None, style=None) -> dict:
    """Send the map to Gemini and get back the structured animation plan."""
    from google.genai import types

    language = language or SETTINGS["video"]["default_language"]
    duration = int(duration or SETTINGS["video"]["default_duration"])
    style = style or SETTINGS["video"]["default_style"]
    topic = topic or "Analyse this map and tell its story."

    template = (ROOT / "prompts" / "analysis.txt").read_text(encoding="utf-8")
    prompt = _fill(
        template,
        {"TOPIC": topic, "LANGUAGE": language, "DURATION": duration, "STYLE": style},
    )

    image_bytes = Path(image_path).read_bytes()
    image_part = types.Part.from_bytes(data=image_bytes, mime_type=_mime(image_path))

    client = _client()

    def _call():
        response = client.models.generate_content(
            model=SETTINGS["gemini"]["analysis_model"],
            contents=[prompt, image_part],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        return extract_json(response.text)

    try:
        return _call()
    except Exception:  # one retry, per the spec's error-handling rule
        return _call()


def generate_metadata(topic, title, hook, narration, language) -> dict:
    """Second (and final) Gemini request: YouTube metadata."""
    from google.genai import types

    template = (ROOT / "prompts" / "script.txt").read_text(encoding="utf-8")
    prompt = _fill(
        template,
        {
            "TOPIC": topic,
            "TITLE": title,
            "HOOK": hook,
            "NARRATION": narration,
            "LANGUAGE": language,
        },
    )
    client = _client()
    response = client.models.generate_content(
        model=SETTINGS["gemini"]["analysis_model"],
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return extract_json(response.text)
