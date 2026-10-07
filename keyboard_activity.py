"""Transient keyboard activity, without text capture or event logging."""
import math

TEXT_KEYS = tuple(range(0x30, 0x3A)) + tuple(range(0x41, 0x5B)) + tuple(range(0x60, 0x70)) + (
    0x08, 0x0D, 0x20, 0xBA, 0xBB, 0xBC, 0xBD, 0xBE, 0xBF, 0xC0,
    0xDB, 0xDC, 0xDD, 0xDE, 0xE2)
SHORTCUT_KEYS = (0x11, 0x12, 0x5B, 0x5C)


class KeyboardActivity:
    def __init__(self):
        self.last_activity = -math.inf
        self.waiting_done = True

    def sample(self, now, pressed, shortcut=False, enabled=True):
        # Only the activity time survives this call. No characters or key history.
        if not enabled:
            self.last_activity = -math.inf
            self.waiting_done = True
        elif pressed and not shortcut:
            self.last_activity = now
            self.waiting_done = False

    def finish_waiting(self):
        self.waiting_done = True

    def animation(self, now, waiting=True):
        elapsed = now - self.last_activity
        if elapsed < 1.2:
            return "jumping"
        if waiting and not self.waiting_done:
            return "review"
        return None
