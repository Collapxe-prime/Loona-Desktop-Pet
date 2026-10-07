"""Short-lived irritation after repeated direct mouse interactions."""
from collections import deque


class MouseMood:
    def __init__(self):
        self.touches = deque(maxlen=2)
        self.pending = False
        self.until = None
        self.last_shake = -float("inf")
        self.approaches = deque(maxlen=3)
        self.cursor_inside = False

    def approach(self, now, inside, outside, moved=True, enabled=True):
        if not enabled:
            self.cursor_inside = inside
            return
        if not moved:
            return
        if outside:
            self.cursor_inside = False
        elif inside and not self.cursor_inside:
            self.cursor_inside = True
            self.approaches.append(now)
            if self.pending or (len(self.approaches) == 3 and now - self.approaches[0] <= 6):
                self.pending = True
                self.until = None

    def touch(self, now):
        self.touches.append(now)
        if self.pending or (len(self.touches) == 2 and now - self.touches[0] <= 6):
            self.pending = True
            self.until = None

    def soothe(self):
        self.pending=False
        self.until=None
        self.touches.clear()
        self.approaches.clear()

    def shake(self, now):
        if now - self.last_shake >= .4:
            self.last_shake = now
            self.touch(now)

    def active(self, now, blocked=False):
        if not self.pending:
            return False
        if blocked:
            self.until = None  # Show the reaction once dragging/falling ends.
            return False
        if self.until is None:
            self.until = now + 6
        if now >= self.until:
            self.pending = False
            self.touches.clear()
            self.approaches.clear()
            return False
        return True
