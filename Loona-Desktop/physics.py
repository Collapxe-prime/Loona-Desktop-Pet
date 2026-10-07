"""Visible platform geometry and public physics interface."""
from friction_solver import Physics, platform_key


def visible_platforms(rectangles, include_bottom=False, non_supporting=()):
    """Rectangles arrive front to back; covered parts of edges are removed."""
    platforms, blockers = [], []
    for rectangle in rectangles:
        left, top, right, bottom = rectangle[:4]
        excluded = len(rectangle) > 4 and rectangle[4] in non_supporting
        edges = [] if excluded else [(top, "top")] + ([(bottom, "bottom")] if include_bottom else [])
        for level, edge in edges:
            spans = [(left, right)]
            probe = level if edge == "top" else level - 1
            for bl, bt, br, bb in blockers:
                if bt <= probe < bb:
                    spans = [(a, b) for lo, hi in spans
                             for a, b in ((lo, min(hi, bl)), (max(lo, br), hi)) if a < b]
            platforms.extend(((lo, level, hi, rectangle[4], left, edge) if include_bottom
                              else (lo, level, hi, rectangle[4], left)) if len(rectangle) > 4
                             else (lo, level, hi) for lo, hi in spans)
        blockers.append((left, top, right, bottom))
    return platforms

