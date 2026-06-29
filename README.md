# Discord Cola Bridge (Python)

Inject Discord messages into ColaOS via mouse + keyboard automation.

## How it works

```
Discord message → Cola plugin (gateway) → pending.jsonl / commands.jsonl
                                                    │
                                          discord_trigger.py --watch
                                                    │
                        ┌───────────────────────────┼──────────────────────┐
                        ▼                           ▼                      ▼
                 Message inject              Model change             Mod switch
                 Click chat → paste         Click selector           Click selector
                 → Enter → agent            → click model            → click mod card
                        │                           │                      │
                        └───────────────────────────┴──────────────────────┘
                                                    │
Discord ←── Cola plugin (outbound.sendText) ←───────┘
```

## Quick Start

### 1. Install
```bash
pip install -r requirements.txt
pip install keyboard  # for find_coords.py hotkeys
```

### 2. Calibrate coordinates
```bash
py find_coords.py
```
Move mouse over each UI element and press the corresponding key:
- `1` = sidebar chat entry
- `2` = chat input area
- `3` = model selector button
- `4-9` = each model in the panel
- `0` = mod selector (top-left)
- `m` = "Cola" mod card
- `n` = "Vibe Cola" mod card
- `s` = save all to config

### 3. Run
```bash
py discord_trigger.py --watch
```

## Discord Commands

| Command | Example | What it does |
|---------|---------|-------------|
| `/model show` | — | Lists all 6 models |
| `/model change pro` | — | Switches model to Pro |
| `/mod show` | — | Lists available mods |
| `/mod change vibe` | `/mod change vibe_cola` | Switches mod |

Both `/mod` and `/model` commands write to `commands.jsonl` → trigger executes mouse clicks → model/mod changes.

## Features

- **Auto-launch**: If Cola isn't running, presses Win → types "Cola" → Enter → waits
- **Image fallback**: If coordinates fail, tries `chat_sidebar_icon.png` via locateOnScreen
- **Mod switching**: Clicks mod selector → clicks target mod card in Switch Mod modal
- **Model switching**: Clicks model button → clicks target model in selection panel

## Files

| File | Purpose |
|------|---------|
| `discord_trigger.py` | Main trigger — watches messages + commands, executes mouse actions |
| `find_coords.py` | Coordinate calibrator — capture positions with hotkeys |
| `capture_chat.py` | Create `chat_sidebar_icon.png` for image recognition fallback |
| `verify_coords.py` | Visual test — moves mouse to configured positions |
| `trigger_config.json` | All coordinates, mod/model positions, navigation settings |
| `requirements.txt` | Python dependencies |
