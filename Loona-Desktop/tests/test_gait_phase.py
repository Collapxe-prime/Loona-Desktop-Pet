import json
from pathlib import Path
import tempfile
import unittest

from gait_phase import advance_phase, frame_index
from main import REVAMP_PACK, REVAMP_ROOT
from revamp_loader import read_pack


class CalibratedGaitTests(unittest.TestCase):
    def test_ground_distances_choose_frames_at_measured_contacts_and_wrap(self):
        steps = [10, 2, 14, 6]
        for distance, expected in ((0, 0), (9.9, 0), (10, 1), (11.9, 1),
                                   (12, 2), (25.9, 2), (26, 3), (31.9, 3), (32, 0)):
            phase = advance_phase(0, distance, 1, sum(steps))
            self.assertEqual(frame_index(phase, 4, steps), expected)
            self.assertEqual(frame_index(advance_phase(0, -distance * 1.5, 1.5, sum(steps)), 4, steps), expected)
        self.assertEqual(frame_index(.25, 4), 1)  # Running keeps its existing mapping.

    def test_walking_uses_same_calibration_both_directions(self):
        from test_behavior import pet
        left = REVAMP_PACK['animations']['walking-left']
        right = REVAMP_PACK['animations']['walking-right']
        self.assertEqual(left['frame_distances_px'], right['frame_distances_px'])
        self.assertAlmostEqual(sum(right['frame_distances_px']), 157.4)
        for scale in (1, 1.5, 2):
            for sign, direction in ((1, 'right'), (-1, 'left')):
                app = pet(scale=scale)
                state = 'walking-' + direction
                app.autonomy.action = state
                app.autonomy.target = app.x + sign * 600
                before = app.x
                app.update_behavior(.05, (1800, 50))
                self.assertAlmostEqual(app.autonomy.walk_x - before, sign * 50 * .05)
                distance = abs(app.x - before) / scale
                self.assertAlmostEqual(app.gait_phase, distance / 157.4)
                self.assertEqual(app.index, frame_index(app.gait_phase, 16))

    def test_walking_displays_every_pose_with_even_cadence_in_both_directions(self):
        from collections import Counter
        from test_behavior import pet
        for scale in (1, 1.5, 2):
            for sign, direction in ((1, 'right'), (-1, 'left')):
                app = pet(scale=scale)
                app.autonomy.action = 'walking-' + direction
                app.autonomy.target = app.x + sign * 1000
                counts = Counter()
                # One pixel per tick at the unchanged 50px/s walking speed.
                for tick in range(1, int(157.4 * scale) + 1):
                    app.update_behavior(tick * .02, (1800, 50))
                    counts[app.index] += 1
                self.assertEqual(set(counts), set(range(16)))
                self.assertLessEqual(max(counts.values()) - min(counts.values()), 2)

    def test_invalid_calibration_is_rejected_before_loading_artwork(self):
        for distances in ([1], [0] * 16, [float('nan')] * 16, [1] * 16):
            data = json.loads((REVAMP_ROOT / 'manifest.json').read_text())
            data['animations']['walking-left']['frame_distances_px'] = distances
            # Only include the bad state: failure must precede any frame reads.
            data['animations'] = {'walking-left': data['animations']['walking-left']}
            with tempfile.TemporaryDirectory() as directory:
                (Path(directory) / 'manifest.json').write_text(json.dumps(data))
                with self.assertRaisesRegex(ValueError, 'frame calibration'):
                    read_pack(directory, {'walking-left'})
