from contextlib import nullcontext
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import uuid
import winreg

from windows_shell import Autostart, TrayIcon, SingleInstance, RUN_VALUE, RUN_KEY, TRAY_MESSAGE


class WindowsShellTests(unittest.TestCase):
    def test_tray_retries_failed_add_readds_after_explorer_restart_and_removes(self):
        notify = Mock(side_effect=[False, True, True, True])
        tray = TrayIcon(123, 456, notify=notify)
        tray.ensure(0)
        self.assertFalse(tray.added)
        tray.ensure(1)
        self.assertEqual(notify.call_count, 1)
        tray.ensure(3)
        self.assertTrue(tray.added)
        tray.ensure(4)
        self.assertEqual(notify.call_count, 2)
        tray.explorer_restarted()
        self.assertTrue(tray.added)
        self.assertEqual(tray.data.uCallbackMessage, TRAY_MESSAGE)
        self.assertEqual(tray.data.hWnd, 123)
        self.assertEqual(tray.data.hIcon, 456)
        tray.close()
        tray.close()
        tray.ensure(100)
        self.assertEqual([call.args[0] for call in notify.call_args_list], [0, 0, 0, 2])

    def test_diagnostics_never_add_tray_icon(self):
        notify = Mock()
        tray = TrayIcon(123, 456, enabled=False, notify=notify)
        tray.ensure(0)
        tray.explorer_restarted()
        tray.close()
        notify.assert_not_called()

    def test_startup_quotes_exe_path_and_removes_only_our_value(self):
        values = {'OtherApp': 'untouched'}
        registry = Mock(spec=winreg)
        registry.REG_SZ = winreg.REG_SZ
        registry.HKEY_CURRENT_USER = winreg.HKEY_CURRENT_USER
        registry.KEY_READ, registry.KEY_SET_VALUE = winreg.KEY_READ, winreg.KEY_SET_VALUE
        registry.OpenKey.side_effect = lambda *args: nullcontext('key')
        registry.CreateKeyEx.side_effect = lambda *args: nullcontext('key')
        def query(key, name):
            if name not in values:
                raise FileNotFoundError(name)
            return values[name], winreg.REG_SZ
        registry.QueryValueEx.side_effect = query
        registry.SetValueEx.side_effect = lambda key, name, reserved, kind, value: values.update({name: value})
        def delete(key, name):
            if name not in values:
                raise FileNotFoundError(name)
            del values[name]
        registry.DeleteValue.side_effect = delete
        with tempfile.TemporaryDirectory(prefix='loona startup ') as directory:
            executable = Path(directory) / 'LoonaDesktopPet.exe'
            executable.touch()
            startup = Autostart(executable, available=True, registry=registry)
            self.assertFalse(startup.enabled())
            registry.SetValueEx.assert_not_called()
            startup.set_enabled(True)
            self.assertTrue(startup.enabled())
            self.assertEqual(values[RUN_VALUE], '"' + str(executable.resolve()) + '"')
            registry.CreateKeyEx.assert_called_with(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE)
            startup.set_enabled(False)
            startup.set_enabled(False)
            self.assertEqual(values, {'OtherApp': 'untouched'})

    def test_dev_startup_cannot_register_python_or_modify_registry(self):
        registry = Mock(spec=winreg)
        startup = Autostart(available=False, registry=registry)
        self.assertFalse(startup.enabled())
        with self.assertRaises(RuntimeError):
            startup.set_enabled(True)
        self.assertEqual(registry.mock_calls, [])

    def test_native_instance_handle_prevents_duplicates_and_is_released(self):
        name = 'Local\\LoonaDesktopPet.Test.' + uuid.uuid4().hex
        first = SingleInstance(name, notify_existing=False)
        second = SingleInstance(name, notify_existing=False)
        try:
            self.assertTrue(first.first)
            self.assertFalse(second.first)
        finally:
            first.close()
            second.close()
        third = SingleInstance(name, notify_existing=False)
        try:
            self.assertTrue(third.first)
        finally:
            third.close()

    def test_recovery_uses_cursor_monitor_cancels_drag_and_stale_window_physics(self):
        import ctypes as C
        from main import DesktopPet, POINT, MONITORINFO
        from test_behavior import pet
        from physics import Physics
        from keyboard_activity import KeyboardActivity
        from mouse_mood import MouseMood
        from head_petting import HeadPetting
        app = pet()
        app.smoke = True
        app.physics = Physics(0, 100)
        app.physics.vx, app.physics.vy = 500, 700
        app.physics.support = (0, 50, 900, 42, 0, 'top')
        app.drag = (10, 10)
        app.releasecapture = Mock()
        app.mouse_mood = MouseMood()
        app.mouse_mood.touch(0); app.mouse_mood.touch(1)
        app.keyboard_activity = KeyboardActivity()
        app.head_petting = HeadPetting()
        def cursor(pointer):
            pos = C.cast(pointer, C.POINTER(POINT)).contents
            pos.x, pos.y = -500, -100
            return True
        app.cursor = cursor
        app.monitor_from_point = Mock(return_value=42)
        def info(monitor, pointer):
            work = C.cast(pointer, C.POINTER(MONITORINFO)).contents.rcWork
            work.left, work.top, work.right, work.bottom = -1920, -200, 0, 840
            return True
        app.monitor_info = info
        app.save = Mock()
        app.restore_to_screen()
        bl, bt, br, feet = app.collision_bounds()
        self.assertGreaterEqual(app.x + bl, -1920)
        self.assertLessEqual(app.x + br, 0)
        self.assertEqual(app.y + feet, 840)
        self.assertIsNone(app.drag)
        self.assertIsNone(app.physics.support)
        self.assertEqual((app.physics.vx, app.physics.vy), (0, 0))
        self.assertFalse(app.mouse_mood.pending)
        self.assertEqual(app.state, app.selected_state)
        app.releasecapture.assert_called_once()
        app.save.assert_called_once()
