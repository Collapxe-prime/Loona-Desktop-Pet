import unittest

from mouse_mood import MouseMood
from test_behavior import pet
from physics import Physics


class MouseMoodTests(unittest.TestCase):
    def test_anger_repeats_tap_without_replaying_upright_ear_intro(self):
        app = pet()
        app.state = 'waiting'
        app.waiting_for_typing = False
        app.waiting_annoyed = True
        app.index = len(app.frames['waiting']) - 1
        app.deadline = 0
        app.advance_animation(1)
        from main import REVAMP_PACK
        self.assertEqual(app.index, REVAMP_PACK['animations']['waiting'].get('loop_start', 0))

    def test_manual_waiting_repeats_without_resetting_ears(self):
        app = pet()
        app.state = 'waiting'
        app.waiting_for_typing = False
        app.waiting_annoyed = False
        app.index = len(app.frames['waiting']) - 1
        app.deadline = 0
        app.advance_animation(1)
        from main import REVAMP_PACK
        self.assertEqual(app.index, REVAMP_PACK['animations']['waiting'].get('loop_start', 0))

    def test_three_cursor_approaches_trigger_waiting_without_clicks(self):
        app = pet()
        app.mouse_mood = MouseMood()
        inside = (app.x + 96, app.y + 104)
        outside = (app.x + 200, app.y + 104)
        for visit in range(3):
            app.update_behavior(visit * 2, outside)
            app.update_behavior(visit * 2 + 1, inside)
            self.assertEqual(app.state == "waiting", visit == 2)
        app.update_behavior(12, outside)
        self.assertNotEqual(app.state, "waiting")

    def test_lingering_border_jitter_and_stationary_cursor_do_not_count(self):
        mood = MouseMood()
        mood.approach(0, True, False)
        for now in range(1, 10):
            mood.approach(now / 10, False, False)
            mood.approach(now / 10, True, False)
        self.assertEqual(len(mood.approaches), 1)
        self.assertFalse(mood.active(1))
        mood.approach(2, False, True, moved=False)
        mood.approach(3, True, False, moved=False)
        self.assertEqual(len(mood.approaches), 1)

    def test_slow_approaches_do_not_trigger(self):
        mood = MouseMood()
        for now in (0, 7, 14):
            mood.approach(now, False, True)
            mood.approach(now + .1, True, False)
        self.assertFalse(mood.active(15))

    def test_real_click_message_sequence_suppresses_wave_from_second_press(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        app = pet()
        app.mouse_mood = MouseMood()
        from mouse_throw import DragMotion
        app.physics = Physics(0,app.y)
        app.drag_motion = DragMotion()
        app.capture = app.releasecapture = lambda *args: None
        app.recenter_walk = app.save = lambda: None
        def cursor(pointer):
            pointer._obj.x, pointer._obj.y = app.x + 96, app.y + 104
            return True
        app.cursor = cursor
        with patch("main.time.monotonic", return_value=1):
            app.wndproc(1, 0x201, 0, 0)
            app.wndproc(1, 0x202, 0, 0)
            self.assertEqual(app.state, "waving")
        for now in (2, 3, 4):
            with patch("main.time.monotonic", return_value=now):
                app.wndproc(1, 0x201, 0, 0)
                self.assertEqual(app.state, "balancing")
                app.wndproc(1, 0x202, 0, 0)
                self.assertEqual(app.state, "waiting")
                self.assertEqual(app.greeting_until, 0)

    def test_two_touches_then_calm_and_repeated_touch_extends(self):
        mood = MouseMood()
        mood.touch(0)
        self.assertFalse(mood.active(0))
        mood.touch(1)
        self.assertTrue(mood.active(1))
        mood.touch(2)
        self.assertTrue(mood.active(2))
        mood.touch(5)
        self.assertTrue(mood.active(5))
        self.assertTrue(mood.active(10.9))
        self.assertFalse(mood.active(11))
        mood.touch(12)
        self.assertFalse(mood.active(12))

    def test_slow_touches_and_fast_mouse_jitter_do_not_trigger(self):
        mood = MouseMood()
        for now in (0, 7, 14):
            mood.touch(now)
        self.assertFalse(mood.active(14))
        mood = MouseMood()
        for now in (0, .01, .02, .03):
            mood.shake(now)
        self.assertFalse(mood.active(1))

    def test_reaction_waits_for_release_and_landing(self):
        mood = MouseMood()
        for now in (0, 1, 2):
            mood.touch(now)
        self.assertFalse(mood.active(3, blocked=True))
        self.assertFalse(mood.active(20, blocked=True))
        self.assertTrue(mood.active(21))
        self.assertTrue(mood.active(26.9))
        self.assertFalse(mood.active(27))

    def test_waiting_overrides_hover_greeting_and_inspection_but_not_fall(self):
        app = pet()
        app.mouse_mood = MouseMood()
        for now in (0, 1, 2):
            app.mouse_mood.touch(now)
        app.request_inspection()
        app.hovered = True
        app.greeting_until = 5
        app.update_behavior(2, (app.x + 96, app.y + 104))
        self.assertEqual(app.state, "waiting")
        self.assertIsNone(app.look_index)  # Keep the waiting artwork and all its frames.
        self.assertFalse(app.inspect_pending)
        app.physics_enabled = True
        app.physics = Physics(2, app.y)
        app.physics.grounded = False
        app.update_behavior(3, (1800, 50))
        self.assertEqual(app.state, "falling")
        app.physics.grounded = True
        app.landing_balance_cycles = 1
        app.update_behavior(4, (1800, 50))
        self.assertEqual(app.state, "balancing")
        app.landing_balance_cycles = 0
        app.update_behavior(5, (1800, 50))
        self.assertEqual(app.state, "waiting")
        app.update_behavior(11.1, (1800, 50))
        self.assertEqual(app.state, "idle")
