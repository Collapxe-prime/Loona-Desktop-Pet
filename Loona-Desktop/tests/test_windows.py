import unittest
from windows import fills_work_area
from physics import visible_platforms, Physics


class FullWindowTests(unittest.TestCase):
    def test_maximized_and_borderless_windows_are_not_supports(self):
        work = (0, 0, 1920, 1040)
        self.assertTrue(fills_work_area((-8, -8, 1928, 1048), work, True))
        self.assertTrue(fills_work_area((0, 0, 1920, 1080), work))
        self.assertFalse(fills_work_area((0, 0, 960, 1040), work))
        self.assertFalse(fills_work_area((200, 200, 1000, 700), work))

    def test_secondary_monitor_and_side_taskbar(self):
        self.assertTrue(fills_work_area((-1920, 0, 0, 1080), (-1872, 0, 0, 1080)))
        self.assertFalse(fills_work_area((-1920, 100, 0, 1000), (-1872, 0, 0, 1080)))

    def test_full_window_still_hides_edges_of_windows_behind_it(self):
        rectangles = [(0, 0, 1920, 1040, 1), (200, 300, 800, 700, 2)]
        self.assertEqual(visible_platforms(rectangles, True, non_supporting={1}), [])
        self.assertEqual(len(visible_platforms(rectangles[1:], True)), 2)

    def test_removed_window_support_settles_on_taskbar_without_window_seating(self):
        body = Physics(0, 832)
        body.support = (0, 1040, 1920, 1, 0, 0, "bottom")
        platforms = visible_platforms([(0, 0, 1920, 1040, 1)], True, non_supporting={1})
        for frame in range(1, 10):
            x, y = body.step(frame * .05, 300, 832, 192, 208, (0, 0, 1920, 1040), platforms=platforms)
        self.assertEqual(y, 832)
        self.assertTrue(body.grounded)
        self.assertIsNone(body.support)
