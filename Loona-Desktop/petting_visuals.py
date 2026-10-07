"""Whole-drawing smile frames plus animated UI heart particles."""
from pathlib import Path
import json,math
from PIL import Image,ImageDraw
from frame_cache import ByteLRU,LazyFrames

def hearts(frame,age):
    overlay=Image.new('RGBA',frame.size)
    draw=ImageDraw.Draw(overlay)
    factor=frame.width/384
    for x,y,delay in ((314,212,0),(76,186,.65),(326,171,1.25)):
        if age<delay:continue
        phase=((age-delay)%2)/2
        alpha=round(220*math.sin(math.pi*phase))
        radius=(13+3*math.sin(math.pi*phase))*factor
        cx=(x+5*math.sin(phase*math.pi*2))*factor
        cy=(y-52*phase)*factor
        points=[]
        for i in range(64):
            t=i*math.pi*2/64
            points.append((cx+radius*math.sin(t)**3,
                           cy-radius*(13*math.cos(t)-5*math.cos(2*t)-2*math.cos(3*t)-math.cos(4*t))/16))
        draw.polygon(points,fill=(255,115,163,alpha))
    result=frame.copy();result.alpha_composite(overlay)
    return result

class PettingVisuals:
    def __init__(self,root):
        root=Path(root)
        self.meta=json.loads((root/'animation.json').read_text())
        cache=ByteLRU(4*1024**2,lambda frame:frame.width*frame.height*4)
        self.hq=LazyFrames([root/'hq'/f'{i:02}.png' for i in range(8)],(384,544),cache)
        self.normal=LazyFrames([root/'frames'/f'{i:02}.png' for i in range(8)],(192,272),cache)

    def index(self,age):
        step=max(0,int(age/.2))
        return min(7,2+step) if step<6 else 4+(step-6)%4

    def image(self,age,hq=True):
        return hearts((self.hq if hq else self.normal)[self.index(age)],age)

    def radius(self,scale):
        return self.meta['radii_hq'][f'{scale:g}']

def load_petting_visuals(root):
    return PettingVisuals(root) if (Path(root)/'animation.json').exists() else None
