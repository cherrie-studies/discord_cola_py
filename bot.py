"""
bot.py — Discord ↔ Cola bridge via keyboard injection

  1. Connects to Discord
  2. On message → clicks "Discord Chat" in sidebar → clicks input → pastes → Enter
  3. Watches Cola's session JSONL for the response
  4. Sends response back to Discord (webhook or bot)

Setup:
  pip install discord.py pyautogui pyperclip
  py bot.py
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

env_file = SCRIPT_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text().split("\n"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip().strip('"').strip("'")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK", "")
ALLOWED_CHANNELS = os.getenv("DISCORD_CHANNEL_IDS", "1519719204071280640").split(",")

CONFIG_FILE = SCRIPT_DIR / "trigger_config.json"
config = {}
if CONFIG_FILE.exists():
    config = json.loads(CONFIG_FILE.read_text())

TRIGGER_PREFIX = config.get("triggerPrefix", "[Discord]")
OUTBOX_DIR = Path.home() / ".cola" / "channels" / "discord"
REPLY_FILE = Path(os.environ.get("COLA_REPLY_FILE", str(OUTBOX_DIR / "reply.txt")))
RESPONSE_TIMEOUT_S = 120
POLL_INTERVAL_S = 1.0

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
    nav = config.get("navigation", {})
    chat = nav.get("selectChat", {}).get("coordinates", {})
    inp = nav.get("focusInput", {}).get("coordinates", {})
    if chat.get("x"):
        click_at(chat["x"], chat["y"], 300)
        print(f"   🖱  Sidebar ({chat['x']}, {chat['y']})")
    if inp.get("x"):
        click_at(inp["x"], inp["y"], 200)
        print(f"   🖱  Input ({inp['x']}, {inp['y']})")

def inject_setup_prompt(reply_file):
    """One-time setup: teach Cola the Discord relay protocol."""
    prompt = (
        'You are connected to Discord via a relay bot. '
        'Messages prefixed with [Discord] are from me (Cherrie) chatting from Discord.\n\n'
        'Rules:\n'
        '1. When you see [Discord] <name>: <message>, treat it as me speaking.\n'
        '2. Reply naturally in my language (Vietnamese or English).\n'
        '3. Keep replies under 1800 chars. Split if needed.\n'
        '4. Write your ENTIRE response to this file (overwrite, no extra text):\n'
        f'   {reply_file}\n'
        '5. The relay bot reads that file and sends it to Discord.\n'
        '6. Use your full capabilities: memory bank, tools, web search.\n\n'
        'Confirm by writing just "OK" to the file.'
    )
    pyautogui.hotkey("ctrl", "a"); time.sleep(0.05)
    pyautogui.press("delete"); time.sleep(0.03)
    pyperclip.copy(prompt)
    pyautogui.hotkey("ctrl", "v"); time.sleep(0.1)
    pyautogui.press("enter"); time.sleep(0.1)


def inject_message(text):
    """Inject just the Discord message into Cola."""
    pyautogui.hotkey("ctrl", "a"); time.sleep(0.05)
    pyautogui.press("delete"); time.sleep(0.03)
    pyperclip.copy(text)
    pyautogui.hotkey("ctrl", "v"); time.sleep(0.1)
    pyautogui.press("enter"); time.sleep(0.1)


def watch_reply_file(path: Path, timeout_s=RESPONSE_TIMEOUT_S):
    """Wait for a reply file to appear and have content, then read it."""
    deadline = time.time() + timeout_s
    path.parent.mkdir(parents=True, exist_ok=True)
    # Clear any old reply
    if path.exists():
        path.write_text("", encoding="utf-8")
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL_S)
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8").strip()
        if content:
            path.write_text("", encoding="utf-8")  # clear for next time
            return content
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
        print(f"✅ Discord: {self.user}")
        print(f"   Channels: {ALLOWED_CHANNELS}")
        print(f"   Config: {'✅ loaded' if config else '⚠  not found'}")
        print(f"   Webhook: {'✅' if DISCORD_WEBHOOK else '❌ (bot replies)'}")
        await self.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(type=discord.ActivityType.watching, name="Cola for replies"),
        )

    async def on_message(self, message: discord.Message):
        if message.author.bot: return
        if str(message.channel.id) not in ALLOWED_CHANNELS: return

        author = message.author.display_name
        content = message.content
        print(f"\n{'─' * 50}")
        print(f"📨 {author}: {content[:100]}")

        if not activate_cola():
            await message.reply("❌ Cola not running.")
            return

        navigate_to_discord_chat()

        text = f"{TRIGGER_PREFIX} {author}: {content}"
        try: await message.channel.typing()
        except: pass

        reply_file = REPLY_FILE
        inject_message(text)
        print(f"   ⌨  {text[:80]}")

        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, watch_reply_file, reply_file)

        if response:
            preview = response[:100].replace("\n", " ")
            print(f"   🤖 {preview}...")
            await self.send_reply(message, response)
        else:
            await message.reply("⏰ No response from Cola.")
            print("   ❌ Timeout")

    async def send_reply(self, message: discord.Message, text: str):
        if DISCORD_WEBHOOK:
            try:
                webhook = discord.Webhook.from_url(DISCORD_WEBHOOK, client=self)
                for chunk in [text[i:i+1900] for i in range(0, len(text), 1900)]:
                    await webhook.send(content=chunk, username="Cola", wait=True)
                print("   ✅ Sent as Cola (webhook)")
                return
            except Exception as e:
                print(f"   ⚠ Webhook: {e}")
        for chunk in [text[i:i+1900] for i in range(0, len(text), 1900)]:
            await message.reply(chunk)
        print("   ✅ Sent as bot")

# ═══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    if "--init" in sys.argv:
        print("Sending setup prompt to Cola...")
        print("Make sure 'Discord Chat' is the active session in Cola.")
        print()
        if not activate_cola():
            print("❌ Cola not running.")
            sys.exit(1)
        navigate_to_discord_chat()
        inject_setup_prompt(REPLY_FILE)
        print("✅ Setup prompt injected. Cola should write 'OK' to reply.txt.")
        print(f"   Watching {REPLY_FILE}...")
        response = watch_reply_file(REPLY_FILE, timeout_s=30)
        if response:
            print(f"   Response: {response[:200]}")
        else:
            print("   ⏰ No confirmation. Check if Cola processed the prompt.")
        sys.exit(0)

    print("Discord ↔ Cola (keyboard injection + reply file)")
    print("=" * 50)
    print(f"   Reply file: {REPLY_FILE}")
    if not DISCORD_TOKEN:
        print("❌ DISCORD_TOKEN not set")
        sys.exit(1)
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    ColaBridge().run(DISCORD_TOKEN)
