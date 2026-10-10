"""Load a complete, validated animation pack; incomplete work stays inactive."""
import json
import math
from pathlib import Path
from PIL import Image
from frame_cache import ByteLRU,LazyFrames


def read_pack(root, states):
    root = Path(root)
    manifest = root / "manifest.json"
    if not manifest.exists():
        return None
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if data.get("version") != 1 or set(data["animations"]) != set(states):
        raise ValueError("Incomplete revamp animation manifest")
    for name, entry in data["animations"].items():
        durations = entry["durations_ms"]
        display_scale=entry.get('display_scale',1)
        display_pivot=entry.get('display_pivot_px',[0,0])
        if (not isinstance(display_scale,(int,float)) or not .8 <= display_scale <= 1.2
                or not isinstance(display_pivot,list) or len(display_pivot)!=2
                or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in display_pivot)):
            raise ValueError(f'Invalid display registration: {name}')
        distances = entry.get('frame_distances_px')
        if distances is not None:
            stride = entry.get('stride_px', 0)
            if (len(distances) != len(durations)
                    or any(not isinstance(d, (int, float)) or not math.isfinite(d) or d <= 0 for d in distances)
                    or not math.isclose(sum(distances), stride, abs_tol=.01)):
                raise ValueError(f'Invalid distance-driven frame calibration: {name}')
        scales = entry.get('width_scales')
        if scales is not None and (len(scales) != len(durations)
                                  or any(not .8 <= s <= 1.2 for s in scales)):
            raise ValueError(f'Invalid width registration: {name}')
        if not durations or any(value <= 0 for value in durations):
            raise ValueError(f"Invalid timings: {name}")
        expected = entry.get('frame_count', data.get('frames_per_animation'))
        if expected is not None and (not isinstance(expected, int) or expected <= 0 or len(durations) != expected):
            raise ValueError(f'Incomplete requested frame count: {name}')
        if not (0 <= entry.get('loop_start', 0) < len(durations)):
            raise ValueError(f'Invalid loop start: {name}')
        for index in range(len(durations)):
            if not (root / name / f"{index:02}.png").is_file():
                raise ValueError(f"Missing revamp frame: {name}/{index}")
    for index in range(16):
        if not (root / "look" / f"{index:02}.png").is_file():
            raise ValueError(f"Missing look direction: {index}")
    return data


def load_pack(root, data, canvas=(192, 272),cache_bytes=4*1024**2):
    result = {}
    cache=ByteLRU(cache_bytes,lambda frame:frame.width*frame.height*4)
    groups = {name: len(entry["durations_ms"]) for name, entry in data["animations"].items()}
    groups["look"] = 16
    for name, count in groups.items():
        entry=data['animations'].get(name,{})
        result[name]=LazyFrames([Path(root)/name/f'{i:02}.png' for i in range(count)],canvas,cache,
            entry.get('width_scales'),entry.get('width_pivot_px',0)*canvas[0]/192,
            entry.get('display_scale',1),
            tuple(v*canvas[i]/(192,272)[i] for i,v in enumerate(entry.get('display_pivot_px',[0,0]))))
    return result
