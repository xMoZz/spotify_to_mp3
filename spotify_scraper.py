"""
spotify_scraper.py — Extracts artist + title from Spotify track URLs.
Uses the Embed Page (open.spotify.com/embed/track/<ID>), which contains
a __NEXT_DATA__ JSON payload.
With retry logic and session management for better success rate.
"""

import re
import json
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
from tqdm import tqdm


def extract_track_id(url: str) -> str | None:
    """Extract the Spotify track ID from a URL."""
    if "/track/" not in url:
        return None
    match = re.search(r"/track/([a-zA-Z0-9]+)", url)
    return match.group(1) if match else None


def fetch_track_info(track_id: str, timeout: int = 15, max_retries: int = 1) -> dict | None:
    """
    Fetch the Spotify Embed Page for a track ID and parse
    artist + title from the __NEXT_DATA__ JSON.
    With retry logic and random delays.
    """
    embed_url = f"https://open.spotify.com/embed/track/{track_id}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    for attempt in range(max_retries):
        try:
            # Random delay before each request (except the first)
            if attempt > 0:
                delay = random.uniform(1.0, 3.0) * (attempt ** 1.5)
                time.sleep(delay)

            req = Request(embed_url, headers=headers)
            with urlopen(req, timeout=timeout) as resp:
                html = resp.read().decode("utf-8", errors="replace")

            # Extract __NEXT_DATA__ JSON
            match = re.search(
                r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
                html,
                re.DOTALL,
            )
            if not match:
                if attempt < max_retries - 1:
                    continue
                return None

            data = json.loads(match.group(1))
            entity = data.get("props", {}).get("pageProps", {}).get("state", {}).get("data", {}).get("entity", {})

            if not entity or entity.get("type") != "track":
                if attempt < max_retries - 1:
                    continue
                return None

            title = entity.get("name") or entity.get("title") or ""
            artists = entity.get("artists", [])
            artist = artists[0].get("name", "") if artists else ""

            return {"track_id": track_id, "artist": artist.strip(), "title": title.strip()}

        except HTTPError as e:
            if e.code == 429:  # Rate Limited
                wait = float(e.headers.get("Retry-After", 5))
                time.sleep(wait + random.uniform(1, 3))
                continue
            elif attempt < max_retries - 1:
                time.sleep(random.uniform(2, 4))
                continue
            return None
        except (URLError, json.JSONDecodeError, KeyError, IndexError, TimeoutError):
            if attempt < max_retries - 1:
                time.sleep(random.uniform(1, 3))
                continue
            return None

    return None


def scrape_urls(urls: list[str], max_workers: int = 5) -> tuple[list[dict], list[str]]:
    """
    Takes a list of Spotify URLs, extracts track IDs,
    scrapes artist + title in parallel, and returns results.

    Returns: (successful_tracks, failed_urls)
             successful_tracks: list of dicts with keys: track_id, artist, title
             failed_urls: list of original URLs that could not be scraped
    """
    # Extract track IDs, keep mapping back to original URL
    track_ids = []
    url_for_track_id = {}
    skipped = []
    for url in urls:
        tid = extract_track_id(url)
        if tid and tid not in track_ids:
            track_ids.append(tid)
            url_for_track_id[tid] = url
        elif not tid:
            skipped.append(url)

    if skipped:
        print(f"  [SKIP] {len(skipped)} invalid/local URLs skipped")

    if not track_ids:
        return [], []

    # Parallel scraping (lower concurrency due to rate limits)
    results = [None] * len(track_ids)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {pool.submit(fetch_track_info, tid): i for i, tid in enumerate(track_ids)}

        with tqdm(total=len(track_ids), desc="  Scraping Spotify", unit="track", ncols=80) as pbar:
            for future in as_completed(future_map):
                idx = future_map[future]
                try:
                    result = future.result()
                    results[idx] = result
                except Exception:
                    results[idx] = None
                pbar.update(1)

    # Separate successful and failed
    successful_tracks = []
    failed_urls = []
    for i, tid in enumerate(track_ids):
        if results[i] is not None:
            successful_tracks.append(results[i])
        else:
            failed_urls.append(url_for_track_id[tid])

    # Stats
    print(f"  [OK] {len(successful_tracks)}/{len(track_ids)} tracks scraped successfully")
    if successful_tracks:
        first = successful_tracks[0]
        print(f"     First: {first['artist']} - {first['title']}")
    if failed_urls:
        print(f"  [RATE-LIMIT] {len(failed_urls)} tracks failed (rate-limited or unavailable)")

    return successful_tracks, failed_urls
