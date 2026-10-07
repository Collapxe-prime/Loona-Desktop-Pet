"""Standalone Windows desktop sprite player. Python 3.10+ and Pillow."""
from __future__ import annotations
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
import logging
import math
import os
from pathlib import Path
import sys
import time

from PIL import Image, ImageFilter
from behavior import Autonomy, WALK_SPEED
from physics import Physics, platform_key
from windows import WindowPlatforms
from keyboard_activity import KeyboardActivity, TEXT_KEYS, SHORTCUT_KEYS
from mouse_mood import MouseMood
from revamp_loader import read_pack, load_pack
from app_metadata import read_version, user_data_directory

BASE = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
DATA_DIR = user_data_directory(BASE, frozen=getattr(sys,'frozen',False))
STATES = {
    "idle": (0, [1680, 660, 660, 840, 840, 1920], "Покой"),
    "running-right": (1, [120] * 7 + [220], "Бег вправо"),
    "running-left": (2, [120] * 7 + [220], "Бег влево"),
    "waving": (3, [140] * 3 + [280], "Приветствие"),
    "jumping": (4, [140] * 4 + [280], "Гримуар"),
    "failed": (5, [140] * 7 + [240], "Неудача"),
    "waiting": (6, [150] * 5 + [260], "Злость"),
    "running": (7, [120] * 5 + [220], "Работа"),
    "review": (8, [150] * 5 + [280], "Проверка"),
}
EXTRA_ANIMATIONS = {
    "sitting": ([180] * 12, "Сидение на краю"),
    "falling": ([80] * 12, "Падение"),
    "slipping": ([30] * 12, "Соскальзывание"),
    "balancing": ([70] * 12, "Удержание баланса"),
}
for extra_name, (extra_durations, extra_label) in EXTRA_ANIMATIONS.items():
    folder = BASE / "assets" / "animations" / extra_name
    if all((folder / f"{i:02}.png").is_file() for i in range(len(extra_durations))):
        STATES[extra_name] = (None, extra_durations, extra_label)
SPEEDS = [1 / 3, 0.5, 1.0, 1.5, 2.0]
SCALES = [1.0, 1.5, 2.0]
REACTION_RADII = [150, 300, 450, 600]
LANDING_BALANCE_SECONDS = 1.0
REVAMP_ROOT = BASE / "assets" / "revamp"
for name, label in (("walking-right", "Ходьба вправо"), ("walking-left", "Ходьба влево")):
    # Both eight-frame and older longer walking packs are supported;
    # read_pack validates the exact frame count from the manifest below.
    if all((REVAMP_ROOT / name / f"{i:02}.png").exists() for i in range(8)):
        STATES[name] = (None, [100] * 8, label)
REVAMP_PACK = read_pack(REVAMP_ROOT, STATES)
if REVAMP_PACK:
    for name, entry in REVAMP_PACK["animations"].items():
        row, _, label = STATES[name]
        STATES[name] = (row, entry["durations_ms"], label)


def load_frames(path: Path):
    if REVAMP_PACK:
        return load_pack(REVAMP_ROOT, REVAMP_PACK)
    with Image.open(path) as src:
        if src.size not in ((1536, 1872), (1536, 2288)):
            raise ValueError("Нужен спрайт-лист 1536×1872 или 1536×2288 с ячейками 192×208.")
        sheet = src.convert("RGBA")
    result = {}
    for name, (row, durations, _) in STATES.items():
        if row is None:
            folder = BASE / "assets" / "animations" / name
            result[name] = []
            for i in range(len(durations)):
                with Image.open(folder / f"{i:02}.png") as frame:
                    result[name].append(frame.convert("RGBA"))
            continue
        result[name] = [sheet.crop((i * 192, row * 208, (i + 1) * 192, (row + 1) * 208))
                        for i in range(len(durations))]
    if sheet.height == 2288:
        result["look"] = [sheet.crop((i % 8 * 192, (9 + i // 8) * 208,
                                     (i % 8 + 1) * 192, (10 + i // 8) * 208))
                          for i in range(16)]
    return result


def look_direction(dx, dy, previous=None):
    """Clockwise: 0=up, 4=right, 8=down, 12=left; small hysteresis."""
    if math.hypot(dx, dy) <= 18:
        return None
    angle = math.degrees(math.atan2(dx, -dy)) % 360
    if previous is not None:
        difference = abs((angle - previous * 22.5 + 180) % 360 - 180)
        if difference <= 14:
            return previous
    return int((angle + 11.25) // 22.5) % 16


def pixel_bytes(frame, scale, quality=None):
    if isinstance(quality,tuple) and quality[0]=='matched':
        from sprite_quality import soften
        frame=soften(frame,quality[1])
    elif quality:
        alpha = frame.getchannel("A")
        rgb = frame.convert("RGB")
        if quality == "look-soft":
            # Cursor poses were drawn at higher effective resolution. Match
            # the other sprites' detail without blurring their silhouettes.
            reduced = frame.convert("RGBa").resize((max(1, frame.width // 2), max(1, frame.height // 2)), Image.Resampling.BILINEAR)
            rgb = reduced.resize(frame.size, Image.Resampling.LANCZOS).convert("RGBA").convert("RGB")
        elif quality == "original":
            rgb = rgb.filter(ImageFilter.UnsharpMask(radius=.7, percent=145, threshold=3))
        else:
            rgb = rgb.filter(ImageFilter.GaussianBlur(radius=.25))
        frame = rgb.convert("RGBA")
        frame.putalpha(alpha)  # Keep silhouettes and transparency exactly intact.
    size = (round(frame.width * scale), round(frame.height * scale))
    if frame.size != size:
        frame = frame.resize(size, Image.Resampling.LANCZOS)
    return size, frame.convert("RGBa").tobytes("raw", "BGRa")


def self_test(sheet):
    frames = load_frames(sheet)
    assert all(len(frames[name]) == len(durations) for name, (_, durations, _) in STATES.items())
    test = Image.new("RGBA", (1, 1), (200, 100, 50, 128))
    assert pixel_bytes(test, 1)[1] == bytes((25, 50, 100, 128))
    for scale in SCALES:
        for group in frames.values():
            for frame in group:
                (width, height), data = pixel_bytes(frame, scale)
                assert len(data) == width * height * 4
    hover_total = 1680 if REVAMP_PACK else 840
    assert sum(STATES["jumping"][1]) == hover_total
    assert sum(d / SPEEDS[0] for d in STATES["jumping"][1]) == hover_total * 3
    print(f"PASS: {sum(len(frames[n]) for n in STATES)} animation frames, {len(frames.get('look', []))} look poses, "
          f"3 scales, premultiplied alpha, hover {hover_total}/{hover_total * 3} ms.")


class POINT(C.Structure):
    _fields_ = [("x", W.LONG), ("y", W.LONG)]


class SIZE(C.Structure):
    _fields_ = [("cx", W.LONG), ("cy", W.LONG)]


class MONITORINFO(C.Structure):
    _fields_ = [("cbSize", W.DWORD), ("rcMonitor", W.RECT),
                ("rcWork", W.RECT), ("dwFlags", W.DWORD)]


class BLENDFUNCTION(C.Structure):
    _fields_ = [("BlendOp", W.BYTE), ("BlendFlags", W.BYTE),
                ("SourceConstantAlpha", W.BYTE), ("AlphaFormat", W.BYTE)]


class BITMAPINFOHEADER(C.Structure):
    _fields_ = [("biSize", W.DWORD), ("biWidth", W.LONG), ("biHeight", W.LONG),
                ("biPlanes", W.WORD), ("biBitCount", W.WORD), ("biCompression", W.DWORD),
                ("biSizeImage", W.DWORD), ("biXPelsPerMeter", W.LONG),
                ("biYPelsPerMeter", W.LONG), ("biClrUsed", W.DWORD), ("biClrImportant", W.DWORD)]


class BITMAPINFO(C.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", W.DWORD * 3)]


LRESULT = C.c_ssize_t
WPARAM = C.c_size_t
LPARAM = C.c_ssize_t
WNDPROC = C.WINFUNCTYPE(LRESULT, W.HWND, W.UINT, WPARAM, LPARAM)


class WNDCLASS(C.Structure):
    _fields_ = [("style", W.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", C.c_int),
                ("cbWndExtra", C.c_int), ("hInstance", W.HINSTANCE), ("hIcon", W.HANDLE),
                ("hCursor", W.HANDLE), ("hbrBackground", W.HANDLE),
                ("lpszMenuName", W.LPCWSTR), ("lpszClassName", W.LPCWSTR)]


def bind(dll, name, restype, *argtypes):
    fn = getattr(dll, name)
    fn.restype, fn.argtypes = restype, argtypes
    return fn


class DesktopPet:
    def __init__(self, sheet, smoke=False):
        self.frames = load_frames(sheet)
        self.hq_frames = load_pack(REVAMP_ROOT / "hq", REVAMP_PACK, canvas=(384, 544)) if REVAMP_PACK else None
        # A fixed resting silhouette removes transparent cell padding without
        # changing the collision shape on every animation frame.
        solid = [f.getchannel("A").point(lambda a: 255 if a >= 64 else 0).getbbox()
                 for f in self.frames["idle"]]
        solid = [b for b in solid if b]
        self.body_bounds = (min(b[0] for b in solid), min(b[1] for b in solid),
                            max(b[2] for b in solid), max(b[3] for b in solid)) if solid else (0, 0, 192, 208)
        self.smoke = smoke
        self.state = "idle"
        self.selected_state = "idle"
        self.dynamic = True
        self.look_enabled = True
        self.autonomous = True
        self.walking = True
        self.physics_enabled = True
        self.windows_enabled = True
        self.window_platforms = WindowPlatforms()
        self.uniform_quality = True
        from sprite_quality import read_profile
        self.quality_profile = read_profile(REVAMP_ROOT) if REVAMP_PACK else None
        self.typing_enabled = True
        self.typing_waiting = True
        self.keyboard_activity = KeyboardActivity()
        self.waiting_for_typing = False
        self.mouse_mood = MouseMood()
        from head_petting import HeadPetting
        self.head_petting = HeadPetting()
        self.petting_active = False
        self.petting_started = None
        from petting_visuals import load_petting_visuals
        self.petting_visuals = load_petting_visuals(BASE / 'assets/petting-smile')
        self.petting_happy = False
        self.petting_happy_started = None
        self.petting_visual_age = 0
        self.petting_heart_tick = None
        self.petting_anger_once = False
        self.waiting_after_petting = False
        self.drag_turn_x = None
        self.drag_turn_direction = 0
        self.reaction_radius = 300
        self.look_index = None
        self.motion_facing = 1
        self.landing_balance_cycles = 0
        self.inspect_pending = False
        self.inspect_started = None
        self.last_cursor = None
        self.last_cursor_motion = -math.inf
        self.hovered = False
        self.hover_suppress_until = 0
        self.greeting_until = 0
        self.startup_wave = not smoke
        self.drag_direction = None
        self.drag_start = None
        self.drag_moved = False
        from mouse_throw import DragMotion
        self.drag_motion = DragMotion()
        self.menu_open = False
        self.speeds = {name: 1.0 for name in STATES}
        self.scale = 1.0
        self.x, self.y = None, None
        self.index = 0
        self.drag = None
        self.cache = {}
        self.paint_count = 0
        self.started = time.monotonic()
        self.closed = False
        if not smoke:
            try:
                settings = json.loads((DATA_DIR / "settings.json").read_text(encoding="utf-8"))
                if settings.get("state") in STATES:
                    self.state = settings["state"]
                self.dynamic = settings.get("dynamic", True) is not False
                self.look_enabled = settings.get("look_enabled", True) is not False
                self.autonomous = settings.get("autonomous", True) is not False
                self.walking = settings.get("walking", True) is not False
                self.physics_enabled = settings.get("physics_enabled", True) is not False
                self.windows_enabled = settings.get("windows_enabled", True) is not False
                self.uniform_quality = settings.get("uniform_quality", True) is not False
                self.typing_enabled = settings.get("typing_enabled", True) is not False
                self.typing_waiting = settings.get("typing_waiting", True) is not False
                if settings.get("reaction_radius") in REACTION_RADII:
                    self.reaction_radius = settings["reaction_radius"]
                if settings.get("scale") in SCALES:
                    self.scale = settings["scale"]
                for name, value in (settings.get("speeds", {}) if settings.get("speed_profile") == "animation-repair-v1" else {}).items():
                    if name in STATES and value in SPEEDS:
                        self.speeds[name] = value
                position = settings.get("position")
                if isinstance(position, list) and len(position) == 2 and all(type(v) is int for v in position):
                    self.x, self.y = position
            except (OSError, ValueError, TypeError, AttributeError):
                pass
        self.selected_state = self.state
        if self.startup_wave:
            self.state = "waving"
        # A stable hover area avoids flicker when animation frames change silhouette.
        bounds = [f.getbbox() for name in ("idle", "jumping") for f in self.frames[name]]
        bounds = [b for b in bounds if b]
        self.hover_bounds = (min(b[0] for b in bounds), min(b[1] for b in bounds),
                             max(b[2] for b in bounds), max(b[3] for b in bounds)) if bounds else (0, 0, 192, 208)
        idle_bounds = [f.getbbox() for f in self.frames['idle'] if f.getbbox()]
        self.petting_bounds = (min(b[0] for b in idle_bounds), min(b[1] for b in idle_bounds),
                               max(b[2] for b in idle_bounds), max(b[3] for b in idle_bounds)) if idle_bounds else self.hover_bounds
        self.user = C.WinDLL("user32", use_last_error=True)
        self.gdi = C.WinDLL("gdi32", use_last_error=True)
        self.kernel = C.WinDLL("kernel32", use_last_error=True)
        u, g, k = self.user, self.gdi, self.kernel
        try:
            bind(u, "SetProcessDpiAwarenessContext", W.BOOL, C.c_void_p)(C.c_void_p(-4))
        except AttributeError:
            u.SetProcessDPIAware()
        self.defproc = bind(u, "DefWindowProcW", LRESULT, W.HWND, W.UINT, WPARAM, LPARAM)
        self.instance = bind(k, "GetModuleHandleW", W.HINSTANCE, W.LPCWSTR)(None)
        self.register = bind(u, "RegisterClassW", W.ATOM, C.POINTER(WNDCLASS))
        self.create = bind(u, "CreateWindowExW", W.HWND, W.DWORD, W.LPCWSTR, W.LPCWSTR,
                           W.DWORD, C.c_int, C.c_int, C.c_int, C.c_int,
                           W.HWND, W.HANDLE, W.HINSTANCE, C.c_void_p)
        self.getdc = bind(u, "GetDC", W.HDC, W.HWND)
        self.releasedc = bind(u, "ReleaseDC", C.c_int, W.HWND, W.HDC)
        self.memdc = bind(g, "CreateCompatibleDC", W.HDC, W.HDC)
        self.deletedc = bind(g, "DeleteDC", W.BOOL, W.HDC)
        self.deleteobj = bind(g, "DeleteObject", W.BOOL, W.HANDLE)
        self.selectobj = bind(g, "SelectObject", W.HANDLE, W.HDC, W.HANDLE)
        self.dib = bind(g, "CreateDIBSection", W.HANDLE, W.HDC, C.POINTER(BITMAPINFO),
                        W.UINT, C.POINTER(C.c_void_p), W.HANDLE, W.DWORD)
        self.update = bind(u, "UpdateLayeredWindow", W.BOOL, W.HWND, W.HDC,
                           C.POINTER(POINT), C.POINTER(SIZE), W.HDC, C.POINTER(POINT),
                           W.DWORD, C.POINTER(BLENDFUNCTION), W.DWORD)
        self.cursor = bind(u, "GetCursorPos", W.BOOL, C.POINTER(POINT))
        self.key_state = bind(u, "GetAsyncKeyState", C.c_short, C.c_int)
        self.set_cursor = bind(u, "SetCursor", W.HANDLE, W.HANDLE)
        self.arrow_cursor = bind(u, "LoadCursorW", W.HANDLE, W.HINSTANCE, C.c_void_p)(None, C.c_void_p(32512))
        if not self.arrow_cursor:
            raise C.WinError(C.get_last_error())
        self.capture = bind(u, "SetCapture", W.HWND, W.HWND)
        self.releasecapture = bind(u, "ReleaseCapture", W.BOOL)
        self.destroy = bind(u, "DestroyWindow", W.BOOL, W.HWND)
        self.show = bind(u, "ShowWindow", W.BOOL, W.HWND, C.c_int)
        self.settimer = bind(u, "SetTimer", C.c_size_t, W.HWND, C.c_size_t, W.UINT, C.c_void_p)
        self.killtimer = bind(u, "KillTimer", W.BOOL, W.HWND, C.c_size_t)
        self.create_menu = bind(u, "CreatePopupMenu", W.HANDLE)
        self.append_menu = bind(u, "AppendMenuW", W.BOOL, W.HANDLE, W.UINT, C.c_size_t, W.LPCWSTR)
        self.track_menu = bind(u, "TrackPopupMenu", W.UINT, W.HANDLE, W.UINT,
                               C.c_int, C.c_int, C.c_int, W.HWND, C.POINTER(W.RECT))
        self.destroy_menu = bind(u, "DestroyMenu", W.BOOL, W.HANDLE)
        self.foreground = bind(u, "SetForegroundWindow", W.BOOL, W.HWND)
        self.callback = WNDPROC(self.wndproc)
        klass = WNDCLASS(0, self.callback, 0, 0, self.instance, None,
                         self.arrow_cursor, None, None, "LoonaDesktopPet")
        if not self.register(C.byref(klass)):
            raise C.WinError(C.get_last_error())
        work = W.RECT()
        bind(u, "SystemParametersInfoW", W.BOOL, W.UINT, W.UINT, C.c_void_p, W.UINT)(48, 0, C.byref(work), 0)
        if self.x is None:
            self.x, self.y = work.right - 240, work.bottom - 224
        # Recover settings that point outside the current virtual desktop.
        metric = bind(u, "GetSystemMetrics", C.c_int, C.c_int)
        left, top, width, height = [metric(v) for v in (76, 77, 78, 79)]
        if not (left - 100 < self.x < left + width and top - 100 < self.y < top + height):
            self.x, self.y = work.right - 240, work.bottom - 224
        self.monitor_from_point = bind(u, "MonitorFromPoint", W.HANDLE, POINT, W.DWORD)
        self.monitor_info = bind(u, "GetMonitorInfoW", W.BOOL, W.HANDLE, C.POINTER(MONITORINFO))
        safe_left, safe_right = self.walking_bounds()
        self.autonomy = Autonomy(time.monotonic(), self.x, safe_left, safe_right,
                                 {name: sum(data[1]) / 1000 for name, data in STATES.items()})
        self.physics = Physics(time.monotonic(), self.y)
        self.hwnd = self.create(0x80000 | 0x80 | 0x8, "LoonaDesktopPet", "Loona Desktop",
                                0x80000000, self.x, self.y, 192, 208, None, None, self.instance, None)
        if not self.hwnd:
            raise C.WinError(C.get_last_error())
        if smoke:
            class_cursor = bind(u, "GetClassLongPtrW", C.c_size_t, W.HWND, C.c_int)(self.hwnd, -12)
            assert class_cursor == self.arrow_cursor, "Window class must define IDC_ARROW"
            handled = bind(u, "SendMessageW", LRESULT, W.HWND, W.UINT, WPARAM, LPARAM)(
                self.hwnd, 0x20, self.hwnd, 1 | (0x200 << 16))
            assert handled == 1, "WM_SETCURSOR must be handled for the client area"
            assert bind(u, "GetCursor", W.HANDLE)() == self.arrow_cursor
            logging.info("SMOKE PASS: class cursor and hover cursor are IDC_ARROW")
        self.render()
        if not smoke:
            self.show(self.hwnd, 4)
        self.deadline = time.monotonic() + self.duration()
        if smoke:
            self.check_dynamic_rendering()
            self.check_petting_rendering()
            self.check_physics_rendering()
            self.is_visible = bind(u, "IsWindowVisible", W.BOOL, W.HWND)
            assert not self.is_visible(self.hwnd), "Smoke-test window must stay hidden"
            logging.info("SMOKE PASS: diagnostic window stays hidden")
        if not self.settimer(self.hwnd, 1, 10, None):
            raise C.WinError(C.get_last_error())
        logging.info("Started pid=%s hwnd=%s state=%s paints=%s", os.getpid(), self.hwnd, self.state, self.paint_count)

    def duration(self):
        if self.state == "balancing" and getattr(self, "landing_balance_cycles", 0) > 0:
            return LANDING_BALANCE_SECONDS / len(self.frames["balancing"])
        return STATES[self.state][1][self.index] / (1000 * self.speeds[self.state])

    def walking_bounds(self, allow_exit=False):
        left, top, right, bottom = self.screen_bounds()
        bl, bt, br, feet = self.collision_bounds()
        safe_left, safe_right = left - bl + 2, max(left - bl + 2, right - br - 2)
        if not allow_exit and self.physics_enabled and hasattr(self, "physics") and self.physics.support:
            lo, level, hi = self.physics.support[:3]
            # Keep the centre of the feet on this platform during autonomous walks.
            centre = (bl + br) / 2
            lo = max(safe_left, lo - centre + 2)
            return lo, max(lo, min(safe_right, hi - centre - 2))
        return safe_left, safe_right

    def window_exit_targets(self):
        if not self.physics_enabled or not self.physics.support:
            return ()
        lo, level, hi = self.physics.support[:3]
        bl, bt, br, feet = self.collision_bounds()
        centre = (bl + br) / 2
        left, right = self.walking_bounds(allow_exit=True)
        # Go beyond the actual window edge, while respecting screen barriers.
        return tuple(goal for goal in (lo - centre - 32, hi - centre + 32)
                     if left <= goal <= right)

    def collision_bounds(self):
        return tuple(round(v * self.scale) for v in getattr(self, "body_bounds", (0, 0, 192, 208)))

    def screen_bounds(self):
        center = POINT(round(self.x + 96 * self.scale), round(self.y + 104 * self.scale))
        monitor = self.monitor_from_point(center, 2)
        info = MONITORINFO()
        info.cbSize = C.sizeof(info)
        if self.monitor_info(monitor, C.byref(info)):
            return info.rcWork.left, info.rcWork.top, info.rcWork.right, info.rcWork.bottom
        return self.x - 220, self.y, self.x + 220 + round(192 * self.scale), self.y + round(208 * self.scale)

    def update_physics(self, now, dragging=False):
        if not self.physics_enabled:
            self.landing_balance_cycles = 0
            self.physics.last_tick = now
            self.physics.vy = 0
            self.physics.vx = 0
            self.physics.y = float(self.y)
            return
        was_grounded = self.physics.grounded
        old_support = self.physics.support
        old_position = self.x, self.y
        self.x, self.y = self.physics.step(now, self.x, self.y,
                                          round(192 * self.scale), round(208 * self.scale),
                                          self.screen_bounds(), dragging=dragging,
                                          paused=self.menu_open,
                                          seated=getattr(self,'state','idle') == 'sitting',
                                          platforms=self.window_platforms.scan(now)
                                          if self.windows_enabled and not self.smoke else (),
                                          body=self.collision_bounds())
        motion = getattr(self, 'drag_motion', None)
        if dragging and motion is not None:
            motion.sample(now, self.x, self.y)
        support = self.physics.support
        if dragging or not self.physics.grounded:
            self.landing_balance_cycles = 0
        elif not was_grounded and not self.menu_open and self.dynamic and "balancing" in self.frames:
            self.landing_balance_cycles = 1
            self.physics.balance_until = 0
            if self.state == "balancing":
                self.index = 0
                self.deadline = now + self.duration()
        if (was_grounded and old_support is not None and not self.physics.grounded
                and not dragging and self.autonomy.leaving_window
                and self.autonomy.action in ("running-left", "running-right", "walking-left", "walking-right")):
            direction = 1 if self.autonomy.action.endswith("-right") else -1
            self.physics.vx += direction * self.autonomy.movement_speed(self.autonomy.action, self.speeds)
            self.physics.air_x = float(self.x)
            self.physics.slipping_until = now + .36
        same_window = (old_support is not None and support is not None
                       and len(old_support) > 3 and len(support) > 3 and platform_key(old_support) == platform_key(support))
        if same_window:
            dx = self.x - old_position[0]
            self.autonomy.walk_x += dx
            if self.autonomy.target is not None:
                self.autonomy.target += dx
            left, right = self.walking_bounds(allow_exit=self.autonomy.leaving_window)
            self.autonomy.left = max(left, self.autonomy.left + dx)
            self.autonomy.right = max(self.autonomy.left, min(right, self.autonomy.right + dx))
            if self.autonomy.target is not None:
                limits = (left, right) if self.autonomy.leaving_window else (self.autonomy.left, self.autonomy.right)
                self.autonomy.target = max(limits[0], min(limits[1], self.autonomy.target))
        if self.physics.grounded and (not was_grounded or old_support != support and not same_window) and not dragging:
            self.recenter_walk()
            self.save()
        if old_position != (self.x, self.y):
            self.render()

    def check_physics_rendering(self):
        original_position, original_physics = (self.x, self.y), self.physics
        left, top, right, bottom = self.screen_bounds()
        bl, bt, br, feet = self.collision_bounds()
        floor = max(top - bt, bottom - feet)
        self.y = max(top - bt, floor - 80)
        before = self.y
        now = time.monotonic()
        self.physics = Physics(now, self.y)
        self.update_physics(now + .05)
        assert self.y > before
        for i in range(2, 40):
            self.update_physics(now + i * .05)
        assert self.y == floor and self.physics.grounded and self.physics.vy == 0
        self.x = right + 100
        self.update_physics(now + 2, dragging=True)
        assert self.x == max(left - bl, right - br)
        self.x=round((left+right-bl-br)/2)
        self.y=max(top-bt,floor-120)
        launch_x,launch_y=self.x,self.y
        self.physics.launch(now+2.1,self.x,self.y,600,-650)
        self.update_physics(now+2.12)
        assert self.x>launch_x and self.y<launch_y
        logging.info('SMOKE PASS: thrown sprite renders upward and horizontal inertia')
        self.x, self.y = original_position
        self.physics = original_physics
        self.recenter_walk()
        self.render()
        logging.info("SMOKE PASS: native gravity rendering, taskbar floor and right screen barrier")
        # Exercise window-top landing through the same controller/render path,
        # using synthetic geometry so no visible test windows are created.
        original_scan, original_smoke, original_windows = self.window_platforms.scan, self.smoke, self.windows_enabled
        try:
            platform_y = top + feet + 80
            if platform_y < bottom:
                self.window_platforms.scan = lambda now: [(left, platform_y, right, 12345, left)]
                self.smoke = False
                self.windows_enabled = True
                self.save = lambda: None
                self.y = platform_y - feet - 10
                self.physics = Physics(now, self.y)
                for i in range(1, 20):
                    self.update_physics(now + i * .05)
                assert self.y + feet == platform_y
                assert self.physics.support == (left, platform_y, right, 12345, left)
                before = self.x, self.y
                self.window_platforms.scan = lambda now: [(left - 2, platform_y - 2, right - 2, 12345, left - 2)]
                self.update_physics(now + 1)
                assert before[0] - 2 <= self.x <= before[0]
                assert self.y == before[1] - 2
                assert self.physics.grounded
                self.window_platforms.scan = lambda now: []
                self.update_physics(now + 1.05)
                assert not self.physics.grounded
                logging.info("SMOKE PASS: window platform landing and falling after removal")
        finally:
            self.window_platforms.scan = original_scan
            self.smoke, self.windows_enabled = original_smoke, original_windows
            if "save" in self.__dict__:
                del self.save
            self.x, self.y = original_position
            self.physics = original_physics
            self.recenter_walk()
            self.render()

    def recenter_walk(self):
        left, right = self.walking_bounds()
        self.autonomy.recenter(time.monotonic(), self.x, left, right)

    def release_drag(self,now):
        clicked = not self.drag_moved
        self.drag = self.drag_direction = None
        self.hovered = False
        velocity = self.drag_motion.velocity(now) if self.physics_enabled and not clicked else (0.,0.)
        thrown = math.hypot(*velocity) > 0
        if thrown:
            self.physics.launch(now,self.x,self.y,*velocity)
            self.landing_balance_cycles=0
            self.gait_driven=False
            self.motion_facing=1 if velocity[0]>=0 else -1
        return clicked,thrown

    def cancel_inspection(self):
        self.inspect_pending = False
        self.inspect_started = None

    def request_inspection(self):
        self.cancel_inspection()
        self.inspect_pending = self.dynamic and "look" in self.frames

    def inspection_look(self, now):
        if not self.dynamic or self.drag is not None:
            self.cancel_inspection()
            return None
        if not (self.inspect_pending or self.inspect_started is not None):
            return None
        stable = (not self.physics_enabled or
                  (self.physics.grounded and not self.physics.sliding
                   and self.landing_balance_cycles == 0 and now >= self.physics.balance_until))
        if not stable or self.startup_wave:
            self.inspect_pending = True
            self.inspect_started = None
            return None
        if self.inspect_started is None:
            self.inspect_pending = False
            self.inspect_started = now
        phase = int((now - self.inspect_started) / .5)
        if phase >= 6:
            self.cancel_inspection()
            self.hovered = False
            self.hover_suppress_until = now + .25
            self.last_cursor_motion = -math.inf
            return None
        rect = None
        if self.physics_enabled and self.physics.support:
            support = self.physics.support
            if len(support) > 3:
                rect = getattr(self.window_platforms, "rectangles", {}).get(support[3])
            if rect is None:
                rect = (support[0], support[1], support[2], support[1] + 180)
        if rect is None:
            return (12, 10, 8, 6, 4, 0)[phase]
        left, top, right, bottom = rect
        points = ((left + 20, top + 30), (left + 20, bottom - 20),
                  ((left + right) / 2, bottom - 20), (right - 20, bottom - 20),
                  (right - 20, top + 30), ((left + right) / 2, top + 30))
        tx, ty = points[phase]
        return look_direction((tx - self.x) / self.scale - 96,
                              (ty - self.y) / self.scale - 104) or 0

    def update_behavior(self, now, position=None):
        if self.menu_open:
            return
        if not self.dynamic or self.drag is not None:
            self.landing_balance_cycles = 0
        if position is None:
            pos = POINT()
            if not self.cursor(C.byref(pos)):
                return
            position = (pos.x, pos.y)
        cursor_moved = position != self.last_cursor
        if cursor_moved:
            self.last_cursor_motion = now
            self.last_cursor = position
        px = (position[0] - self.x) / self.scale
        py = (position[1] - self.y) / self.scale
        nearby = math.hypot(px - 96, py - 104) * self.scale <= self.reaction_radius
        left, top, right, bottom = self.hover_bounds
        inside = left <= px < right and top <= py < bottom
        mood = getattr(self, "mouse_mood", None)
        keyboard = getattr(self, "keyboard_activity", None)
        typing_action = keyboard.animation(now, self.typing_waiting) if (
            keyboard is not None and self.typing_enabled) else None
        petter = getattr(self, 'head_petting', None)
        petting_allowed = (self.dynamic and self.selected_state == 'idle' and self.drag is None
            and not self.startup_wave and typing_action is None and len(self.frames['idle']) >= 21
            and (not self.physics_enabled or (self.physics.grounded and not self.physics.sliding
                 and now >= self.physics.balance_until and self.landing_balance_cycles == 0)))
        if petter:petter.bounds=getattr(self,'petting_bounds',self.hover_bounds)
        head_candidate = bool(petter and petting_allowed and petter.in_sprite(px,py))
        if petter and petter.sample(now,px,py,enabled=petting_allowed,moved=cursor_moved):
            self.petting_anger_once=False
            if mood:mood.soothe()
            self.greeting_until=0
            self.cancel_inspection()
        if not petting_allowed:
            self.petting_anger_once=False
        elif petter and petter.consume_stop_anger():
            self.petting_anger_once=True
        petting = bool(petter and petter.active(now))
        if mood:
            mood.approach(now, inside,
                outside=not (left - 12 <= px < right + 12 and top - 12 <= py < bottom + 12),
                moved=cursor_moved, enabled=self.dynamic and self.drag is None and not self.startup_wave and not head_candidate and not petting)
        annoyed = mood.active(now, blocked=(not self.dynamic or (self.drag is not None and self.drag_moved)
            or self.startup_wave or (self.physics_enabled and (
                not self.physics.grounded or self.physics.sliding
                or now < self.physics.balance_until or self.landing_balance_cycles > 0)))) if mood else False
        annoyed = annoyed or getattr(self,'petting_anger_once',False)
        if annoyed:
            self.greeting_until = 0
            self.cancel_inspection()
        inspect_look = self.inspection_look(now)
        if not inside:
            self.hovered = False
        action, new_x = self.autonomy.update(
            now, self.x, self.speeds,
            enabled=self.dynamic and self.autonomous and self.selected_state == "idle",
            interrupted=(self.startup_wave or self.drag is not None or typing_action or annoyed or petting or head_candidate
                         or self.inspect_pending or self.inspect_started is not None
                         or nearby or now < self.greeting_until
                         or (self.physics_enabled and (not self.physics.grounded or self.physics.sliding
                                                      or now < self.physics.balance_until
                                                      or getattr(self, "landing_balance_cycles", 0) > 0))), walking=self.walking,
            on_window=self.physics_enabled and self.physics.support is not None and "sitting" in self.frames,
            exit_targets=self.window_exit_targets() if self.physics_enabled else ())
        walk_distance = round(new_x) - self.x
        moved = walk_distance != 0
        self.x = round(new_x)
        if self.physics_enabled and abs(self.physics.slide_velocity) >= 8:
            self.motion_facing = 1 if self.physics.slide_velocity > 0 else -1
        target = "waving" if self.startup_wave else self.selected_state
        if self.dynamic and not self.startup_wave:
            if self.drag is not None:
                target = "balancing" if "balancing" in self.frames else self.selected_state
            elif self.drag is None and self.physics_enabled and not self.physics.grounded:
                target = "slipping" if now < self.physics.slipping_until else "falling"
                if target not in self.frames:
                    target = self.selected_state
            elif self.physics_enabled and self.drag is None and getattr(self, "landing_balance_cycles", 0) > 0:
                target = "balancing"
            elif self.physics_enabled and self.drag is None and (self.physics.sliding or now < self.physics.balance_until):
                target = "slipping" if self.physics.sliding else "balancing"
                if target not in self.frames:
                    target = self.selected_state
            elif annoyed:
                target = "waiting"
            elif petting or head_candidate:
                target = "idle"
            elif inspect_look is not None:
                target = "idle"
            elif now < self.greeting_until:
                target = "waving"
            elif typing_action is not None:
                target = typing_action
            elif action is not None:
                target = action
        look = None if petting or head_candidate else inspect_look
        if (look is None and self.dynamic and self.look_enabled and "look" in self.frames
                and target == "idle" and self.drag is None
                and nearby and not petting and not head_candidate
                and (not self.physics_enabled or self.physics.grounded)
                and now - self.last_cursor_motion < 1.0):
            look = look_direction(px - 96, py - 104, self.look_index)
        changed_state = target != self.state
        was_petting = getattr(self,'petting_active',False)
        self.petting_active = petting and target == 'idle'
        if self.petting_active and not was_petting:self.petting_started=now
        pet_index = petter.frame(now,self.petting_started) if self.petting_active else None
        changed_pet = self.petting_active != was_petting or (pet_index is not None and pet_index != self.index)
        if was_petting and not self.petting_active:self.petting_started=None
        was_happy = getattr(self, 'petting_happy', False)
        self.petting_happy = bool(self.petting_active and petter.happy(now)
                                 and getattr(self, 'petting_visuals', None))
        if self.petting_happy and not was_happy:
            self.petting_happy_started = now
        previous_tick = getattr(self, 'petting_heart_tick', None)
        if self.petting_happy:
            self.petting_visual_age = now - self.petting_happy_started
            self.petting_heart_tick = int(self.petting_visual_age * 15)
        else:
            self.petting_happy_started = None
            self.petting_heart_tick = None
        changed_pet |= self.petting_happy != was_happy or self.petting_heart_tick != previous_tick
        waiting_for_typing = (self.dynamic and target == "review"
                              and typing_action == "review" and not annoyed
                              and self.drag is None and inspect_look is None
                              and now >= self.greeting_until)
        changed_wait_source = waiting_for_typing != getattr(self, "waiting_for_typing", False)
        waiting_after_petting = getattr(self,'petting_anger_once',False) and target == 'waiting'
        changed_wait_source |= waiting_after_petting != getattr(self,'waiting_after_petting',False)
        self.waiting_after_petting=waiting_after_petting
        self.waiting_for_typing = waiting_for_typing
        self.waiting_annoyed = annoyed and target == "waiting"
        changed_look = look != self.look_index
        stride = (REVAMP_PACK or {}).get('animations', {}).get(target, {}).get('stride_px')
        self.gait_driven = bool(stride and target == action and self.dynamic
                                and self.autonomous and self.selected_state == 'idle')
        gait_index = None
        if self.gait_driven:
            from gait_phase import advance_phase
            phase = getattr(self, 'gait_phase', 0.0) if getattr(self, 'gait_state', None) == target else 0.0
            self.gait_phase = advance_phase(phase, walk_distance, self.scale, stride)
            self.gait_state = target
            gait_index = int(self.gait_phase * len(self.frames[target]))
        else:
            self.gait_state = None
        if changed_state or changed_look or changed_wait_source or changed_pet:
            if changed_state or changed_wait_source or (self.look_index is not None and look is None):
                self.index = 0
                self.state = target
                self.deadline = now + self.duration()
            self.look_index = look
            if pet_index is not None:
                self.index=pet_index
            elif changed_pet and target=='idle':
                self.index=20
                self.deadline=now+self.duration()
            if gait_index is not None:
                self.index = gait_index
            self.render()
        elif moved:
            if gait_index is not None:
                self.index = gait_index
            self.render()

    def advance_animation(self, now, position=None):
        if getattr(self,'petting_active',False):
            return False
        if getattr(self, 'gait_driven', False):
            return False
        if self.look_index is not None or now < self.deadline:
            return False
        # Keep cadence on its timeline: timer jitter must not lengthen a cycle
        # by another timer tick for every added frame. After a long suspension,
        # resume the current pose rather than replaying hours of missed time.
        cycle = sum(STATES[self.state][1]) / (1000 * self.speeds[self.state])
        if now - self.deadline > max(1.0, cycle):
            self.deadline = now
        next_index = self.index + 1
        if (self.state == 'waiting' and getattr(self,'waiting_after_petting',False)
                and next_index >= len(self.frames['waiting'])):
            self.petting_anger_once=False
            self.update_behavior(now,position)
            self.render()
            return True
        if (self.state == "review" and getattr(self, "waiting_for_typing", False)
                and next_index >= len(self.frames["review"])):
            self.keyboard_activity.finish_waiting()
            self.index = 0
            self.deadline = now + self.duration()
            self.update_behavior(now, position)
            self.render()
            return True
        if (self.state == "balancing" and getattr(self, "landing_balance_cycles", 0) > 0
                and next_index >= len(self.frames["balancing"])):
            self.landing_balance_cycles -= 1
            self.index = 0
            self.deadline += self.duration()
            if self.landing_balance_cycles == 0:
                self.update_behavior(now, position)
            self.render()
            return True
        if self.startup_wave and self.state == "waving" and next_index >= len(self.frames["waving"]):
            self.startup_wave = False
            self.hovered = False
            self.last_cursor_motion = -math.inf
            self.hover_suppress_until = now + .15
            self.update_behavior(now, position)
            # A manually selected waving loop remains available after the startup greeting.
            if self.state == "waving":
                self.index = 0
                self.deadline = now + self.duration()
                self.render()
        else:
            self.index = next_index % len(self.frames[self.state])
            if self.index == 0 and self.state == "waiting" and REVAMP_PACK:
                self.index = REVAMP_PACK["animations"]["waiting"].get("loop_start", 0)
            self.deadline += self.duration()
            self.render()
        return True

    def check_dynamic_rendering(self):
        original = self.dynamic, self.look_enabled, self.selected_state
        self.dynamic = self.look_enabled = True
        self.selected_state = "idle"
        now = time.monotonic()
        # Exercise the real render path for all look poses and transient states.
        petter = self.head_petting
        self.head_petting = None  # Gaze diagnostics are separate from stroking diagnostics.
        for i in range(len(self.frames.get("look", []))):
            angle = math.radians(i * 22.5)
            self.look_index = None
            distance = min(100, self.reaction_radius / self.scale * .7)
            pos = (self.x + (96 + distance * math.sin(angle)) * self.scale,
                   self.y + (104 - distance * math.cos(angle)) * self.scale)
            self.update_behavior(now, pos)
            assert self.look_index == i
        self.head_petting = petter
        # The synthetic circle can cross the current silhouette several times;
        # isolate the next hover check from the valid repeated-approach reaction.
        self.mouse_mood = MouseMood()
        self.hovered = True
        self.update_behavior(now, (self.x + 96 * self.scale, self.y + 104 * self.scale))
        assert self.state == "idle"  # Hovering no longer opens the grimoire.
        self.drag, self.drag_direction = (0, 0), "running-left"
        self.update_behavior(now, (self.x, self.y))
        assert self.state == "balancing"
        self.drag_direction = "running-right"
        self.update_behavior(now, (self.x, self.y))
        assert self.state == "balancing"
        self.drag = self.drag_direction = None
        self.greeting_until = now + .5
        self.update_behavior(now, (self.x, self.y))
        assert self.state == "waving"
        self.greeting_until = 0
        self.update_behavior(now + 2, (self.x, self.y))
        assert self.state == "idle" and self.look_index is None
        self.dynamic, self.look_enabled, self.selected_state = original
        self.last_cursor = None
        logging.info("SMOKE PASS: 16 look directions, no grimoire on hover, both drag directions, greeting and idle restore")
        original_x = self.x
        self.autonomy.blocked = False
        stroll = self.autonomy.walk_states[1]
        self.autonomy.action = stroll
        self.autonomy.target = self.x + 40
        self.autonomy.walk_x = float(self.x)
        self.autonomy.last_tick = now
        far = (self.x + 96 * self.scale + self.reaction_radius + 100, self.y + 104 * self.scale)
        self.update_behavior(now + .05, far)
        assert self.x > original_x and self.state == stroll
        if REVAMP_PACK and REVAMP_PACK['animations'][stroll].get('stride_px'):
            assert self.gait_driven and self.gait_phase > 0
            phase_index = self.index
            assert not self.advance_animation(now + .1, far)
            assert self.index == phase_index
        for i in range(2, 25):
            self.update_behavior(now + i * .05, far)
        assert self.x == original_x + 40 and self.state == "idle"
        assert not getattr(self, 'gait_driven', False)
        self.x = original_x
        self.recenter_walk()
        self.render()
        logging.info("SMOKE PASS: autonomous walking rendered and returned to idle")

    def check_petting_rendering(self):
        if len(self.frames['idle'])<21:return
        original=self.dynamic,self.selected_state,self.physics_enabled,self.head_petting
        from head_petting import HeadPetting
        self.dynamic=True;self.selected_state='idle';self.physics_enabled=False
        self.head_petting=HeadPetting()
        now=time.monotonic()
        points=list(range(88,121,2))+list(range(118,87,-2))
        for i,x in enumerate(points):
            self.update_behavior(now+i*.02,(self.x+x*self.scale,self.y+68*self.scale))
        assert self.petting_active and self.state=='idle' and self.look_index is None
        self.update_behavior(now+.8,(self.x+104*self.scale,self.y+68*self.scale))
        assert self.index==18
        self.render()
        self.update_behavior(now+2.5,(self.x+self.reaction_radius+300,self.y))
        assert not self.petting_active
        self.head_petting=HeadPetting()
        for i in range(160):
            phase=i%32
            x=88+2*(phase if phase<=16 else 32-phase)
            self.update_behavior(now+3+i*.02,(self.x+x*self.scale,self.y+150*self.scale))
            if i<100:assert not self.petting_happy
            if i==105:assert self.petting_happy
        assert self.petting_happy and self.petting_visuals is not None
        self.render()
        self.update_behavior(now+8,(self.x+self.reaction_radius+300,self.y))
        assert not self.petting_happy
        self.dynamic,self.selected_state,self.physics_enabled,self.head_petting=original
        logging.info('SMOKE PASS: sprite stroking renders smile and hearts after two continuous seconds, then releases')

    def render(self):
        group, frame_index = ("look", self.look_index) if self.look_index is not None else (self.state, self.index)
        mirrored = group in ("slipping", "falling") and getattr(self, "motion_facing", 1) < 0
        quality = ("new" if group in EXTRA_ANIMATIONS else "original") if self.uniform_quality and not REVAMP_PACK else None
        if REVAMP_PACK and self.uniform_quality and self.quality_profile:
            from sprite_quality import radius_for
            quality_group = 'idle' if frame_index in REVAMP_PACK['animations'].get(group,{}).get('idle_pose_frames',[]) else group
            quality = ('matched',radius_for(self.quality_profile,quality_group,self.scale))
        elif REVAMP_PACK and group == "look" and self.uniform_quality:
            quality = "look-soft"
        if getattr(self, 'petting_happy', False):
            frame = self.petting_visuals.image(self.petting_visual_age, hq=bool(self.hq_frames))
            quality = ('matched', self.petting_visuals.radius(self.scale)) if self.uniform_quality else None
            # Moving particles are rendered directly, avoiding an ever-growing cache.
            (width, height), pixels = pixel_bytes(frame, self.scale / 2 if self.hq_frames else self.scale, quality=quality)
        else:
            key = (group, frame_index, self.scale, mirrored, quality)
            if key not in self.cache:
                frame = (self.hq_frames or self.frames)[group][frame_index]
                if mirrored:
                    frame = frame.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                self.cache[key] = pixel_bytes(frame, self.scale / 2 if self.hq_frames else self.scale, quality=quality)
            (width, height), pixels = self.cache[key]
        screen = self.getdc(None)
        dc = self.memdc(screen)
        bitmap = previous = None
        try:
            info = BITMAPINFO()
            info.bmiHeader = BITMAPINFOHEADER(C.sizeof(BITMAPINFOHEADER), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
            bits = C.c_void_p()
            bitmap = self.dib(dc, C.byref(info), 0, C.byref(bits), None, 0)
            if not bitmap or not bits.value:
                raise C.WinError(C.get_last_error())
            previous = self.selectobj(dc, bitmap)
            C.memmove(bits, pixels, len(pixels))
            ok = self.update(self.hwnd, screen, C.byref(POINT(self.x, self.y)),
                             C.byref(SIZE(width, height)), dc, C.byref(POINT(0, 0)),
                             0, C.byref(BLENDFUNCTION(0, 0, 255, 1)), 2)
            if not ok:
                raise C.WinError(C.get_last_error())
            self.paint_count += 1
        finally:
            if previous:
                self.selectobj(dc, previous)
            if bitmap:
                self.deleteobj(bitmap)
            if dc:
                self.deletedc(dc)
            if screen:
                self.releasedc(None, screen)

    def save(self):
        if self.smoke:
            return
        try:
            DATA_DIR.mkdir(parents=True,exist_ok=True)
            temp = DATA_DIR / "settings.json.tmp"
            temp.write_text(json.dumps({"state": self.selected_state, "speeds": self.speeds,
                                       "speed_profile": "animation-repair-v1",
                                       "dynamic": self.dynamic, "look_enabled": self.look_enabled,
                                       "autonomous": self.autonomous, "walking": self.walking,
                                       "physics_enabled": self.physics_enabled,
                                       "windows_enabled": self.windows_enabled,
                                       "uniform_quality": self.uniform_quality,
                                       "typing_enabled": self.typing_enabled,
                                       "typing_waiting": self.typing_waiting,
                                       "reaction_radius": self.reaction_radius,
                                       "scale": self.scale, "position": [self.x, self.y]}, indent=2), encoding="utf-8")
            temp.replace(DATA_DIR / "settings.json")
        except OSError:
            logging.exception("Cannot save settings")

    def reset_animation(self):
        self.gait_driven = False
        self.gait_state = None
        self.index = 0
        self.look_index = None
        self.deadline = time.monotonic() + self.duration()
        self.render()
        self.save()

    def menu(self):
        self.cancel_inspection()
        self.menu_open = True
        self.hovered = False
        self.autonomy.pause(time.monotonic())
        root, animations, speed, scale, radius = [self.create_menu() for _ in range(5)]
        try:
            for i, (name, (_, _, label)) in enumerate(STATES.items()):
                self.append_menu(animations, 8 if name == self.selected_state else 0, 100 + i, label)
            for i, value in enumerate(SPEEDS):
                label = "×⅓ — в 3 раза медленнее" if i == 0 else f"×{value:g}"
                self.append_menu(speed, 8 if value == self.speeds[self.selected_state] else 0, 200 + i, label)
            for i, value in enumerate(SCALES):
                self.append_menu(scale, 8 if value == self.scale else 0, 300 + i, f"{round(value * 100)}%")
            for i, value in enumerate(REACTION_RADII):
                self.append_menu(radius, 8 if value == self.reaction_radius else 0, 500 + i, f"{value} пикселей")
            for handle, label in [(animations, "Основная анимация"),
                                  (speed, "Скорость: " + STATES[self.selected_state][2]),
                                  (scale, "Размер"), (radius, "Радиус реакции на курсор")]:
                self.append_menu(root, 16, handle, label)
            self.append_menu(root, 0x800, 0, None)
            self.append_menu(root, 8 if self.dynamic else 0, 401, "Автоматические реакции")
            self.append_menu(root, (8 if self.look_enabled else 0) | (0 if "look" in self.frames else 3),
                             402, "Смотреть на курсор")
            self.append_menu(root, 8 if self.autonomous else 0, 403, "Самостоятельные действия")
            self.append_menu(root, 8 if self.walking else 0, 404, "Самостоятельные прогулки")
            self.append_menu(root, 8 if self.physics_enabled else 0, 405, "Гравитация и границы экрана")
            self.append_menu(root, 8 if self.windows_enabled else 0, 406, "Стоять и ходить по окнам")
            if not REVAMP_PACK:
                self.append_menu(root, 8 if self.uniform_quality else 0, 407, "Выровнять чёткость анимаций")
            self.append_menu(root, 8 if self.typing_enabled else 0, 408, "Гримуар при наборе текста")
            self.append_menu(root, 8 if self.typing_waiting else 0, 409, "Проверка после набора текста")
            self.append_menu(root, 0x800, 0, None)
            self.append_menu(root, 0, 400, "Выход")
            pos = POINT()
            self.cursor(C.byref(pos))
            self.foreground(self.hwnd)
            command = self.track_menu(root, 0x100 | 2, pos.x, pos.y, 0, self.hwnd, None)
            if 100 <= command < 100 + len(STATES):
                self.landing_balance_cycles = 0
                self.startup_wave = False
                self.selected_state = self.state = list(STATES)[command - 100]
                self.greeting_until = 0
                self.reset_animation()
            elif 200 <= command < 200 + len(SPEEDS):
                self.speeds[self.selected_state] = SPEEDS[command - 200]
                self.reset_animation()
            elif 300 <= command < 300 + len(SCALES):
                self.scale = SCALES[command - 300]
                self.update_physics(time.monotonic(), dragging=True)
                self.recenter_walk()
                self.reset_animation()
            elif command == 400:
                self.destroy(self.hwnd)
            elif command == 401:
                self.dynamic = not self.dynamic
                self.greeting_until = 0
                self.save()
            elif command == 402:
                self.look_enabled = not self.look_enabled
                self.save()
            elif command == 403:
                self.autonomous = not self.autonomous
                self.save()
            elif command == 404:
                self.walking = not self.walking
                self.save()
            elif command == 405:
                self.physics_enabled = not self.physics_enabled
                self.physics.last_tick = time.monotonic()
                self.physics.vy = 0
                self.save()
            elif command == 406:
                self.windows_enabled = not self.windows_enabled
                self.physics.support = None
                self.recenter_walk()
                self.save()
            elif command == 407:
                self.uniform_quality = not self.uniform_quality
                self.cache.clear()
                self.render()
                self.save()
            elif command == 408:
                self.typing_enabled = not self.typing_enabled
                self.keyboard_activity.sample(time.monotonic(), False, enabled=False)
                self.save()
            elif command == 409:
                self.typing_waiting = not self.typing_waiting
                self.save()
            elif 500 <= command < 500 + len(REACTION_RADII):
                self.reaction_radius = REACTION_RADII[command - 500]
                self.save()
        finally:
            self.destroy_menu(root)  # Also frees its child menus.
            self.menu_open = False
            if not self.closed:
                self.hover_suppress_until = time.monotonic() + .15
                self.update_behavior(time.monotonic())
                self.deadline = time.monotonic() + self.duration()

    def wndproc(self, hwnd, message, wparam, lparam):
        try:
            if message == 0x20 and (lparam & 0xFFFF) == 1:  # WM_SETCURSOR, HTCLIENT
                self.set_cursor(self.arrow_cursor)
                return 1
            if message == 0x113:  # WM_TIMER
                now = time.monotonic()
                if self.smoke:
                    assert not self.is_visible(hwnd), "Diagnostic animations must never appear on the desktop"
                    elapsed = now - self.started
                    if elapsed > 2:
                        assert self.paint_count >= len(STATES)
                        logging.info("SMOKE PASS: native layered window painted all %s animations", len(STATES))
                        self.destroy(hwnd)
                    else:
                        target = list(STATES)[min(int(elapsed / (2 / len(STATES))), len(STATES) - 1)]
                        if target != self.state:
                            self.state = target
                            self.reset_animation()
                else:
                    enabled = self.typing_enabled and self.dynamic and not self.menu_open and self.drag is None
                    self.keyboard_activity.sample(
                        now, enabled and any(self.key_state(key) & 0x8000 for key in TEXT_KEYS),
                        shortcut=enabled and any(self.key_state(key) & 0x8000 for key in SHORTCUT_KEYS),
                        enabled=enabled)
                    self.update_physics(now, dragging=self.drag is not None)
                    self.update_behavior(now)
                    self.advance_animation(now)
                return 0
            if message == 0x201:  # WM_LBUTTONDOWN
                now = time.monotonic()
                self.cancel_inspection()
                if self.dynamic:
                    self.mouse_mood.touch(time.monotonic())
                pos = POINT()
                self.cursor(C.byref(pos))
                self.drag = (pos.x - self.x, pos.y - self.y)
                self.drag_start = (pos.x, pos.y)
                self.drag_turn_x = pos.x
                self.drag_turn_direction = 0
                self.drag_moved = False
                self.drag_motion.start(now,self.x,self.y)
                self.drag_direction = None
                self.startup_wave = False
                self.greeting_until = 0
                self.hovered = False
                self.physics.vx = self.physics.vy = 0
                self.physics.last_tick = now
                self.capture(hwnd)
                self.update_behavior(time.monotonic(), (pos.x, pos.y))
                return 0
            if message == 0x200 and self.drag:  # WM_MOUSEMOVE
                pos = POINT()
                self.cursor(C.byref(pos))
                new_x, new_y = pos.x - self.drag[0], pos.y - self.drag[1]
                # Count deliberate back-and-forth strokes, not mouse jitter.
                stroke = pos.x - self.drag_turn_x
                if abs(stroke) >= 25 * self.scale:
                    direction = 1 if stroke > 0 else -1
                    if self.drag_turn_direction and direction != self.drag_turn_direction and self.dynamic:
                        self.mouse_mood.shake(time.monotonic())
                    self.drag_turn_direction = direction
                    self.drag_turn_x = pos.x
                dx = new_x - self.x
                if abs(dx) >= 2:
                    self.drag_direction = "running-right" if dx > 0 else "running-left"
                if math.hypot(pos.x - self.drag_start[0], pos.y - self.drag_start[1]) > 4 * self.scale:
                    self.drag_moved = True
                self.x, self.y = new_x, new_y
                self.update_physics(time.monotonic(), dragging=True)
                self.update_behavior(time.monotonic(), (pos.x, pos.y))
                self.render()
                return 0
            if message == 0x200 and not self.menu_open:
                now = time.monotonic()
                if self.dynamic and now >= self.hover_suppress_until:
                    self.hovered = True
                    self.update_behavior(now)
                return 0
            if message == 0x202 and self.drag is not None:
                now = time.monotonic()
                # Include the release position even if Windows coalesced the
                # final motion message. Record the bounded pet, not a cursor
                # that may have travelled outside its physical screen limits.
                pos = POINT()
                self.cursor(C.byref(pos))
                self.x,self.y = pos.x-self.drag[0],pos.y-self.drag[1]
                self.update_physics(now,dragging=True)
                clicked,thrown = self.release_drag(now)
                if not clicked:
                    self.request_inspection()
                self.greeting_until = (now + sum(STATES["waving"][1]) / (1000 * self.speeds["waving"])) if clicked and self.dynamic and not self.mouse_mood.pending else 0
                self.hover_suppress_until = max(now + .2, self.greeting_until)
                self.releasecapture()
                self.recenter_walk()
                self.update_behavior(now)
                self.save()
                return 0
            if message == 0x215 and self.drag is not None:
                self.drag = None
                self.drag_direction = None
                self.hovered = False
                self.recenter_walk()
                self.update_behavior(time.monotonic())
                return 0
            if message == 0x205:  # WM_RBUTTONUP
                self.menu()
                return 0
            if message == 0x10:  # WM_CLOSE
                self.destroy(hwnd)
                return 0
            if message == 2:  # WM_DESTROY
                self.closed = True
                self.killtimer(hwnd, 1)
                self.save()
                self.user.PostQuitMessage(0)
                return 0
        except Exception:
            logging.exception("Window handler failed")
            self.user.PostQuitMessage(1)
            return 0
        return self.defproc(hwnd, message, wparam, lparam)

    def run(self):
        msg = W.MSG()
        get = bind(self.user, "GetMessageW", W.BOOL, C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT)
        translate = bind(self.user, "TranslateMessage", W.BOOL, C.POINTER(W.MSG))
        dispatch = bind(self.user, "DispatchMessageW", LRESULT, C.POINTER(W.MSG))
        try:
            while True:
                value = get(C.byref(msg), None, 0, 0)
                if value == -1:
                    raise C.WinError(C.get_last_error())
                if value == 0:
                    return int(msg.wParam)
                translate(C.byref(msg))
                dispatch(C.byref(msg))
        finally:
            if not self.closed:
                self.destroy(self.hwnd)


def main():
    parser = argparse.ArgumentParser(description="Loona Desktop — самостоятельный проигрыватель спрайтов")
    parser.add_argument("--sheet", type=Path, default=BASE / "assets" / "Loona.png")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--version", action="store_true", help="Show version from VERSION")
    args = parser.parse_args()
    if args.version:
        version=read_version(BASE)
        if sys.stdout is not None:print(version)
        else:logging.info('Loona Desktop version %s',version)
        return 0
    if args.self_test:
        self_test(args.sheet)
        return 0
    return DesktopPet(args.sheet, smoke=args.smoke_test).run()


if __name__ == "__main__":
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=DATA_DIR / "desktop-pet.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
    try:
        sys.exit(main())
    except Exception as error:
        logging.exception("Startup failed")
        if "--smoke-test" not in sys.argv:
            C.windll.user32.MessageBoxW(None, str(error) + "\n\nПодробности: " + str(DATA_DIR/'desktop-pet.log'), "Loona Desktop", 16)
        sys.exit(1)
