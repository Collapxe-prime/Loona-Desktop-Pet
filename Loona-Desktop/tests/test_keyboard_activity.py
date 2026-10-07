import unittest

from keyboard_activity import KeyboardActivity
from test_behavior import pet
from physics import Physics


class KeyboardTests(unittest.TestCase):
    def test_typing_pause_review_and_resume(self):
        activity = KeyboardActivity()
        self.assertIsNone(activity.animation(0))
        activity.sample(1, True)
        self.assertEqual(activity.animation(2), "jumping")
        self.assertEqual(activity.animation(2.3), "review")
        activity.sample(3, True)
        self.assertEqual(activity.animation(3), "jumping")
        activity.finish_waiting()
        self.assertIsNone(activity.animation(8.3))

    def test_shortcuts_do_not_trigger_and_disable_clears_activity(self):
        activity = KeyboardActivity()
        activity.sample(1, True, shortcut=True)
        self.assertIsNone(activity.animation(1))
        activity.sample(2, True)
        activity.sample(3, False, enabled=False)
        self.assertIsNone(activity.animation(3))

    def test_held_key_extends_activity_and_waiting_can_be_disabled(self):
        activity = KeyboardActivity()
        for now in range(10):
            activity.sample(now, True)
            self.assertEqual(activity.animation(now), "jumping")
        self.assertIsNone(activity.animation(11, waiting=False))

    def test_typing_interrupts_walk_but_physics_has_priority(self):
        app = pet()
        app.typing_enabled = app.typing_waiting = True
        app.keyboard_activity = KeyboardActivity()
        app.keyboard_activity.sample(10, True)
        app.autonomy.action, app.autonomy.target = "running-right", 0
        app.update_behavior(10, (1800, 50))
        self.assertEqual(app.state, "jumping")
        self.assertEqual(app.x, -500)
        self.assertIsNone(app.autonomy.action)
        app.physics_enabled = True
        app.physics = Physics(10, app.y)
        app.physics.grounded = False
        app.update_behavior(10.1, (1800, 50))
        self.assertEqual(app.state, "falling")
        app.physics.grounded = True
        app.landing_balance_cycles = 1
        app.update_behavior(10.2, (1800, 50))
        self.assertEqual(app.state, "balancing")
        app.landing_balance_cycles = 0
        app.update_behavior(11.3, (1800, 50))
        self.assertEqual(app.state, "review")
        app.keyboard_activity.finish_waiting()
        app.update_behavior(15.3, (1800, 50))
        self.assertEqual(app.state, "idle")

    def test_review_plays_one_complete_cycle_at_every_speed(self):
        for speed in (1 / 3, .5, 1, 1.5, 2):
            app = pet()
            app.autonomous = False
            app.typing_enabled = app.typing_waiting = True
            app.keyboard_activity = KeyboardActivity()
            app.keyboard_activity.sample(0, True)
            app.speeds["review"] = speed
            app.update_behavior(2, (1800, 50))
            self.assertEqual(app.state, "review")
            count = len(app.frames["review"])
            for index in range(1, count + 1):
                now = app.deadline
                app.update_behavior(now, (1800, 50))
                app.advance_animation(now, (1800, 50))
                if index < count:
                    self.assertEqual(app.state, "review")
                    self.assertEqual(app.index, index)
                else:
                    self.assertEqual(app.state, "idle")
            app.update_behavior(now + 10, (1800, 50))
            self.assertNotEqual(app.state, "review")
            app.keyboard_activity.sample(now + 11, True)
            app.update_behavior(now + 12.3, (1800, 50))
            self.assertEqual(app.state, "review")

