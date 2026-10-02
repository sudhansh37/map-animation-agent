"""Central configuration and secret loading.

Secrets come from environment variables (locally from a .env file, in
GitHub Actions from Repository Secrets). Nothing is ever hard-coded.
"""
import json
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # dotenv is optional at runtime
    def load_dotenv(*_args, **_kwargs):
        return False

# Project root = one level above this file's parent (app/ -> project/)
ROOT = Path(__file__).resolve().parent.parent

load_dotenv(ROOT / ".env")


def load_settings() -> dict:
    with open(ROOT / "config" / "settings.json", "r", encoding="utf-8") as fh:
        return json.load(fh)


SETTINGS = load_settings()


def resolution(settings: dict | None = None) -> tuple[int, int]:
    """Return (width, height) for the configured resolution preset."""
    settings = settings or SETTINGS
    name = settings["video"]["resolution"]
    preset = settings["resolution_presets"][name]
    return int(preset["width"]), int(preset["height"])


class Secrets:
    """Reads secrets from the environment. Empty string means 'not set'."""

    @staticmethod
    def _get(name: str) -> str:
        return os.getenv(name, "").strip()

    @property
    def gemini_api_key(self) -> str:
        return self._get("GEMINI_API_KEY")

    @property
    def youtube_client_id(self) -> str:
        return self._get("YOUTUBE_CLIENT_ID")

    @property
    def youtube_client_secret(self) -> str:
        return self._get("YOUTUBE_CLIENT_SECRET")

    @property
    def youtube_refresh_token(self) -> str:
        return self._get("YOUTUBE_REFRESH_TOKEN")

    @property
    def hf_token(self) -> str:
        return self._get("HF_TOKEN")


SECRETS = Secrets()
