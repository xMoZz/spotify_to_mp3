"""Quick test of spotify_scraper"""
from spotify_scraper import fetch_track_info, extract_track_id

ids = ["2pgoFRo3xdakkhPwKe56jI", "6P9W5oSyfRBONP1nUV4b2U", "1fr92Vupmcs2vgLMFVQ7rd"]
for tid in ids:
    result = fetch_track_info(tid)
    if result:
        artist = result["artist"]
        title = result["title"]
        print(f"{artist} - {title}")
    else:
        print(f"FAILED: {tid}")
