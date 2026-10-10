"""Native tray and opt-in per-user startup; no additional UI runtime."""
import ctypes as C
from ctypes import wintypes as W
import logging
from pathlib import Path
import sys
import winreg

from app_metadata import APP_TITLE

TRAY_MESSAGE = 0x8001
RESTORE_MESSAGE = 0x8002
RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
RUN_VALUE = 'LoonaDesktopPet'


class NotifyIconData(C.Structure):
    _fields_ = [('cbSize', W.DWORD), ('hWnd', W.HWND), ('uID', W.UINT),
                ('uFlags', W.UINT), ('uCallbackMessage', W.UINT), ('hIcon', W.HANDLE),
                ('szTip', W.WCHAR * 128), ('dwState', W.DWORD), ('dwStateMask', W.DWORD),
                ('szInfo', W.WCHAR * 256), ('uVersion', W.UINT),
                ('szInfoTitle', W.WCHAR * 64), ('dwInfoFlags', W.DWORD),
                ('guidItem', W.BYTE * 16), ('hBalloonIcon', W.HANDLE)]


class TrayIcon:
    def __init__(self, hwnd, icon, enabled=True, notify=None):
        self.enabled = enabled
        self.added = False
        self.retry_at = 0
        self.data = NotifyIconData()
        self.data.cbSize = C.sizeof(self.data)
        self.data.hWnd, self.data.uID = hwnd, 1
        self.data.uFlags = 1 | 2 | 4  # Message, icon, tooltip.
        self.data.uCallbackMessage = TRAY_MESSAGE
        self.data.hIcon, self.data.szTip = icon, APP_TITLE
        if notify is None:
            notify = C.WinDLL('shell32', use_last_error=True).Shell_NotifyIconW
            notify.argtypes = [W.DWORD, C.POINTER(NotifyIconData)]
            notify.restype = W.BOOL
        self.notify = notify

    def ensure(self, now):
        if not self.enabled or self.added or now < self.retry_at:
            return
        self.added = bool(self.notify(0, C.byref(self.data)))
        self.retry_at = now + 3

    def explorer_restarted(self):
        self.added = False
        self.retry_at = 0
        self.ensure(0)

    def close(self):
        self.enabled = False
        if self.added:
            self.notify(2, C.byref(self.data))
            self.added = False


class Autostart:
    def __init__(self, executable=None, available=None, registry=winreg):
        self.executable = Path(executable or sys.executable).resolve()
        self.available = getattr(sys, 'frozen', False) if available is None else available
        self.registry = registry

    @property
    def command(self):
        return '"' + str(self.executable) + '"'

    def enabled(self):
        if not self.available:
            return False
        r = self.registry
        try:
            with r.OpenKey(r.HKEY_CURRENT_USER, RUN_KEY, 0, r.KEY_READ) as key:
                value, kind = r.QueryValueEx(key, RUN_VALUE)
            return kind == r.REG_SZ and value.casefold() == self.command.casefold()
        except FileNotFoundError:
            return False

    def set_enabled(self, enabled):
        if not self.available:
            raise RuntimeError('Автозагрузка доступна в собранном .exe')
        r = self.registry
        if enabled:
            if not self.executable.is_file() or self.executable.suffix.lower() != '.exe':
                raise FileNotFoundError('Не найден исполняемый файл приложения')
            with r.CreateKeyEx(r.HKEY_CURRENT_USER, RUN_KEY, 0, r.KEY_SET_VALUE) as key:
                r.SetValueEx(key, RUN_VALUE, 0, r.REG_SZ, self.command)
        else:
            try:
                with r.OpenKey(r.HKEY_CURRENT_USER, RUN_KEY, 0, r.KEY_SET_VALUE) as key:
                    r.DeleteValue(key, RUN_VALUE)
            except FileNotFoundError:
                pass


class SingleInstance:
    """Keep startup and manual launches from creating duplicate pets."""
    def __init__(self, name=r'Local\LoonaDesktopPet.Desktop', notify_existing=True):
        self.kernel = C.WinDLL('kernel32', use_last_error=True)
        create = self.kernel.CreateMutexW
        create.argtypes = [C.c_void_p, W.BOOL, W.LPCWSTR]
        create.restype = W.HANDLE
        self.handle = create(None, False, name)
        error = C.get_last_error()
        if not self.handle:
            raise C.WinError(error)
        self.first = error != 183  # ERROR_ALREADY_EXISTS
        if not self.first and notify_existing:
            user = C.WinDLL('user32', use_last_error=True)
            find = user.FindWindowW
            find.argtypes, find.restype = [W.LPCWSTR, W.LPCWSTR], W.HWND
            post = user.PostMessageW
            post.argtypes, post.restype = [W.HWND, W.UINT, C.c_size_t, C.c_ssize_t], W.BOOL
            hwnd = find('LoonaDesktopPet', APP_TITLE)
            if hwnd:
                post(hwnd, RESTORE_MESSAGE, 0, 0)
            logging.info('Existing Loona instance reused')

    def close(self):
        if self.handle:
            close = self.kernel.CloseHandle
            close.argtypes, close.restype = [W.HANDLE], W.BOOL
            close(self.handle)
            self.handle = None
