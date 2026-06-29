# Discord → Cola Trigger (Python)

Inject Discord messages into ColaOS by controlling the mouse and keyboard — Cola thinks you typed it.

## How it works

```
Discord message → Cola plugin (gateway) → pending.jsonl
                                              │
                                    discord_trigger.py --watch
                                              │
                          ① Activate Cola window
                          ② Find "Discord Integration" in sidebar (image recognition)
                          ③ Click it
                          ④ Click input area → Ctrl+V → Enter
                                              │
                                    Cola agent processes
                                    (full tools, memory bank, multi-turn)
                                              │
Discord ←── Cola plugin (outbound) ←──────────┘
```

## Quick Start

### Prerequisites
- Python 3.10+
- ColaOS running and visible on screen
- [Cola Discord plugin](https://github.com/cherrie-studies/discord_cola) installed and loaded

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Capture the chat icon (one-time setup)
```bash
python capture_chat.py
```
This guides you through cropping a screenshot of the "Discord Integration" text from Cola's sidebar. Saves as `chat_sidebar_icon.png`.

### 3. Verify image recognition works
```bash
python capture_chat.py --test
```
Should print: `✅ Found at screen position: (x, y)`

### 4. Configure (optional)
Edit [`trigger_config.json`](trigger_config.json):
```json
{
  "mod": "vibe_cola",
  "chatName": "Discord Integration",
  "triggerPrefix": "[Discord]"
}
```

### 5. Run
```bash
python discord_trigger.py --watch
```

Now send a message in your Discord channel. The trigger polls every 2 seconds, finds the message, and injects it into Cola.

## Configuration

| Key | Default | Description |
|-----|---------|-------------|
| `mod` | `"normal"` | Which Cola mod to expect (`"normal"` or `"vibe_cola"`) |
| `chatName` | `"Discord Integration"` | Name of the Cola chat session to navigate to |
| `triggerPrefix` | `"[Discord]"` | Prefix added before each injected message |
| `navigation.mode` | `"image"` | `"image"` = pyautogui.locateOnScreen, `"coordinate"` = fixed pixels |
| `navigation.selectChat.image` | `"chat_sidebar_icon.png"` | Screenshot of sidebar entry |
| `navigation.selectChat.confidence` | `0.8` | Image match confidence (0.0-1.0). Lower if matching fails |
| `navigation.focusInput.windowRelative` | `{"x":0.5, "y":0.9}` | Where to click for input focus (% of window) |

## Files

| File | Purpose |
|------|---------|
| `discord_trigger.py` | Main trigger — image-based mouse navigation + keyboard injection |
| `capture_chat.py` | Setup helper — capture and test the sidebar icon |
| `trigger_config.json` | Mod, chat name, navigation settings |
| `requirements.txt` | Python dependencies |
