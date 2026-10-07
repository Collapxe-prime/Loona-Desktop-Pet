import unittest
from physics import Physics

BOUNDS = (0, 0, 6000, 1040)


def platform(left, level, now, interactive=True, width=1800, edge="top"):
    return (left, level, left + width, 42, left, now, edge, interactive)


def standing(x=900):
    body = Physics(0, 292)
    x, y = body.step(.05, x, 292, 192, 208, BOUNDS, platforms=[platform(200, 500, .05)])
    return body, x, y


class FrictionTests(unittest.TestCase):
    def test_seated_pose_holds_moderate_acceleration_that_slides_standing_pose(self):
        results=[]
        for seated in (False,True):
            body,x,y=standing();left=200.
            for frame in range(1,9):
                velocity=frame*10000/60
                left+=velocity/60;now=.05+frame/60
                x,y=body.step(now,x,y,192,208,BOUNDS,platforms=[platform(left,500,now)],seated=seated)
            results.append((abs(body.slide_velocity),abs((x-left)-700),body.balance_until))
            self.assertTrue(body.grounded)
        self.assertGreater(results[0][0],25)
        self.assertLess(results[1][0],1)
        self.assertLess(results[1][1],results[0][1])
        self.assertEqual(results[1][2],0)  # Remains seated rather than immediately standing to balance.

    def test_seated_pose_can_still_slide_and_fall_after_a_large_jerk(self):
        body,x,y=standing();left=200.;slid=False
        for frame in range(1,30):
            left+=100;now=.05+frame/60
            x,y=body.step(now,x,y,192,208,BOUNDS,platforms=[platform(left,500,now)],seated=True)
            slid |= body.grounded and body.sliding
            if not body.grounded:break
        self.assertTrue(slid)
        self.assertFalse(body.grounded)

    def test_both_edges_keep_contact_during_gentle_diagonal_cached_window_motion(self):
        for edge in ('top', 'bottom'):
            for fps in (30, 60, 120):
                with self.subTest(edge=edge, fps=fps):
                    body = Physics(0, 292)
                    x, y = body.step(.05, 900, 292, 192, 208, BOUNDS,
                                     platforms=[platform(200, 500, .05, edge=edge)])
                    for frame in range(1, fps + 1):
                        elapsed = frame / fps
                        scan = int(elapsed * 30 + 1e-8) / 30
                        level = 500 + scan * 180
                        x, y = body.step(.05 + elapsed, x, y, 192, 208, BOUNDS,
                            platforms=[platform(200 + scan * 120, level, .05 + scan, edge=edge)])
                        self.assertTrue(body.grounded)
                        self.assertEqual(body.support[6], edge)
                        self.assertLessEqual(abs(y + 208 - level), .5)
                    self.assertGreater(x, 990)

    def test_lower_edge_still_detaches_when_window_is_pulled_down_fast(self):
        body = Physics(0, 292)
        x, y = body.step(.05, 900, 292, 192, 208, BOUNDS,
                         platforms=[platform(200, 500, .05, edge='bottom')])
        x, y = body.step(.1, x, y, 192, 208, BOUNDS,
                         platforms=[platform(200, 520, .1, edge='bottom')])
        self.assertFalse(body.grounded)
        self.assertIsNone(body.support)
        self.assertEqual(y, 296)

    def test_landing_on_descending_window_matches_its_vertical_speed_without_repeated_bounces(self):
        body, x, y = standing()
        for frame in range(1, 91):
            now = .05 + frame / 60
            x, y = body.step(now, x, y, 192, 208, BOUNDS,
                             platforms=[platform(200, 500 + frame * 200 / 60, now)])
            if frame > 40:
                self.assertTrue(body.grounded)
                self.assertAlmostEqual(body.vy, 200)
                self.assertLessEqual(abs(y + 208 - (500 + frame * 200 / 60)), .5)

    def test_gentle_acceleration_tracks_then_fast_uniform_motion_does_not_throw_pet(self):
        body, x, y = standing()
        left, velocity = 200., 0.
        for frame in range(1, 151):
            velocity = min(1800, velocity + 20)  # 1200px/s²: within grip.
            left += velocity / 60
            now = .05 + frame / 60
            x, y = body.step(now, x, y, 192, 208, BOUNDS, platforms=[platform(left, 500, now)])
            self.assertTrue(body.grounded)
            self.assertFalse(body.sliding)
        self.assertAlmostEqual(body.vx, 1800)
        self.assertLess(abs((x - left) - 700), 20)

    def test_jerk_slides_on_surface_before_falling_from_edge(self):
        body, x, y = standing()
        left = 200.
        for frame in range(1, 12):
            left += 100
            now = .05 + frame / 60
            previous_x, previous_vx = x, body.vx
            x, y = body.step(now, x, y, 192, 208, BOUNDS, platforms=[platform(left, 500, now)])
            if body.grounded:
                self.assertLess(x - previous_x, 25)
                self.assertTrue(body.sliding)
            else:
                # Leaving contact retains velocity, with air drag; there is no kick.
                self.assertLessEqual(abs(body.vx), abs(previous_vx) + .01)
                self.assertGreater(body.y, 292)
                break
        self.assertFalse(body.grounded)

    def test_stopping_window_retains_momentum_and_reversal_does_not_reverse_body_instantly(self):
        for reverse in (False, True):
            body, x, y = standing()
            left = 200.
            for frame in range(1, 61):
                speed = min(600, frame * 20)
                left += speed / 60
                now = .05 + frame / 60
                x, y = body.step(now, x, y, 192, 208, BOUNDS, platforms=[platform(left, 500, now)])
            before = x
            now += 1 / 60
            if reverse:
                left -= 10
            x, y = body.step(now, x, y, 192, 208, BOUNDS, platforms=[platform(left, 500, now)])
            self.assertGreater(x, before)
            self.assertGreater(body.vx, 500)
            self.assertTrue(body.grounded)
            self.assertTrue(body.sliding)

    def test_window_descending_faster_than_gravity_leaves_body_behind(self):
        body, x, y = standing()
        x, y = body.step(.1, x, y, 192, 208, BOUNDS, platforms=[platform(200, 520, .1)])
        self.assertEqual(y, 296)
        self.assertFalse(body.grounded)
        self.assertEqual(body.vy, 80)

    def test_upward_window_pushes_then_stopping_can_launch_body(self):
        body, x, y = standing()
        x, y = body.step(.1, x, y, 192, 208, BOUNDS, platforms=[platform(200, 480, .1)])
        self.assertEqual(y, 272)
        self.assertAlmostEqual(body.vy, -400)
        x, y = body.step(.15, x, y, 192, 208, BOUNDS, platforms=[platform(200, 480, .15)])
        self.assertFalse(body.grounded)
        self.assertLess(y, 272)

    def test_lower_edge_of_same_window_catches_after_upper_edge_drops_away(self):
        body, x, y = standing()
        # Window is moved down: upper edge below the body does not pull it down.
        # Later the upper edge shifts beyond its feet, while a lower visible
        # segment remains underneath (e.g. top edge occluded by another window).
        for frame in range(1, 40):
            now = .05 + frame / 60
            edges = [platform(200, 550, now, edge="bottom")]
            x, y = body.step(now, x, y, 192, 208, BOUNDS, platforms=edges)
            if body.grounded:
                break
        self.assertEqual(y + 208, 550)
        self.assertEqual(body.support[6], "bottom")

    def test_new_window_system_changes_do_not_impart_velocity(self):
        body, x, y = standing()
        for frame in range(1, 5):
            now = .05 + frame / 60
            x, y = body.step(now, x, y, 192, 208, BOUNDS,
                             platforms=[platform(200 + frame * 30, 500, now, interactive=False)])
            self.assertEqual(x, 900)
            self.assertEqual(body.vx, 0)
            self.assertEqual(body.balance_until, 0)

    def test_cached_geometry_does_not_reverse_inertia_between_scans(self):
        for fps in (20, 60, 120):
            body, x, y = standing()
            last_x = x
            for frame in range(1, fps + 1):
                time = frame / fps
                scan_time = int(time * 20 + 1e-8) / 20
                p = platform(200 + scan_time * 400, 500, .05 + scan_time)
                x, y = body.step(.05 + time, x, y, 192, 208, BOUNDS, platforms=[p])
                self.assertGreaterEqual(x, last_x)
                self.assertTrue(body.grounded)
                last_x = x
            self.assertAlmostEqual(body.vx, 400)
            self.assertLess(abs(x - 1300), 40)

    def test_no_snap_back_after_short_jolt_and_stationary_surface_stops_sliding(self):
        body, x, y = standing()
        x, y = body.step(.1, x, y, 192, 208, BOUNDS, platforms=[platform(300, 500, .1)])
        self.assertLess(x, 1000)
        for frame in range(1, 40):
            now = .1 + frame / 60
            x, y = body.step(now, x, y, 192, 208, BOUNDS, platforms=[platform(300, 500, now)])
        self.assertTrue(body.grounded)
        self.assertFalse(body.sliding)
        self.assertEqual(body.vx, 0)
        self.assertLess(x, 1000)


if __name__ == "__main__":
    unittest.main()
