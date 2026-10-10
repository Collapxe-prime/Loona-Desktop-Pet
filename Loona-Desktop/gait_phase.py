"""Distance-driven sprite phase keeps planted feet stationary in world space."""
from bisect import bisect_right
from itertools import accumulate


def frame_index(phase, count, distances=None):
    """Nonuniform drawings advance after their measured ground displacement."""
    phase %= 1.0
    if distances is None:
        return min(count - 1, int(phase * count))
    boundaries = list(accumulate(distances))
    return min(count - 1, bisect_right(boundaries, phase * boundaries[-1]))


def advance_phase(phase, distance, scale, stride):
    if scale <= 0 or stride <= 0:
        raise ValueError('Scale and stride must be positive')
    return (phase + abs(distance) / (scale * stride)) % 1.0

