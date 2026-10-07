import random
import unittest

from behavior import Autonomy, WALK_SPEED, WALK_DISTANCE

SPEEDS = {state: 1 for state in ("running", "review", "running-left", "running-right")}
DURATIONS = {"running": .82, "review": 1.03}


class AutonomyTests(unittest.TestCase):
    def test_occasional_stroll_becomes_directional_run_and_finishes_at_target(self):
        from behavior import STROLL_SPEED
        durations=dict(DURATIONS,**{'walking-left':4.2,'walking-right':4.2,'running-left':3,'running-right':3})
        speeds=dict(SPEEDS,**{'walking-left':1,'walking-right':1})
        for direction in ('left','right'):
            actor=Autonomy(0,900,0,2000,durations,random.Random(42))
            actor.rng.choice=lambda choices: 'walk' if 'walk' in choices else (min(choices) if direction=='left' else max(choices))
            actor.rng.random=lambda:0
            actor.start_action(0,900,speeds,walking=True)
            self.assertEqual(actor.action,'running-'+direction)
            self.assertGreater(actor.movement_speed(actor.action,speeds),STROLL_SPEED)
            goal=actor.target;x=900
            for i in range(1,500):
                state,x=actor.update(i*.05,x,speeds)
                if state is None:break
            self.assertEqual(x,goal)
            self.assertIsNone(actor.action)
            actor.rng.random=lambda:1
            actor.start_action(30,900,speeds,walking=True)
            self.assertEqual(actor.action,'walking-'+direction)

    def test_grimoire_is_available_as_a_random_action(self):
        durations=dict(DURATIONS,jumping=1.68)
        speeds=dict(SPEEDS,jumping=1)
        actor=Autonomy(0,100,-100,400,durations,random.Random(42))
        actor.rng.choice=lambda choices: 'jumping' if 'jumping' in choices else choices[0]
        actor.start_action(1,100,speeds,walking=False)
        self.assertEqual(actor.action,'jumping')
        self.assertGreater(actor.until,1)
        self.assertIsNone(actor.update(actor.until,100,speeds)[0])

    def test_new_pack_uses_walking_for_strolls_and_window_exits(self):
        from behavior import STROLL_SPEED
        durations = dict(DURATIONS, **{'walking-right': 1.6, 'walking-left': 1.6})
        speeds = dict(SPEEDS, **{'walking-right': 1, 'walking-left': 1})
        actor = Autonomy(0, 100, -1000, 2000, durations, random.Random(42))
        actor.rng.choice = lambda choices: 'walk' if 'walk' in choices else choices[-1]
        actor.start_action(0, 100, speeds, walking=True)
        self.assertEqual(actor.action, 'walking-right')
        self.assertEqual(actor.update(.05, 100, speeds)[1], 100 + STROLL_SPEED * .05)
        actor.rng.choice = lambda choices: 'leave-window' if 'leave-window' in choices else choices[0]
        actor.start_action(1, 100, speeds, walking=True, on_window=True, exit_targets=(-200,))
        self.assertEqual(actor.action, 'walking-left')

    def test_exit_choice_requires_window_walking_and_reachable_edge(self):
        actor = self.make()
        actor.rng.choice = lambda choices: "leave-window" if "leave-window" in choices else choices[0]
        for on_window, walking, goals in [(False, True, (450,)), (True, False, (450,)), (True, True, ())]:
            actor.start_action(0, 100, SPEEDS, walking=walking, on_window=on_window, exit_targets=goals)
            self.assertFalse(actor.leaving_window)
        actor.start_action(0, 100, SPEEDS, walking=True, on_window=True, exit_targets=(450,))
        self.assertTrue(actor.leaving_window)
        self.assertEqual(actor.target, 450)
        self.assertGreater(actor.target, actor.right)
        actor.pause(1)
        self.assertFalse(actor.leaving_window)

    def test_sitting_is_random_behavior_only_on_window_and_holds_pose(self):
        actor = self.make()
        actor.rng.choice = lambda choices: "sitting" if "sitting" in choices else "running"
        actor.start_action(0, 100, SPEEDS, walking=False, on_window=False)
        self.assertEqual(actor.action, "running")
        actor.start_action(5, 100, SPEEDS, walking=False, on_window=True)
        self.assertEqual(actor.action, "sitting")
        self.assertGreaterEqual(actor.until, 65)
        self.assertLessEqual(actor.until, 185)
        self.assertEqual(actor.update(actor.until - .1, 100, SPEEDS, on_window=True), ("sitting", 100))
        self.assertIsNone(actor.update(actor.until, 100, SPEEDS, on_window=True)[0])

    def make(self):
        return Autonomy(0, 100, -100, 400, DURATIONS, random.Random(42))

    def test_short_random_interval(self):
        actor = self.make()
        for now in range(50):
            actor.schedule(now)
            self.assertGreaterEqual(actor.next_action - now, 3)
            self.assertLessEqual(actor.next_action - now, 6)

    def test_phone_repeats_for_thirty_to_forty_five_seconds_regardless_of_frame_speed(self):
        actor = self.make()
        actor.rng.choice = lambda choices: "running"
        fast = dict(SPEEDS, running=2)
        actor.start_action(5, 100, fast, walking=False)
        self.assertGreaterEqual(actor.until, 35)
        self.assertLessEqual(actor.until, 50)
        self.assertEqual(actor.update(actor.until - .1, 100, fast)[0], "running")
        self.assertIsNone(actor.update(actor.until, 100, fast)[0])

    def test_walk_reaches_target_without_overshooting(self):
        actor = self.make()
        actor.action, actor.target = "running-right", 175
        x = 100
        for i in range(1, 31):
            state, x = actor.update(i * .05, x, SPEEDS)
            self.assertLessEqual(x, 175)
            if state is None:
                break
        self.assertEqual(x, 175)
        self.assertIsNone(actor.action)

    def test_long_pause_does_not_teleport(self):
        actor = self.make()
        actor.action, actor.target = "running-right", 300
        _, x = actor.update(30, 100, SPEEDS)
        self.assertLessEqual(x - 100, WALK_SPEED * .05)

    def test_interruption_stops_and_reschedules_on_release(self):
        actor = self.make()
        actor.action, actor.target = "running-left", 0
        state, x = actor.update(.1, 100, SPEEDS, interrupted=True)
        self.assertEqual((state, x), (None, 100))
        actor.update(2, 100, SPEEDS)
        self.assertTrue(5 <= actor.next_action <= 8)
        self.assertIsNone(actor.action)

    def test_disabled_walking_still_allows_stationary_actions(self):
        actor = self.make()
        actor.next_action = 0
        state, x = actor.update(.05, 100, SPEEDS, walking=False)
        self.assertIn(state, ("running", "review"))
        self.assertEqual(x, 100)

    def test_safe_local_territory_and_recenter_after_drag(self):
        actor = self.make()
        self.assertEqual((actor.left, actor.right), (-100, 400))
        actor.recenter(10, 500, 0, 600)
        self.assertEqual((actor.left, actor.right), (0, 600))
        for _ in range(100):
            actor.start_action(10, 500, SPEEDS, walking=True)
            if actor.target is not None:
                self.assertTrue(0 <= actor.target <= 600)

    def test_long_stride_is_preferred_over_a_short_stride_near_barrier(self):
        actor = Autonomy(0, 900, 0, 1000, DURATIONS, random.Random(42))
        original_choice = actor.rng.choice
        actor.rng.choice = lambda choices: "walk" if "walk" in choices else original_choice(choices)
        for _ in range(100):
            actor.start_action(0, 900, SPEEDS, walking=True)
            self.assertTrue(WALK_DISTANCE[0] <= abs(actor.target - 900) <= WALK_DISTANCE[1])
            self.assertEqual(actor.action, "running-left")


if __name__ == "__main__":
    unittest.main()
