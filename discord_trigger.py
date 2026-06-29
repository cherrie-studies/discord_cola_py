"""
discord_trigger.py — Inject Discord messages into ColaOS via keyboard simulation

Reads pending messages from ~/.cola/channels/discord/pending.jsonl,
activates the Cola window, navigates to the configured chat session,
pastes the message, and presses Enter.

Config: trigger_config.json (mod, chatName, navigation shortcuts)

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
    # Defaults
    return {
        "mod": "normal",
        "chatName": "Discord Integration",
        "triggerPrefix": "[Discord]",
        "navigation": {
            "clearSearch": {"keys": ["escape"], "waitMs": 200},
            "activateChat": {"keys": ["ctrl", "k"]},
            "typeAndSelect": {"waitAfterTypeMs": 500},
        },
    }


config = load_config()


# ── Win32 helpers ──────────────────────────────────────────────────────
user32 = ctypes.windll.user32

SW_RESTORE = 9


def find_cola_window():
    """Find Cola's main window handle. Returns hwnd or None."""
    hwnd = user32.FindWindowW(COLA_CLASS, COLA_TITLE)
    if hwnd:
        return hwnd
    # Fallback: enumerate windows
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


def send_key_combo(*keys, wait_ms: int = 300):
    """Press a key combination (e.g. ctrl+k) using pyautogui."""
    import pyautogui
    pyautogui.hotkey(*keys)
    time.sleep(wait_ms / 1000.0)


def type_text(text: str, wait_ms: int = 0):
    """Type text via clipboard + Ctrl+V."""
    import pyautogui
    import pyperclip
    pyperclip.copy(text)
    pyautogui.hotkey("ctrl", "v")
    if wait_ms:
        time.sleep(wait_ms / 1000.0)


# ── Cola UI navigation ─────────────────────────────────────────────────
def navigate_to_chat(chat_name: str) -> bool:
    """Navigate to the target chat session in Cola via keyboard shortcuts."""
    nav = config.get("navigation", {})

    # Step 1: Clear any open menus/modals (press Escape)
    clear = nav.get("clearSearch", {})
    if clear.get("keys"):
        send_key_combo(*clear["keys"], wait_ms=clear.get("waitMs", 200))

    # Step 2: Open command palette / chat switcher
    activate = nav.get("activateChat", {})
    if activate.get("keys"):
        send_key_combo(*activate["keys"], wait_ms=500)

    # Step 3: Type the chat name
    import pyautogui
    import pyperclip
    type_select = nav.get("typeAndSelect", {})
    pyperclip.copy(chat_name)
    pyautogui.hotkey("ctrl", "v")
    wait_ms = type_select.get("waitAfterTypeMs", 500)
    time.sleep(wait_ms / 1000.0)

    # Step 4: Press Enter to select (first result should match)
    pyautogui.press("enter")
    time.sleep(0.3)

    print(f"  Navigated to chat: {chat_name}")
    return True


def inject_message(text: str) -> bool:
    """Paste text into the active Cola chat input and press Enter."""
    try:
        import pyautogui
        import pyperclip
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
    print(f"[{now}] Processing {len(pending)} message(s) (mod={mod}, chat={chat_name})")

    if not activate_cola_window():
        return 0

    # Navigate to the target chat
    navigate_to_chat(chat_name)

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
