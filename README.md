# Spotify Playlist Downloader

Converts Spotify playlists to MP3 files by scraping track info from Spotify and downloading the audio from YouTube.

## Features

- **No API keys required** — scrapes Spotify Embed Pages instead of using the Spotify/YouTube APIs
- **Smart search** — prefers audio/lyric videos over official music videos
- **Parallel processing** — scrapes and downloads multiple tracks simultaneously
- **CLI + GUI** — use from the terminal or the included graphical interface
- **Retry logic** — handles rate limits and temporary failures gracefully
- **MP3 metadata** — embedded artist and title tags

## Requirements

- Python 3.10+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) (`pip install yt-dlp`)
- [ffmpeg](https://ffmpeg.org/) (required by yt-dlp for MP3 conversion)
- [tqdm](https://github.com/tqdm/tqdm) (`pip install tqdm`)

### Installing ffmpeg

**Windows:**
```powershell
winget install ffmpeg
```

**Linux (Debian/Ubuntu):**
```bash
sudo apt install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

### Installing Python dependencies

```bash
pip install -r requirements.txt
```

## Usage

### CLI

```bash
# Download from a file containing Spotify URLs (one per line)
python main.py playlist.txt

# Specify a custom output folder
python main.py playlist.txt --out my_playlist

# Pass URLs directly
python main.py --urls "https://open.spotify.com/track/ABCDEF" "https://open.spotify.com/track/123456"

# Scrape only (no download) to preview tracks
python main.py playlist.txt --no-download

# Adjust concurrency
python main.py playlist.txt --workers 5 --download-workers 3
```

### GUI

```bash
python gui.py
```

A window will open where you can:
1. Paste your Spotify URLs into the text area (one per line or a block)
2. Enter an output folder name (default: `LikedSongs`)
3. Click "Start Download"
4. Watch the live log output

> **Tip:** In the Spotify desktop app (PC), you can hold `Shift` to select multiple songs in a playlist. Press `Ctrl + C` to copy all their links at once — then paste them directly into the text box or `playlist.txt`.

## Output Structure

```
spotify_playlist_downloader/
└── out/
    └── PlaylistName/
        ├── Artist - Title.mp3
        ├── Artist - Title.mp3
        └── playlist.txt
```

The `playlist.txt` file contains the scraped track list (artist - title) for reference.

## License

MIT
