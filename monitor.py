"""
Clipboard change monitor — polls NSPasteboard.changeCount() on the main run loop.
Does NOT use a background thread to avoid pyobjc/Cocoa threading issues.
"""

import logging
from pasteboard_utils import get_change_count, get_pasteboard_content
from storage import StorageManager

logger = logging.getLogger(__name__)


class ClipboardMonitor:
    """
    Polls NSPasteboard for changes. Designed to be driven by a rumps.Timer
    on the main run loop, avoiding all AppKit background-thread issues.

    Usage:
        monitor = ClipboardMonitor()
        timer = rumps.Timer(monitor.poll, 0.5)
        timer.start()
    """

    def __init__(self, storage=None):
        self.storage = storage or StorageManager()
        self._last_change_count = get_change_count()
        self._callbacks = []

        logger.info(
            f"ClipboardMonitor ready (initial change_count={self._last_change_count})"
        )

    def add_callback(self, callback):
        """Register a callback to be called when a new entry is added."""
        self._callbacks.append(callback)

    def poll(self, _=None):
        """
        Check for clipboard changes. Called by rumps.Timer on the main thread.
        Returns True if a new entry was added.
        """
        try:
            current_count = get_change_count()

            if current_count != self._last_change_count:
                self._last_change_count = current_count
                content = get_pasteboard_content()

                if content:
                    entry = self.storage.add_entry(
                        entry_type=content["type"],
                        data=content["data"],
                        metadata=content.get("metadata", {}),
                    )

                    if entry:
                        logger.info(
                            f"New clipboard entry: type={entry['type']}, "
                            f"preview={entry['preview'][:50]}"
                        )
                        # Notify callbacks
                        for cb in self._callbacks:
                            try:
                                cb(entry)
                            except Exception as e:
                                logger.warning(f"Callback error: {e}")
                        return True

        except Exception as e:
            logger.error(f"Monitor poll error: {e}")

        return False
