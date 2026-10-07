"""Distance-driven sprite phase keeps planted feet stationary in world space."""
def advance_phase(phase, distance, scale, stride):
    if scale <= 0 or stride <= 0:
        raise ValueError('Scale and stride must be positive')
    return (phase + abs(distance) / (scale * stride)) % 1.0

