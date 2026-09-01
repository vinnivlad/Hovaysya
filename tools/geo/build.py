"""Turn the OSM extract into a coordinate for each canonical gazetteer name.

Two things make this more than a join.

**A district is not a point.** OSM holds Troieshchyna as 22 numbered
microdistricts, Pozniaky as 17. The centroid of all of them is a better answer
than any one, and the spread around it is a free quality check: candidates 30 km
apart mean the match is wrong, not that the district is large.

**Stem matching produces confident wrong answers.** The first run matched
Троєщина -- 494 mentions, the commonest name after Київ -- to a *village* called
Троєщина out in the oblast, and Антонов to Антоновичі near Chornobyl. So city
names are matched only inside Kyiv and only against urban kinds, and everything
else lands in the report for eyes rather than in the table.

    python -m tools.geo.build              # writes tools/nlp/coords.py
    python -m tools.geo.build --report     # what matched how, and how badly
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from ..nlp.gazetteer import (CITY, LANDMARKS, MY_AREA, MY_DISTRICT, OBLAST,
                             _strip_apostrophes)

REPO_ROOT = Path(__file__).resolve().parents[2]
OSM_PATH = REPO_ROOT / "data" / "osm-places.json"
OUT_PATH = REPO_ROOT / "tools" / "nlp" / "coords.py"

# Distance from home rather than a bounding box, which is both simpler and
# strictly better. A box drawn generously enough to hold Kyiv held Brovary too,
# and threw away the exact match for it; a box drawn tightly enough to exclude
# Brovary would have thrown away Vyshneve and Hatne, which are in his ring by his
# own ruling precisely because the ring crosses the city boundary.
#
# The limits are what makes a wrong match impossible rather than unlikely. The
# only OSM place called Нивки in the whole oblast is a hamlet in the Chornobyl
# zone, 90 km out; the Kyiv district of that name -- 200 mentions -- is simply not
# in the extract, and it has to end up in the report rather than at 51.34.
LIMIT_KM = {"my-area": 25.0, "my-district": 25.0, "city": 25.0,
            "oblast": 160.0, "elsewhere": 1200.0}

# A district whose pieces sit this far apart was not matched, it was guessed.
SPREAD_LIMIT_KM = 8.0

# Home, from the gazetteer, geocoded once against OSM: node 2962022989,
# "Жуляни, Солом'янський район, Київ".
HOME_POINT = (50.39282, 30.44217)


def km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance, good to a few metres at this scale."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def _norm(text: str) -> str:
    return _strip_apostrophes(text).lower()


def match(place, rows: list[dict]) -> tuple[tuple[float, float] | None, dict]:
    """A coordinate for one gazetteer entry, and how it was arrived at."""
    limit = LIMIT_KM.get(place.tier, 25.0)
    cand = [r for r in rows
            if any(st in _norm(r["name"]) for st in place.stems)
            and km(HOME_POINT, (r["lat"], r["lon"])) <= limit]
    if not cand:
        return None, {"how": "нема кандидатів у межах", "n": 0}

    # An exact name beats a stem, and among exact names the nearest wins -- two
    # villages share a name often enough in this oblast.
    exact = [r for r in cand if _norm(r["name"]) == _norm(place.name)]
    if exact:
        exact.sort(key=lambda r: km(HOME_POINT, (r["lat"], r["lon"])))
        used = exact[:1]
    else:
        # No exact name means a district held as its numbered pieces: OSM has
        # Troieshchyna as 22 microdistricts and Pozniaky as 17, and their centroid
        # is a better answer than any one of them.
        used = cand

    lat = sum(r["lat"] for r in used) / len(used)
    lon = sum(r["lon"] for r in used) / len(used)
    spread = max((km((lat, lon), (r["lat"], r["lon"])) for r in used), default=0.0)
    return (round(lat, 5), round(lon, 5)), {
        "how": "назва" if exact else f"центроїд ×{len(used)}",
        "n": len(used),
        "spread": round(spread, 1),
        "names": sorted({r["name"] for r in used})[:3],
    }


def build(rows: list[dict]):
    from .hand import HAND, TOO_BIG_FOR_A_POINT

    got, flagged, missing = {}, [], []
    for group in (MY_AREA, MY_DISTRICT, CITY, OBLAST, LANDMARKS):
        for place in group:
            if place.name in TOO_BIG_FOR_A_POINT:
                continue
            if place.name in HAND:
                lat, lon, osm = HAND[place.name]
                got[place.name] = ((lat, lon), {"how": f"руками ({osm})",
                                                "n": 1, "spread": 0.0})
                continue
            point, how = match(place, rows)
            if point is None:
                missing.append((place, how))
                continue
            if how.get("spread", 0.0) > SPREAD_LIMIT_KM:
                flagged.append((place, point, how))
                continue
            got[place.name] = (point, how)
    return got, flagged, missing


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--osm", default=str(OSM_PATH))
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()

    rows = json.loads(Path(args.osm).read_text(encoding="utf-8"))
    got, flagged, missing = build(rows)
    print(f"{len(got)} з координатами · {len(flagged)} з завеликим розкидом · "
          f"{len(missing)} без кандидатів")

    header = [
        '"""Where each canonical gazetteer name is, to five decimal places.',
        "",
        "Generated by `python -m tools.geo.build` -- do not edit. The sources are",
        "an Overpass query over the whole of Kyiv oblast (`tools/geo/osm.py`, and",
        "the query is in it, so this can be rebuilt and checked) plus the",
        "hand-geocoded exceptions in `tools/geo/hand.py`, each carrying the OSM",
        "object it came from.",
        "",
        "A name absent from here has no coordinate on purpose: Правий берег is",
        "half a city, Київщина is the oblast. Callers must cope with that rather",
        "than substitute a centre.",
        '"""',
        "",
        "# name: (lat, lon)",
        "POINTS: dict[str, tuple[float, float]] = {",
    ]
    body = [f"    {name!r}: ({pt[0]}, {pt[1]}),"
            for name, (pt, _how) in sorted(got.items())]
    Path(args.out).write_text(chr(10).join(header + body + ["}", ""]),
                              encoding="utf-8")
    print(f"  → {args.out}")

    if args.report:
        if flagged:
            print("\nрозкид більший за", SPREAD_LIMIT_KM, "км — збіг сумнівний:")
            for place, point, how in flagged:
                print(f"  {place.name:26} {how['how']:10} розкид {how['spread']:6} км"
                      f"  {', '.join(how['names'])}")
        if missing:
            print("\nбез кандидатів — потрібні руки:")
            for place, _how in missing:
                print(f"  {place.tier:12} {place.name}")
        wide = sorted(((h.get("spread", 0), name, h)
                       for name, (_pt, h) in got.items()), reverse=True)[:8]
        print("\nнайбільший розкид серед прийнятих:")
        for spread, name, how in wide:
            print(f"  {name:26} {spread:5} км  {how['how']}")


if __name__ == "__main__":
    main()
