"""Velocity-based contact: finite friction, one-way platforms, no window attachment."""
import math

GRAVITY = 1600.0
STATIC_FRICTION = 7000.0
SLIDING_FRICTION = 3800.0
SEATED_GRIP = 2.0
AIR_DRAG = .7
THROW_AIR_DRAG = 1.4
GROUND_DRAG = 3.8
CONTACT_DOWN_SPEED = 300.0
CONTACT_DOWN_GAP = 12.0


def platform_key(p):
    return (p[3], p[6] if len(p) > 6 else "top") if p is not None and len(p) > 3 else None


class Physics:
    def __init__(self, now, y):
        self.last_tick = now
        self.y = float(y)
        self.vx = self.vy = 0.0
        self.air_x = None
        self.air_drag = AIR_DRAG
        self.grounded = True
        self.support = None
        self.window_sample = None
        self.window_velocity = (0.0, 0.0)
        self.window_acceleration = 0.0
        self.window_motion = {}
        self.slipping_until = self.balance_until = 0.0

    @property
    def slide_velocity(self):
        return self.vx - (self.window_velocity[0] if self.grounded and self.support else 0)

    def launch(self,now,x,y,vx,vy):
        """Transfer a released drag into free flight without inheriting contact."""
        self.last_tick=now
        self.air_x=float(x)
        self.y=float(y)
        self.vx,self.vy=float(vx),float(vy)
        self.air_drag=THROW_AIR_DRAG
        self.grounded=False
        self.support=None
        self.window_sample=None
        self.window_velocity=(0.,0.)
        self.window_acceleration=0.
        self.balance_until=self.slipping_until=0.

    @property
    def sliding(self):
        return abs(self.slide_velocity) > (25 if self.support else 8)

    def record_platform(self, p, now):
        stamp = p[5] if len(p) > 5 else now
        key = platform_key(p)
        record = self.window_motion.get(key)
        previous = record[0] if record else None
        interactive = p[7] if len(p) > 7 else True
        if previous is None:
            velocity, acceleration = (0.0, 0.0), 0.0
        elif stamp > previous[3]:
            elapsed = stamp - previous[3]
            velocity = ((p[4] - previous[1]) / elapsed, (p[1] - previous[2]) / elapsed)
            acceleration = (velocity[0] - record[1][0]) / elapsed if interactive else 0
        else:
            velocity, acceleration = record[1:]
        if not interactive:
            velocity, acceleration = (0.0, 0.0), 0.0
        result = ((key, p[4], p[1], stamp), velocity, acceleration)
        self.window_motion[key] = result
        return result

    def sample_window(self, p, now):
        self.window_sample, self.window_velocity, self.window_acceleration = self.record_platform(p, now)

    def step(self, now, x, y, width, height, bounds, dragging=False, paused=False, platforms=(), body=None, seated=False):
        dt = min(.05, max(0, now - self.last_tick))
        self.last_tick = now
        left, top, right, bottom = bounds
        bl, bt, br, feet = body or (0, 0, width, height)
        min_x, min_y = left - bl, top - bt
        max_x, floor = max(min_x, right - br), max(min_y, bottom - feet)
        if round(self.y) != y:
            self.y = float(y)
        if self.air_x is None or round(self.air_x) != x:
            self.air_x = float(x)
        self.air_x = max(min_x, min(max_x, self.air_x))
        self.y = max(min_y, min(floor, self.y))
        previous = self.support
        keys = set()
        for p in platforms:
            if len(p) > 3:
                keys.add(platform_key(p))
                self.record_platform(p, now)
        self.window_motion = {key: value for key, value in self.window_motion.items() if key in keys}
        old_feet = self.y + feet
        centre = self.air_x + (bl + br) / 2
        current = None
        if previous is not None:
            current = next((p for p in platforms if platform_key(p) == platform_key(previous)
                            and p[0] <= centre < p[2]), None)
        if current is not None and len(current) > 3:
            self.sample_window(current, now)
        else:
            self.window_sample = None
            self.window_velocity = (0.0, 0.0)
            self.window_acceleration = 0.0
        if dragging or paused:
            self.vx = self.vy = 0.0
            self.window_sample = None
            self.window_velocity = (0.0, 0.0)
            if dragging:
                self.air_drag = AIR_DRAG
                self.support = None
                self.grounded = self.y >= floor
            return round(self.air_x), round(self.y)

        next_vy = min(1200, self.vy + GRAVITY * dt)
        predicted_feet = old_feet + next_vy * dt
        # Window rectangles arrive in discrete scans. Keep an existing contact
        # across a small, gentle downward step, on either edge. This tolerance
        # cannot catch an airborne body or pull it after a fast downward move.
        gentle_descent = (current is not None and previous is not None
                          and abs(previous[1] - old_feet) <= .51
                          and 0 < self.window_velocity[1] <= CONTACT_DOWN_SPEED
                          and next_vy >= 0
                          and 0 <= current[1] - old_feet <= CONTACT_DOWN_GAP)
        # Upward edges push; braking upward motion can still leave the body airborne.
        contact = (current is not None and current[1] - feet >= min_y
                   and (current[1] <= predicted_feet + .51 or gentle_descent))
        floor_contact = current is None and self.y >= floor and next_vy >= 0
        old_vx = self.vx
        if contact:
            grip = SEATED_GRIP if seated else 1.0
            target = self.window_velocity[0]
            difference = target - self.vx
            static = (abs(difference) <= STATIC_FRICTION * grip * dt
                      and abs(self.window_acceleration) <= STATIC_FRICTION * grip)
            if static:
                self.vx = target
            else:
                self.vx += max(-SLIDING_FRICTION * grip * dt, min(SLIDING_FRICTION * grip * dt, difference))
            self.air_x += (old_vx + self.vx) * .5 * dt
            if abs(self.window_acceleration) > 1200 and (not seated or abs(self.vx-target)>25):
                self.balance_until = now + 1.05
            if abs(self.vx - target) > 25:
                self.slipping_until = now + .36
        else:
            rate = GROUND_DRAG if floor_contact else self.air_drag
            decay = math.exp(-rate * dt)
            self.air_x += self.vx * (1 - decay) / rate
            self.vx *= decay
            if abs(self.vx) < 8:
                self.vx = 0.0
        if self.air_x < min_x or self.air_x > max_x:
            self.air_x = max(min_x, min(max_x, self.air_x))
            self.vx = 0.0

        centre = self.air_x + (bl + br) / 2
        self.support = None
        if contact and current[0] <= centre < current[2]:
            self.support = current
            self.y = min(floor, current[1] - feet)
            self.vy = self.window_velocity[1]
        else:
            if contact:
                self.slipping_until = now + .36
            self.vy = next_vy
            self.y = max(min_y, min(floor, self.y + self.vy * dt))
            # Landing scans may include lower edges of the very same window.
            # Only downward crossing catches: no cooldown or artificial kick.
            hits = [p for p in platforms if p[0] <= centre < p[2] and p[1] - feet >= min_y
                    and old_feet <= p[1] + .51 and self.y + feet >= p[1]
                    and self.vy >= 0]
            if hits:
                self.support = min(hits, key=lambda p: p[1])
                self.y = self.support[1] - feet
                if len(self.support) > 3:
                    self.sample_window(self.support, now)
                    self.vy = self.window_velocity[1]
                else:
                    self.vy = 0.0
        self.grounded = self.support is not None or self.y >= floor
        if self.grounded:
            self.air_drag = AIR_DRAG
        if self.y >= floor:
            self.vy = 0.0
        elif self.y <= min_y and self.vy < 0:
            # A toss that reaches the ceiling must lose upward velocity there,
            # rather than staying pinned until gravity cancels it seconds later.
            self.vy = 0.0
        if self.support is None:
            self.window_sample = None
            self.window_velocity = (0.0, 0.0)
        return round(self.air_x), round(self.y)
