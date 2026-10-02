"""Gemini is the 'brain': it analyses the map and writes the animation plan
and the YouTube metadata. Actual animation is done locally (see map_engine).

Model names are resolved resiliently: an env override, then the configured
model, then a candidate list, tried in order until one works. This keeps the
pipeline working across different Gemini model tiers/keys.
"""
import mimetypes
import os
from pathlib import Path

from .config import ROOT, SECRETS, SETTINGS
from .utils import extract_json


def _client():
    from google import genai  # imported lazily so the module loads without the SDK

    if not SECRETS.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return genai.Client(api_key=SECRETS.gemini_api_key)


def _dedupe(items):
    seen, out = set(), []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def text_model_candidates():
    env = os.getenv("GEMINI_MODEL", "").strip()
    configured = SETTINGS["gemini"].get("analysis_model")
    candidates = SETTINGS["gemini"].get("analysis_model_candidates", [])
    return _dedupe(([env] if env else []) + [configured] + list(candidates))


def available_models():
    """Best-effort list of model ids the key can see (for debugging)."""
    try:
        client = _client()
        names = []
        for model in client.models.list():
            name = getattr(model, "name", "") or ""
            names.append(name.replace("models/", ""))
        return names
    except Exception as exc:  # noqa: BLE001
        print(f"[analyzer] could not list models: {exc}")
        return []


def _mime(path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "image/jpeg"


def _fill(template: str, mapping: dict) -> str:
    for key, value in mapping.items():
        template = template.replace(f"__{key}__", str(value))
    return template


def _generate(client, models, contents, config, label):
    """Try each candidate model in order and return the first success."""
    errors = []
    for model in models:
        try:
            response = client.models.generate_content(model=model, contents=contents, config=config)
            print(f"[analyzer] {label}: using model {model}")
            return response
        except Exception as exc:  # noqa: BLE001 - try the next candidate
            errors.append(f"{model}: {exc}")
            print(f"[analyzer] {label}: model {model} failed -> {exc}")
    raise RuntimeError(f"All candidate models failed for {label}:\n" + "\n".join(errors))


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
    config = types.GenerateContentConfig(response_mime_type="application/json")
    client = _client()
    models = text_model_candidates()

    try:
        response = _generate(client, models, [prompt, image_part], config, "map analysis")
        return extract_json(response.text)
    except Exception as exc:  # one retry, per the spec's error-handling rule
        print(f"[analyzer] analysis attempt failed ({exc}); retrying once")
        response = _generate(client, models, [prompt, image_part], config, "map analysis (retry)")
        return extract_json(response.text)


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
    config = types.GenerateContentConfig(response_mime_type="application/json")
    client = _client()
    response = _generate(client, text_model_candidates(), prompt, config, "metadata")
    return extract_json(response.text)
