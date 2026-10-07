"""Calibrate detail bandwidth while preserving sprite alpha and registration."""
from PIL import Image,ImageFilter
import json

def read_profile(root):
    path=root/'quality-profile.json'
    if not path.exists():return None
    data=json.loads(path.read_text())
    if data.get('version')!=1:raise ValueError('Unsupported sprite quality profile')
    return data

def radius_for(profile,group,pet_scale):
    return profile['scales'][f'{pet_scale:g}']['radii_hq'][group]

def soften(frame,radius):
    if radius<=.001:return frame
    premult=frame.convert('RGBa')
    # Pillow cannot filter RGBa directly: treat its stored bytes as RGBA,
    # filter all premultiplied channels, then unpremultiply the result.
    filtered=Image.frombytes('RGBA',frame.size,premult.tobytes()).filter(ImageFilter.GaussianBlur(radius))
    rgb=Image.frombytes('RGBa',frame.size,filtered.tobytes()).convert('RGBA')
    rgb.putalpha(frame.getchannel('A'))
    return rgb

def sharpness(frame):
    """Normalized high-frequency edge energy, excluding alpha silhouette edges.

    L1 Laplacian / L1 gradient measures edge crispness rather than total detail
    count. It is a comparison metric, not a claim about photographic quality.
    """
    # Offline calibration only; normal pet playback does not need NumPy in memory.
    import numpy as np
    a=np.asarray(frame,dtype=np.float64)
    gray=(a[:,:,0]*.2126+a[:,:,1]*.7152+a[:,:,2]*.0722)/255
    opaque=frame.getchannel('A').point(lambda v:255 if v>=250 else 0).filter(ImageFilter.MinFilter(5))
    mask=np.asarray(opaque)[1:-1,1:-1]>0
    center=gray[1:-1,1:-1]
    dx=gray[1:-1,2:]-gray[1:-1,:-2]
    dy=gray[2:,1:-1]-gray[:-2,1:-1]
    lap=gray[1:-1,2:]+gray[1:-1,:-2]+gray[2:,1:-1]+gray[:-2,1:-1]-4*center
    grad=np.abs(dx)+np.abs(dy)
    return float(np.sum(np.abs(lap)[mask])/max(1e-9,np.sum(grad[mask])))

