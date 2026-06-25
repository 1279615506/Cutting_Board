#!/usr/bin/env python3
"""
Clipboard History — macOS menu bar app for clipboard history.
Tracks all copied content throughout the day and lets you paste from history.
"""

import sys

# Set up logging FIRST — before any pyobjc imports that might configure handlers
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
    force=True,
)

from monitor import ClipboardMonitor
from storage import StorageManager
from ui import MenuBarApp


def main():
    logging.info("Starting Clipboard History...")

    # Single shared StorageManager — monitor writes, UI reads from the same instance
    storage = StorageManager()
    monitor = ClipboardMonitor(storage=storage)
    app = MenuBarApp(monitor, storage=storage)
    app.run()


if __name__ == "__main__":
    main()
