"""
verify_coords.py — Quick test: takes a screenshot and prints where Cola is.

Run this to verify the coordinates in trigger_config.json are correct.
It will move your mouse to the configured positions (without clicking)
so you can visually confirm.

Usage: py verify_coords.py
"""

import json
import time
from pathlib import Path

import pyautogui

CONFIG_FILE = Path(__file__).parent / "trigger_config.json"
config = json.loads(CONFIG_FILE.read_text())

nav = config["navigation"]
chat_coords = nav["selectChat"]["coordinates"]
input_coords = nav["focusInput"]["coordinates"]

print(f"Mod: {config['mod']}")
print(f"Chat: {config['chatName']}")
print()
print("This will move your mouse to the configured positions.")
print("Watch where it goes — it should land on 'Discord Chat' in Cola's sidebar,")
print("then on the chat input area.")
print()
input("Press Enter to start (you have 3 seconds)...")

print("3...")
time.sleep(1)
print("2...")
time.sleep(1)
print("1...")
time.sleep(1)

print(f"Moving to chat entry: ({chat_coords['x']}, {chat_coords['y']})")
pyautogui.moveTo(chat_coords["x"], chat_coords["y"], duration=0.5)
time.sleep(1.5)

print(f"Moving to input area: ({input_coords['x']}, {input_coords['y']})")
pyautogui.moveTo(input_coords["x"], input_coords["y"], duration=0.5)
time.sleep(1.5)

print()
print("Did the mouse land on the right spots?")
ans = input("(y/n): ").strip().lower()

if ans == "y":
    print("✅ Coordinates verified! Run: py discord_trigger.py --watch")
else:
    print("❌ Coordinates are off. Let's recalibrate.")
    print()
    print("Move your mouse to 'Discord Chat' in the sidebar and note the position:")
    try:
        while True:
            x, y = pyautogui.position()
            print(f"\rMouse at: ({x:4d}, {y:4d})   Press Ctrl+C when ready", end="")
    except KeyboardInterrupt:
        pass
    x, y = pyautogui.position()
    print(f"\nChat position: ({x}, {y})")
    print(f"Update trigger_config.json → navigation.selectChat.coordinates: {{'x': {x}, 'y': {y}}}")
