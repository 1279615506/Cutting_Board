"""
Low-level NSPasteboard read/write wrapper using pyobjc.
Supports text, images, file references, and URLs.
"""

import logging
from AppKit import (
    NSPasteboard,
    NSPasteboardTypeString,
    NSPasteboardTypeTIFF,
    NSPasteboardTypePNG,
    NSPasteboardTypeURL,
    NSPasteboardTypeFileURL,
)
from Foundation import NSURL
from PIL import Image
import io

logger = logging.getLogger(__name__)

# Legacy type for file paths (still widely used)
NSFilenamesPboardType = "NSFilenamesPboardType"


def get_change_count():
    """Return the current pasteboard change count. Increments on every copy/paste."""
    pb = NSPasteboard.generalPasteboard()
    return pb.changeCount()


def get_pasteboard_content():
    """
    Read the current pasteboard content.
    Returns a dict: {"type": str, "data": any, "metadata": dict}
    Types: "text", "image", "file", "url", "unknown"
    Returns None if pasteboard is empty or unreadable.
    """
    pb = NSPasteboard.generalPasteboard()
    available_types = pb.types()

    if not available_types:
        return None

    # --- Image ---
    if NSPasteboardTypeTIFF in available_types:
        try:
            tiff_data = pb.dataForType_(NSPasteboardTypeTIFF)
            if tiff_data:
                img_bytes = tiff_data.bytes().tobytes()
                image = Image.open(io.BytesIO(img_bytes))
                return {
                    "type": "image",
                    "data": image,
                    "metadata": {
                        "width": image.width,
                        "height": image.height,
                        "format": image.format or "TIFF",
                    },
                }
        except Exception as e:
            logger.warning(f"Failed to read image from pasteboard: {e}")

    # --- File references ---
    if NSFilenamesPboardType in available_types:
        try:
            file_paths = pb.propertyListForType_(NSFilenamesPboardType)
            if file_paths:
                return {
                    "type": "file",
                    "data": list(file_paths),
                    "metadata": {"count": len(file_paths)},
                }
        except Exception as e:
            logger.warning(f"Failed to read file paths from pasteboard: {e}")

    # --- File URL (modern API) ---
    if NSPasteboardTypeFileURL in available_types:
        try:
            file_urls = pb.propertyListForType_(NSPasteboardTypeFileURL)
            if file_urls:
                # Convert file:// URLs to paths
                paths = []
                for url_str in file_urls:
                    ns_url = NSURL.URLWithString_(url_str)
                    if ns_url and ns_url.path():
                        paths.append(ns_url.path())
                if paths:
                    return {
                        "type": "file",
                        "data": paths,
                        "metadata": {"count": len(paths)},
                    }
        except Exception as e:
            logger.warning(f"Failed to read file URLs from pasteboard: {e}")

    # --- URL ---
    if NSPasteboardTypeURL in available_types:
        try:
            url_str = pb.stringForType_(NSPasteboardTypeURL)
            if url_str:
                return {
                    "type": "url",
                    "data": url_str,
                    "metadata": {},
                }
        except Exception as e:
            logger.warning(f"Failed to read URL from pasteboard: {e}")

    # --- Plain text (check last, since images/files may also carry string types) ---
    if NSPasteboardTypeString in available_types:
        try:
            text = pb.stringForType_(NSPasteboardTypeString)
            if text:
                return {
                    "type": "text",
                    "data": text,
                    "metadata": {"length": len(text)},
                }
        except Exception as e:
            logger.warning(f"Failed to read text from pasteboard: {e}")

    # --- Unknown ---
    logger.debug(f"No recognized type found. Available types: {available_types}")
    return None


def set_pasteboard_content(entry):
    """
    Write clipboard content back from a history entry.
    entry is a dict with keys: type, content, image_path
    """
    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()

    entry_type = entry.get("type")

    if entry_type == "text":
        content = entry.get("content", "")
        pb.setString_forType_(content, NSPasteboardTypeString)

    elif entry_type == "url":
        url = entry.get("content", "")
        pb.setString_forType_(url, NSPasteboardTypeString)
        pb.setString_forType_(url, NSPasteboardTypeURL)

    elif entry_type == "image":
        image_path = entry.get("image_path", "")
        if image_path:
            try:
                img = Image.open(image_path)
                # Write as PNG first (most compatible)
                png_buffer = io.BytesIO()
                img.convert("RGBA").save(png_buffer, format="PNG")
                png_data = png_buffer.getvalue()
                pb.setData_forType_(png_data, NSPasteboardTypePNG)

                # Also write as TIFF for older apps
                tiff_buffer = io.BytesIO()
                img.save(tiff_buffer, format="TIFF")
                tiff_data = tiff_buffer.getvalue()
                pb.setData_forType_(tiff_data, NSPasteboardTypeTIFF)
            except Exception as e:
                logger.warning(f"Failed to write image to pasteboard: {e}")

    elif entry_type == "file":
        paths = entry.get("content", [])
        if isinstance(paths, str):
            paths = [paths]
        if paths:
            # Write file paths (legacy NSFilenamesPboardType)
            pb.setPropertyList_forType_(paths, NSFilenamesPboardType)
            # Also write file URLs (modern API)
            url_strings = []
            for p in paths:
                ns_url = NSURL.fileURLWithPath_(p)
                url_strings.append(ns_url.absoluteString())
            if url_strings:
                pb.setPropertyList_forType_(url_strings, NSPasteboardTypeFileURL)

    else:
        logger.warning(f"Unknown entry type: {entry_type}")
        # Fallback: try to write as string
        pb.setString_forType_(str(entry.get("content", "")), NSPasteboardTypeString)


def simulate_paste():
    """
    Simulate Cmd+V keystroke using CGEvent to paste into the frontmost app.
    Requires Accessibility permissions.
    """
    try:
        from Quartz import (
            CGEventCreateKeyboardEvent,
            CGEventPost,
            kCGHIDEventTap,
            kCGEventFlagMaskCommand,
        )

        # Cmd key down
        cmd_down = CGEventCreateKeyboardEvent(None, 0x37, True)  # 0x37 = left command
        CGEventPost(kCGHIDEventTap, cmd_down)

        # V key down with Cmd modifier
        v_down = CGEventCreateKeyboardEvent(None, 0x09, True)  # 0x09 = V
        from Quartz import CGEventSetFlags
        CGEventSetFlags(v_down, kCGEventFlagMaskCommand)
        CGEventPost(kCGHIDEventTap, v_down)

        # V key up
        v_up = CGEventCreateKeyboardEvent(None, 0x09, False)
        CGEventPost(kCGHIDEventTap, v_up)

        # Cmd key up
        cmd_up = CGEventCreateKeyboardEvent(None, 0x37, False)
        CGEventPost(kCGHIDEventTap, cmd_up)

        logger.info("Simulated Cmd+V paste")
    except ImportError as e:
        logger.warning(f"Cannot simulate paste (missing Quartz): {e}")
    except Exception as e:
        logger.warning(f"Failed to simulate paste: {e}")
