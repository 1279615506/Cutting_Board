"""
Rumps-based macOS menu bar UI for clipboard history.
Compact menu design with reliable pasteback via osascript.
"""

import rumps
import logging
import subprocess
import threading
import time
from datetime import datetime
from pasteboard_utils import set_pasteboard_content
from storage import StorageManager

logger = logging.getLogger(__name__)

TYPE_ICONS = {
    "text": "📝",
    "image": "🖼",
    "file": "📁",
    "url": "🔗",
    "unknown": "📎",
}
PREVIEW_LEN = 28
MAX_DISPLAY = 10


def short_time(iso_ts):
    try:
        ts = datetime.fromisoformat(iso_ts)
        delta = datetime.now() - ts
        secs = int(delta.total_seconds())
        if secs < 0:
            return "刚刚"
        if secs < 60:
            return f"{secs}s"
        mins = secs // 60
        if mins < 60:
            return f"{mins}分"
        hrs = mins // 60
        if hrs < 24:
            return f"{hrs}时"
        return f"{hrs // 24}天"
    except Exception:
        return ""


def do_paste():
    script = 'tell application "System Events" to keystroke "v" using command down'
    try:
        subprocess.run(["osascript", "-e", script], timeout=2)
    except Exception as e:
        logger.warning(f"Paste failed: {e}")


class MenuBarApp(rumps.App):

    def __init__(self, monitor, storage=None):
        self._monitor = monitor
        self._storage = storage or StorageManager()

        super().__init__(
            name="📋",
            title=None,
            menu=self._build_menu(),
            quit_button=None,
        )

        self._monitor.add_callback(self._on_new_entry)
        logger.info("MenuBarApp ready")

    # ── Timer callbacks (driven by @rumps.timer decorators) ────────────

    @rumps.timer(0.5)
    def _poll_monitor(self, _=None):
        """Poll clipboard every 0.5s — started automatically by rumps."""
        try:
            self._monitor.poll()
        except Exception as e:
            logger.error(f"Poll error: {e}")

    @rumps.timer(2)
    def _refresh_menu(self, _=None):
        """Refresh menu every 2s — started automatically by rumps."""
        try:
            self._menu.clear()
            self.menu = self._build_menu()
        except Exception as e:
            logger.warning(f"Menu refresh error: {e}")

    def _on_new_entry(self, entry):
        logger.info(f"New: {entry['id']} | {entry['preview'][:30]}")
        self._refresh_menu()

    # ── menu builder ─────────────────────────────────────────────────

    def _build_menu(self):
        items = []
        recent = self._storage.get_recent_entries(MAX_DISPLAY)

        if recent:
            for entry in recent:
                icon = TYPE_ICONS.get(entry["type"], "📎")
                p = entry["preview"][:PREVIEW_LEN].replace("\n", " ")
                if len(entry["preview"]) > PREVIEW_LEN:
                    p += "…"
                t = short_time(entry["timestamp"])
                title = f"{icon} {p}  ({t})"

                def make_cb(eid):
                    return lambda _: self._on_select(eid)

                items.append(rumps.MenuItem(title=title, callback=make_cb(entry["id"])))
        else:
            items.append(rumps.MenuItem("（暂无记录，复制任意内容即可）", callback=None))

        items.append(rumps.separator)
        items.append(rumps.MenuItem("📂 打开历史文件夹", callback=self._open_folder))
        items.append(rumps.MenuItem("🗑 清空今天的历史", callback=self._clear_today))
        items.append(rumps.MenuItem("🗑 清空所有历史", callback=self._clear_all))
        items.append(rumps.separator)
        items.append(rumps.MenuItem(
            f"今日 {len(self._storage.get_today_entries())} 条  |  点击条目 → Cmd+V 粘贴",
            callback=None,
        ))
        items.append(rumps.separator)
        items.append(rumps.MenuItem("⏏ 退出", callback=self._quit))
        return items

    # ── actions ──────────────────────────────────────────────────────

    def _on_select(self, entry_id):
        entry = self._storage.get_entry_by_id(entry_id)
        if not entry:
            rumps.notification("历史粘贴板", "记录不存在", "")
            return

        logger.info(f"Select: {entry['type']} | {entry['preview'][:30]}")
        set_pasteboard_content(entry)

        if entry["type"] in ("text", "url"):
            threading.Thread(target=self._delayed_paste, daemon=True).start()

    def _delayed_paste(self):
        time.sleep(0.25)
        do_paste()

    def _open_folder(self, _):
        from pathlib import Path
        data_path = Path(__file__).parent / "data"
        subprocess.Popen(["open", str(data_path)])

    def _clear_today(self, _):
        self._storage.clear_today()
        self._refresh_menu()
        rumps.notification("历史粘贴板", "已清空", "今天的历史记录已删除")

    def _clear_all(self, _):
        self._storage.clear_all()
        self._refresh_menu()
        rumps.notification("历史粘贴板", "已清空", "所有历史记录已删除")

    def _quit(self, _):
        logger.info("Quit")
        rumps.quit_application()
