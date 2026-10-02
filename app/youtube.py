"""YouTube Data API upload using an OAuth refresh token.

No credentials are ever hard-coded - they come from the environment
(Repository Secrets in GitHub Actions).
"""
from .config import SECRETS


def _service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    if not (
        SECRETS.youtube_client_id
        and SECRETS.youtube_client_secret
        and SECRETS.youtube_refresh_token
    ):
        raise RuntimeError(
            "YouTube credentials incomplete: need YOUTUBE_CLIENT_ID, "
            "YOUTUBE_CLIENT_SECRET and YOUTUBE_REFRESH_TOKEN"
        )

    credentials = Credentials(
        token=None,
        refresh_token=SECRETS.youtube_refresh_token,
        client_id=SECRETS.youtube_client_id,
        client_secret=SECRETS.youtube_client_secret,
        token_uri="https://oauth2.googleapis.com/token",
    )
    return build("youtube", "v3", credentials=credentials)


def upload(video_path, title, description="", tags=None, category_id="27", privacy="private") -> dict:
    """Upload a video. privacy is one of: public, private, unlisted."""
    from googleapiclient.http import MediaFileUpload

    youtube = _service()
    body = {
        "snippet": {
            "title": (title or "Map Short")[:100],
            "description": (description or "")[:5000],
            "tags": tags or [],
            "categoryId": str(category_id),
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        _, response = request.next_chunk()
    return response
