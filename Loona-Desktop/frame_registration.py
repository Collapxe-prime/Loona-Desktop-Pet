"""Display-only registration; original drawings remain unchanged."""
from PIL import Image


def uniform_register(frame, factor, pivot):
    """Scale the complete drawing around a fixed contact point on its canvas."""
    if abs(factor-1)<1e-9:
        return frame
    if not .8 <= factor <= 1.2:
        raise ValueError('Invalid uniform registration factor')
    x,y=pivot
    return frame.convert('RGBa').transform(frame.size,Image.Transform.AFFINE,
            (1/factor,0,x*(1-1/factor),0,1/factor,y*(1-1/factor)),
            Image.Resampling.BICUBIC).convert('RGBA')

def horizontal_register(frame, factor, pivot):
    if abs(factor-1)<1e-9:
        return frame
    if not .8 <= factor <= 1.2:
        raise ValueError('Invalid horizontal registration factor')
    return frame.convert('RGBa').transform(frame.size,Image.Transform.AFFINE,
            (1/factor,0,pivot*(1-1/factor),0,1,0),
            Image.Resampling.BICUBIC).convert('RGBA')
