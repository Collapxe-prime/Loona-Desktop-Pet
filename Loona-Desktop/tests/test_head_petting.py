import unittest
from head_petting import HeadPetting
from mouse_mood import MouseMood
from test_behavior import pet
from physics import Physics

def stroke_points():
    return [(i*.02,x,68) for i,x in enumerate(list(range(88,121,2))+list(range(118,87,-2)))]

class HeadPettingTests(unittest.TestCase):
    def test_long_stroke_stop_emits_one_event_on_leave_or_pause(self):
        for leave in (False,True):
            detector=HeadPetting()
            for i in range(251):
                phase=i%32
                detector.sample(i*.02,88+2*(phase if phase<=16 else 32-phase),140)
            _,x,y=detector.last
            detector.sample(5.7,300 if leave else x,y,moved=leave)
            self.assertTrue(detector.consume_stop_anger())
            self.assertFalse(detector.consume_stop_anger())
            self.assertFalse(detector.active(5.7))

    def test_short_stroke_or_forced_interruption_does_not_trigger_stop_anger(self):
        for length,enabled in ((200,True),(251,False)):
            detector=HeadPetting()
            for i in range(length):
                phase=i%32
                detector.sample(i*.02,88+2*(phase if phase<=16 else 32-phase),140)
            detector.sample(6,300,140,enabled=enabled)
            self.assertFalse(detector.consume_stop_anger())

    def test_stop_after_four_seconds_plays_exactly_one_full_anger_cycle(self):
        app=pet();app.head_petting=HeadPetting();app.mouse_mood=MouseMood()
        for i in range(251):
            phase=i%32;x=88+2*(phase if phase<=16 else 32-phase)
            position=(app.x+x,app.y+140)
            app.update_behavior(i*.02,position)
        app.update_behavior(5.7,position)
        self.assertEqual(app.state,'waiting')
        self.assertTrue(app.waiting_after_petting)
        shown=[]
        for _ in range(len(app.frames['waiting'])):
            shown.append(app.index)
            app.advance_animation(app.deadline,position)
        self.assertEqual(shown,list(range(len(app.frames['waiting']))))
        self.assertEqual(app.state,'idle')
        self.assertFalse(app.petting_anger_once)
        app.update_behavior(20,position)
        # A stationary cursor no longer prevents subsequent autonomous actions.
        self.assertNotEqual(app.state,'waiting')
        self.assertFalse(app.petting_active)

    def test_smile_starts_after_two_seconds_of_continuous_strokes(self):
        detector=HeadPetting()
        for i in range(160):
            phase=i%32
            detector.sample(i*.02,88+2*(phase if phase<=16 else 32-phase),68)
            if i<100:self.assertFalse(detector.happy(i*.02))
            if i==100:self.assertTrue(detector.happy(i*.02))
        self.assertTrue(detector.happy(3.18))
        detector.sample(3.2,104,68,enabled=False)
        self.assertFalse(detector.happy(3.2))

    def test_waiting_or_a_pause_does_not_earn_a_smile(self):
        detector=HeadPetting()
        for t,x,y in stroke_points():detector.sample(t,x,y)
        for i in range(150):detector.sample(.7+i*.02,104,68,moved=False)
        self.assertFalse(detector.happy(3.7))
        for t,x,y in stroke_points():detector.sample(4+t,x,y)
        self.assertFalse(detector.happy(4.64))

    def test_application_switches_to_smile_and_drag_cancels_it(self):
        from pathlib import Path
        from petting_visuals import load_petting_visuals
        app=pet();app.head_petting=HeadPetting()
        app.petting_visuals=load_petting_visuals(Path(__file__).resolve().parents[1]/'assets/petting-smile')
        for i in range(160):
            phase=i%32;x=88+2*(phase if phase<=16 else 32-phase)
            app.update_behavior(i*.02,(app.x+x,app.y+150))
            if i<100:self.assertFalse(app.petting_happy)
            if i==100:self.assertTrue(app.petting_happy)
        self.assertTrue(app.petting_happy)
        self.assertGreater(app.petting_visual_age,0)
        app.drag=(0,0);app.drag_moved=True
        app.update_behavior(3.2,(app.x+104,app.y+68))
        self.assertFalse(app.petting_happy)
        self.assertEqual(app.state,'balancing')

    def test_slow_back_and_forth_strokes_trigger_and_release(self):
        detector=HeadPetting();hits=[]
        for now,x,y in stroke_points():
            if detector.sample(now,x,y):hits.append(now)
        self.assertTrue(hits)
        self.assertTrue(detector.active(hits[-1]+.5))
        self.assertFalse(detector.active(hits[-1]+1.3))

    def test_stationary_cursor_does_not_trigger(self):
        detector=HeadPetting()
        self.assertFalse(any(detector.sample(i*.02,104,68) for i in range(100)))

    def test_bunched_mouse_messages_do_not_reset_small_strokes(self):
        detector=HeadPetting()
        for i in range(260):
            now=i*.01;phase=i%32
            x=90+(phase if phase<=16 else 32-phase)
            detector.sample(now,x,140)
            detector.sample(now+.0001,x+.666,140)
        self.assertTrue(detector.happy(2.59))

    def test_fast_back_and_forth_on_sprite_still_counts(self):
        detector=HeadPetting()
        for i in range(220):detector.sample(i*.01,88 if i%2 else 120,140)
        self.assertTrue(detector.happy(2.19))

    def test_vertical_and_circular_strokes_are_accepted(self):
        import math
        scenarios=[[(i*.02,104,76+16*math.sin(i*.12)) for i in range(160)],
                   [(i*.02,104+18*math.cos(i*.12),76+14*math.sin(i*.12)) for i in range(160)]]
        for points in scenarios:
            detector=HeadPetting()
            for t,x,y in points:detector.sample(t,x,y)
            self.assertTrue(detector.happy(points[-1][0]))

    def test_stroking_works_at_head_body_and_feet(self):
        for y in (42,120,190):
            detector=HeadPetting()
            self.assertTrue(any(detector.sample(t,x,y) for t,x,_ in stroke_points()))

    def test_outside_sprite_and_motion_of_window_do_not_count(self):
        for moved,y in ((True,225),(False,68)):
            detector=HeadPetting()
            self.assertFalse(any(detector.sample(t,x,y,moved=moved) for t,x,_ in stroke_points()))

    def test_disabled_dragging_cancels_the_reaction(self):
        detector=HeadPetting()
        for t,x,y in stroke_points():detector.sample(t,x,y)
        self.assertTrue(detector.active(.7))
        detector.sample(.7,104,68,enabled=False)
        self.assertFalse(detector.active(.7))

    def test_anger_blocks_stroking_until_reaction_ends(self):
        app=pet();app.head_petting=HeadPetting();app.mouse_mood=MouseMood()
        app.mouse_mood.touch(0);app.mouse_mood.touch(.1)
        for now,x,y in stroke_points():
            app.hovered=True
            app.update_behavior(now,(app.x+x,app.y+y))
        self.assertFalse(app.petting_active)
        self.assertTrue(app.mouse_mood.pending)
        self.assertEqual(app.state,'waiting');self.assertIsNone(app.look_index)
        app.update_behavior(.8,(app.x+104,app.y+68))
        self.assertEqual(app.state,'waiting')
        app.advance_animation(app.deadline)
        self.assertEqual(app.state,'waiting')
        app.update_behavior(7,(1800,50))
        self.assertFalse(app.mouse_mood.pending)
        self.assertFalse(app.petting_active)
        for now,x,y in stroke_points():
            app.update_behavior(now+8,(app.x+x,app.y+y))
        self.assertTrue(app.petting_active)
        self.assertEqual(app.state,'idle')

    def test_one_second_of_continuous_strokes_calms_both_anger_sources(self):
        for source in ('mouse', 'stop-petting'):
            app=pet();app.head_petting=HeadPetting();app.mouse_mood=MouseMood()
            if source == 'mouse':
                app.mouse_mood.touch(-.2);app.mouse_mood.touch(-.1)
            else:
                app.petting_anger_once=True
            for i in range(51):
                phase=i%32
                x=88+2*(phase if phase<=16 else 32-phase)
                app.update_behavior(i*.02,(app.x+x,app.y+68))
                if i < 50:
                    self.assertEqual(app.state,'waiting')
                    self.assertFalse(app.petting_active)
            self.assertEqual(app.state,'idle')
            self.assertTrue(app.petting_active)
            self.assertFalse(app.mouse_mood.pending)
            self.assertFalse(app.petting_anger_once)

    def test_leaving_sprite_resets_calming_progress_and_hover_alone_does_not_calm(self):
        app=pet();app.head_petting=HeadPetting();app.mouse_mood=MouseMood()
        app.mouse_mood.touch(-.2);app.mouse_mood.touch(-.1)
        for offset in (0, 1):
            for now,x,y in stroke_points():
                app.update_behavior(now+offset,(app.x+x,app.y+y))
            self.assertEqual(app.state,'waiting')
            app.update_behavior(offset+.7,(1800,50))
        position=(app.x+104,app.y+68)
        for now in (2, 2.5, 3, 3.5):
            app.update_behavior(now,position)
            self.assertEqual(app.state,'waiting')
            self.assertFalse(app.petting_active)

    def test_drag_and_fall_keep_their_priority(self):
        app=pet();app.head_petting=HeadPetting();app.mouse_mood=MouseMood()
        for now,x,y in stroke_points():app.update_behavior(now,(app.x+x,app.y+y))
        app.drag=(0,0);app.drag_moved=True
        app.update_behavior(.7,(app.x+104,app.y+68))
        self.assertEqual(app.state,'balancing');self.assertFalse(app.petting_active)
        app.drag=None;app.physics_enabled=True;app.physics=Physics(.8,app.y);app.physics.grounded=False
        for now,x,y in stroke_points():app.update_behavior(now+1,(app.x+x,app.y+y))
        self.assertEqual(app.state,'falling');self.assertFalse(app.petting_active)

    def test_typing_retains_book_and_review(self):
        from keyboard_activity import KeyboardActivity
        app=pet();app.head_petting=HeadPetting();app.typing_enabled=app.typing_waiting=True
        app.keyboard_activity=KeyboardActivity();app.keyboard_activity.sample(0,True)
        for now,x,y in stroke_points():app.update_behavior(now,(app.x+x,app.y+y))
        self.assertEqual(app.state,'jumping');self.assertFalse(app.petting_active)
        app.update_behavior(1.5,(app.x+104,app.y+68))
        self.assertEqual(app.state,'review')

if __name__=='__main__':unittest.main()
