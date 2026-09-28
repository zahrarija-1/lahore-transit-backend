"""
Transit AI - Find stop names that are probably the same place.

"Chungi Amar Sidhu" and "Chungi Amer Sidhu" are one junction spelled two
ways. To the app they are two unrelated stops, which breaks search by name
and hides a real interchange between the routes that serve them.

This writes a review file. It does not merge anything, because only you
can tell a spelling variant from two genuinely different places: the
matcher scores "5 Number Stop" against "25 Number Stop" at 0.94, and
those are a kilometre apart.

Now that coordinates exist, the distance column decides most rows on its
own. Two stops with the same name a few metres apart are the same place.
The same name two kilometres apart is not.

    cd backend
    python scripts/find_name_variants.py

Output: data/review/name_variants.csv
"""

import csv
import difflib
import math
import os
import re
import sys
from collections import defaultdict

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
REVIEW_DIR = os.path.join(DATA_DIR, "review")

# Below this, names are different places rather than different spellings.
SIMILARITY_THRESHOLD = 0.82

# Words that carry no meaning for matching. "Chowk" and "Stop" appear on
# half the dataset and make everything look similar to everything else.
NOISE = {"stop", "chowk", "road", "rd", "more", "mor", "pul", "bridge",
         "underpass", "flyover", "station", "terminal", "bazar", "bazaar"}


def normalise(name):
    """Strip case, punctuation and filler so real differences stand out."""
    text = name.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    words = [w for w in text.split() if w and w not in NOISE]
    return " ".join(words)


def metres(a, b):
    return math.hypot((a[0] - b[0]) * 111_320, (a[1] - b[1]) * 94_900)


def main():
    stops_path = os.path.join(DATA_DIR, "stops.csv")
    route_stops_path = os.path.join(DATA_DIR, "route_stops.csv")

    with open(stops_path, "r", encoding="utf-8-sig", newline="") as handle:
        stops = list(csv.DictReader(handle))

    with open(route_stops_path, "r", encoding="utf-8-sig", newline="") as h:
        route_stops = list(csv.DictReader(h))

    # Which routes use each stop - context when deciding whether two names
    # are the same place.
    routes_for = defaultdict(set)
    for row in route_stops:
        routes_for[row["stop_id"]].add(row["route_id"])

    points = {}
    for stop in stops:
        try:
            points[stop["stop_id"]] = (
                float(stop["latitude"]), float(stop["longitude"])
            )
        except (TypeError, ValueError):
            pass

    candidates = []
    seen = set()

    for index, a in enumerate(stops):
        norm_a = normalise(a["stop_name"])
        if not norm_a:
            continue

        for b in stops[index + 1:]:
            norm_b = normalise(b["stop_name"])
            if not norm_b:
                continue

            if norm_a == norm_b:
                score = 1.0
            else:
                score = difflib.SequenceMatcher(None, norm_a, norm_b).ratio()
                if score < SIMILARITY_THRESHOLD:
                    continue

            pair = tuple(sorted([a["stop_id"], b["stop_id"]]))
            if pair in seen:
                continue
            seen.add(pair)

            point_a = points.get(a["stop_id"])
            point_b = points.get(b["stop_id"])

            if point_a and point_b:
                distance = round(metres(point_a, point_b))
                # Same name within 60 m is one stop entered twice. Past a
                # few hundred metres it is two places, whatever the names
                # look like.
                if distance <= 60:
                    verdict = "almost certainly same"
                elif distance <= 300:
                    verdict = "check the map"
                else:
                    verdict = "probably different"
            else:
                distance = ""
                verdict = "no coordinates"

            candidates.append({
                "score": round(score, 3),
                "metres_apart": distance,
                "verdict": verdict,
                "keep_id": a["stop_id"],
                "keep_name": a["stop_name"],
                "keep_routes": " ".join(sorted(routes_for[a["stop_id"]])),
                "merge_id": b["stop_id"],
                "merge_name": b["stop_name"],
                "merge_routes": " ".join(sorted(routes_for[b["stop_id"]])),
                "same_place": "",
            })

    # Closest first: the rows worth acting on come to the top.
    candidates.sort(
        key=lambda c: (c["metres_apart"] if c["metres_apart"] != "" else 9e9)
    )

    os.makedirs(REVIEW_DIR, exist_ok=True)
    out_path = os.path.join(REVIEW_DIR, "name_variants.csv")

    with open(out_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "score", "metres_apart", "verdict",
            "keep_id", "keep_name", "keep_routes",
            "merge_id", "merge_name", "merge_routes", "same_place",
        ])
        writer.writeheader()
        writer.writerows(candidates)

    print(f"{len(stops)} stops compared")
    print(f"{len(candidates)} pair(s) similar enough to check")
    print()

    for c in candidates[:15]:
        gap = f"{c['metres_apart']:>6} m" if c["metres_apart"] != "" else "     -"
        print(f"  {gap}  {c['verdict']:<22} "
              f"{c['keep_name']:<30} | {c['merge_name']}")

    if len(candidates) > 15:
        print(f"  ... and {len(candidates) - 15} more")

    print()
    print(f"Written: {out_path}")
    print()
    print("Open it and set same_place:")
    print("  y   one place, two spellings. merge_id is replaced by keep_id")
    print("      everywhere and its row is removed.")
    print("  n   or leave blank. Nothing happens.")
    print()
    print("The verdict column is a suggestion, not a decision. Check the")
    print("route columns too: two stops on the same route are almost never")
    print("the same place.")
    print()
    print("Then: python scripts/apply_name_fixes.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())