"""
Transit AI - Print one route's stops in order, with coordinates.

A quick eyeball check after filling coordinates by hand. On a real bus
route the latitude and longitude move steadily in one direction, because
the bus drives one way. A number that jumps and comes back means that
stop was located in the wrong place.

    python scripts/check_route.py FRT18
"""

import csv
import math
import os
import sys

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def metres(a, b):
    return math.hypot((a[0] - b[0]) * 111_320, (a[1] - b[1]) * 94_900)


def main():
    route_id = sys.argv[1] if len(sys.argv) > 1 else "FRT18"

    with open(os.path.join(DATA_DIR, "stops.csv"),
              encoding="utf-8-sig", newline="") as handle:
        stops = {r["stop_id"]: r for r in csv.DictReader(handle)}

    with open(os.path.join(DATA_DIR, "route_stops.csv"),
              encoding="utf-8-sig", newline="") as handle:
        sequence = sorted(
            (int(r["stop_sequence"]), r["stop_id"])
            for r in csv.DictReader(handle)
            if r["route_id"] == route_id
        )

    if not sequence:
        print(f"No stops found for {route_id}.")
        return 1

    print(f"{route_id} - {len(sequence)} stops")
    print()

    previous = None

    for position, stop_id in sequence:
        stop = stops.get(stop_id)

        if stop is None:
            print(f"  {position:>3} {stop_id}  MISSING FROM stops.csv")
            continue

        try:
            point = (float(stop["latitude"]), float(stop["longitude"]))
        except (TypeError, ValueError):
            print(f"  {position:>3} {stop_id} {stop['stop_name']:<26} "
                  f"no coordinates")
            previous = None
            continue

        gap = ""
        if previous is not None:
            distance = metres(previous, point)
            # Consecutive stops on a city bus route sit a few hundred
            # metres apart. Much more than that is worth a second look.
            flag = "  <-- large jump" if distance > 3000 else ""
            gap = f"{distance:>7.0f} m{flag}"

        print(f"  {position:>3} {stop_id} {stop['stop_name']:<26} "
              f"{point[0]:.6f}, {point[1]:.6f}  {gap}")

        previous = point

    return 0


if __name__ == "__main__":
    sys.exit(main())