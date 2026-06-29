# Discord → Cola Trigger (Python)

Inject Discord messages into ColaOS via keyboard simulation.

## How it works

```
Discord message → Cola plugin (gateway) → pending.jsonl
                                              │
                                    discord_trigger.py --watch
                                              │
                                    Activate Cola → Ctrl+V → Enter
                                              │
                                    Cola agent (full tools, memory bank)
                                              │
Discord ←── Cola plugin (outbound) ←──────────┘
```

The Python script only handles **input injection** — reading pending messages and pasting them into Cola. The [Cola Discord plugin](https://github.com/cherrie-studies/discord_cola) handles Discord connection and sending replies back.

## Setup

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Run once (process any pending messages)
python discord_trigger.py

# Watch continuously (poll every 2 seconds)
python discord_trigger.py --watch
```

## Requirements

- ColaOS running and visible
- [Cola Discord plugin](../discord_cola/plugin/) installed and loaded
- Windows (uses Win32 API for window activation)
- `pyautogui` for keyboard simulation
- `pyperclip` for clipboard pasting

## Files

| File | Purpose |
|------|---------|
| `discord_trigger.py` | Keyboard injection script |
| `requirements.txt` | Python dependencies |
