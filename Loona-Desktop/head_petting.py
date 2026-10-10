"""Recognize gentle strokes anywhere on the sprite without changing dragging."""
import math

ANGER_CALM_SECONDS = 1.0
SITTING_CANCEL_SECONDS = 4.0

class HeadPetting:
    def __init__(self,bounds=(20,20,170,202)):
        self.bounds=bounds
        self.until=-math.inf
        self.happy_until=-math.inf
        self.stop_anger_pending=False
        self.clear_motion()

    def clear_motion(self):
        self.last=None
        self.session_started=None
        self.last_motion=None
        self.travel=0

    def in_sprite(self,x,y):
        left,top,right,bottom=self.bounds
        return left<=x<right and top<=y<bottom

    def end_session(self,voluntary=False):
        if (voluntary and self.session_started is not None and self.last_motion is not None
                and self.last_motion-self.session_started>4 and self.travel>=14):
            self.stop_anger_pending=True
            self.until=self.happy_until=-math.inf
        self.clear_motion()

    def consume_stop_anger(self):
        result=self.stop_anger_pending
        self.stop_anger_pending=False
        return result

    def sample(self,now,x,y,enabled=True,moved=True):
        if not enabled:
            self.clear_motion();self.until=self.happy_until=-math.inf
            self.stop_anger_pending=False
            return False
        if not self.in_sprite(x,y):
            self.end_session(voluntary=True)
            return False
        if self.last is None:
            self.last=(now,x,y)
            return False
        old_time,old_x,old_y=self.last
        if not moved:
            # Window movement underneath an unmoving mouse is never stroking.
            if (abs(x-old_x)>1 or abs(y-old_y)>1
                    or (self.last_motion is not None and now-self.last_motion>.6)):
                self.end_session(voluntary=abs(x-old_x)<=1 and abs(y-old_y)<=1)
                self.last=(now,x,y)
            return False
        self.last=(now,x,y)
        dx,dy=x-old_x,y-old_y
        dt=now-old_time
        distance=math.hypot(dx,dy)
        # WM_MOUSEMOVE and timer samples can arrive only microseconds apart.
        # Their instantaneous velocity is not a reliable gesture filter.
        if dt<0 or dt>.6:
            self.end_session(voluntary=dt>.6);self.last=(now,x,y)
            return False
        if distance<.5:return False
        if self.session_started is None:self.session_started=old_time
        self.last_motion=now
        self.travel+=distance
        # Any smooth path over the sprite counts: circles, vertical or horizontal.
        if self.travel>=14 and now-self.session_started>=.1:
            self.until=now+1.2
            if now-self.session_started>=2:self.happy_until=self.until
            return True
        return False

    def active(self,now):
        return now<self.until

    def calms_anger(self,now):
        return self.sustained_stroke(now, ANGER_CALM_SECONDS)

    def cancels_sitting(self,now):
        return self.sustained_stroke(now, SITTING_CANCEL_SECONDS)

    def sustained_stroke(self,now,seconds):
        return (self.active(now) and self.session_started is not None
                and self.last_motion is not None and now-self.last_motion <= .6
                and now-self.session_started >= seconds)

    def happy(self,now):
        return self.active(now) and now<self.happy_until

    def frame(self,now,started):
        elapsed=now-started
        remaining=self.until-now
        if elapsed<.12:return 16
        if elapsed<.24:return 17
        if remaining<.12:return 20
        if remaining<.24:return 19
        return 18
