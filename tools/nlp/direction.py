"""Which of several named places to say, and which to leave alone.

The case that asked for it, on 2026-08-30: the siren said Obolon and the
explanation said Vyshhorod, both true, and the pair read as a contradiction. Both
are north, so "say the nearest" would have produced one answer instead of two.

But not always, and his refinement is the whole rule: "якщо обидві цілі
знаходяться в секторі 90 град від мене, то беремо ближню, інакше залишаємо як є,
мо скоріше то різні цілі." With one threat over Obolon and another coming from
Vasylkiv in the south, the nearest name is the harmless one -- and saying only it
would be a lie by omission. Direction is what separates the two cases, and
distance never could.

So: places inside one 90-degree sector are one thing seen twice, and the nearest
of them is the answer. Places spread wider are separate things and both get said.
"""

from __future__ import annotations

import math

from .coords import POINTS

# Nearer than this to the centre and a bearing means nothing -- and it is also
# home itself, which is the nearest thing there can be.
AT_HOME_KM = 0.4


def bearing(origin: tuple[float, float], point: tuple[float, float]) -> float:
    """Initial bearing from `origin` to `point`, degrees clockwise from north."""
    lat1, lat2 = math.radians(origin[0]), math.radians(point[0])
    dlon = math.radians(point[1] - origin[1])
    y = math.sin(dlon) * math.cos(lat2)
    x = (math.cos(lat1) * math.sin(lat2)
         - math.sin(lat1) * math.cos(lat2) * math.cos(dlon))
    return math.degrees(math.atan2(y, x)) % 360.0


def spread(bearings: list[float]) -> float:
    """The smallest arc containing every bearing.

    Found as 360 minus the largest gap between neighbours, which is the only way
    that works on a circle: bearings of 350 and 10 are twenty degrees apart, not
    three hundred and forty.
    """
    if len(bearings) < 2:
        return 0.0
    order = sorted(bearings)
    gaps = [b - a for a, b in zip(order, order[1:])]
    gaps.append(360.0 - (order[-1] - order[0]))
    return 360.0 - max(gaps)


def km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def say(names: list[str], centre: tuple[float, float] | None,
        sector_deg: float = 90.0) -> list[str]:
    """The names worth saying, in the order given.

    Unchanged unless every name has a coordinate: a name with no point cannot be
    judged, and dropping it because its neighbour is nearer would silently lose
    whichever of them mattered.
    """
    if centre is None or sector_deg <= 0 or len(names) < 2:
        return names
    points = [(n, POINTS[n]) for n in names if n in POINTS]
    if len(points) != len(names):
        return names

    with_dist = [(km(centre, pt), n, pt) for n, pt in points]
    nearest = min(with_dist)
    if nearest[0] <= AT_HOME_KM:
        return [nearest[1]]          # home itself, and nothing is nearer

    bearings = [bearing(centre, pt) for _d, _n, pt in with_dist
                if _d > AT_HOME_KM]
    if spread(bearings) > sector_deg:
        return names                 # separate things, and both get said
    return [nearest[1]]
