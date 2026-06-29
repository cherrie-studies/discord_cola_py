"""
bot.py — Discord ↔ Cola bridge via WebSocket injection

  1. Connects to Discord
  2. On message → injects agent.prompt via Cola's WebSocket (no keyboard!)
  3. Watches Cola's session JSONL for the response
  4. Sends response back to Discord (webhook or bot)

Setup:
  pip install discord.py websockets pyperclip  (pyautogui only for fallback launcher)
  py bot.py
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import discord
import websockets

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

GATEWAY_TOKEN_FILE = Path.home() / ".cola" / "gateway-token"
COLA_WS_URL = "ws://127.0.0.1:19532"
COLA_SCOPE = "desktop:local"
COLA_SESSION_DIR = Path.home() / ".cola" / "sessions" / "desktop-local"
STATE_FILE = COLA_SESSION_DIR / "state.json"
RESPONSE_TIMEOUT_S = 120
POLL_INTERVAL_S = 1.5

def get_gateway_token():
    if GATEWAY_TOKEN_FILE.exists():
        return GATEWAY_TOKEN_FILE.read_text().strip()
    return ""

# ═══════════════════════════════════════════════════════════════════════
# WebSocket injection
# ═══════════════════════════════════════════════════════════════════════

async def ws_inject_prompt(text: str) -> bool:
    """Send agent.prompt to Cola via WebSocket."""
    token = get_gateway_token()
    if not token:
        print("   ❌ No gateway token found")
        return False
    url = f"{COLA_WS_URL}?token={token}"
    try:
        async with websockets.connect(url, close_timeout=5, ping_interval=None) as ws:
            req = {
                "method": "agent.prompt",
                "id": f"discord_{int(time.time()*1000)}",
                "params": {
                    "scope": COLA_SCOPE,
                    "text": text,
                    "attachments": [],
                    "hidden": False,
                },
            }
            await ws.send(json.dumps(req))
            # Wait briefly for acknowledgment
            try:
                ack = await asyncio.wait_for(ws.recv(), timeout=3)
                data = json.loads(ack)
                if data.get("type") == "error":
                    print(f"   ❌ WS error: {data.get('error', '')}")
                    return False
            except asyncio.TimeoutError:
                pass  # async — no immediate ack is fine
            return True
    except Exception as e:
        print(f"   ❌ WS failed: {e}")
        return False

# ═══════════════════════════════════════════════════════════════════════
# Session watcher
# ═══════════════════════════════════════════════════════════════════════

def get_active_session():
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text())
        path = state.get("activeSessionFile", "")
        if path and Path(path).exists():
            return Path(path)
    files = sorted(COLA_SESSION_DIR.glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)
    return files[0] if files else None

def extract_text(entry):
    msg = entry.get("message", {})
    if msg.get("role") != "assistant":
        return None
    content = msg.get("content", [])
    if not isinstance(content, list):
        return None
    texts = []
    for block in content:
        if block.get("type") == "text":
            t = block.get("text", "").strip()
            if t:
                texts.append(t)
    return "\n\n".join(texts) if texts else None

async def watch_response(session_file, start_size, timeout_s=RESPONSE_TIMEOUT_S):
    deadline = time.time() + timeout_s
    last_size = start_size
    while time.time() < deadline:
        await asyncio.sleep(POLL_INTERVAL_S)
        current_file = get_active_session()
        if current_file and current_file != session_file:
            session_file = current_file
            last_size = 0
        if not session_file.exists():
            continue
        sz = session_file.stat().st_size
        if sz <= last_size:
            continue
        with session_file.open("r", encoding="utf-8") as f:
            f.seek(last_size)
            new_text = f.read()
        last_size = sz
        for line in new_text.strip().split("\n"):
            if not line.strip(): continue
            try: entry = json.loads(line)
            except: continue
            text = extract_text(entry)
            if text: return text
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
        print(f"   WS injection: {COLA_WS_URL}")
        print(f"   Scope: {COLA_SCOPE}")
        print(f"   Webhook: {'✅ configured' if DISCORD_WEBHOOK else '❌ not set (bot replies)'}")
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

        # Snapshot session
        session_file = get_active_session()
        start_size = session_file.stat().st_size if session_file else 0
        sess = session_file.name if session_file else "N/A"
        print(f"   📄 Session: {sess} ({start_size}B)")

        # Inject via WebSocket
        text = f"[Discord] {author}: {content}"
        await message.channel.trigger_typing()
        ok = await ws_inject_prompt(text)
        if not ok:
            await message.reply("❌ Cola not reachable. Is it running?")
            return
        print(f"   ⚡ WS injected: {text[:80]}")

        # Watch for response
        response = await watch_response(session_file, start_size)

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
                print(f"   ⚠ Webhook failed: {e}")
        for chunk in [text[i:i+1900] for i in range(0, len(text), 1900)]:
            await message.reply(chunk)
        print("   ✅ Sent as bot")

# ═══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("Discord ↔ Cola (WebSocket injection)")
    print("=" * 40)
    if not DISCORD_TOKEN:
        print("❌ DISCORD_TOKEN not set")
        sys.exit(1)
    COLA_SESSION_DIR.mkdir(parents=True, exist_ok=True)
    ColaBridge().run(DISCORD_TOKEN)
