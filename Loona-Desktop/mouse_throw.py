"""Short, recent drag history estimates release velocity in screen pixels/sec."""
from collections import deque
import math

HISTORY_SECONDS = .120
WEIGHT_SECONDS = .025
STOP_SECONDS = .080
MIN_THROW_SPEED = 140.0
THROW_SPEED_GAIN = .75
MAX_THROW_SPEED = 1250.0

class DragMotion:
    def __init__(self):
        self.samples = deque(maxlen=256)
        self.last_motion = -math.inf

    def start(self,now,x,y):
        self.samples.clear()
        self.last_motion = -math.inf
        self.sample(now,x,y)

    def sample(self,now,x,y):
        if self.samples:
            old=self.samples[-1]
            if now<old[0]:return
            if math.hypot(x-old[1],y-old[2])>=.75:
                self.last_motion=now
            if now==old[0]:self.samples.pop()
        self.samples.append((now,float(x),float(y)))
        while self.samples and self.samples[0][0]<now-HISTORY_SECONDS:
            self.samples.popleft()

    def velocity(self,now):
        if len(self.samples)<2 or now-self.last_motion>=STOP_SECONDS:
            return 0.,0.
        records=[p for p in self.samples if now-p[0]<=HISTORY_SECONDS]
        if len(records)<2 or records[-1][0]-records[0][0]<.008:
            return 0.,0.
        # Recency-weighted regression is stable with coalesced mouse events,
        # and estimates the final stroke rather than the entire drag gesture.
        weights=[math.exp((p[0]-now)/WEIGHT_SECONDS) for p in records]
        total=sum(weights)
        t=sum(w*(p[0]-now) for w,p in zip(weights,records))/total
        cx=sum(w*p[1] for w,p in zip(weights,records))/total
        cy=sum(w*p[2] for w,p in zip(weights,records))/total
        denominator=sum(w*(p[0]-now-t)**2 for w,p in zip(weights,records))
        if denominator<1e-9:return 0.,0.
        vx=sum(w*(p[0]-now-t)*(p[1]-cx) for w,p in zip(weights,records))/denominator
        vy=sum(w*(p[0]-now-t)*(p[2]-cy) for w,p in zip(weights,records))/denominator
        speed=math.hypot(vx,vy)
        if speed<MIN_THROW_SPEED:return 0.,0.
        # The drag controls position directly, but release transfers only part
        # of its speed so quick strokes do not fling the pet across the desktop.
        factor=min(THROW_SPEED_GAIN,MAX_THROW_SPEED/speed)
        return vx*factor,vy*factor

