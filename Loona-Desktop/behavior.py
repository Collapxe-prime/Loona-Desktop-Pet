"""Autonomous actions with a local walking territory and interruptible scheduling."""
import random

WALK_DISTANCE = (450, 1100)
WANDER_RADIUS = 1400
PHONE_HOLD_SECONDS = (30, 45)
SITTING_HOLD_SECONDS = (60, 180)
SITTING_WEIGHT = 6
TASKBAR_SITTING_CHANCE = .25
WALK_SPEED = 180
STROLL_SPEED = 50
SPRINT_CHANCE = .15


class Autonomy:
    def __init__(self, now, x, left, right, durations, rng=None):
        self.rng = rng or random.Random()
        self.durations = durations
        self.walk_states = ("walking-left", "walking-right") if "walking-right" in durations else ("running-left", "running-right")
        self.action = None
        self.until = 0
        self.target = None
        self.walk_x = float(x)
        self.last_tick = now
        self.blocked = False
        self.sitting_remaining = None
        self.recenter(now, x, left, right)

    def schedule(self, now):
        self.next_action = now + self.rng.uniform(3, 6)

    def recenter(self, now, x, left, right):
        self.pause(now)
        self.leaving_window = False
        self.left = max(left, x - WANDER_RADIUS)
        self.right = max(self.left, min(right, x + WANDER_RADIUS))
        self.action = None
        self.target = None
        self.walk_x = float(x)
        self.last_tick = now
        self.blocked = False
        self.schedule(now)

    @property
    def sitting_committed(self):
        return self.action == 'sitting' or self.sitting_remaining is not None

    def cancel_sitting(self, now):
        self.sitting_remaining = None
        if self.action == 'sitting':
            self.action = None
        self.schedule(now)

    def pause(self, now, preserve_sitting=True):
        if not preserve_sitting:
            self.sitting_remaining = None
        elif self.action == 'sitting':
            remaining = max(0, self.until - now)
            self.sitting_remaining = remaining if remaining > 0 else None
        self.leaving_window = False
        self.action = self.target = None
        self.blocked = True
        self.last_tick = now

    def start_action(self, now, x, speeds, walking, on_window=False, exit_targets=(), on_taskbar=False):
        self.leaving_window = False
        choices = ["running", "review"] + (["walk", "walk"] if walking else [])
        if 'jumping' in self.durations:
            choices.append('jumping')
        if on_window:
            choices += ["sitting"] * SITTING_WEIGHT
            if walking and exit_targets:
                choices += ["leave-window"]
        choice = ("sitting" if on_taskbar and not on_window
                  and self.rng.random() < TASKBAR_SITTING_CHANCE else self.rng.choice(choices))
        if choice == "leave-window":
            self.target = self.rng.choice(exit_targets)
            self.walk_x = float(x)
            self.action = self.walk_states[1 if self.target > x else 0]
            self.leaving_window = True
            return
        if choice == "walk":
            distance = self.rng.uniform(*WALK_DISTANCE)
            goals = [max(self.left, x - distance), min(self.right, x + distance)]
            goals = [goal for goal in goals if abs(goal - x) >= 40]
            full_stride = [goal for goal in goals if abs(goal - x) >= WALK_DISTANCE[0]]
            goals = full_stride or goals
            if goals:
                self.target = self.rng.choice(goals)
                self.walk_x = float(x)
                self.action = self.walk_states[1 if self.target > x else 0]
                running_states=('running-left','running-right')
                if (self.walk_states[0]=='walking-left'
                        and all(n in self.durations and n in speeds for n in running_states)
                        and self.rng.random()<SPRINT_CHANCE):
                    self.action=running_states[1 if self.target>x else 0]
                return
            choice = "running"
        self.action = choice
        self.until = now + (self.rng.uniform(*SITTING_HOLD_SECONDS) if choice == "sitting" else
                            self.rng.uniform(*PHONE_HOLD_SECONDS) if choice == "running" else
                            self.durations[choice] * self.rng.randint(1, 2) / speeds[choice])

    def update(self, now, x, speeds, enabled=True, interrupted=False, walking=True, on_window=False, exit_targets=(), on_taskbar=False):
        dt = min(.05, max(0, now - self.last_tick))
        self.last_tick = now
        if not enabled or interrupted:
            self.pause(now, preserve_sitting=enabled)
            return None, x
        if self.sitting_remaining is not None:
            self.action = 'sitting'
            self.until = now + self.sitting_remaining
            self.sitting_remaining = None
            self.blocked = False
            return self.action, x
        if self.blocked:
            self.blocked = False
            self.schedule(now)
            return None, x
        if self.action is None and now >= self.next_action:
            self.start_action(now, x, speeds, walking, on_window=on_window, exit_targets=exit_targets,
                              on_taskbar=on_taskbar)
        if self.action in ("running-left", "running-right", "walking-left", "walking-right"):
            distance = self.target - self.walk_x
            step = self.movement_speed(self.action, speeds) * dt
            if abs(distance) <= step:
                x = self.target
                self.action = self.target = None
                self.leaving_window = False
                self.schedule(now)
                return None, x
            self.walk_x += step if distance > 0 else -step
            return self.action, self.walk_x
        if self.action is not None and now >= self.until:
            self.action = None
            self.schedule(now)
        return self.action, x

    @staticmethod
    def movement_speed(action, speeds):
        return (STROLL_SPEED if action.startswith("walking-") else WALK_SPEED) * speeds[action]
