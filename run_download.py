"""Download only - skip scrape for already-known tracks"""
import os
from youtube_downloader import download_all

# Read the already-scraped playlist
playlist_path = r"C:\Users\xmozz\Desktop\SongDownloads\LikedSongs\playlist.txt"
if not os.path.isfile(playlist_path):
    print(f"Playlist not found: {playlist_path}")
    exit(1)

tracks = []
with open(playlist_path, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        if " - " in line:
            parts = line.split(" - ", 1)
            artist, title = parts[0].strip(), parts[1].strip()
        else:
            artist, title = "", line
        tracks.append({"artist": artist, "title": title})

print(f"Loaded {len(tracks)} tracks from playlist")

out = r"C:\Users\xmozz\Desktop\SongDownloads\LikedSongs"
successful, failed = download_all(tracks, output_dir=out, max_workers=3)

print(f"\n{'='*50}")
print("SUMMARY")
print(f"{'='*50}")
print(f"  Erfolgreich: {len(successful)}/{len(tracks)}")
print(f"  Fehlgeschlagen: {len(failed)}/{len(tracks)}")
print(f"  Speicherort: {out}")

if failed:
    print(f"\n  Fehlgeschlagene Tracks:")
    for t in failed:
        print(f"    - {t['artist']} - {t['title']}")
