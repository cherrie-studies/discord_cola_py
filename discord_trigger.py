"""
discord_trigger.py — Inject Discord messages into ColaOS via mouse + keyboard

Watches two files:
  - pending.jsonl  → messages to inject into Cola
  - commands.jsonl → UI commands (model switching, etc.)

Also handles /model commands: clicks model selector, selects target model.

Usage:
    py discord_trigger.py           # run once
    py discord_trigger.py --watch   # poll every N seconds

Dependencies: pyautogui, pyperclip, opencv-python, pillow
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
COMMANDS_FILE = Path.home() / ".cola" / "channels" / "discord" / "commands.jsonl"
DONE_FILE = Path.home() / ".cola" / "channels" / "discord" / "triggered.jsonl"
RESULTS_FILE = Path.home() / ".cola" / "channels" / "discord" / "command_results.jsonl"
COLA_CLASS = "Chrome_WidgetWin_1"
COLA_TITLE = "Cola"
POLL_INTERVAL_S = 2

# ── Config ─────────────────────────────────────────────────────────────
def load_config() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    return {
        "mod": "normal",
        "chatName": "Discord Chat",
        "triggerPrefix": "[Discord]",
        "navigation": {"mode": "coordinate"},
    }

config = load_config()

# ── Win32 ──────────────────────────────────────────────────────────────
user32 = ctypes.windll.user32

def find_cola_window():
    hwnd = user32.FindWindowW(COLA_CLASS, COLA_TITLE)
    if not hwnd:
        result = []
        def cb(h, _):
            n = user32.GetWindowTextLengthW(h)
            if n:
                b = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(h, b, n + 1)
                if b.value and "Cola" in b.value:
                    result.append(h); return False
            return True
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(cb), 0)
        hwnd = result[0] if result else None
    if not hwnd:
        return None, None
    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
    rect = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return hwnd, rect

def activate_cola_window(hwnd):
    if not hwnd: return False
    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.5)
    return True

# ── Mouse / keyboard ───────────────────────────────────────────────────
def click_at(x, y, wait_ms=300):
    import pyautogui
    pyautogui.click(x, y)
    time.sleep(wait_ms / 1000.0)

def inject_message(text):
    import pyautogui, pyperclip
    pyautogui.hotkey("ctrl", "a"); time.sleep(0.1)
    pyautogui.press("delete"); time.sleep(0.05)
    pyperclip.copy(text)
    pyautogui.hotkey("ctrl", "v"); time.sleep(0.2)
    pyautogui.press("enter"); time.sleep(0.1)

# ── File I/O ───────────────────────────────────────────────────────────
def read_jsonl(path):
    if not path.exists(): return []
    try:
        raw = path.read_text("utf-8").strip()
        return [json.loads(l) for l in raw.split("\n") if l.strip()] if raw else []
    except: return []

def clear_file(path):
    path.write_text("", "utf-8")

def append_jsonl(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj) + "\n")

# ── Message injection ──────────────────────────────────────────────────
def process_messages():
    pending = read_jsonl(PENDING_FILE)
    if not pending: return 0

    hwnd, rect = find_cola_window()
    if not hwnd: return 0
    if not activate_cola_window(hwnd): return 0

    prefix = config.get("triggerPrefix", "[Discord]")
    nav = config.get("navigation", {})

    # Click sidebar chat entry
    chat = nav.get("selectChat", {}).get("coordinates", {})
    if chat.get("x"):
        click_at(chat["x"], chat["y"], 300)

    # Click input area
    inp = nav.get("focusInput", {}).get("coordinates", {})
    if inp.get("x"):
        click_at(inp["x"], inp["y"], 200)

    for msg in pending:
        author = msg.get("author", "Cherrie")
        content = msg.get("content", "")
        text = f"{prefix} {author}: {content}"
        preview = text[:80] + ("..." if len(text) > 80 else "")
        print(f"  → Injecting: \"{preview}\"")
        inject_message(text)
        time.sleep(0.3)
        print("  ✓ Sent")

    for m in pending:
        m["triggeredAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        append_jsonl(DONE_FILE, m)
    clear_file(PENDING_FILE)
    return len(pending)

# ── Model switching ────────────────────────────────────────────────────
VALID_MODELS = ["max", "pro", "lite", "code", "glm", "doubao"]

def change_model(target):
    nav = config.get("navigation", {})
    sel = nav.get("modelSelector", {}).get("coordinates", {})
    models = nav.get("modelPositions", {})

    if not sel.get("x"):
        print(f"  ✗ modelSelector coordinates not in config")
        return False
    if target not in models or not models[target].get("x"):
        print(f"  ✗ Model '{target}' position not configured")
        print(f"  → Run: py find_coords.py")
        return False

    click_at(sel["x"], sel["y"], 800)
    pos = models[target]
    click_at(pos["x"], pos["y"], 500)
    print(f"  ✅ Model → {target}")
    return True

def process_commands():
    cmds = read_jsonl(COMMANDS_FILE)
    if not cmds: return 0

    hwnd, _ = find_cola_window()
    if not hwnd: return 0
    if not activate_cola_window(hwnd): return 0

    print(f"Processing {len(cmds)} command(s)")
    for cmd in cmds:
        if cmd.get("command") == "change_model":
            target = cmd.get("target", "")
            ok = change_model(target)
            append_jsonl(RESULTS_FILE, {
                "command": "change_model",
                "target": target,
                "success": ok,
                "channelId": cmd.get("channelId", ""),
                "completedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            })
    clear_file(COMMANDS_FILE)
    return len(cmds)

# ── Main ───────────────────────────────────────────────────────────────
def watch():
    mod = config.get("mod", "normal")
    chat = config.get("chatName", "Discord Chat")
    interval = config.get("pollIntervalMs", 2000) / 1000
    print(f"Discord trigger watching:")
    print(f"  Messages: {PENDING_FILE}")
    print(f"  Commands: {COMMANDS_FILE}")
    print(f"  Mod: {mod} | Chat: {chat} | Poll: {interval}s")
    print("Press Ctrl+C to stop.\n")
    try:
        while True:
            try:
                process_commands()
                count = process_messages()
                if count:
                    print(f"[{time.strftime('%H:%M:%S')}] Processed {count} message(s)")
            except Exception as e:
                print(f"Error: {e}")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped.")

def run_once():
    process_commands()
    count = process_messages()
    print(f"{count} message(s) processed." if count else "No pending messages.")

if __name__ == "__main__":
    if "--watch" in sys.argv:
        watch()
    else:
        run_once()
