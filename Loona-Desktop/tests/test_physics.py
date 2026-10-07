import unittest

from physics import Physics, visible_platforms


class PhysicsTests(unittest.TestCase):



    def test_bottom_edge_outside_window_width_does_not_catch_fall(self):
        body = Physics(0, 300)
        x, y = 1000, 300
        for frame in range(1, 80):
            x, y = body.step(frame * .05, x, y, 192, 208, (0, 0, 1920, 1040),
                             platforms=[(200, 600, 800, 42, 200, frame * .05, "bottom")])
        self.assertEqual(y, 832)
        self.assertIsNone(body.support)

    def test_visible_bottom_edges_are_clipped_by_foreground_windows(self):
        self.assertEqual(visible_platforms([(300, 200, 600, 900, 1), (100, 400, 800, 700, 2)], True),
                         [(300, 200, 600, 1, 300, "top"), (300, 900, 600, 1, 300, "bottom"),
                          (100, 400, 300, 2, 100, "top"), (600, 400, 800, 2, 100, "top"),
                          (100, 700, 300, 2, 100, "bottom"), (600, 700, 800, 2, 100, "bottom")])

    def test_landing_preserves_momentum_then_surface_friction_stops_smoothly(self):
        body = Physics(0, 828)
        body.grounded = False
        body.vx, body.vy = 400, 200
        x, y = body.step(.05, 300, 828, 192, 208, (0, 0, 1920, 1040))
        self.assertTrue(body.grounded)
        self.assertGreater(body.vx, 350)
        landing_x, previous_speed = x, body.vx
        for frame in range(2, 61):
            x, y = body.step(frame * .05, x, y, 192, 208, (0, 0, 1920, 1040))
            self.assertLessEqual(body.vx, previous_speed)
            self.assertEqual(y, 832)
            previous_speed = body.vx
        self.assertGreater(x - landing_x, 90)
        self.assertLess(x - landing_x, 110)
        self.assertEqual(body.vx, 0)

    def test_air_inertia_distance_is_consistent_at_different_frame_rates(self):
        outcomes = []
        for fps in (20, 60, 120):
            body = Physics(0, 0)
            body.grounded = False
            body.vx = 500
            x, y = 300, 0
            for frame in range(1, fps + 1):
                x, y = body.step(frame / fps, x, y, 192, 208, (0, 0, 5000, 10000))
            outcomes.append(x)
            self.assertGreater(body.vx, 240)
            self.assertLess(body.vx, 250)
        self.assertLessEqual(max(outcomes) - min(outcomes), 1)

    def test_visible_body_touches_floor_and_sides_without_transparent_padding(self):
        for scale in (1, 2):
            shape = tuple(v * scale for v in (54, 49, 138, 202))
            body = Physics(0, 2000)
            x, y = body.step(.05, 2000, 2000, 192 * scale, 208 * scale,
                             (0, 0, 1920, 1040), body=shape)
            self.assertEqual(x + shape[2], 1920)
            self.assertEqual(y + shape[3], 1040)
            x, y = body.step(.1, -1000, -1000, 192 * scale, 208 * scale,
                             (0, 0, 1920, 1040), body=shape, dragging=True)
            self.assertEqual(x + shape[0], 0)
            self.assertEqual(y + shape[1], 0)







    def test_different_window_does_not_carry_and_drag_detaches(self):
        for dragging in (False, True):
            body = Physics(0, 292)
            x, y = body.step(.05, 300, 292, 192, 208, (0, 0, 1920, 1040),
                             platforms=[(200, 500, 800, 42, 200)])
            x, y = body.step(.1, x, y, 192, 208, (0, 0, 1920, 1040),
                             platforms=[(300, 600, 900, 43 if not dragging else 42, 300)], dragging=dragging)
            self.assertEqual(x, 300)
            self.assertIsNone(body.support)
            self.assertEqual(y, 292 if dragging else 296)

    def test_lands_on_highest_crossed_window_even_at_terminal_speed(self):
        body = Physics(0, 100)
        body.vy = 1200
        x, y = body.step(.05, 300, 100, 192, 208, (0, 0, 1920, 1040),
                         platforms=[(200, 350, 800), (200, 330, 800)])
        self.assertEqual(y, 122)
        self.assertEqual(body.support, (200, 330, 800))
        self.assertTrue(body.grounded)
        self.assertEqual(body.vy, 0)

    def test_window_support_is_stable_then_removing_it_starts_fall(self):
        body = Physics(0, 292)
        for frame in range(1, 100):
            _, y = body.step(frame / 60, 300, 292, 192, 208, (0, 0, 1920, 1040),
                             platforms=[(200, 500, 800)])
            self.assertEqual(y, 292)
            self.assertTrue(body.grounded)
        _, y = body.step(2, 300, y, 192, 208, (0, 0, 1920, 1040))
        self.assertGreater(y, 292)
        self.assertFalse(body.grounded)

    def test_walk_off_or_move_window_away_removes_support(self):
        for x, platform in [(900, (200, 500, 800)), (300, (800, 500, 1200))]:
            body = Physics(0, 292)
            _, y = body.step(.05, x, 292, 192, 208, (0, 0, 1920, 1040), platforms=[platform])
            self.assertGreater(y, 292)
            self.assertFalse(body.grounded)

    def test_window_cannot_catch_pet_from_below_or_when_dragging(self):
        for dragging in [False, True]:
            body = Physics(0, 400)
            _, y = body.step(.05, 300, 400, 192, 208, (0, 0, 1920, 1040),
                             platforms=[(200, 500, 800)], dragging=dragging)
            self.assertGreaterEqual(y, 400)
            self.assertIsNone(body.support)

    def test_occluded_window_tops_are_split_in_z_order(self):
        self.assertEqual(visible_platforms([(300, 200, 600, 700), (100, 400, 900, 800)]),
                         [(300, 200, 600), (100, 400, 300), (600, 400, 900)])
        self.assertEqual(visible_platforms([(0, 0, 1920, 1040), (100, 400, 900, 800)]),
                         [(0, 0, 1920)])

    def test_falls_and_stops_above_taskbar_without_penetrating_floor(self):
        body = Physics(0, 100)
        x, y = 300, 100
        # Work area ends at 1040, above a 40px taskbar on a 1080px monitor.
        for frame in range(1, 301):
            x, y = body.step(frame / 60, x, y, 192, 208, (0, 0, 1920, 1040))
            self.assertLessEqual(y + 208, 1040)
        self.assertEqual(y, 832)
        self.assertTrue(body.grounded)
        self.assertEqual(body.vy, 0)

    def test_dragging_holds_position_then_release_starts_falling(self):
        body = Physics(0, 100)
        self.assertEqual(body.step(1, 300, 100, 192, 208, (0, 0, 1920, 1040), dragging=True), (300, 100))
        self.assertEqual(body.vy, 0)
        _, y = body.step(1.05, 300, 100, 192, 208, (0, 0, 1920, 1040))
        self.assertGreater(y, 100)

    def test_solid_left_right_and_top_boundaries(self):
        for x, expected in [(-500, 0), (2000, 1728)]:
            body = Physics(0, -200)
            self.assertEqual(body.step(1, x, -200, 192, 208, (0, 0, 1920, 1040), dragging=True), (expected, 0))

    def test_scaled_sprite_on_monitor_with_negative_coordinates(self):
        body = Physics(0, 800)
        x, y = body.step(.05, -100, 800, 384, 416, (-1920, -200, 0, 1000))
        self.assertEqual((x, y), (-384, 584))
        self.assertTrue(body.grounded)

    def test_menu_pause_and_long_frame_do_not_cause_teleport(self):
        body = Physics(0, 100)
        self.assertEqual(body.step(20, 300, 100, 192, 208, (0, 0, 1920, 1040), paused=True), (300, 100))
        _, y = body.step(50, 300, 100, 192, 208, (0, 0, 1920, 1040))
        self.assertLessEqual(y - 100, 4)

    def test_large_scale_still_stays_in_small_work_area(self):
        body = Physics(0, 100)
        self.assertEqual(body.step(1, 200, 100, 384, 416, (0, 0, 300, 350)), (0, 0))


if __name__ == "__main__":
    unittest.main()
