"""Narration audio via Gemini TTS (with an optional gTTS fallback).

The TTS model is resolved resiliently (env override -> configured -> a
candidate list), and the first model that works is reused for every chunk.
"""
import base64
import os
import re
import wave
from pathlib import Path

from .config import SECRETS, SETTINGS

SAMPLE_RATE = 24000  # Gemini TTS returns 24 kHz, 16-bit, mono PCM


def _client():
    from google import genai

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


def tts_model_candidates():
    env = os.getenv("GEMINI_TTS_MODEL", "").strip()
    configured = SETTINGS["gemini"].get("tts_model")
    candidates = SETTINGS["gemini"].get("tts_model_candidates", [])
    return _dedupe(([env] if env else []) + [configured] + list(candidates))


def _chunks(text: str, max_chars: int = 600):
    """Split narration on sentence boundaries so each TTS call stays small."""
    parts = [p for p in re.split(r"(?<=[।.!?])\s+", text.strip()) if p]
    if not parts:
        return [text]
    out, current = [], ""
    for part in parts:
        if len(current) + len(part) + 1 <= max_chars:
            current = (current + " " + part).strip()
        else:
            if current:
                out.append(current)
            current = part
    if current:
        out.append(current)
    return out


def _tts_config(voice):
    from google.genai import types

    return types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
            )
        ),
    )


def _tts_call(client, model, chunk, config) -> bytes:
    response = client.models.generate_content(model=model, contents=chunk, config=config)
    data = response.candidates[0].content.parts[0].inline_data.data
    if isinstance(data, str):
        data = base64.b64decode(data)
    return data


def _write_wav(path, pcm: bytes):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm)


def synthesize(text: str, out_wav, voice: str | None = None) -> str:
    """Generate narration audio and write it to out_wav. Returns the path."""
    voice = voice or SETTINGS["gemini"]["tts_voice"]
    client = _client()
    config = _tts_config(voice)
    models = tts_model_candidates()

    pcm = bytearray()
    chosen = None
    last_error = None
    for chunk in _chunks(text):
        if chosen is None:
            for model in models:
                try:
                    pcm.extend(_tts_call(client, model, chunk, config))
                    chosen = model
                    print(f"[tts] using model: {model}")
                    break
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    print(f"[tts] model {model} failed -> {exc}")
            if chosen is None:
                raise RuntimeError(f"All TTS models failed: {last_error}")
        else:
            pcm.extend(_tts_call(client, chosen, chunk, config))

    _write_wav(out_wav, bytes(pcm))
    return str(out_wav)


def synthesize_with_fallback(text: str, out_wav, voice=None) -> str:
    """Try Gemini TTS; if it fails, fall back to local gTTS if available."""
    try:
        return synthesize(text, out_wav, voice)
    except Exception as exc:  # noqa: BLE001 - we want to continue without audio
        print(f"[tts] Gemini TTS failed ({exc}); trying local fallback")
    try:
        from gtts import gTTS  # optional dependency

        mp3 = str(Path(out_wav).with_suffix(".mp3"))
        gTTS(text=text).save(mp3)
        return mp3
    except Exception as exc:  # noqa: BLE001
        print(f"[tts] Fallback TTS unavailable ({exc}); continuing without narration")
        return ""


def duration_of(wav_path) -> float:
    try:
        with wave.open(str(wav_path), "rb") as wav:
            return wav.getnframes() / float(wav.getframerate())
    except Exception:  # noqa: BLE001
        return 0.0
