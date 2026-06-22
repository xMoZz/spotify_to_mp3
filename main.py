#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

"""
Spotify Playlist Downloader - Main Script.

Workflow:
1. Reads Spotify track URLs from a text file (or STDIN)
2. Scrapes artist + title from Spotify Embed Pages
3. Searches for the songs on YouTube (prefers audio/lyrics)
4. Downloads them as MP3 into the out/ folder

Usage:
    python main.py playlist.txt
    python main.py --urls "https://open.spotify.com/track/..."
    (Without arguments: prompts for URLs via STDIN)
"""

import argparse
import os
import sys
import re
from pathlib import Path

from spotify_scraper import scrape_urls
from youtube_downloader import download_all


def parse_urls_from_text(text: str) -> list[str]:
    """Extract all Spotify URLs from a text."""
    return re.findall(r"https?://open\.spotify\.com/(?:track|local)/[^\s<>\"'()]+", text)


def read_input_file(path: str) -> list[str]:
    """Read a file and extract all Spotify URLs."""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    return parse_urls_from_text(text)


def main():
    parser = argparse.ArgumentParser(
        description="Spotify to YouTube MP3 Downloader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py playlist.txt
  python main.py --urls "https://open.spotify.com/track/ABCDEF"
  python main.py --out my_music
        """,
    )

    # Positional: optional filename (also treats as --input)
    parser.add_argument(
        "filename", nargs="?",
        help="File containing Spotify URLs (one per line or inline)",
    )
    parser.add_argument(
        "--urls", "-u",
        nargs="+",
        help="Spotify URLs directly as arguments",
    )
    parser.add_argument(
        "--out", "-o",
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"),
        help="Output directory (default: ./out/ next to main.py)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=10,
        help="Parallel scraper threads (default: 10)",
    )
    parser.add_argument(
        "--download-workers",
        type=int,
        default=3,
        help="Parallel downloads (default: 3)",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Only scrape (show artist + title), do not download",
    )

    args = parser.parse_args()

    # Collect URLs
    urls = []
    if args.urls:
        for u in args.urls:
            if os.path.isfile(u):
                urls.extend(read_input_file(u))
            else:
                urls.append(u)
    elif args.filename:
        urls = read_input_file(args.filename)
    else:
        # Interactive: prompt for URLs via STDIN
        print("[Spotify Playlist Downloader]")
        print("=" * 50)
        print("Paste Spotify URLs (one per line, empty line to start):")
        print("-" * 50)
        for line in sys.stdin:
            line = line.strip()
            if not line:
                break
            extracted = parse_urls_from_text(line)
            urls.extend(extracted)
        print("-" * 50)

    if not urls:
        print("[ERROR] No valid Spotify URLs found.")
        sys.exit(1)

    # Statistics
    track_urls = [u for u in urls if "/track/" in u]
    local_urls = [u for u in urls if "/local/" in u]
    unique_track_urls = list(dict.fromkeys(track_urls))

    print(f"\n[STATS] URLs found: {len(urls)} total")
    print(f"  Track URLs: {len(unique_track_urls)}")
    print(f"  Invalid URLs (skipped): {len(local_urls)}")

    if local_urls:
        for u in local_urls:
            print(f"    [SKIP] {u[:80]}...")

    # === Step 1: Scrape Spotify ===
    print(f"\n{'='*50}")
    print("[STEP 1] Scraping Spotify track info")
    print(f"{'='*50}")

    tracks = scrape_urls(unique_track_urls, max_workers=args.workers)
    valid_tracks = [t for t in tracks if t is not None]

    if not valid_tracks:
        print("\n[ERROR] Could not scrape any track info.")
        sys.exit(1)

    print(f"\n[TRACKS] Found tracks (first 5):")
    for t in valid_tracks[:5]:
        print(f"  - {t['artist']} - {t['title']}")
    if len(valid_tracks) > 5:
        print(f"  ... and {len(valid_tracks) - 5} more")

    # Output directory
    output_dir = args.out
    os.makedirs(output_dir, exist_ok=True)

    # Save playlist file
    playlist_path = os.path.join(output_dir, "playlist.txt")
    with open(playlist_path, "w", encoding="utf-8") as f:
        for t in valid_tracks:
            f.write(f"{t['artist']} - {t['title']}\n")
    print(f"\n[SAVED] Playlist saved: {playlist_path}")

    if args.no_download:
        print("\n[STOP] --no-download set. Done.")
        return

    # === Step 2: YouTube Downloads ===
    print(f"\n{'='*50}")
    print("[STEP 2] YouTube MP3 Downloads")
    print(f"{'='*50}")

    successful, failed = download_all(
        valid_tracks,
        output_dir=output_dir,
        max_workers=args.download_workers,
    )

    # === Final Summary ===
    print(f"\n{'='*50}")
    print("[SUMMARY]")
    print(f"{'='*50}")
    print(f"  Successful: {len(successful)}/{len(valid_tracks)}")
    print(f"  Failed: {len(failed)}/{len(valid_tracks)}")
    print(f"  Output: {output_dir}")

    if failed:
        print(f"\n  Failed tracks:")
        for t in failed:
            print(f"    - {t['artist']} - {t['title']}")

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
