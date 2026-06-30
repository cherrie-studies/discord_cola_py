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

def inject_message(text):
    """Inject the Discord message into Cola."""
    pyautogui.hotkey("ctrl", "a"); time.sleep(0.05)
    pyautogui.press("delete"); time.sleep(0.03)
    pyperclip.copy(text)
    pyautogui.hotkey("ctrl", "v"); time.sleep(0.1)
    pyautogui.press("enter"); time.sleep(0.1)


def watch_reply_file(path: Path, timeout_s=RESPONSE_TIMEOUT_S):
    """Wait for reply.txt to have content. Returns (text, [file_paths]) or (None, [])."""
    deadline = time.time() + timeout_s
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.write_text("", encoding="utf-8")
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL_S)
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            continue
        path.write_text("", encoding="utf-8")  # clear
        # Parse: text before ---file---, file paths after
        if "---file---" in content:
            parts = content.split("---file---", 1)
            text = parts[0].strip()
            files = [f.strip() for f in parts[1].strip().split("\n") if f.strip()]
            # Validate paths exist
            files = [f for f in files if Path(f).exists() and Path(f).stat().st_size < 8_000_000]
            return text, files
        return content, []
    return None, []

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
        content = message.content or ""
        print(f"\n{'─' * 50}")
        print(f"📨 {author}: {content[:100] or '<attachment>'} ")

        if not activate_cola():
            await message.reply("❌ Cola not running.")
            return

        # Download attachments
        attachment_paths = []
        if message.attachments:
            attach_dir = OUTBOX_DIR / "attachments" / str(message.id)
            attach_dir.mkdir(parents=True, exist_ok=True)
            for att in message.attachments:
                path = attach_dir / att.filename
                await att.save(path)
                attachment_paths.append(str(path))
                print(f"   📎 Downloaded: {att.filename} ({att.size}B)")

        navigate_to_discord_chat()

        # Build injected text
        if content:
            text = f"{TRIGGER_PREFIX} {author}: {content}"
        else:
            text = f"{TRIGGER_PREFIX} {author}: sent an attachment"
        if attachment_paths:
            text += "\nAttachments:\n" + "\n".join(f"- {p}" for p in attachment_paths)

        try: await message.channel.typing()
        except: pass

        reply_file = REPLY_FILE
        inject_message(text)
        print(f"   ⌨  {text[:80]}")

        loop = asyncio.get_running_loop()
        text, files = await loop.run_in_executor(None, watch_reply_file, reply_file)

        if text or files:
            if text:
                preview = text[:100].replace("\n", " ")
                print(f"   🤖 {preview}...")
            if files:
                print(f"   📎 {len(files)} file(s): {[Path(f).name for f in files]}")
            await self.send_reply(message, text, files)
        else:
            await message.reply("⏰ No response from Cola.")
            print("   ❌ Timeout")

    async def send_reply(self, message: discord.Message, text: str = "", files: list = None):
        files = files or []
        discord_files = []
        for fp in files:
            try:
                discord_files.append(discord.File(fp))
            except Exception as e:
                print(f"   ⚠ File attach failed: {fp} — {e}")

        if DISCORD_WEBHOOK:
            try:
                webhook = discord.Webhook.from_url(DISCORD_WEBHOOK, client=self)
                for chunk in [text[i:i+1900] for i in range(0, len(text), 1900)] if text else [""]:
                    kwargs = {"content": chunk, "username": "Cola", "wait": True}
                    if discord_files and chunk == ([text[i:i+1900] for i in range(0, len(text), 1900)] if text else [""])[-1]:
                        kwargs["files"] = discord_files
                    await webhook.send(**kwargs)
                print(f"   ✅ Sent as Cola (webhook)" + (f" + {len(files)} files" if files else ""))
                return
            except Exception as e:
                print(f"   ⚠ Webhook: {e}")
        # Fallback: bot reply
        for chunk in [text[i:i+1900] for i in range(0, len(text), 1900)] if text else [""]:
            kwargs = {"content": chunk}
            if discord_files and chunk == ([text[i:i+1900] for i in range(0, len(text), 1900)] if text else [""])[-1]:
                kwargs["files"] = discord_files
            await message.reply(**kwargs)
        print("   ✅ Sent as bot" + (f" + {len(files)} files" if files else ""))

# ═══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("Discord ↔ Cola (keyboard injection + reply file)")
    print("=" * 50)
    print(f"   Reply file: {REPLY_FILE}")
    print(f"   Setup: copy INIT_PROMPT.md into Cola's 'Discord Chat' first")
    if not DISCORD_TOKEN:
        print("❌ DISCORD_TOKEN not set")
        sys.exit(1)
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    ColaBridge().run(DISCORD_TOKEN)
