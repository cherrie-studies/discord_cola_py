"""
discord_trigger.py — Inject Discord messages into ColaOS via mouse + keyboard

Watches for messages (pending.jsonl) and commands (commands.jsonl).
Handles: message injection, model switching, mod switching, Cola launch.

Features:
  - Coordinate-based mouse clicks (primary)
  - Image recognition fallback for chat selection
  - Mod switching via Switch Mod modal
  - Auto-launch Cola if not running

Usage:
    py discord_trigger.py           # run once
    py discord_trigger.py --watch   # poll continuously
"""

import json
import os
import sys
import subprocess
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
CHAT_ICON = SCRIPT_DIR / "chat_sidebar_icon.png"
COLA_CLASS = "Chrome_WidgetWin_1"
COLA_TITLE = "Cola"

# ── Config ─────────────────────────────────────────────────────────────
def load_config():
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    return {"mod": "vibe_cola", "chatName": "Discord Chat", "triggerPrefix": "[Discord]", "navigation": {"mode": "coordinate"}}

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

def activate_window(hwnd):
    if not hwnd: return False
    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.5)
    return True

# ── Cola launch ────────────────────────────────────────────────────────
def launch_cola(retries=30, retry_ms=2000):
    """Launch Cola via Win+R, wait for window to appear."""
    import pyautogui, pyperclip
    print("  🚀 Launching Cola...")
    pyautogui.hotkey("win")
    time.sleep(0.3)
    pyperclip.copy("Cola")
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.3)
    pyautogui.press("enter")
    time.sleep(0.5)

    for i in range(retries):
        hwnd, _ = find_cola_window()
        if hwnd:
            activate_window(hwnd)
            print(f"  ✅ Cola launched (waited {(i+1)*retry_ms/1000:.0f}s)")
            return True
        time.sleep(retry_ms / 1000)

    print("  ✗ Cola did not start within timeout")
    return False

def ensure_cola_running():
    """Find Cola window or launch it."""
    hwnd, _ = find_cola_window()
    if hwnd:
        return hwnd, True  # already running
    return None, launch_cola()

# ── Mouse / keyboard ───────────────────────────────────────────────────
def click_at(x, y, wait_ms=300):
    import pyautogui
    pyautogui.click(x, y)
    time.sleep(wait_ms / 1000.0)

def paste_and_send(text):
    import pyautogui, pyperclip
    pyautogui.hotkey("ctrl", "a"); time.sleep(0.08)
    pyautogui.press("delete"); time.sleep(0.05)
    pyperclip.copy(text)
    pyautogui.hotkey("ctrl", "v"); time.sleep(0.15)
    pyautogui.press("enter"); time.sleep(0.1)

# ── Chat selection with image fallback ─────────────────────────────────
def select_chat():
    """Click the 'Discord Chat' entry in sidebar. Tries coordinates first, then image recognition."""
    nav = config.get("navigation", {})

    # 1. Try coordinates
    coords = nav.get("selectChat", {}).get("coordinates", {})
    if coords.get("x") and coords.get("y"):
        click_at(coords["x"], coords["y"], 300)
        return True

    # 2. Try image recognition
    if CHAT_ICON.exists():
        import pyautogui
        try:
            loc = pyautogui.locateOnScreen(str(CHAT_ICON), confidence=0.8)
            if loc:
                cx = loc.left + loc.width // 2
                cy = loc.top + loc.height // 2
                click_at(cx, cy, 300)
                return True
        except Exception as e:
            print(f"  ⚠ Image recognition failed: {e}")

    print("  ✗ Cannot find chat — no coordinates or icon configured.")
    print("  → Run: py find_coords.py")
    return False

# ── Model switching ────────────────────────────────────────────────────
def change_model(target):
    nav = config.get("navigation", {})
    sel = nav.get("modelSelector", {}).get("coordinates", {})
    models = config.get("modelPositions", {})

    if not sel.get("x"):
        print("  ✗ modelSelector not configured"); return False
    if target not in models or not models[target].get("x"):
        print(f"  ✗ Model '{target}' position not in config"); return False

    click_at(sel["x"], sel["y"], 800)   # open panel
    click_at(models[target]["x"], models[target]["y"], 500)  # select
    print(f"  ✅ Model → {target}")
    return True

# ── Mod switching ──────────────────────────────────────────────────────
def switch_mod(target_mod):
    """Switch Cola mod by clicking the mod selector → clicking target mod card."""
    nav = config.get("navigation", {})
    switch = config.get("switchMod", {})

    sel = nav.get("modSelector", {}).get("coordinates", {})
    target = switch.get(target_mod, {})

    if not sel.get("x"):
        print("  ✗ modSelector not configured"); return False
    if not target.get("x"):
        print(f"  ✗ Mod '{target_mod}' position not in config"); return False

    # Click mod selector to open Switch Mod modal
    click_at(sel["x"], sel["y"], 600)
    # Click target mod card
    click_at(target["x"], target["y"], 500)
    print(f"  ✅ Mod → {target_mod}")
    return True

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

    hwnd, running = ensure_cola_running()
    if not hwnd: return 0

    prefix = config.get("triggerPrefix", "[Discord]")
    nav = config.get("navigation", {})

    select_chat()
    inp = nav.get("focusInput", {}).get("coordinates", {})
    if inp.get("x"):
        click_at(inp["x"], inp["y"], 200)

    for msg in pending:
        text = f"{prefix} {msg.get('author', 'Cherrie')}: {msg.get('content', '')}"
        preview = text[:80] + ("..." if len(text) > 80 else "")
        print(f"  → {preview}")
        paste_and_send(text)
        time.sleep(0.3)
        print("  ✓ Sent")

    for m in pending:
        m["triggeredAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        append_jsonl(DONE_FILE, m)
    clear_file(PENDING_FILE)
    return len(pending)

# ── Command processing ─────────────────────────────────────────────────
def process_commands():
    cmds = read_jsonl(COMMANDS_FILE)
    if not cmds: return 0

    hwnd, running = ensure_cola_running()
    if not hwnd: return 0

    print(f"Processing {len(cmds)} command(s)")
    for cmd in cmds:
        ctype = cmd.get("command", "")
        result = {"command": ctype, "success": False}

        if ctype == "change_model":
            target = cmd.get("target", "")
            result["target"] = target
            result["success"] = change_model(target)

        elif ctype == "switch_mod":
            target = cmd.get("target", "")
            result["target"] = target
            result["success"] = switch_mod(target)

        elif ctype == "relaunch_cola":
            import pyautogui, pyperclip
            # Close existing Cola windows
            hwnd, _ = find_cola_window()
            if hwnd:
                user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
                time.sleep(2)
            result["success"] = launch_cola()

        result["completedAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        result["channelId"] = cmd.get("channelId", "")
        append_jsonl(RESULTS_FILE, result)

    clear_file(COMMANDS_FILE)
    return len(cmds)

# ── Main ───────────────────────────────────────────────────────────────
def watch():
    mod = config.get("mod", "vibe_cola")
    chat = config.get("chatName", "Discord Chat")
    interval = config.get("pollIntervalMs", 2000) / 1000
    print(f"Discord trigger v2 — watching every {interval}s")
    print(f"  Mod: {mod} | Chat: {chat}")
    print(f"  Messages: {PENDING_FILE}")
    print(f"  Commands: {COMMANDS_FILE}")
    print("Press Ctrl+C to stop.\n")
    try:
        while True:
            try:
                process_commands()
                n = process_messages()
                if n:
                    print(f"[{time.strftime('%H:%M:%S')}] {n} message(s)")
            except Exception as e:
                print(f"Error: {e}")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nStopped.")

def run_once():
    process_commands()
    n = process_messages()
    print(f"{n} message(s) processed." if n else "No pending messages.")

if __name__ == "__main__":
    if "--watch" in sys.argv:
        watch()
    else:
        run_once()
