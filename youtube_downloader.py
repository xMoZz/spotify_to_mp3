"""
youtube_downloader.py — Searches songs on YouTube and downloads them as MP3.
Prefers audio/lyric videos, avoids official music videos.
"""

import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm


def sanitize_filename(name: str) -> str:
    """Remove characters that cause issues in filenames."""
    return re.sub(r'[<>:"/\\|?*]', "", name).strip()


def download_song(
    artist: str,
    title: str,
    output_dir: str,
    track_id: str = None,
    timeout: int = 120,
) -> bool:
    """
    Search a song on YouTube and download it as MP3.

    Search strategy:
    1. "Artist Title lyrics" — lyric videos are usually audio-only
    2. "Artist Title audio" — fallback
    3. "Artist Title" — last resort

    Returns: True on success, False on failure
    """
    if not artist and not title:
        return False

    sanitized = sanitize_filename(f"{artist} - {title}" if artist else title)
    output_template = os.path.join(output_dir, f"{sanitized}.%(ext)s")

    # Search queries in order of preference
    queries = []
    if artist and title:
        queries.append(f"{artist} {title} lyrics")
        queries.append(f"{artist} {title} audio")
        queries.append(f"{artist} {title}")
    elif title:
        queries.append(f"{title} lyrics")
        queries.append(f"{title} audio")
        queries.append(title)

    expected_file = os.path.join(output_dir, f"{sanitized}.mp3")

    # Resume: skip if MP3 already exists
    if os.path.isfile(expected_file):
        return True

    for query in queries:
        search_string = f"ytsearch1:{query}"

        try:
            result = subprocess.run(
                ["yt-dlp",
                 "--extract-audio",
                 "--audio-format", "mp3",
                 "--audio-quality", "0",
                 "--output", output_template,
                 "--no-playlist",
                 "--add-metadata",
                 "--default-search", "ytsearch",
                 "--ignore-errors",
                 "--quiet",
                 search_string],
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if result.returncode == 0 and os.path.isfile(expected_file):
                return True

            # Debug: print why it failed
            label = f"{artist} - {title}" if artist else title
            if result.returncode != 0:
                err = result.stderr.strip()[:200] if result.stderr else "unknown error"
                print(f"  [yt-dlp error] {label}: exit={result.returncode}, {err}")
                if "javascript runtime" in err.lower() or "js runtime" in err.lower():
                    print(f"     → Install deno: winget install deno  (or: npm install -g deno)")
            elif not os.path.isfile(expected_file):
                # File wasn't created - check what IS in the output dir
                try:
                    files = os.listdir(output_dir) if os.path.isdir(output_dir) else []
                except Exception:
                    files = []
                similar = [f for f in files if sanitized[:20].lower() in f.lower()]
                hint = f" (similar files: {similar[:3]})" if similar else ""
                print(f"  [yt-dlp error] {label}: MP3 not found at {expected_file}{hint}")

        except subprocess.TimeoutExpired:
            continue
        except FileNotFoundError:
            print("  [ERROR] yt-dlp not found! Please install: pip install yt-dlp")
            return False
        except Exception as e:
            continue

    return False


def download_all(
    tracks: list[dict],
    output_dir: str,
    max_workers: int = 3,
) -> tuple[list[dict], list[dict]]:
    """
    Downloads a list of tracks in parallel.

    tracks: list of dicts with keys: artist, title, track_id
    output_dir: target directory
    max_workers: parallel downloads (low due to YouTube rate limits)

    Returns: (successful, failed) — lists of track dicts respectively
    """
    os.makedirs(output_dir, exist_ok=True)

    successful = []
    failed = []
    total = len([t for t in tracks if t is not None])

    if total == 0:
        print("  [WARN] No tracks to download")
        return successful, failed

    print(f"\n  -> Starting downloads ({total} tracks, {max_workers} parallel)")
    print(f"  -> Target: {output_dir}\n")

    valid_tracks = [t for t in tracks if t is not None]

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {
            pool.submit(
                download_song,
                t["artist"],
                t["title"],
                output_dir,
                t.get("track_id"),
            ): t
            for t in valid_tracks
        }

        with tqdm(total=total, desc="  YouTube Downloads", unit="track", ncols=80) as pbar:
            for future in as_completed(future_map):
                track = future_map[future]
                label = f"{track['artist']} - {track['title']}"

                try:
                    ok = future.result()
                except Exception:
                    ok = False

                if ok:
                    successful.append(track)
                    pbar.set_postfix_str("OK", refresh=False)
                else:
                    failed.append(track)
                    pbar.write(f"  [FAIL] {label}")

                pbar.update(1)

    return successful, failed
