"""
capture_chat.py — Helper to set up image-based navigation

Use this ONCE to capture the sidebar chat entry screenshot
and test that pyautogui can find it.

Usage:
    python capture_chat.py

This will:
    1. Prompt you to make Cola's sidebar visible
    2. Take a full screenshot
    3. Let you select the region with "Discord Integration" text
    4. Save it as chat_sidebar_icon.png
    5. Test that locateOnScreen finds it
"""

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
ICON_FILE = SCRIPT_DIR / "chat_sidebar_icon.png"


def main():
    try:
        import pyautogui
        from PIL import Image
    except ImportError:
        print("Missing dependencies. Run:")
        print("  pip install pyautogui pillow opencv-python")
        sys.exit(1)

    print("=" * 50)
    print("Discord Trigger — Chat Icon Capture")
    print("=" * 50)
    print()
    print("This will help you create the screenshot needed for")
    print("image-based chat navigation.")
    print()
    input("1. Make Cola window visible with sidebar showing. Press Enter...")

    # Take full screenshot
    print("2. Taking screenshot...")
    img = pyautogui.screenshot()
    temp_file = SCRIPT_DIR / "_full_screen.png"
    img.save(str(temp_file))
    print(f"   Saved full screen to: {temp_file}")

    # Open the image for the user to inspect
    print()
    print("3. Open this image and find the 'Discord Integration' text in the sidebar.")
    print(f"   File: {temp_file}")
    print()
    print("   Now run this Python snippet to select the region:")
    print()
    print("   from PIL import Image")
    print(f"   img = Image.open(r'{temp_file}')")
    print("   # Crop to JUST the chat name text (leave small margin)")
    print("   # left, top, right, bottom (pixels)")
    print("   cropped = img.crop((left, top, right, bottom))")
    print(f"   cropped.save(r'{ICON_FILE}')")
    print(f"   print('Saved to {ICON_FILE}')")
    print()
    print("4. After saving, test with:")
    print(f"   python capture_chat.py --test")
    print()
    print("Then clean up:")
    print(f"   del {temp_file}")


def test_locate():
    """Test that the icon can be found on screen."""
    try:
        import pyautogui
    except ImportError:
        print("Missing pyautogui. Run: pip install pyautogui opencv-python")
        sys.exit(1)

    if not ICON_FILE.exists():
        print(f"✗ Icon file not found: {ICON_FILE}")
        print("  Run 'python capture_chat.py' first to create it.")
        sys.exit(1)

    print(f"Testing locateOnScreen with: {ICON_FILE}")
    location = pyautogui.locateOnScreen(str(ICON_FILE), confidence=0.8)

    if location:
        x = location.left + location.width // 2
        y = location.top + location.height // 2
        print(f"✅ Found at screen position: ({x}, {y})")
        print(f"   Bounds: left={location.left}, top={location.top}, w={location.width}, h={location.height}")
        print()
        print("Ready! Run the trigger: python discord_trigger.py --watch")
    else:
        print("✗ Not found on screen.")
        print("  → Is the Cola sidebar visible?")
        print("  → Does the icon image match the current screen text?")
        print("  → Try lowering confidence in trigger_config.json (e.g. 0.7)")
        sys.exit(1)


if __name__ == "__main__":
    if "--test" in sys.argv:
        test_locate()
    else:
        main()
