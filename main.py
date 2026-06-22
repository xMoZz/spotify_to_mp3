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
import time
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

    # Output directory
    output_dir = args.out
    os.makedirs(output_dir, exist_ok=True)

    # === Load existing playlist for resume ===
    playlist_path = os.path.join(output_dir, "playlist.txt")
    existing_entries = set()
    if os.path.isfile(playlist_path):
        with open(playlist_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    existing_entries.add(line)
        print(f"\n[RESUME] Loaded {len(existing_entries)} tracks from existing playlist")

    # === Split into batches of 100 ===
    batch_size = 100
    all_urls = unique_track_urls
    batches = [all_urls[i:i + batch_size] for i in range(0, len(all_urls), batch_size)]
    total_new_this_run = 0
    total_still_failed = 0

    print(f"\n{'='*50}")
    print(f"Processing {len(all_urls)} URLs in {len(batches)} batches of {batch_size}")
    print(f"{'='*50}")

    for batch_idx, batch_urls in enumerate(batches, 1):
        print(f"\n{'='*50}")
        print(f"[BATCH {batch_idx}/{len(batches)}] {len(batch_urls)} URLs")
        print(f"{'='*50}")

        # Scrape this batch (with auto-retry on rate-limit)
        max_scrape_rounds = 5
        scrape_round = 1
        pending_urls = batch_urls
        batch_tracks_accumulated = []

        while scrape_round <= max_scrape_rounds and pending_urls:
            if scrape_round > 1:
                wait = 120 if not tracks else 60
                print(f"\n{'='*50}")
                print(f"[RATE-LIMIT] Round {scrape_round-1} got {len(tracks)}/{original_pending}.")
                print(f"  Waiting {wait}s before retry ({scrape_round}/{max_scrape_rounds})...")
                print(f"  Remaining in batch: {len(pending_urls)} URLs")
                print(f"{'='*50}")
                time.sleep(wait)

            original_pending = len(pending_urls)
            tracks, failed_urls = scrape_urls(pending_urls, max_workers=args.workers)

            if tracks:
                batch_tracks_accumulated.extend(tracks)

            pending_urls = failed_urls
            scrape_round += 1

        if pending_urls:
            total_still_failed += len(pending_urls)
            print(f"\n  [WARN] {len(pending_urls)} URLs in batch {batch_idx} still failed after {max_scrape_rounds} rounds.")

        # Merge batch tracks into playlist
        new_in_batch = []
        if batch_tracks_accumulated:
            new_in_batch = [t for t in batch_tracks_accumulated
                           if f"{t['artist']} - {t['title']}" not in existing_entries]
            total_new_this_run += len(new_in_batch)
            existing_entries.update(f"{t['artist']} - {t['title']}" for t in batch_tracks_accumulated)

            # Save playlist
            with open(playlist_path, "w", encoding="utf-8") as f:
                for entry in sorted(existing_entries):
                    f.write(entry + "\n")
        print(f"\n[PLAYLIST] {len(existing_entries)} total (+{len(new_in_batch)} new from batch {batch_idx})")

        # Download new tracks from this batch
        if not args.no_download and new_in_batch:
            print(f"\n{'='*50}")
            print(f"[DOWNLOAD Batch {batch_idx}/{len(batches)}] {len(new_in_batch)} tracks")
            print(f"{'='*50}")

            successful, failed = download_all(
                new_in_batch,
                output_dir=output_dir,
                max_workers=args.download_workers,
            )
            print(f"  -> {len(successful)}/{len(new_in_batch)} downloaded")

    # === Final Summary ===
    print(f"\n{'='*50}")
    print("[SUMMARY]")
    print(f"{'='*50}")
    print(f"  Playlist: {len(existing_entries)} total tracks")
    print(f"  New this run: {total_new_this_run}")
    print(f"  Output: {output_dir}")

    if total_still_failed:
        print(f"\n  ⚠ {total_still_failed} URLs still not scraped after all batches.")
        print(f"    Run again later — playlist resumes where it left off.")
        sys.exit(1)
    elif args.no_download:
        print("\n  [--no-download] Scraping only. Done.")
        return
    else:
        print("\n  All done. ✓")


if __name__ == "__main__":
    main()
