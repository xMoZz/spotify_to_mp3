#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GUI for the Spotify → YouTube MP3 Downloader.
tkinter (standard library), no extra dependencies besides tqdm + yt-dlp.
"""

import os
import re
import sys
import threading
import queue
import tkinter as tk
from tkinter import ttk, scrolledtext

from spotify_scraper import scrape_urls
from youtube_downloader import download_all


def parse_urls_from_text(text: str) -> list[str]:
    """Extract all Spotify URLs from a text."""
    return re.findall(r"https?://open\.spotify\.com/(?:track|local)/[^\s<>\"'()]+", text)


class PrintRedirector:
    """Captures print() output and routes it to a queue (thread-safe)."""
    def __init__(self, log_queue: queue.Queue):
        self.queue = log_queue

    def write(self, text: str):
        if text:
            self.queue.put(text)

    def flush(self):
        pass


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Spotify → YouTube MP3 Downloader")
        self.root.geometry("850x750")
        self.root.minsize(600, 500)

        # Queue for log messages from the worker thread
        self.log_queue = queue.Queue()

        # Build the GUI
        self._build_ui()

        # Start log polling (every 100ms)
        self._poll_log()

    def _build_ui(self):
        # === URL Input ===
        url_frame = ttk.LabelFrame(self.root, text="Spotify URLs", padding=10)
        url_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))

        self.urls_text = tk.Text(url_frame, wrap=tk.WORD, font=("Consolas", 10), height=12)
        self.urls_text.insert(tk.END, "https://open.spotify.com/track/...")
        self.urls_text.pack(fill=tk.BOTH, expand=True)

        # === Output Name ===
        name_frame = ttk.Frame(self.root, padding=10)
        name_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(name_frame, text="Output folder name:").pack(side=tk.LEFT, padx=(0, 8))
        self.name_entry = ttk.Entry(name_frame, font=("Consolas", 10))
        self.name_entry.insert(0, "LikedSongs")
        self.name_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Path preview (read-only)
        self.path_label = ttk.Label(name_frame, text="", foreground="gray")
        self.path_label.pack(side=tk.LEFT, padx=(8, 0))

        # Live path preview updates
        self.name_entry.bind("<KeyRelease>", self._update_path_preview)
        self._update_path_preview()

        # === Buttons ===
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill=tk.X, padx=10, pady=5)

        self.start_btn = ttk.Button(
            btn_frame, text="▶ Start Download", command=self._on_start
        )
        self.start_btn.pack(side=tk.LEFT)

        self.stop_btn = ttk.Button(
            btn_frame, text="Cancel", command=self._on_stop, state=tk.DISABLED
        )
        self.stop_btn.pack(side=tk.LEFT, padx=(8, 0))

        # === Log Output ===
        log_frame = ttk.LabelFrame(self.root, text="Log", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 10))

        self.log_text = scrolledtext.ScrolledText(
            log_frame, wrap=tk.WORD, font=("Consolas", 9), state=tk.DISABLED, height=15
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Color tags for log levels
        self.log_text.tag_config("ok", foreground="green")
        self.log_text.tag_config("fail", foreground="red")
        self.log_text.tag_config("info", foreground="blue")
        self.log_text.tag_config("warn", foreground="orange")

        # Worker thread reference
        self.worker = None
        self.stop_requested = False

    def _update_path_preview(self, event=None):
        name = self.name_entry.get().strip() or "?"
        base = os.path.dirname(os.path.abspath(__file__))
        out = os.path.join(base, "out", name)
        self.path_label.config(text=f"→ {out}")

    def _log(self, msg: str, tag: str = None):
        """Add a message to the log text widget (must be called from the main thread)."""
        self.log_text.config(state=tk.NORMAL)
        if tag:
            self.log_text.insert(tk.END, msg + "\n", tag)
        else:
            self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _poll_log(self):
        """Read all new log messages from the queue and write them to the text widget."""
        try:
            while True:
                msg = self.log_queue.get_nowait()
                # Simple tagging based on content
                tag = None
                if msg.startswith("[OK]") or "Successfully" in msg or "Successful" in msg:
                    tag = "ok"
                elif msg.startswith("[FAIL]") or msg.startswith("[ERROR]") or "Failed" in msg:
                    tag = "fail"
                elif msg.startswith("[INFO]"):
                    tag = "info"
                elif msg.startswith("[WARN]") or msg.startswith("[SKIP]"):
                    tag = "warn"
                self._log(msg.rstrip(), tag)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_log)

    def _on_start(self):
        """Start the download in a separate thread."""
        raw_text = self.urls_text.get("1.0", tk.END).strip()
        if not raw_text or raw_text == "https://open.spotify.com/track/...":
            self._log("[WARN] No URLs entered!", "warn")
            return

        urls = parse_urls_from_text(raw_text)
        if not urls:
            self._log("[WARN] No valid Spotify URLs found!", "warn")
            return

        name = self.name_entry.get().strip() or "Download"
        base_dir = os.path.dirname(os.path.abspath(__file__))
        output_dir = os.path.join(base_dir, "out", name)

        # UI state: disable buttons
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.stop_requested = False

        # Set up print() redirect
        self._old_stdout = sys.stdout
        sys.stdout = PrintRedirector(self.log_queue)

        self._log(f"[INFO] Starting download of {len(urls)} tracks → {output_dir}", "info")
        self._log("[INFO] Log output appears below.\n", "info")

        # Worker thread
        def worker():
            try:
                self._run(urls, output_dir)
            finally:
                # Restore print() redirect (in the main thread)
                self.root.after(0, self._restore_stdout)
                self.root.after(0, self._on_finished)

        self.worker = threading.Thread(target=worker, daemon=True)
        self.worker.start()

    def _run(self, urls: list[str], output_dir: str):
        """Run the actual download (executed in the worker thread)."""
        # Filter track URLs
        track_urls = [u for u in urls if "/track/" in u]
        unique_urls = list(dict.fromkeys(track_urls))

        if not unique_urls:
            print("[ERROR] No valid track URLs found.")
            return

        print(f"[STATS] {len(unique_urls)} unique track URLs found")

        # === Step 1: Scrape Spotify ===
        print("\n" + "=" * 50)
        print("[STEP 1] Scraping Spotify track info")
        print("=" * 50)

        tracks = scrape_urls(unique_urls, max_workers=10)
        valid_tracks = [t for t in tracks if t is not None]

        if not valid_tracks:
            print("\n[ERROR] Could not scrape any track info.")
            return

        # === Step 2: YouTube Downloads ===
        print(f"\n{'='*50}")
        print("[STEP 2] YouTube MP3 Downloads")
        print(f"{'='*50}")

        # Check if cancelled
        if self.stop_requested:
            print("\n[STOP] Download cancelled.")
            return

        os.makedirs(output_dir, exist_ok=True)

        successful, failed = download_all(
            valid_tracks,
            output_dir=output_dir,
            max_workers=3,
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

    def _restore_stdout(self):
        sys.stdout = self._old_stdout

    def _on_finished(self):
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self._log("\n[INFO] Download completed.\n", "info")

    def _on_stop(self):
        """Request cancellation."""
        self.stop_requested = True
        self._log("[WARN] Cancellation requested – running downloads will finish, but no new ones will start.", "warn")
        self.stop_btn.config(state=tk.DISABLED)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
