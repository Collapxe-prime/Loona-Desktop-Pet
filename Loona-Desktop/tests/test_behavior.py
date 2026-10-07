"""Regression tests for interaction priority and stable animation playback."""
import math
import unittest

from main import DesktopPet, STATES, look_direction
from behavior import Autonomy


def pet(selected="idle", look=True, scale=1):
    app = DesktopPet.__new__(DesktopPet)
    app.selected_state = app.state = selected
    app.dynamic = app.look_enabled = True
    app.autonomous = app.walking = True
    app.physics_enabled = False
    app.reaction_radius = 300
    app.menu_open = False
    app.hovered = False
    app.hover_suppress_until = app.greeting_until = 0
    app.startup_wave = False
    app.drag = app.drag_direction = None
    app.look_index = app.last_cursor = None
    app.last_cursor_motion = -math.inf
    app.x, app.y, app.scale = -500, 100, scale
    app.screen_bounds = lambda: (-1920, 0, 1920, 1040)
    app.hover_bounds = (20, 20, 170, 200)
    app.frames = {name: [None] * len(durations) for name, (_, durations, _) in STATES.items()}
    if look:
        app.frames["look"] = [None] * 16
    app.speeds = {name: 1 for name in STATES}
    app.speeds["jumping"] = 1 / 3
    app.autonomy = Autonomy(0, app.x, app.x - 220, app.x + 220,
                           {name: sum(data[1]) / 1000 for name, data in STATES.items()})
    app.autonomy.next_action = math.inf  # Existing interaction tests do not schedule spontaneous actions.
    app.index = 0
    app.landing_balance_cycles = 0
    app.inspect_pending = False
    app.inspect_started = None
    app.deadline = 999
    app.paints = []
    app.render = lambda: app.paints.append((app.state, app.look_index))
    return app


class BehaviorTests(unittest.TestCase):
    def test_timer_jitter_does_not_accumulate_per_frame(self):
        app = pet(selected='running-right')
        app.deadline = 10
        app.advance_animation(10.015)
        self.assertAlmostEqual(app.deadline, 10 + app.duration())
        for _ in range(len(app.frames['running-right'])):
            expected = app.deadline
            app.advance_animation(expected + .015)
            self.assertAlmostEqual(app.deadline, expected + app.duration())

    def test_matching_window_velocity_does_not_show_slipping_or_block_inspection(self):
        from physics import Physics
        from types import SimpleNamespace
        app = pet()
        app.physics_enabled = True
        app.physics = Physics(0, app.y)
        app.physics.support = (-800, 308, 100, 42, -800, 10, "top", True)
        app.physics.vx = 800
        app.physics.window_velocity = (800, 0)
        app.window_platforms = SimpleNamespace(rectangles={42: (-800, 308, 100, 850)})
        app.update_behavior(10, (1800, 50))
        self.assertEqual(app.state, "idle")
        app.request_inspection()
        app.update_behavior(11, (1800, 50))
        self.assertEqual(app.inspect_started, 11)
        self.assertIsNotNone(app.look_index)

    def test_post_drag_inspection_checks_window_corners_then_restores_selected_animation(self):
        from physics import Physics
        from types import SimpleNamespace
        app = pet(selected="running")
        app.physics_enabled = True
        app.physics = Physics(0, app.y)
        app.physics.support = (-800, 308, 100, 42, -800, 10, "top")
        app.window_platforms = SimpleNamespace(rectangles={42: (-800, 308, 100, 850)})
        app.request_inspection()
        directions = []
        for phase in range(6):
            app.hovered = True  # The cursor can still be over the pet after release.
            app.update_behavior(10 + phase * .5, (app.x + 96, app.y + 104))
            self.assertEqual(app.state, "idle")
            self.assertIsNotNone(app.look_index)
            directions.append(app.look_index)
        self.assertGreaterEqual(len(set(directions)), 3)
        app.update_behavior(13.1, (1000, 200))
        self.assertEqual(app.state, "running")
        self.assertIsNone(app.look_index)
        self.assertFalse(app.inspect_pending)
        self.assertIsNone(app.inspect_started)

    def test_inspection_waits_for_landing_balance_and_inertia_to_finish(self):
        from physics import Physics
        app = pet()
        app.physics_enabled = True
        app.physics = Physics(0, app.y)
        app.physics.grounded = False
        app.request_inspection()
        app.update_behavior(10, (1000, 200))
        self.assertEqual(app.state, "falling")
        self.assertTrue(app.inspect_pending)
        self.assertIsNone(app.inspect_started)
        app.physics.grounded = True
        app.landing_balance_cycles = 2
        app.update_behavior(11, (1000, 200))
        self.assertEqual(app.state, "balancing")
        self.assertIsNone(app.inspect_started)
        app.landing_balance_cycles = 0
        app.physics.vx = 40
        app.update_behavior(12, (1000, 200))
        self.assertEqual(app.state, "slipping")
        app.physics.vx = 0
        app.update_behavior(13, (1000, 200))
        self.assertEqual(app.inspect_started, 13)
        self.assertIsNotNone(app.look_index)

    def test_drag_or_disabled_reactions_cancel_inspection_and_v1_does_not_schedule_it(self):
        for mode in ("drag", "disabled", "v1"):
            app = pet(look=mode != "v1")
            app.request_inspection()
            if mode == "drag":
                app.drag = (0, 0)
            elif mode == "disabled":
                app.dynamic = False
            app.update_behavior(10, (1000, 200))
            self.assertFalse(app.inspect_pending)
            self.assertIsNone(app.inspect_started)

    def test_landing_plays_exactly_one_full_balance_cycle_at_any_animation_speed(self):
        from physics import Physics
        from types import SimpleNamespace
        for window in (False, True):
            for speed in (1 / 3, 1, 2):
                app = pet()
                app.x, app.y = 300, 291 if window else 831
                app.physics_enabled = app.windows_enabled = True
                app.smoke = False
                app.physics = Physics(0, app.y)
                app.physics.grounded = False
                app.physics.vx = 100
                app.speeds["balancing"] = speed
                app.window_platforms = SimpleNamespace(scan=lambda now: [(200, 500, 900, 42, 200, now, "top", False)] if window else [])
                app.save = lambda: None
                app.update_physics(.05)
                self.assertTrue(app.physics.grounded)
                self.assertEqual(app.landing_balance_cycles, 1)
                app.update_behavior(.05, (1800, 50))
                self.assertEqual(app.state, "balancing")
                count = len(app.frames["balancing"])
                for frame in range(1, count + 1):
                    now = app.deadline
                    app.update_physics(now)
                    app.update_behavior(now, (1800, 50))
                    app.advance_animation(now, (1800, 50))
                    self.assertEqual(app.landing_balance_cycles, 1 - frame // count)
                    if frame < count:
                        self.assertEqual(app.state, "balancing")
                        self.assertEqual(app.index, frame % count)
                self.assertNotEqual(app.state, "balancing")
                self.assertAlmostEqual(now - .05, 1.0)
                self.assertEqual(app.selected_state, "idle")

    def test_stationary_ground_contact_does_not_restart_landing_balance(self):
        from physics import Physics
        from types import SimpleNamespace
        app = pet()
        app.physics_enabled = app.windows_enabled = True
        app.smoke = False
        app.y = 832
        app.physics = Physics(0, app.y)
        app.window_platforms = SimpleNamespace(scan=lambda now: [])
        app.update_physics(.05)
        self.assertEqual(app.landing_balance_cycles, 0)

    def test_random_walk_off_window_is_not_clamped_and_triggers_slipping_then_fall(self):
        from physics import Physics
        from types import SimpleNamespace
        app = pet()
        app.x, app.y = 300, 292
        app.physics_enabled = app.windows_enabled = True
        app.smoke = False
        app.physics = Physics(0, 292)
        app.physics.support = (200, 500, 800, 42, 200, 0, "top")
        app.screen_bounds = lambda: (0, 0, 1920, 1040)
        app.window_platforms = SimpleNamespace(scan=lambda now: [(200, 500, 800, 42, 200, now, "top")])
        app.save = lambda: None
        app.autonomy.recenter(0, app.x, *app.walking_bounds())
        app.autonomy.rng.choice = lambda choices: "leave-window" if "leave-window" in choices else max(choices)
        app.autonomy.next_action = 0
        # The gentler gait needs longer to reach the edge; allow the physical
        # travel time rather than imposing the former five-second sprint.
        max_frames=math.ceil((800-(app.x+96)+30)/app.autonomy.movement_speed('walking-right',app.speeds)/.05)+20
        for frame in range(1, max_frames+1):
            now = frame * .05
            app.update_physics(now)
            app.update_behavior(now, (1800, 50))
            if not app.physics.grounded:
                break
        self.assertLess(frame, max_frames)
        self.assertGreaterEqual(app.x + 96, 800)
        self.assertEqual(app.state, "slipping")
        self.assertGreater(app.physics.vx, 0)
        app.update_behavior(now + .4, (1800, 50))
        self.assertEqual(app.state, "falling")

    def test_balancing_plays_complete_cycle_and_overrides_hover_without_losing_base(self):
        from physics import Physics
        app = pet()
        app.physics_enabled = True
        app.physics = Physics(0, app.y)
        app.physics.support = (0, 500, 1000, 42, 0, 20, "top")
        app.physics.balance_until = 20 + sum(STATES["balancing"][1]) / 1000 + .05
        app.hovered = True
        pos = (app.x + 96, app.y + 104)
        app.update_behavior(20, pos)
        self.assertEqual(app.state, "balancing")
        count = len(app.frames["balancing"])
        for i in range(1, count + 1):
            now = app.deadline
            app.update_behavior(now, pos)
            app.advance_animation(now, pos)
            self.assertEqual(app.state, "balancing")
            self.assertEqual(app.index, i % count)
        app.hovered = False
        app.update_behavior(app.physics.balance_until + .05, (1000, 200))
        self.assertEqual(app.state, "idle")
        self.assertEqual(app.selected_state, "idle")

    def test_slip_changes_to_fall_and_ground_slide_keeps_slipping_pose(self):
        from physics import Physics
        app = pet()
        app.physics_enabled = True
        app.physics = Physics(0, app.y)
        app.physics.grounded = False
        app.physics.slipping_until = 10.36
        app.physics.vx = -100
        app.update_behavior(10, (1000, 200))
        self.assertEqual(app.state, "slipping")
        self.assertEqual(app.motion_facing, -1)
        app.update_behavior(10.5, (1000, 200))
        self.assertEqual(app.state, "falling")
        app.physics.grounded = True
        app.update_behavior(10.6, (1000, 200))
        self.assertEqual(app.state, "slipping")
        app.physics.vx = 0
        app.update_behavior(11, (1000, 200))
        self.assertEqual(app.state, "idle")

    def test_new_loops_play_every_frame_without_restarting_each_behavior_tick(self):
        for name in ("sitting", "falling", "slipping", "balancing"):
            if name not in STATES:
                continue
            app = pet(selected=name)
            app.deadline = 10 + app.duration()
            for index in range(1, len(app.frames[name]) + 1):
                now = app.deadline
                app.update_behavior(now, (1000, 200))
                app.advance_animation(now, (1000, 200))
                self.assertEqual(app.index, index % len(app.frames[name]))
                self.assertEqual(app.state, name)

    def test_falling_animation_interrupts_phone_and_hover_and_restores_after_landing(self):
        from physics import Physics
        app = pet()
        app.physics_enabled = True
        app.physics = Physics(0, app.y)
        app.physics.grounded = False
        app.hovered = True
        app.autonomy.action = "running"
        app.autonomy.until = 100
        app.update_behavior(10, (app.x + 96, app.y + 104))
        self.assertEqual(app.state, "falling")
        self.assertIsNone(app.autonomy.action)
        app.physics.grounded = True
        app.hovered = False
        app.update_behavior(11, (1000, 200))
        self.assertEqual(app.state, "idle")
        self.assertEqual(app.selected_state, "idle")

    def test_window_movement_preserves_action_and_translates_walk_target(self):
        from physics import Physics
        from types import SimpleNamespace
        app = pet()
        app.x, app.y = 300, 292
        app.physics_enabled = app.windows_enabled = True
        app.smoke = False
        app.physics = Physics(0, 292)
        app.physics.support = (200, 500, 800, 42, 200)
        app.physics.sample_window(app.physics.support, 0)
        app.screen_bounds = lambda: (0, 0, 1920, 1040)
        app.window_platforms = SimpleNamespace(scan=lambda now: [(202, 498, 802, 42, 202)])
        app.autonomy.recenter(0, 300, 112, 696)
        app.autonomy.action = "running-right"
        app.autonomy.target = 600
        app.autonomy.walk_x = 300
        app.update_physics(.05)
        self.assertEqual((app.x, app.y), (301, 290))
        self.assertEqual(app.autonomy.action, "running-right")
        self.assertEqual(app.autonomy.target, 601)
        self.assertEqual(app.autonomy.walk_x, 301)

    def test_autonomous_walk_bounds_keep_feet_on_window_at_both_scales(self):
        from physics import Physics
        for scale in (1, 2):
            app = pet(scale=scale)
            app.physics_enabled = True
            app.physics = Physics(0, 0)
            app.physics.support = (200, 500, 800)
            app.screen_bounds = lambda: (0, 0, 1920, 1040)
            left, right = app.walking_bounds()
            self.assertGreater(left + 96 * scale, 200)
            self.assertLess(right + 96 * scale, 800)

    def test_startup_wave_plays_all_frames_once_even_with_reactions_disabled(self):
        app = pet()
        app.dynamic = False
        app.startup_wave = True
        app.state = "waving"
        app.deadline = 10 + app.duration()
        position = (1000, 200)
        self.assertFalse(app.advance_animation(app.deadline - .001, position))
        for index in range(1, len(app.frames["waving"])):
            app.update_behavior(app.deadline, position)
            app.advance_animation(app.deadline, position)
            self.assertEqual((app.state, app.index), ("waving", index))
        app.advance_animation(app.deadline, position)
        self.assertFalse(app.startup_wave)
        self.assertEqual((app.state, app.index, app.selected_state), ("idle", 0, "idle"))
        app.update_behavior(60, position)
        self.assertEqual(app.state, "idle")

    def test_startup_preserves_the_chosen_base_animation(self):
        app = pet("running")
        app.startup_wave = True
        app.state, app.index, app.deadline = "waving", len(app.frames["waving"]) - 1, 20
        app.update_behavior(19, (1000, 200))
        self.assertEqual(app.state, "waving")
        app.advance_animation(20, (1000, 200))
        self.assertEqual(app.state, "running")
        self.assertEqual(app.selected_state, "running")

    def test_all_cardinal_and_diagonal_directions(self):
        for i in range(16):
            angle = math.radians(i * 22.5)
            self.assertEqual(look_direction(100 * math.sin(angle), -100 * math.cos(angle)), i)
        self.assertIsNone(look_direction(2, 2))

    def test_hover_preserves_manual_state_without_opening_grimoire(self):
        app = pet("review")
        app.hovered = True
        app.update_behavior(10, (-400, 200))
        self.assertEqual(app.state, "review")
        deadline, paints = app.deadline, len(app.paints)
        app.index = 2
        app.update_behavior(10.2, (-400, 200))
        self.assertEqual((app.index, app.deadline, len(app.paints)), (2, deadline, paints))
        app.update_behavior(11, (1000, 200))
        self.assertEqual(app.state, "review")
        self.assertEqual(app.selected_state, "review")
        self.assertEqual(app.speeds["jumping"], 1 / 3)

    def test_holding_and_dragging_play_balance_over_hover_and_greeting(self):
        app = pet()
        app.hovered = True
        app.greeting_until = 20
        app.drag = (1, 1)
        for direction in (None, "running-left", "running-right"):
            app.drag_direction = direction
            app.update_behavior(10, (-400, 200))
            self.assertEqual(app.state, "balancing")
        app.drag = app.drag_direction = None
        app.update_behavior(10, (1000, 200))
        self.assertEqual(app.state, "waving")
        app.update_behavior(21, (1000, 200))
        self.assertEqual(app.state, "idle")

    def test_scaled_gaze_on_negative_monitor_returns_to_breathing(self):
        app = pet(scale=2)
        position = (app.x + 96 * 2, app.y + 104 * 2 - 200)
        app.update_behavior(10, position)
        self.assertEqual(app.look_index, 0)
        app.update_behavior(10.5, position)
        self.assertEqual(app.look_index, 0)
        app.update_behavior(11.1, position)
        self.assertIsNone(app.look_index)
        self.assertEqual(app.state, "idle")

    def test_disabling_reactions_restores_manual_animation(self):
        app = pet("running")
        app.hovered = True
        app.update_behavior(10, (-400, 200))
        self.assertEqual(app.state, "running")
        app.dynamic = False
        app.update_behavior(10.1, (-400, 200))
        self.assertEqual(app.state, "running")
        self.assertIsNone(app.look_index)

    def test_v1_sheet_without_look_rows_does_not_open_book_on_hover(self):
        app = pet(look=False)
        app.update_behavior(10, (1000, 200))
        self.assertIsNone(app.look_index)
        app.hovered = True
        app.update_behavior(10.2, (-400, 200))
        self.assertEqual(app.state, "idle")

    def test_menu_does_not_trigger_hover(self):
        app = pet("waiting")
        app.menu_open = app.hovered = True
        app.update_behavior(10, (-400, 200))
        self.assertEqual(app.state, "waiting")
        self.assertEqual(app.paints, [])

    def test_distant_cursor_does_not_trigger_look(self):
        app = pet()
        app.update_behavior(10, (1000, 200))
        self.assertIsNone(app.look_index)
        app.update_behavior(10.1, (app.x + 96, app.y + 104 - 200))
        self.assertEqual(app.look_index, 0)

    def test_near_cursor_interrupts_walking_without_overwriting_base_state(self):
        app = pet()
        app.autonomy.action = "running-right"
        app.autonomy.target = app.x + 100
        app.autonomy.last_tick = 10
        app.update_behavior(10.05, (1000, 200))
        self.assertEqual(app.state, "running-right")
        old_x = app.x
        app.update_behavior(10.1, (app.x + 96, app.y + 104 - 200))
        self.assertEqual(app.x, old_x)
        self.assertEqual(app.state, "idle")
        self.assertEqual(app.selected_state, "idle")
        self.assertIsNone(app.autonomy.action)


if __name__ == "__main__":
    unittest.main()
