"""
Transit AI - Fill stops.csv from lahore_transit_map.csv.

That file already carries a latitude and longitude for almost every stop,
so geocoding 316 names one at a time is unnecessary. This copies them
across, and deals with the two ways the source disagrees with itself.

1. A stop that appears on several routes can carry several coordinates.
   Usually they sit tens of metres apart - the shelter on each side of the
   road, or two GPS readings of the same spot. Those are averaged.

2. Sometimes they sit kilometres apart, which is not noise: one of the
   readings is simply wrong. Those are written to a review file and left
   out of stops.csv, because an averaged point between two places is a
   third place that does not exist.

    cd backend
    python scripts/import_coordinates_from_map.py path/to/lahore_transit_map.csv

Backs up stops.csv first.
"""

import csv
import os
import shutil
import sys
from collections import defaultdict
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
REVIEW_DIR = os.path.join(DATA_DIR, "review")
BACKUP_DIR = os.path.join(DATA_DIR, "backup")

LAT_MIN, LAT_MAX = 31.20, 31.80
LON_MIN, LON_MAX = 74.00, 74.70

# Two readings of one stop can differ by this much and still be the same
# place. Beyond it, somebody has to look. A bus shelter and the shelter
# across the road are about 30 m apart; 200 m is already a different
# junction.
SAME_PLACE_METRES = 200


def metres_between(a, b):
    """Flat-earth distance. Fine over a city, and needs no dependencies."""
    lat_metres = (a[0] - b[0]) * 111_320
    # Longitude degrees shrink towards the poles; 94,900 m is the width of
    # one degree at Lahore's latitude.
    lon_metres = (a[1] - b[1]) * 94_900
    return (lat_metres ** 2 + lon_metres ** 2) ** 0.5


def spread(points):
    """Widest gap in a group of points, in metres."""
    if len(points) < 2:
        return 0.0
    return max(
        metres_between(points[i], points[j])
        for i in range(len(points))
        for j in range(i + 1, len(points))
    )


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/import_coordinates_from_map.py "
              "<lahore_transit_map.csv>")
        return 1

    source_path = sys.argv[1]
    if not os.path.exists(source_path):
        print(f"Not found: {source_path}")
        return 1

    stops_path = os.path.join(DATA_DIR, "stops.csv")

    with open(source_path, "r", encoding="utf-8-sig", newline="") as handle:
        source = list(csv.DictReader(handle))

    # ------------------------------------------------------------------
    # Gather every coordinate offered for each stop
    # ------------------------------------------------------------------
    points = defaultdict(list)
    names = {}
    routes_for = defaultdict(set)
    rejected_rows = 0

    for row in source:
        stop_id = row.get("stop_id", "").strip()
        if not stop_id:
            continue

        names.setdefault(stop_id, row.get("stop_name", "").strip())
        routes_for[stop_id].add(row.get("route_id", ""))

        try:
            lat = float(row["latitude"])
            lon = float(row["longitude"])
        except (KeyError, TypeError, ValueError):
            continue    # blank cell, nothing to take

        if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
            rejected_rows += 1
            continue

        points[stop_id].append((lat, lon))

    print(f"{len(source)} rows read from {os.path.basename(source_path)}")
    print(f"  stop_id values        : {len(names)}")
    if rejected_rows:
        print(f"  rows outside Lahore   : {rejected_rows} (ignored)")

    # ------------------------------------------------------------------
    # Decide one coordinate per stop
    # ------------------------------------------------------------------
    resolved = {}
    disputed = []
    no_data = []
    averaged = 0

    for stop_id in names:
        group = points.get(stop_id, [])

        if not group:
            no_data.append(stop_id)
            continue

        unique = sorted({(round(p[0], 6), round(p[1], 6)) for p in group})

        if len(unique) == 1:
            resolved[stop_id] = unique[0]
            continue

        gap = spread(unique)

        if gap <= SAME_PLACE_METRES:
            lat = sum(p[0] for p in unique) / len(unique)
            lon = sum(p[1] for p in unique) / len(unique)
            resolved[stop_id] = (lat, lon)
            averaged += 1
        else:
            disputed.append({
                "stop_id": stop_id,
                "stop_name": names[stop_id],
                "routes": " ".join(sorted(routes_for[stop_id])),
                "gap_metres": round(gap),
                "options": unique,
            })

    print()
    print(f"  resolved directly     : {len(resolved) - averaged}")
    print(f"  averaged (within {SAME_PLACE_METRES} m): {averaged}")
    print(f"  disputed (too far apart): {len(disputed)}")
    print(f"  no coordinate at all  : {len(no_data)}")

    # ------------------------------------------------------------------
    # Review files for the ones a person has to settle
    # ------------------------------------------------------------------
    os.makedirs(REVIEW_DIR, exist_ok=True)

    if disputed or no_data:
        review_path = os.path.join(REVIEW_DIR, "coordinates_to_check.csv")

        with open(review_path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow([
                "stop_id", "stop_name", "routes", "problem",
                "gap_metres", "option_1", "option_2", "option_3",
                "latitude", "longitude", "approved",
            ])

            for item in disputed:
                options = [f"{lat:.6f},{lon:.6f}" for lat, lon in item["options"]]
                options += [""] * (3 - len(options))
                writer.writerow([
                    item["stop_id"], item["stop_name"], item["routes"],
                    "readings disagree", item["gap_metres"],
                    options[0], options[1], options[2],
                    "", "", "",
                ])

            for stop_id in no_data:
                writer.writerow([
                    stop_id, names[stop_id],
                    " ".join(sorted(routes_for[stop_id])),
                    "no coordinate in source", "",
                    "", "", "",
                    "", "", "",
                ])

        print()
        print(f"  written: {review_path}")

    # ------------------------------------------------------------------
    # Write the ones that are settled
    # ------------------------------------------------------------------
    with open(stops_path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        stops = list(reader)

    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"stops_{stamp}.csv")
    shutil.copy2(stops_path, backup_path)

    written = 0
    unmatched = 0

    for stop in stops:
        point = resolved.get(stop["stop_id"])
        if point is None:
            unmatched += 1
            continue
        stop["latitude"] = f"{point[0]:.6f}"
        stop["longitude"] = f"{point[1]:.6f}"
        written += 1

    with open(stops_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(stops)

    print()
    print(f"Backed up to {backup_path}")
    print(f"stops.csv: {written} of {len(stops)} stops now have coordinates")

    if unmatched:
        print(f"           {unmatched} still empty")

    print()
    print("NEXT:")
    if disputed or no_data:
        print("  1. Open data/review/coordinates_to_check.csv")
        print("     - readings disagree: pick the right option, copy it into")
        print("       the latitude and longitude columns, mark approved = y")
        print("     - no coordinate: look the stop up on a map and type it in")
        print("  2. python scripts/apply_coordinates.py")
        print("  3. python scripts/audit_data.py")
        print("  4. python database.py")
    else:
        print("  python scripts/audit_data.py")
        print("  python database.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())