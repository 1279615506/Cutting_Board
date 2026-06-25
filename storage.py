"""
JSON-based clipboard history storage with image file cache.
"""

import json
import os
import uuid
import logging
from datetime import datetime, date
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent / "data"
HISTORY_FILE = BASE_DIR / "history.json"
IMAGES_DIR = BASE_DIR / "images"
MAX_ENTRIES = 500
PREVIEW_MAX_LENGTH = 60


class StorageManager:
    """Manages clipboard history persistence."""

    def __init__(self):
        self._ensure_dirs()
        self._entries = self._load()

    def _ensure_dirs(self):
        """Create data directories if they don't exist."""
        BASE_DIR.mkdir(parents=True, exist_ok=True)
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    def _load(self):
        """Load history from JSON file."""
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load history: {e}")
        return []

    def _save(self):
        """Save history to JSON file."""
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self._entries, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error(f"Failed to save history: {e}")

    def add_entry(self, entry_type, data, metadata=None):
        """
        Add a new clipboard entry.
        Returns the new entry dict, or None if it should be skipped (duplicate of last).
        """
        metadata = metadata or {}

        # Deduplicate: skip if same type and content as the most recent entry
        if self._entries:
            last = self._entries[-1]
            if last["type"] == entry_type:
                if entry_type == "text" and last.get("content") == data:
                    # Same text, skip
                    return None
                if entry_type == "url" and last.get("content") == data:
                    return None

        entry = {
            "id": str(uuid.uuid4())[:8],
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "type": entry_type,
            "preview": "",
            "content": None,
            "image_path": None,
            "metadata": metadata,
        }

        if entry_type == "text":
            text = data if isinstance(data, str) else str(data)
            entry["content"] = text
            entry["preview"] = text[:PREVIEW_MAX_LENGTH].replace("\n", " ").strip()
            if len(text) > PREVIEW_MAX_LENGTH:
                entry["preview"] += "…"

        elif entry_type == "url":
            url = data if isinstance(data, str) else str(data)
            entry["content"] = url
            entry["preview"] = url[:PREVIEW_MAX_LENGTH]
            if len(url) > PREVIEW_MAX_LENGTH:
                entry["preview"] += "…"

        elif entry_type == "image":
            # Save the PIL Image to disk
            ts = datetime.now().strftime("%H-%M-%S-%f")[:15]
            filename = f"img_{ts}.png"
            filepath = IMAGES_DIR / filename
            try:
                data.save(filepath, format="PNG")
            except Exception as e:
                logger.warning(f"Failed to save image: {e}")
                # Try TIFF as fallback
                filename = f"img_{ts}.tiff"
                filepath = IMAGES_DIR / filename
                try:
                    data.save(filepath, format="TIFF")
                except Exception as e2:
                    logger.error(f"Failed to save image: {e2}")
                    return None
            entry["image_path"] = str(filepath)
            w = metadata.get("width", "?")
            h = metadata.get("height", "?")
            entry["preview"] = f"[图片] {w}×{h}"
            # Store content as None — image is on disk
            entry["content"] = None

        elif entry_type == "file":
            paths = data if isinstance(data, list) else [data]
            entry["content"] = paths
            if len(paths) == 1:
                entry["preview"] = f"📁 {os.path.basename(paths[0])}"
            else:
                entry["preview"] = f"📁 {len(paths)} 个文件"
                entry["content"] = paths  # store all paths

        else:
            entry["type"] = "unknown"
            entry["content"] = str(data)
            entry["preview"] = str(data)[:PREVIEW_MAX_LENGTH]

        self._entries.append(entry)

        # Trim to max entries
        while len(self._entries) > MAX_ENTRIES:
            removed = self._entries.pop(0)
            # Clean up image file for removed entry
            if removed.get("image_path") and os.path.exists(removed["image_path"]):
                try:
                    os.remove(removed["image_path"])
                except OSError:
                    pass

        self._save()
        return entry

    def get_recent_entries(self, n=20):
        """Return the most recent N entries."""
        return self._entries[-n:][::-1]  # newest first

    def get_today_entries(self):
        """Return today's entries (newest first)."""
        today_str = date.today().isoformat()
        today_entries = [
            e for e in self._entries if e["timestamp"].startswith(today_str)
        ]
        return today_entries[::-1]

    def get_entry_by_id(self, entry_id):
        """Find an entry by its ID."""
        for e in self._entries:
            if e["id"] == entry_id:
                return e
        return None

    def clear_today(self):
        """Remove all entries from today and their associated image files."""
        today_str = date.today().isoformat()
        removed = []
        kept = []
        for e in self._entries:
            if e["timestamp"].startswith(today_str):
                removed.append(e)
            else:
                kept.append(e)

        # Delete images for removed entries
        for e in removed:
            if e.get("image_path") and os.path.exists(e["image_path"]):
                try:
                    os.remove(e["image_path"])
                except OSError:
                    pass

        self._entries = kept
        self._save()
        logger.info(f"Cleared {len(removed)} entries from today")

    def clear_all(self):
        """Remove all entries and image files."""
        for e in self._entries:
            if e.get("image_path") and os.path.exists(e["image_path"]):
                try:
                    os.remove(e["image_path"])
                except OSError:
                    pass
        self._entries = []
        self._save()
        logger.info("Cleared all entries")

    def cleanup_old_images(self, max_age_days=2):
        """Remove image files older than max_age_days that are no longer referenced."""
        from datetime import timedelta

        cutoff = datetime.now() - timedelta(days=max_age_days)
        referenced_paths = {e.get("image_path") for e in self._entries if e.get("image_path")}

        if IMAGES_DIR.exists():
            for img_file in IMAGES_DIR.iterdir():
                if img_file.is_file():
                    img_path = str(img_file)
                    if img_path not in referenced_paths:
                        mtime = datetime.fromtimestamp(img_file.stat().st_mtime)
                        if mtime < cutoff:
                            try:
                                img_file.unlink()
                                logger.debug(f"Cleaned up orphaned image: {img_file.name}")
                            except OSError:
                                pass

    def __len__(self):
        return len(self._entries)
