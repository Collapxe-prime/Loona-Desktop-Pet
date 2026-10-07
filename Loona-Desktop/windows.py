"""Read-only discovery of visible desktop window platforms, cached at 30 Hz."""
import ctypes as C
from ctypes import wintypes as W

from physics import visible_platforms


class MONITORINFO(C.Structure):
    _fields_ = [("cbSize", W.DWORD), ("rcMonitor", W.RECT), ("rcWork", W.RECT), ("dwFlags", W.DWORD)]


def fills_work_area(rect, work, maximized=False):
    """Also recognize borderless fullscreen windows and taskbars on any edge."""
    if maximized:
        return True
    if work is None:
        return False
    left, top, right, bottom = rect
    wl, wt, wr, wb = work
    return left <= wl + 2 and top <= wt + 2 and right >= wr - 2 and bottom >= wb - 2


class GUITHREADINFO(C.Structure):
    _fields_ = [("cbSize", W.DWORD), ("flags", W.DWORD),
                ("hwndActive", W.HWND), ("hwndFocus", W.HWND), ("hwndCapture", W.HWND),
                ("hwndMenuOwner", W.HWND), ("hwndMoveSize", W.HWND), ("hwndCaret", W.HWND),
                ("rcCaret", W.RECT)]


def bind(dll, name, result, *args):
    fn = getattr(dll, name)
    fn.restype, fn.argtypes = result, args
    return fn


class WindowPlatforms:
    def __init__(self):
        u = C.WinDLL("user32", use_last_error=True)
        d = C.WinDLL("dwmapi", use_last_error=True)
        self.first = bind(u, "GetTopWindow", W.HWND, W.HWND)
        self.next = bind(u, "GetWindow", W.HWND, W.HWND, W.UINT)
        self.visible = bind(u, "IsWindowVisible", W.BOOL, W.HWND)
        self.iconic = bind(u, "IsIconic", W.BOOL, W.HWND)
        self.zoomed = bind(u, "IsZoomed", W.BOOL, W.HWND)
        self.monitor = bind(u, "MonitorFromWindow", W.HANDLE, W.HWND, W.DWORD)
        self.monitor_info = bind(u, "GetMonitorInfoW", W.BOOL, W.HANDLE, C.POINTER(MONITORINFO))
        self.rect = bind(u, "GetWindowRect", W.BOOL, W.HWND, C.POINTER(W.RECT))
        self.attr = bind(d, "DwmGetWindowAttribute", C.c_long, W.HWND, W.DWORD, C.c_void_p, W.DWORD)
        self.class_name = bind(u, "GetClassNameW", C.c_int, W.HWND, W.LPWSTR, C.c_int)
        self.style = bind(u, "GetWindowLongPtrW", C.c_ssize_t, W.HWND, C.c_int)
        self.gui_info = bind(u, "GetGUIThreadInfo", W.BOOL, W.DWORD, C.POINTER(GUITHREADINFO))
        self.dragged_window = None
        self.drag_until = 0.0
        self.last_scan = -1e9
        self.platforms = []
        self.rectangles = {}

    def scan(self, now):
        if now - self.last_scan < 1 / 30:
            return self.platforms
        self.last_scan = now
        gui = GUITHREADINFO()
        gui.cbSize = C.sizeof(gui)
        if self.gui_info(0, C.byref(gui)) and gui.flags & 2 and gui.hwndMoveSize:
            self.dragged_window = gui.hwndMoveSize
            self.drag_until = now + .12
        rectangles, seen, non_supporting = [], set(), set()
        hwnd = self.first(None)
        while hwnd and hwnd not in seen:
            seen.add(hwnd)
            following = self.next(hwnd, 2)  # GW_HWNDNEXT: front to back.
            if self.visible(hwnd) and not self.iconic(hwnd):
                name = C.create_unicode_buffer(256)
                self.class_name(hwnd, name, len(name))
                cloaked = W.DWORD()
                self.attr(hwnd, 14, C.byref(cloaked), C.sizeof(cloaked))
                excluded = name.value in ("LoonaDesktopPet", "Progman", "WorkerW",
                                          "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "#32768")
                if not excluded and not cloaked.value and not self.style(hwnd, -20) & 0x80:
                    rect = W.RECT()
                    ok = self.attr(hwnd, 9, C.byref(rect), C.sizeof(rect)) == 0
                    if not ok:
                        ok = self.rect(hwnd, C.byref(rect))
                    if ok and rect.right - rect.left >= 80 and rect.bottom - rect.top >= 40:
                        rectangles.append((rect.left, rect.top, rect.right, rect.bottom, hwnd))
                        info = MONITORINFO()
                        info.cbSize = C.sizeof(info)
                        monitor = self.monitor(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
                        work = None
                        if monitor and self.monitor_info(monitor, C.byref(info)):
                            work = (info.rcWork.left, info.rcWork.top, info.rcWork.right, info.rcWork.bottom)
                        if fills_work_area(rectangles[-1][:4], work, self.zoomed(hwnd)):
                            non_supporting.add(hwnd)
            hwnd = following
        # Timestamp the scan, not each physics tick: cached geometry must not
        # produce alternating zero and exaggerated window velocities.
        self.rectangles = {r[4]: r[:4] for r in rectangles}
        self.platforms = [(*p[:5], now, p[5], p[3] == self.dragged_window and now <= self.drag_until)
                          for p in visible_platforms(rectangles, include_bottom=True, non_supporting=non_supporting)]
        return self.platforms
