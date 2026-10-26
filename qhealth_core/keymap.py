"""Windows scan codes -> Linux evdev key codes, so the keyboard heatmap uses one key numbering everywhere.

Set-1 scan codes (what Windows Raw Input reports as MakeCode) equal evdev codes for the main block;
only the E0-prefixed keys (arrows, right modifiers, nav cluster...) need a table.
"""
from typing import Optional

_E0_KEYS = {
    0x1C: 96,   # keypad Enter
    0x1D: 97,   # right Ctrl
    0x35: 98,   # keypad /
    0x37: 99,   # Print Screen
    0x38: 100,  # right Alt
    0x47: 102,  # Home
    0x48: 103,  # Up
    0x49: 104,  # Page Up
    0x4B: 105,  # Left
    0x4D: 106,  # Right
    0x4F: 107,  # End
    0x50: 108,  # Down
    0x51: 109,  # Page Down
    0x52: 110,  # Insert
    0x53: 111,  # Delete
    0x5B: 125,  # left Windows / Super
    0x5C: 126,  # right Windows
    0x5D: 127,  # Menu
}


def scancode_to_evdev(make_code: int, extended: bool) -> Optional[int]:
    """None for keys we don't count (fake shifts around E0 keys, overrun codes...)."""
    if extended:
        return _E0_KEYS.get(make_code)
    return make_code if 0 < make_code < 0x80 else None
