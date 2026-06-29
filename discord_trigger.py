"""
discord_trigger.py — Inject Discord messages into ColaOS via keyboard simulation

Reads pending messages from ~/.cola/channels/discord/pending.jsonl,
activates the Cola window, pastes the message, and presses Enter.
Cola's agent processes it with full capabilities (tools, memory bank).

Usage:
    python discord_trigger.py           # run once
    python discord_trigger.py --watch   # poll every 2s

Dependencies:
    pip install pyautogui pyperclip
"""

import json
import os
import sys
import time
import ctypes
import ctypes.wintypes
from pathlib import Path


# ── Constants ──────────────────────────────────────────────────────────
PENDING_FILE = Path.home() / ".cola" / "channels" / "discord" / "pending.jsonl"
DONE_FILE = Path.home() / ".cola" / "channels" / "discord" / "triggered.jsonl"
COLA_CLASS = "Chrome_WidgetWin_1"
COLA_TITLE = "Cola"
POLL_INTERVAL_S = 2


# ── Win32 helpers (no pyautogui needed for window activation) ──────────
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

SW_RESTORE = 9
SW_SHOW = 5


def find_cola_window():
    """Find Cola's main window handle. Returns hwnd or None."""
    hwnd = user32.FindWindowW(COLA_CLASS, COLA_TITLE)
    if hwnd:
        return hwnd
    # Fallback: enumerate windows
    result = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

    def enum_callback(hwnd, lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        if title and "Cola" in title:
            result.append(hwnd)
            return False  # stop
        return True

    user32.EnumWindows(WNDENUMPROC(enum_callback), 0)
    return result[0] if result else None


def activate_cola_window():
    """Bring Cola window to foreground."""
    hwnd = find_cola_window()
    if not hwnd:
        print("  ✗ Cola window not found. Is Cola running?")
        return False
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.5)
    return True


def type_message(text: str):
    """Paste text into the active window and press Enter."""
    try:
        import pyperclip
        pyperclip.copy(text)
    except ImportError:
        print("  ⚠ pyperclip not installed, using SendKeys fallback")
        # Fallback: very slow char-by-char
        import pyautogui
        pyautogui.write(text, interval=0.01)
        pyautogui.press("enter")
        return

    # Clipboard paste → Enter
    import pyautogui
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.2)
    pyautogui.press("enter")


# ── Message queue ──────────────────────────────────────────────────────
def read_pending() -> list[dict]:
    """Read all pending messages from the JSONL file."""
    if not PENDING_FILE.exists():
        return []
    try:
        lines = PENDING_FILE.read_text(encoding="utf-8").strip().split("\n")
        return [json.loads(line) for line in lines if line.strip()]
    except Exception as e:
        print(f"  ✗ Error reading pending file: {e}")
        return []


def clear_pending():
    """Clear the pending file."""
    PENDING_FILE.write_text("", encoding="utf-8")


def archive_processed(messages: list[dict]):
    """Append processed messages to the done log."""
    DONE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DONE_FILE.open("a", encoding="utf-8") as f:
        for msg in messages:
            msg["triggeredAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            f.write(json.dumps(msg) + "\n")


# ── Main ───────────────────────────────────────────────────────────────
def process_once() -> int:
    """Process all pending messages. Returns number processed."""
    pending = read_pending()
    if not pending:
        return 0

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(f"[{now}] Processing {len(pending)} pending message(s)")

    if not activate_cola_window():
        return 0

    for msg in pending:
        author = msg.get("author", "Cherrie")
        content = msg.get("content", "")
        text = f"[Discord] {author}: {content}"

        preview = text[:80] + ("..." if len(text) > 80 else "")
        print(f"  → Typing: \"{preview}\"")
        type_message(text)
        time.sleep(0.3)
        print("  ✓ Sent")

    archive_processed(pending)
    clear_pending()
    return len(pending)


def watch():
    """Poll for new messages continuously."""
    print(f"Discord trigger watching {PENDING_FILE} every {POLL_INTERVAL_S}s")
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
