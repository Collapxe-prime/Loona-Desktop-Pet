import math,unittest
from mouse_throw import DragMotion,MAX_THROW_SPEED,THROW_SPEED_GAIN
from physics import Physics
from main import DesktopPet

class MouseThrowTests(unittest.TestCase):
    def trace(self,vx,vy,fps=120):
        m=DragMotion();m.start(0,0,0)
        for i in range(1,round(.2*fps)+1):
            t=i/fps;m.sample(t,vx*t,vy*t)
        return m,t

    def test_fast_release_preserves_vector_and_is_event_rate_independent(self):
        for fps in (30,60,120,1000):
            m,t=self.trace(650,-850,fps)
            vx,vy=m.velocity(t)
            self.assertAlmostEqual(vx,650*THROW_SPEED_GAIN,places=6)
            self.assertAlmostEqual(vy,-850*THROW_SPEED_GAIN,places=6)

    def test_hold_and_gentle_placement_have_no_throw(self):
        m,t=self.trace(900,-500)
        x,y=m.samples[-1][1:]
        for i in range(1,12):m.sample(t+i*.01,x,y)
        self.assertEqual(m.velocity(t+.11),(0.,0.))
        gentle,t=self.trace(80,30)
        self.assertEqual(gentle.velocity(t),(0.,0.))

    def test_latest_stroke_sets_direction_instead_of_drag_start(self):
        m=DragMotion();m.start(0,0,0)
        for i in range(1,101):
            t=i*.005
            x=-600*t if t<=.4 else -240+900*(t-.4)
            m.sample(t,x,0)
        self.assertGreater(m.velocity(.5)[0],850*THROW_SPEED_GAIN)

    def test_cap_keeps_diagonal_direction(self):
        m,t=self.trace(5000,-5000)
        vx,vy=m.velocity(t)
        self.assertAlmostEqual(math.hypot(vx,vy),MAX_THROW_SPEED)
        self.assertAlmostEqual(vx,-vy)

    def app(self,m,t,moved=True,enabled=True):
        app=DesktopPet.__new__(DesktopPet)
        app.x,app.y=500,400
        app.drag=(0,0);app.drag_direction='running-right'
        app.hovered=True;app.drag_moved=moved
        app.drag_motion=m;app.physics_enabled=enabled
        app.physics=Physics(t,400)
        return app

    def test_release_enters_flight_and_clears_window_contact(self):
        m,t=self.trace(650,-850)
        app=self.app(m,t)
        app.physics.support=(0,608,1000,42,0)
        app.physics.window_velocity=(300,0)
        app.physics.balance_until=10
        self.assertEqual(app.release_drag(t),(False,True))
        self.assertIsNone(app.drag)
        self.assertIsNone(app.physics.support)
        self.assertFalse(app.physics.grounded)
        self.assertEqual(app.physics.window_velocity,(0,0))
        x,y=app.physics.step(t+.02,app.x,app.y,192,208,(0,0,3000,2000))
        self.assertGreater(x,500)
        self.assertLess(y,400)

    def test_click_and_disabled_physics_never_launch(self):
        m,t=self.trace(650,-850)
        for moved,enabled in ((False,True),(True,False)):
            app=self.app(m,t,moved,enabled)
            self.assertEqual(app.release_drag(t),(not moved,False))
            self.assertEqual((app.physics.vx,app.physics.vy),(0,0))

    def test_thrown_sprite_lands_and_friction_stops_it(self):
        m,t=self.trace(650,-600)
        app=self.app(m,t)
        app.x=app.y=300
        app.physics.y=300
        self.assertEqual(app.release_drag(t),(False,True))
        body=app.physics
        x,y=300,300
        for i in range(1,501):
            x,y=body.step(t+i*.01,x,y,192,208,(0,0,4000,1040))
        self.assertGreater(x,550)
        self.assertLess(x,680)  # A normal flick must not coast across the desktop.
        self.assertEqual(y,832)
        self.assertTrue(body.grounded)
        self.assertEqual((body.vx,body.vy),(0,0))

    def test_extra_throw_damping_ends_on_contact(self):
        from friction_solver import AIR_DRAG,THROW_AIR_DRAG
        body=Physics(0,830)
        self.assertEqual(body.air_drag,AIR_DRAG)
        body.launch(0,300,830,500,100)
        self.assertEqual(body.air_drag,THROW_AIR_DRAG)
        body.step(.05,300,830,192,208,(0,0,4000,1040))
        self.assertTrue(body.grounded)
        self.assertEqual(body.air_drag,AIR_DRAG)

    def test_ceiling_stops_upward_throw_without_pin(self):
        body=Physics(0,1);body.launch(0,300,1,100,-1500)
        x,y=body.step(.01,300,1,192,208,(0,0,2000,1040))
        self.assertEqual(y,0)
        self.assertEqual(body.vy,0)
        x,y=body.step(.05,x,y,192,208,(0,0,2000,1040))
        self.assertGreater(y,0)

    def test_real_mouse_message_handlers_transfer_drag_velocity(self):
        import ctypes as C
        from unittest.mock import patch
        from main import POINT
        from mouse_mood import MouseMood
        m=DragMotion()
        app=self.app(m,0)
        app.scale=1
        app.dynamic=True
        app.menu_open=False
        app.frames={'look':[None]*16}
        app.mouse_mood=MouseMood()
        app.windows_enabled=False
        app.smoke=True
        app.screen_bounds=lambda:(0,0,4000,2000)
        app.collision_bounds=lambda:(0,0,192,208)
        app.capture=lambda hwnd:None
        app.releasecapture=lambda:None
        app.render=lambda:None
        app.save=lambda:None
        app.recenter_walk=lambda:None
        app.update_behavior=lambda *args:None
        point=[580,480]
        def cursor(ptr):
            p=C.cast(ptr,C.POINTER(POINT)).contents
            p.x,p.y=point
        app.cursor=cursor
        with patch('main.time.monotonic',return_value=0):
            self.assertEqual(app.wndproc(1,0x201,0,0),0)
        for i in range(1,21):
            t=i*.01
            point[:]=[580+round(700*t),480-round(600*t)]
            with patch('main.time.monotonic',return_value=t):
                self.assertEqual(app.wndproc(1,0x200,0,0),0)
        with patch('main.time.monotonic',return_value=.2):
            self.assertEqual(app.wndproc(1,0x202,0,0),0)
        self.assertIsNone(app.drag)
        self.assertAlmostEqual(app.physics.vx,700*THROW_SPEED_GAIN)
        self.assertAlmostEqual(app.physics.vy,-600*THROW_SPEED_GAIN)
        self.assertFalse(app.physics.grounded)
        self.assertTrue(app.inspect_pending)

if __name__=='__main__':unittest.main()
