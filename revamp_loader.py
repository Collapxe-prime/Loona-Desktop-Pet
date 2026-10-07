"""Load a complete, validated animation pack; incomplete work stays inactive."""
import json
from pathlib import Path
from PIL import Image


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


def load_pack(root, data, canvas=(192, 272)):
    result = {}
    groups = {name: len(entry["durations_ms"]) for name, entry in data["animations"].items()}
    groups["look"] = 16
    for name, count in groups.items():
        frames = []
        for index in range(count):
            with Image.open(Path(root) / name / f"{index:02}.png") as src:
                if src.size != canvas or src.mode != "RGBA" or not src.getbbox():
                    raise ValueError(f"Invalid RGBA sprite: {name}/{index}")
                frame = src.copy()
                entry = data['animations'].get(name,{})
                if entry.get('width_scales'):
                    from frame_registration import horizontal_register
                    frame = horizontal_register(frame, entry['width_scales'][index],
                                                entry['width_pivot_px'] * canvas[0]/192)
                frames.append(frame)
        result[name] = frames
    return result
