#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GUI for the Spotify → YouTube MP3 Downloader.
tkinter (standard library), no extra dependencies besides tqdm + yt-dlp.
"""

import os
import re
import sys
import time
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
        batches = [unique_urls[i:i + batch_size] for i in range(0, len(unique_urls), batch_size)]
        total_new_this_run = 0
        total_still_failed = 0

        print(f"\n{'='*50}")
        print(f"Processing {len(unique_urls)} URLs in {len(batches)} batches of {batch_size}")
        print(f"{'='*50}")

        for batch_idx, batch_urls in enumerate(batches, 1):
            if self.stop_requested:
                print("\n[STOP] Download cancelled.")
                return

            print(f"\n{'='*50}")
            print(f"[BATCH {batch_idx}/{len(batches)}] {len(batch_urls)} URLs")
            print(f"{'='*50}")

            # Scrape this batch (with auto-retry on rate-limit)
            max_scrape_rounds = 5
            scrape_round = 1
            pending_urls = batch_urls
            batch_tracks_accumulated = []

            while scrape_round <= max_scrape_rounds and pending_urls:
                if self.stop_requested:
                    print("\n[STOP] Download cancelled.")
                    return

                if scrape_round > 1:
                    wait = 120 if not tracks else 60
                    print(f"\n{'='*50}")
                    print(f"[RATE-LIMIT] Round {scrape_round-1} got {len(tracks)}/{original_pending}.")
                    print(f"  Waiting {wait}s before retry ({scrape_round}/{max_scrape_rounds})...")
                    print(f"  Remaining in batch: {len(pending_urls)} URLs")
                    print(f"{'='*50}")
                    time.sleep(wait)

                original_pending = len(pending_urls)
                tracks, failed_urls = scrape_urls(pending_urls, max_workers=10)

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
                os.makedirs(output_dir, exist_ok=True)
                with open(playlist_path, "w", encoding="utf-8") as f:
                    for entry in sorted(existing_entries):
                        f.write(entry + "\n")
            print(f"\n[PLAYLIST] {len(existing_entries)} total (+{len(new_in_batch)} new from batch {batch_idx})")

            # Download new tracks from this batch
            if new_in_batch:
                print(f"\n{'='*50}")
                print(f"[DOWNLOAD Batch {batch_idx}/{len(batches)}] {len(new_in_batch)} tracks")
                print(f"{'='*50}")

                successful, failed = download_all(
                    new_in_batch,
                    output_dir=output_dir,
                    max_workers=3,
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
            print(f"\n  [WARN] {total_still_failed} URLs still not scraped after all batches.")
            print(f"    Run again later — playlist resumes where it left off.")
        else:
            print("\n  All done. ✓")

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
