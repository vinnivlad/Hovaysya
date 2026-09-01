"""Fetch every named place around Kyiv from OpenStreetMap, once.

His suggestion, and better than geocoding names one at a time: "по координатам
можна зробити вигрузку з OpenStreetMap по києву і агломерації". One query is one
provenance -- the query is in this file, so the table it produces can be rebuilt
and checked years from now, which the throwaway script behind the 2026-08-29
distance measurement could not be.

Overpass rather than a Geofabrik extract on purpose: a `.osm.pbf` needs a parser,
and this needs no third-party package at all, which is the property that lets the
watcher run on a 1 GB box.

The bounding box is Kyiv plus the ring of towns the channels actually name --
Vasylkiv and Bila Tserkva to the south, Brovary and Boryspil east, Vyshhorod and
Slavutych north, Fastiv west. Wider than the agglomeration proper, because
"агломерація" in these channels means whatever a drone crosses on the way in.

    python -m tools.geo.osm            # writes data/osm-places.json
    python -m tools.geo.osm --stats
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = REPO_ROOT / "data" / "osm-places.json"

ENDPOINT = "https://overpass-api.de/api/interpreter"

# south, west, north, east
BBOX = (49.2, 29.0, 51.6, 32.3)

# What counts as a place worth a name. `suburb`, `neighbourhood` and `quarter`
# are what Kyiv's districts are tagged as; `city`/`town`/`village` covers the
# ring; `hamlet` catches the small ones the channels still name.
KINDS = ("city", "town", "village", "hamlet", "suburb", "neighbourhood",
         "quarter", "borough", "city_district")

QUERY = """
[out:json][timeout:120];
(
  node["place"~"^(%(kinds)s)$"]["name"](%(bbox)s);
  way["place"~"^(%(kinds)s)$"]["name"](%(bbox)s);
  relation["place"~"^(%(kinds)s)$"]["name"](%(bbox)s);
);
out center tags;
"""


def fetch(timeout: float = 180.0) -> dict:
    body = QUERY % {"kinds": "|".join(KINDS),
                    "bbox": ",".join(str(x) for x in BBOX)}
    request = urllib.request.Request(
        ENDPOINT,
        data=urllib.parse.urlencode({"data": body}).encode(),
        headers={"User-Agent": "hovaysya/1.0 (personal air-alert tool)"})
    with urllib.request.urlopen(request, timeout=timeout) as reply:
        return json.loads(reply.read().decode("utf-8"))


def places(raw: dict) -> list[dict]:
    """One row per named place: the Ukrainian name, its kind, its centre."""
    out = []
    for el in raw.get("elements", []):
        tags = el.get("tags") or {}
        name = tags.get("name:uk") or tags.get("name")
        if not name:
            continue
        centre = el if "lat" in el else (el.get("center") or {})
        lat, lon = centre.get("lat"), centre.get("lon")
        if lat is None or lon is None:
            continue
        out.append({
            "name": name,
            "kind": tags.get("place", ""),
            "lat": round(float(lat), 5),
            "lon": round(float(lon), 5),
            "osm": f"{el.get('type', '')}/{el.get('id', '')}",
        })
    # One row per name, the most specific kind winning, so a suburb beats the
    # city relation that contains it.
    rank = {k: i for i, k in enumerate(reversed(KINDS))}
    best: dict[str, dict] = {}
    for row in out:
        old = best.get(row["name"])
        if old is None or rank.get(row["kind"], -1) > rank.get(old["kind"], -1):
            best[row["name"]] = row
    return sorted(best.values(), key=lambda r: r["name"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--stats", action="store_true")
    args = ap.parse_args()

    try:
        raw = fetch()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SystemExit(f"Overpass не відповів: {exc}")

    rows = places(raw)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"{out}: {len(rows)} названих місць")
    if args.stats:
        from collections import Counter
        for kind, n in Counter(r["kind"] for r in rows).most_common():
            print(f"  {kind:16} {n}")


if __name__ == "__main__":
    main()
