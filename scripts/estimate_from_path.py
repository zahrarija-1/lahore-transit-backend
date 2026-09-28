"""
Transit AI - Estimate a missing stop from the route it sits on.

Works only where all three of these hold:

    the route has recorded geometry in route_paths
    the stop has a neighbour with coordinates before it
    and one after it

Then the stop's position is taken along the recorded road, at the point
proportional to its place in the sequence. The result is on the road the
bus actually uses, which a straight line between two stops would not be.

It is still an estimate. The bus stop could be anywhere along that
stretch. Every value written this way is listed at the end so it can be
checked, and it should be checked before the demo.

Where a route has no geometry, or several stops in a row are missing,
this refuses rather than spreading guesses evenly along a line. Eight
evenly spaced points between two places is not data.

    cd backend
    python scripts/estimate_from_path.py
"""

import csv
import math
import os
import shutil
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
BACKUP_DIR = os.path.join(DATA_DIR, "backup")
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "transit_ai.db")


def metres(a, b):
    lat = (a[0] - b[0]) * 111_320
    lon = (a[1] - b[1]) * 94_900
    return math.hypot(lat, lon)


def nearest_index(path, point):
    """Where along the recorded road a known stop sits."""
    best = 0
    best_distance = float("inf")
    for index, candidate in enumerate(path):
        distance = metres(candidate, point)
        if distance < best_distance:
            best_distance = distance
            best = index
    return best, best_distance


def point_at_fraction(path, start, end, fraction):
    """
    Walk the road from start to end and stop at the given fraction of
    the way. Measured by actual distance travelled, not by point count,
    because recorded points are not evenly spaced.
    """

    segment = path[start:end + 1] if start <= end else path[end:start + 1][::-1]

    if len(segment) < 2:
        return segment[0] if segment else None

    lengths = [metres(segment[i], segment[i + 1])
               for i in range(len(segment) - 1)]
    total = sum(lengths)

    if total == 0:
        return segment[0]

    target = total * fraction
    walked = 0.0

    for index, length in enumerate(lengths):
        if walked + length >= target:
            remaining = (target - walked) / length if length else 0
            a = segment[index]
            b = segment[index + 1]
            return (
                a[0] + (b[0] - a[0]) * remaining,
                a[1] + (b[1] - a[1]) * remaining,
            )
        walked += length

    return segment[-1]


def main():
    stops_path = os.path.join(DATA_DIR, "stops.csv")
    route_stops_path = os.path.join(DATA_DIR, "route_stops.csv")

    with open(stops_path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        stops = list(reader)

    with open(route_stops_path, "r", encoding="utf-8-sig", newline="") as h:
        route_stops = list(csv.DictReader(h))

    coords = {}
    names = {}
    for stop in stops:
        names[stop["stop_id"]] = stop["stop_name"]
        try:
            coords[stop["stop_id"]] = (
                float(stop["latitude"]), float(stop["longitude"])
            )
        except (TypeError, ValueError):
            pass

    missing = {s["stop_id"] for s in stops if s["stop_id"] not in coords}

    if not missing:
        print("Every stop already has coordinates.")
        return 0

    print(f"{len(missing)} stop(s) without coordinates")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    paths = defaultdict(list)
    cursor.execute("""
        SELECT route_id, latitude, longitude
        FROM route_paths
        WHERE direction = 'FW'
        ORDER BY route_id, point_sequence
    """)
    for route_id, lat, lon in cursor.fetchall():
        paths[route_id].append((lat, lon))
    conn.close()

    sequences = defaultdict(list)
    for row in route_stops:
        sequences[row["route_id"]].append(
            (int(row["stop_sequence"]), row["stop_id"])
        )
    for route_id in sequences:
        sequences[route_id].sort()

    estimated = {}
    refused = []

    for route_id, sequence in sequences.items():
        path = paths.get(route_id)

        for position, (_, stop_id) in enumerate(sequence):

            if stop_id not in missing or stop_id in estimated:
                continue

            if not path:
                refused.append((stop_id, route_id, "route has no geometry"))
                continue

            before = next(
                (sequence[i][1] for i in range(position - 1, -1, -1)
                 if sequence[i][1] in coords), None
            )
            after = next(
                (sequence[i][1] for i in range(position + 1, len(sequence))
                 if sequence[i][1] in coords), None
            )

            if before is None or after is None:
                refused.append((stop_id, route_id, "no neighbour on one side"))
                continue

            # How many missing stops share this gap. One can be placed at
            # the midpoint with some confidence; several cannot.
            gap = [s for _, s in sequence[
                next(i for i, (_, s) in enumerate(sequence) if s == before) + 1:
                next(i for i, (_, s) in enumerate(sequence) if s == after)
            ]]

            if len(gap) > 1:
                refused.append((
                    stop_id, route_id,
                    f"{len(gap)} stops missing in a row between "
                    f"{names[before]} and {names[after]}"
                ))
                continue

            start, start_error = nearest_index(path, coords[before])
            end, end_error = nearest_index(path, coords[after])

            # If the known stops are far from the recorded road, the road
            # is not the one they sit on and the estimate means nothing.
            if start_error > 300 or end_error > 300:
                refused.append((
                    stop_id, route_id,
                    "neighbouring stops do not sit on the recorded path"
                ))
                continue

            point = point_at_fraction(path, start, end, 0.5)

            if point is None:
                refused.append((stop_id, route_id, "path too short"))
                continue

            estimated[stop_id] = (point, route_id, names[before], names[after])

    print(f"  estimated : {len(estimated)}")
    print(f"  refused   : {len(refused)}")

    if refused:
        print()
        print("Cannot be estimated, and must be entered by hand:")
        for stop_id, route_id, reason in refused:
            print(f"  {stop_id} {names[stop_id]:<26} {route_id}  {reason}")

    if not estimated:
        return 0

    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(stops_path, os.path.join(BACKUP_DIR, f"stops_{stamp}.csv"))

    for stop in stops:
        if stop["stop_id"] not in estimated:
            continue
        point = estimated[stop["stop_id"]][0]
        stop["latitude"] = f"{point[0]:.6f}"
        stop["longitude"] = f"{point[1]:.6f}"

    with open(stops_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(stops)

    print()
    print("ESTIMATED - verify these on a map before the demo:")
    for stop_id, (point, route_id, before, after) in estimated.items():
        print(f"  {stop_id} {names[stop_id]:<26} "
              f"{point[0]:.6f}, {point[1]:.6f}")
        print(f"       on {route_id}, midway between {before} and {after}")

    print()
    print("These are positions along the recorded road, not surveyed")
    print("stop locations. Say so in the dataset chapter.")

    return 0


if __name__ == "__main__":
    sys.exit(main())