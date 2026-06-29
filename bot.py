"""
bot.py — Standalone Discord ↔ Cola bridge

Pure Python — no Cola plugin needed.
  1. Connects to Discord (discord.py)
  2. Reads trigger_config.json for mouse coordinates
  3. On message → clicks sidebar → clicks input → pastes → Enter
  4. Watches Cola's session JSONL for the response
  5. Sends response back to Discord

Setup:
  pip install discord.py pyautogui pyperclip
  py bot.py

Config:
  DISCORD_TOKEN in .env or set as env var
  trigger_config.json for mouse coordinates
"""

import asyncio
import json
import os
import sys
import time
import ctypes
import ctypes.wintypes
from pathlib import Path

import discord
import pyautogui
import pyperclip

# ═══════════════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════════════

SCRIPT_DIR = Path(__file__).parent.resolve()

# Load .env if present
env_file = SCRIPT_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text().split("\n"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip().strip('"').strip("'")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK", "")  # optional: replies appear as "Cola"
ALLOWED_CHANNELS = os.getenv("DISCORD_CHANNEL_IDS", "1519719204071280640").split(",")

# Load trigger config
CONFIG_FILE = SCRIPT_DIR / "trigger_config.json"
config = {}
if CONFIG_FILE.exists():
    config = json.loads(CONFIG_FILE.read_text())

TRIGGER_PREFIX = config.get("triggerPrefix", "[Discord]")
COLA_SESSION_DIR = Path.home() / ".cola" / "sessions" / "desktop-local"
STATE_FILE = COLA_SESSION_DIR / "state.json"
RESPONSE_TIMEOUT_S = 120
POLL_INTERVAL_S = 1.5

# ═══════════════════════════════════════════════════════════════════════
# Cola window control
# ═══════════════════════════════════════════════════════════════════════
user32 = ctypes.windll.user32

def find_cola():
    hwnd = user32.FindWindowW("Chrome_WidgetWin_1", "Cola")
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
    return hwnd

def activate_cola():
    hwnd = find_cola()
    if not hwnd: return False
    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.4)
    return True

def click_at(x, y, wait_ms=300):
    pyautogui.click(x, y)
    time.sleep(wait_ms / 1000.0)

def navigate_to_discord_chat():
    """Click sidebar chat entry + input area using config coordinates."""
    nav = config.get("navigation", {})
    chat = nav.get("selectChat", {}).get("coordinates", {})
    inp = nav.get("focusInput", {}).get("coordinates", {})

    if chat.get("x"):
        print(f"   🖱  Sidebar → ({chat['x']}, {chat['y']})")
        click_at(chat["x"], chat["y"], 300)
    if inp.get("x"):
        print(f"   🖱  Input → ({inp['x']}, {inp['y']})")
        click_at(inp["x"], inp["y"], 200)

def inject_message(text):
    pyautogui.hotkey("ctrl", "a"); time.sleep(0.05)
    pyautogui.press("delete"); time.sleep(0.03)
    pyperclip.copy(text)
    pyautogui.hotkey("ctrl", "v"); time.sleep(0.1)
    pyautogui.press("enter"); time.sleep(0.1)

# ═══════════════════════════════════════════════════════════════════════
# Session file watcher
# ═══════════════════════════════════════════════════════════════════════

def get_active_session():
    """Read state.json to find which session file is active."""
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text())
        path = state.get("activeSessionFile", "")
        if path and Path(path).exists():
            return Path(path)
    # Fallback: latest by mtime
    files = sorted(COLA_SESSION_DIR.glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)
    return files[0] if files else None

def extract_text_from_message(entry):
    """Extract display text from a session JSONL entry."""
    msg = entry.get("message", {})
    if msg.get("role") != "assistant":
        return None
    content = msg.get("content", [])
    if not isinstance(content, list):
        return None
    texts = []
    for block in content:
        if block.get("type") == "text":
            t = block.get("text", "")
            if t.strip():
                texts.append(t.strip())
    return "\n\n".join(texts) if texts else None

def watch_for_response(session_file, start_size, timeout_s=RESPONSE_TIMEOUT_S):
    """Watch session JSONL for new assistant text. Returns text or None."""
    deadline = time.time() + timeout_s
    last_size = start_size

    while time.time() < deadline:
        time.sleep(POLL_INTERVAL_S)

        # Session might switch mid-conversation
        current_file = get_active_session()
        if current_file and current_file != session_file:
            session_file = current_file
            last_size = 0  # reset for new file

        if not session_file.exists():
            continue

        current_size = session_file.stat().st_size
        if current_size <= last_size:
            continue

        with session_file.open("r", encoding="utf-8") as f:
            f.seek(last_size)
            new_text = f.read()
        last_size = current_size

        for line in new_text.strip().split("\n"):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            text = extract_text_from_message(entry)
            if text:
                return text

    return None

# ═══════════════════════════════════════════════════════════════════════
# Discord bot
# ═══════════════════════════════════════════════════════════════════════

class ColaBridge(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)

    async def on_ready(self):
        print(f"✅ Discord: {self.user} (ID: {self.user.id})")
        print(f"   Channels: {ALLOWED_CHANNELS}")
        print(f"   Sessions: {COLA_SESSION_DIR}")
        print(f"   Config: {'✅ loaded' if config else '⚠  not found'}")
        await self.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(type=discord.ActivityType.watching, name="Cola for replies"),
        )

    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if str(message.channel.id) not in ALLOWED_CHANNELS:
            return

        author = message.author.display_name
        content = message.content
        print(f"\n{'─' * 55}")
        print(f"📨 {author}: {content[:100]}")

        if not activate_cola():
            await message.reply("❌ Cola not running.")
            return

        # Navigate to Discord Chat in sidebar
        navigate_to_discord_chat()

        # Snapshot current session
        session_file = get_active_session()
        start_size = session_file.stat().st_size if session_file else 0
        sess_name = session_file.name if session_file else "N/A"
        print(f"   📄 Session: {sess_name} ({start_size}B)")

        # Inject
        text = f"{TRIGGER_PREFIX} {author}: {content}"
        await message.channel.trigger_typing()
        inject_message(text)
        print(f"   ⌨  Injected: {text[:90]}")

        # Watch for response
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None, watch_for_response, session_file, start_size
        )

        if response:
            preview = response[:100].replace("\n", " ")
            print(f"   🤖 Response: {preview}...")
            await self.send_reply(message, response)
        else:
            await message.reply("⏰ Cola didn't respond in time.")
            print(f"   ❌ Timeout")

    async def send_reply(self, message: discord.Message, text: str):
        """Send reply via webhook (appears as 'Cola') or fallback to bot reply."""
        if DISCORD_WEBHOOK:
            try:
                webhook = discord.Webhook.from_url(DISCORD_WEBHOOK, client=self)
                # Split long messages
                for chunk in [text[i:i+1900] for i in range(0, len(text), 1900)]:
                    await webhook.send(
                        content=chunk,
                        username="Cola",
                        avatar_url="https://cdn.colaos.ai/cola-avatar.png",
                        wait=True,
                    )
                print("   ✅ Sent as Cola (webhook)")
                return
            except Exception as e:
                print(f"   ⚠ Webhook failed: {e}, falling back to bot reply")
        # Fallback: regular bot reply
        for chunk in [text[i:i+1900] for i in range(0, len(text), 1900)]:
            await message.reply(chunk)
        print("   ✅ Sent as bot")

# ═══════════════════════════════════════════════════════════════════════
# Entry
# ═══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("Discord ↔ Cola Bridge (standalone Python)")
    print("=" * 45)
    if not DISCORD_TOKEN:
        print("❌ DISCORD_TOKEN not set. Create .env or set env var.")
        sys.exit(1)
    COLA_SESSION_DIR.mkdir(parents=True, exist_ok=True)
    ColaBridge().run(DISCORD_TOKEN)
