"""
discord_trigger.py — Inject Discord messages into ColaOS via mouse + keyboard

Reads pending messages from ~/.cola/channels/discord/pending.jsonl,
activates the Cola window, uses image recognition to find and click
the target chat in the sidebar, then pastes the message and presses Enter.

Config: trigger_config.json
  - navigation.mode = "image": uses pyautogui.locateOnScreen()
  - navigation.selectChat.image: screenshot of the chat entry in sidebar
  - navigation.focusInput.windowRelative: where to click for input focus

Setup:
  1. Screenshot only the "Discord Integration" text in Cola's sidebar
  2. Save as chat_sidebar_icon.png next to this script
  3. Run: python discord_trigger.py --watch

Usage:
    python discord_trigger.py           # run once
    python discord_trigger.py --watch   # poll every 2s

Dependencies:
    pip install pyautogui pyperclip opencv-python pillow
"""

import json
import os
import sys
import time
import ctypes
import ctypes.wintypes
from pathlib import Path


# ── Paths ──────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.resolve()
CONFIG_FILE = SCRIPT_DIR / "trigger_config.json"
PENDING_FILE = Path.home() / ".cola" / "channels" / "discord" / "pending.jsonl"
DONE_FILE = Path.home() / ".cola" / "channels" / "discord" / "triggered.jsonl"
COLA_CLASS = "Chrome_WidgetWin_1"
COLA_TITLE = "Cola"
POLL_INTERVAL_S = 2


# ── Config ─────────────────────────────────────────────────────────────
def load_config() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    return {
        "mod": "normal",
        "chatName": "Discord Integration",
        "triggerPrefix": "[Discord]",
        "navigation": {
            "mode": "image",
            "selectChat": {
                "method": "locateOnScreen",
                "image": "chat_sidebar_icon.png",
                "confidence": 0.8,
                "clickOffset": {"x": 0, "y": 0},
            },
            "focusInput": {
                "method": "clickAt",
                "windowRelative": {"x": 0.5, "y": 0.9},
            },
        },
    }


config = load_config()


# ── Win32 helpers ──────────────────────────────────────────────────────
user32 = ctypes.windll.user32


def find_cola_window():
    """Find Cola's main window. Returns (hwnd, rect) or (None, None)."""
    hwnd = user32.FindWindowW(COLA_CLASS, COLA_TITLE)
    if not hwnd:
        # Fallback: enumerate
        result = []

        def enum_callback(hwnd, lparam):
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if buf.value and "Cola" in buf.value:
                result.append(hwnd)
                return False
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_callback), 0)
        hwnd = result[0] if result else None

    if not hwnd:
        return None, None

    # Get window rect
    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    rect = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return hwnd, rect


def activate_cola_window(hwnd) -> bool:
    """Bring Cola window to foreground."""
    if not hwnd:
        return False
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.5)
    return True


# ── Image-based navigation ─────────────────────────────────────────────
def find_chat_on_screen() -> tuple | None:
    """Find the target chat entry using image recognition. Returns (x, y) center or None."""
    import pyautogui

    nav = config.get("navigation", {})
    select = nav.get("selectChat", {})
    image_name = select.get("image", "chat_sidebar_icon.png")
    confidence = select.get("confidence", 0.8)

    # Resolve image path: try script dir, then channels dir
    image_path = SCRIPT_DIR / image_name
    if not image_path.exists():
        alt = Path.home() / ".cola" / "channels" / "discord" / image_name
        if alt.exists():
            image_path = alt
        else:
            print(f"  ✗ Image not found: {image_path}")
            print(f"  → Screenshot the 'Discord Integration' text in Cola's sidebar")
            print(f"  → Save as: {image_path}")
            return None

    try:
        location = pyautogui.locateOnScreen(str(image_path), confidence=confidence)
        if location:
            offset = select.get("clickOffset", {"x": 0, "y": 0})
            x = location.left + location.width // 2 + offset.get("x", 0)
            y = location.top + location.height // 2 + offset.get("y", 0)
            return (x, y)
    except Exception as e:
        print(f"  ✗ Image recognition failed: {e}")
        print(f"  → Make sure 'pip install opencv-python' is done")

    return None


def click_chat_in_sidebar() -> bool:
    """Find and click the target chat in Cola's sidebar."""
    import pyautogui

    pos = find_chat_on_screen()
    if not pos:
        # Fallback: tell user what to do
        print("  ⚠ Could not find chat entry on screen.")
        print("  → Is the sidebar visible? Is Cola window in foreground?")
        print("  → Verify chat_sidebar_icon.png matches the actual sidebar text.")
        return False

    x, y = pos
    print(f"  🖱 Clicking chat at ({x}, {y})")
    pyautogui.click(x, y)
    time.sleep(0.3)
    return True


def click_input_area(hwnd, rect) -> bool:
    """Click the chat input area using window-relative coordinates."""
    import pyautogui

    nav = config.get("navigation", {})
    focus = nav.get("focusInput", {})
    relative = focus.get("windowRelative", {"x": 0.5, "y": 0.9})

    if rect:
        x = rect.left + int((rect.right - rect.left) * relative["x"])
        y = rect.top + int((rect.bottom - rect.top) * relative["y"])
    else:
        # Fallback: center-bottom of screen
        import pyautogui as pg
        x = pg.size()[0] // 2
        y = int(pg.size()[1] * 0.9)

    pyautogui.click(x, y)
    time.sleep(0.2)
    return True


# ── Message injection ──────────────────────────────────────────────────
def select_all_and_delete():
    """Clear any existing text in the input field."""
    import pyautogui
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.1)
    pyautogui.press("delete")
    time.sleep(0.1)


def inject_message(text: str) -> bool:
    """Paste text into the active Cola chat input and press Enter."""
    try:
        import pyperclip
        import pyautogui

        select_all_and_delete()
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.2)
        pyautogui.press("enter")
        return True
    except Exception as e:
        print(f"  ✗ Inject failed: {e}")
        return False


# ── Message queue ──────────────────────────────────────────────────────
def read_pending() -> list[dict]:
    if not PENDING_FILE.exists():
        return []
    try:
        lines = PENDING_FILE.read_text(encoding="utf-8").strip().split("\n")
        return [json.loads(line) for line in lines if line.strip()]
    except Exception as e:
        print(f"  ✗ Error reading pending: {e}")
        return []


def clear_pending():
    PENDING_FILE.write_text("", encoding="utf-8")


def archive_processed(messages: list[dict]):
    DONE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DONE_FILE.open("a", encoding="utf-8") as f:
        for msg in messages:
            msg["triggeredAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            f.write(json.dumps(msg) + "\n")


# ── Main ───────────────────────────────────────────────────────────────
def process_once() -> int:
    pending = read_pending()
    if not pending:
        return 0

    mod = config.get("mod", "normal")
    chat_name = config.get("chatName", "Discord Integration")
    prefix = config.get("triggerPrefix", "[Discord]")

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(f"[{now}] Processing {len(pending)} message(s) (mod={mod})")

    hwnd, rect = find_cola_window()
    if not hwnd:
        print("  ✗ Cola window not found. Is Cola running?")
        return 0

    if not activate_cola_window(hwnd):
        return 0

    # Navigate via mouse
    nav_mode = config.get("navigation", {}).get("mode", "image")
    if nav_mode == "image":
        if not click_chat_in_sidebar():
            return 0

    # Click input area to ensure focus
    click_input_area(hwnd, rect)
    time.sleep(0.2)

    for msg in pending:
        author = msg.get("author", "Cherrie")
        content = msg.get("content", "")
        text = f"{prefix} {author}: {content}"

        preview = text[:80] + ("..." if len(text) > 80 else "")
        print(f"  → Injecting: \"{preview}\"")
        inject_message(text)
        time.sleep(0.3)
        print("  ✓ Sent")

    archive_processed(pending)
    clear_pending()
    return len(pending)


def watch():
    mod = config.get("mod", "normal")
    chat = config.get("chatName", "Discord Integration")
    print(f"Discord trigger watching {PENDING_FILE}")
    print(f"  Mod: {mod} | Chat: {chat} | Poll: {POLL_INTERVAL_S}s")
    print("Press Ctrl+C to stop.\n")
    try:
        while True:
            try:
                process_once()
            except Exception as e:
                print(f"Error: {e}")
            time.sleep(POLL_INTERVAL_S)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    if "--watch" in sys.argv:
        watch()
    else:
        count = process_once()
        if count:
            print(f"Processed {count} messages.")
        else:
            print("No pending messages.")
