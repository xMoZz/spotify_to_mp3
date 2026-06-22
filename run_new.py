"""Run scrape + download for new playlist"""
import os, re
from spotify_scraper import scrape_urls
from youtube_downloader import download_all

with open("new_playlist.txt", "r") as f:
    urls = [l.strip() for l in f if l.strip()]

track_urls = [u for u in urls if "/track/" in u]
unique = list(dict.fromkeys(track_urls))
print(f"Unique track URLs: {len(unique)}")

# Scrape
tracks = scrape_urls(unique, max_workers=5)
valid = [t for t in tracks if t is not None]
print(f"Scraped: {len(valid)} tracks")

# Save playlist
out = r"C:\Users\xmozz\Desktop\SongDownloads"
fpath = os.path.join(out, "playlist.txt")
with open(fpath, "w", encoding="utf-8") as f:
    for t in valid:
        f.write(f"{t['artist']} - {t['title']}\n")
print(f"Playlist saved: {fpath}")

# Print first few
for t in valid[:10]:
    print(f"  {t['artist']} - {t['title']}")

# Now download
successful, failed = download_all(valid, output_dir=out, max_workers=3)
print(f"\nDone: {len(successful)}/{len(valid)} successful, {len(failed)} failed")
