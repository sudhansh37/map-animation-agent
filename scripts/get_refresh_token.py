"""One-time helper to obtain a YouTube refresh token.

Run locally (NOT in CI):
    python scripts/get_refresh_token.py

It opens a browser consent screen and prints the refresh token, which you
then store as the YOUTUBE_REFRESH_TOKEN secret.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def main() -> None:
    from google_auth_oauthlib.flow import InstalledAppFlow

    client_id = os.getenv("YOUTUBE_CLIENT_ID", "").strip()
    client_secret = os.getenv("YOUTUBE_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise SystemExit("Set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET in .env first.")

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    print("\nAdd this to your .env and to GitHub Repository Secrets:\n")
    print(f"YOUTUBE_REFRESH_TOKEN={credentials.refresh_token}\n")


if __name__ == "__main__":
    main()
