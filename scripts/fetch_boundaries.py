"""Fetch administrative-boundary GeoJSON for a region - NO API KEY needed.

India  : one file per state (district polygons).
World  : the geoBoundaries open API (country + admin level).

Examples:
    python scripts/fetch_boundaries.py --state "Kerala"
    python scripts/fetch_boundaries.py --state "Maharashtra" --out-dir assets/geo
    python scripts/fetch_boundaries.py --country IND --adm ADM2 --out-dir assets/geo
"""
import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

INDIA_STATES_URL = (
    "https://raw.githubusercontent.com/udit-001/india-maps-data/main/geojson/states/{slug}.geojson"
)
GEOBOUNDARIES_API = "https://www.geoboundaries.org/api/current/gbOpen/{iso3}/{adm}/"

HEADERS = {"User-Agent": "Mozilla/5.0 (map-animation-agent)"}


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")


def _download(url: str, out: Path) -> Path:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=90) as response:
        data = response.read()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return out


def fetch_india_state(state: str, out_dir: Path) -> Path:
    slug = slugify(state)
    out = Path(out_dir) / f"{slug}.geojson"
    _download(INDIA_STATES_URL.format(slug=slug), out)
    return out


def fetch_geoboundaries(iso3: str, adm: str, out_dir: Path) -> Path:
    api = GEOBOUNDARIES_API.format(iso3=iso3.upper(), adm=adm.upper())
    request = urllib.request.Request(api, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=90) as response:
        meta = json.load(response)
    url = meta.get("gjDownloadURL") or meta.get("simplifiedGeometryGeoJSON")
    if not url:
        raise RuntimeError(f"No GeoJSON link in geoBoundaries response for {iso3}/{adm}")
    out = Path(out_dir) / f"{iso3.lower()}-{adm.lower()}.geojson"
    _download(url, out)
    return out


def _report(path: Path) -> None:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    count = len(data.get("features", []))
    print(f"[fetch] saved {path}  ({count} features)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download boundary GeoJSON (no API key)")
    parser.add_argument("--state", help="Indian state name, e.g. 'Kerala'")
    parser.add_argument("--country", help="ISO-3 country code for geoBoundaries, e.g. IND")
    parser.add_argument("--adm", default="ADM2", help="Admin level for geoBoundaries (ADM0..ADM5)")
    parser.add_argument("--out-dir", default="assets/geo")
    args = parser.parse_args()

    if not args.state and not args.country:
        parser.error("give either --state or --country")

    out_dir = Path(args.out_dir)
    if args.state:
        _report(fetch_india_state(args.state, out_dir))
    if args.country:
        _report(fetch_geoboundaries(args.country, args.adm, out_dir))


if __name__ == "__main__":
    main()
