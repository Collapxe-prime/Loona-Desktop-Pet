import unittest

from main import DesktopPet, STATES, REVAMP_PACK, SPEED_PROFILE, SPEEDS, animation_speeds, speed_choices


class AnimationSpeedTests(unittest.TestCase):
    def test_run_distance_binding_respects_size_and_saved_speed_both_directions(self):
        from test_behavior import pet
        for scale in (1, 1.5, 2):
            for rate in (.5, 1, 2):
                for direction, sign in (('right', 1), ('left', -1)):
                    state = 'running-' + direction
                    app = pet(scale=scale)
                    app.speeds[state] = rate
                    app.autonomy.action = state
                    app.autonomy.target = app.x + sign * 600
                    before = app.x
                    app.update_behavior(.05, (1800, 50))
                    self.assertAlmostEqual(app.autonomy.walk_x - before, sign * 180 * rate * .05)
                    self.assertAlmostEqual(app.gait_phase, abs(app.x - before) / (230.4 * scale))
                    # When travel stops, the run pose must not continue cycling.
                    phase = app.gait_phase
                    app.update_behavior(.05, (1800, 50))
                    self.assertEqual(app.gait_phase, phase)

    def test_locomotion_uses_authored_tempo_without_changing_travel_speed(self):
        from test_behavior import pet
        for kind, speed, cycle in (('running', 180, .64), ('walking', 50, 1.28)):
            for direction, sign in (('right', 1), ('left', -1)):
                state = kind + '-' + direction
                app = pet()
                app.speeds = animation_speeds()
                app.autonomy.action = state
                app.autonomy.target = app.x + sign * 600
                before = app.x
                app.update_behavior(.05, (1800, 50))
                self.assertAlmostEqual(app.autonomy.walk_x - before, sign * speed * .05)
                self.assertTrue(app.gait_driven)
                distance = abs(app.x - before)
                # Supplied run sequence contains two repetitions of the gait;
                # its full-frame sequence must cover twice the distance.
                repetitions = 2 if kind == 'running' else 1
                stride = speed * cycle * repetitions if kind == 'running' else 157.4
                self.assertAlmostEqual(app.gait_phase, distance / stride)
                app.deadline = 0
                phase = app.gait_phase
                self.assertFalse(app.advance_animation(.1))  # No extra timer advancement.
                self.assertEqual(app.gait_phase, phase)
                self.assertAlmostEqual(sum(STATES[state][1]) / 1000, cycle)
                self.assertEqual(len(REVAMP_PACK['animations'][state]['durations_ms']), 16)

    def test_rebased_one_x_defaults_keep_previous_slow_grimoire_and_work_tempo(self):
        app = DesktopPet.__new__(DesktopPet)
        app.speeds = animation_speeds()
        for name, (_, durations, _) in STATES.items():
            app.state = name
            measured = 0
            for index in range(len(durations)):
                app.index = index
                measured += app.duration()
            self.assertEqual(app.speeds[name], 1.0)
            self.assertAlmostEqual(measured, sum(durations) / 1000)
        self.assertAlmostEqual(sum(STATES['jumping'][1]) / 1000, 1.68 * 3)
        self.assertAlmostEqual(sum(STATES['running'][1]) / 1000, 1.64 * 3)

    def test_legacy_rebase_preserves_each_old_speed_and_is_not_repeated_on_restart(self):
        app = DesktopPet.__new__(DesktopPet)
        for name, old_cycle in (('jumping', 1.68), ('running', 1.64)):
            for old_speed in SPEEDS:
                legacy = {'speed_profile': 'animation-repair-v1',
                          'speeds': {name: old_speed, 'running-right': 2, 'idle': .5}}
                app.speeds = animation_speeds(legacy)
                self.assertEqual(app.speeds[name], old_speed * 3)
                self.assertIn(app.speeds[name], speed_choices(name))
                app.state = name
                cycle = 0
                for index in range(len(STATES[name][1])):
                    app.index = index
                    cycle += app.duration()
                self.assertAlmostEqual(cycle, old_cycle / old_speed)
                normalized = {'speed_profile': SPEED_PROFILE, 'speeds': app.speeds}
                self.assertEqual(animation_speeds(normalized), app.speeds)
                self.assertEqual(app.speeds['running-right'], 2)
                self.assertEqual(app.speeds['idle'], .5)

    def test_saved_choices_override_defaults_without_changing_missing_states(self):
        speeds = animation_speeds({'speed_profile': 'animation-repair-v1',
                                  'speeds': {'jumping': 1.0, 'idle': .5,
                                             'running': 99, 'obsolete': .5}})
        self.assertEqual(speeds['jumping'], 3.0)
        self.assertEqual(speeds['idle'], .5)
        self.assertEqual(speeds['running'], 1.0)
        self.assertNotIn('obsolete', speeds)
        self.assertEqual(animation_speeds({'speeds': {'running': 2.0}})['running'], 1.0)
