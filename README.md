# AI Map Animation Shorts — Automation Agent

Upload a map image (PNG/JPG). Gemini analyses it and returns a structured
animation plan; the video is then rendered **programmatically** with
Python + Pillow + FFmpeg (no paid video-generation API), narration is made
with Gemini TTS, and the finished 9:16 MP4 can be uploaded to YouTube.

```
MAP IMAGE -> GEMINI ANALYSIS -> PLAN JSON -> NARRATION -> RENDER -> 1080x1920 MP4 -> (YouTube)
```

## What it produces

- `output/video.mp4` — 9:16 H.264 MP4, configurable 720p / 1080p / 1440p / 2160p (4K)
- `output/thumbnail.jpg` — simple, readable Shorts thumbnail
- `output/metadata.json` — title, description, tags, category
- `output/plan.json` — the normalised animation plan (useful for debugging)

## Where the result shows up on GitHub

After every run the workflow copies the result into `videos/latest/` and commits
it back into the repository, so you can open it directly on GitHub (GitHub plays
MP4 files in the file view):

- `videos/latest/video.mp4`
- `videos/latest/thumbnail.jpg`
- `videos/latest/metadata.json`
- `videos/latest/plan.json`

The same files are also attached to the workflow run as the `map-short` artifact.

## API keys — what you need to add

Put these in a local `.env` (copy `.env.example`) **and** in the repository's
**Settings → Secrets and variables → Actions → Repository secrets**.

| Secret | Required? | What it is for | Where to get it |
|---|---|---|---|
| `GEMINI_API_KEY` | **Yes** | The "brain": map analysis, animation plan, metadata, and narration via Gemini TTS | https://aistudio.google.com/apikey |
| `YOUTUBE_CLIENT_ID` | Only for upload | OAuth 2.0 client id | Google Cloud Console → APIs & Services → Credentials |
| `YOUTUBE_CLIENT_SECRET` | Only for upload | OAuth 2.0 client secret | same as above |
| `YOUTUBE_REFRESH_TOKEN` | Only for upload | Long-lived token so CI can upload without a browser | run `python scripts/get_refresh_token.py` once, locally |
| `HF_TOKEN` | Optional | Only if you later switch the image engine to a Hugging Face model | https://huggingface.co/settings/tokens |

`ENABLE_IMAGE_GEN` is **not** a key — it is a flag (`true`/`false`) that turns
on the local open-source text-to-image engine (SD-Turbo, runs on CPU).

**Minimum to render a video: just `GEMINI_API_KEY`.** The three YouTube secrets
are only needed when you pass `--upload`.

Model names are resolved automatically: the code tries `GEMINI_MODEL` (env),
then the configured model, then a candidate list, until one works. Defaults
target the current Gemini 3.x line (`gemini-3.5-flash-lite` for analysis,
`gemini-3.8-flash-lite-tts` for speech). Override with `GEMINI_MODEL` /
`GEMINI_TTS_MODEL` if your key uses different models. If Gemini TTS is not
available on your key, narration falls back to gTTS automatically.

## Project layout

```
map-animation-agent/
├── app/
│   ├── main.py          # pipeline entry point (CLI)
│   ├── config.py        # settings + secret loading
│   ├── analyzer.py      # Gemini: map analysis + metadata
│   ├── planner.py       # validate / normalise the plan JSON
│   ├── map_engine.py    # programmatic zoom / pan / route / markers (Pillow)
│   ├── image_engine.py  # OPTIONAL local text-to-image (SD-Turbo)
│   ├── tts.py           # narration via Gemini TTS (+ gTTS fallback)
│   ├── subtitles.py     # optional SRT (captions are off by default)
│   ├── renderer.py      # FFmpeg composition + thumbnail
│   ├── youtube.py       # YouTube upload (refresh token)
│   └── utils.py         # shared helpers
├── prompts/             # analysis.txt, script.txt
├── config/settings.json # resolution, fps, models, feature flags
├── scripts/             # get_refresh_token.py
├── assets/              # music/ fonts/ generated/
├── input/               # put your map here
├── output/              # results
├── requirements.txt
├── .env.example
└── .github/workflows/generate.yml
```

## Local setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
sudo apt-get install -y ffmpeg fonts-noto-core fonts-noto-devanagari   # or your OS equivalent

cp .env.example .env        # then fill in GEMINI_API_KEY
```

Put a map in `input/`, then:

```bash
python -m app.main --topic "Mughal empire" --language Hindi --duration 45 \
                   --resolution 1080p --style "cinematic documentary"
```

Useful flags:

- `--map path/to/map.png` — pick a specific map (default: first file in `input/`)
- `--resolution 720p|1080p|1440p|2160p`
- `--no-tts` / `--no-music`
- `--images` — enable local text-to-image (needs the optional torch/diffusers install)
- `--upload --privacy public|private|unlisted`

## Running on GitHub Actions

1. Push this repo, then add the secrets from the table above.
2. **Actions → Generate Map Short → Run workflow.**
3. Optionally paste a `map_url` (a direct image link) or commit a map into `input/`.
4. When it finishes, download the `map-short` artifact (video, thumbnail, metadata).

## Notes and honest limits

- **Coordinates.** Gemini estimates each location's x,y on the map (0–1). It is
  good but not perfect — historical or stylised maps can be off. You can hand-edit
  `output/plan.json` and re-render if a scene lands wrong.
- **Resolution vs. source.** Output can be 4K, but real sharpness is capped by the
  source map (and any generated images). Zooming a small map will look soft.
- **Gemini TTS.** Uses a preview TTS model; check that your API key/tier has access.
- **YouTube.** Uploaded videos from an unaudited API project are locked to private
  until the project is verified, and the default quota allows only a few uploads/day.
- **Music.** Only use royalty-free tracks you have the right to use.
- **Captions** are off by default (`config/settings.json → features.captions`).
  Flip it to `true` to burn subtitles (needs a Devanagari-capable font for Hindi).

## Cost

Roughly **two Gemini requests per video** (analysis + metadata) plus TTS calls.
Everything visual is rendered locally, so there are no per-second video charges.
