"""Display-only horizontal registration; original drawings remain unchanged."""
from PIL import Image

def horizontal_register(frame, factor, pivot):
    if abs(factor-1)<1e-9:
        return frame
    if not .8 <= factor <= 1.2:
        raise ValueError('Invalid horizontal registration factor')
    return frame.convert('RGBa').transform(frame.size,Image.Transform.AFFINE,
            (1/factor,0,pivot*(1-1/factor),0,1,0),
            Image.Resampling.BICUBIC).convert('RGBA')
