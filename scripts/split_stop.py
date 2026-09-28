"""
Transit AI - Split one stop_id that covers two different places.

Ghazi Chowk and Sabzi Mandi each appear at two points kilometres apart,
and each point fits its own routes precisely. They are not bad readings:
two real places share one stop_id.

Averaging them would invent a third place between the two. Deleting one
would silently move several routes. The fix is to give the second place
its own stop_id and repoint the routes that use it.

    cd backend
    python scripts/split_stop.py STOP0041 FRT13 31.436390 74.291350 "Ghazi Chowk (Township)"

Arguments:
    stop_id    the id currently covering both places
    routes     comma-separated routes that belong to the NEW stop
    latitude   the new stop's coordinates
    longitude
    name       what to call the new stop

The original stop keeps its id, its name and the routes not listed.
Backs up all three CSVs first.
"""

import csv
import os
import shutil
import sys
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
BACKUP_DIR = os.path.join(DATA_DIR, "backup")

LAT_MIN, LAT_MAX = 31.20, 31.80
LON_MIN, LON_MAX = 74.00, 74.70


def read_csv(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames, list(reader)


def write_csv(path, fieldnames, rows):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def next_stop_id(stops):
    """First unused STOPnnnn, so ids stay in one sequence."""
    used = set()
    for stop in stops:
        value = stop["stop_id"].strip()
        if value.startswith("STOP") and value[4:].isdigit():
            used.add(int(value[4:]))
    return f"STOP{max(used) + 1:04d}" if used else "STOP0001"


def main():
    if len(sys.argv) < 6:
        print(__doc__)
        return 1

    old_id = sys.argv[1].strip()
    move_routes = {r.strip() for r in sys.argv[2].split(",") if r.strip()}
    new_name = sys.argv[5].strip()

    try:
        latitude = float(sys.argv[3])
        longitude = float(sys.argv[4])
    except ValueError:
        print("Latitude and longitude must be numbers.")
        return 1

    if not (LAT_MIN <= latitude <= LAT_MAX
            and LON_MIN <= longitude <= LON_MAX):
        print(f"{latitude}, {longitude} is outside Lahore. Refusing.")
        return 1

    stops_path = os.path.join(DATA_DIR, "stops.csv")
    route_stops_path = os.path.join(DATA_DIR, "route_stops.csv")

    stops_fields, stops = read_csv(stops_path)
    rs_fields, route_stops = read_csv(route_stops_path)

    original = next((s for s in stops if s["stop_id"] == old_id), None)
    if original is None:
        print(f"No stop with id {old_id}.")
        return 1

    affected = [r for r in route_stops
                if r["stop_id"] == old_id and r["route_id"] in move_routes]

    if not affected:
        routes_here = sorted({r["route_id"] for r in route_stops
                              if r["stop_id"] == old_id})
        print(f"{old_id} is not used by {', '.join(sorted(move_routes))}.")
        print(f"It is used by: {', '.join(routes_here)}")
        return 1

    staying = sorted({r["route_id"] for r in route_stops
                      if r["stop_id"] == old_id
                      and r["route_id"] not in move_routes})

    if not staying:
        print(f"Every route using {old_id} is in the move list, so there")
        print("would be nothing left behind. Change its coordinates")
        print("instead of splitting it.")
        return 1

    new_id = next_stop_id(stops)

    print(f"Splitting {old_id} '{original['stop_name']}'")
    print()
    print(f"  stays as {old_id}: {', '.join(staying)}")
    print(f"  moves to {new_id}: {', '.join(sorted(move_routes))}")
    print(f"  new stop: {new_name} at {latitude:.6f}, {longitude:.6f}")
    print(f"  rows to repoint: {len(affected)}")

    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for path in (stops_path, route_stops_path):
        name = os.path.basename(path).replace(".csv", "")
        shutil.copy2(path, os.path.join(BACKUP_DIR, f"{name}_{stamp}.csv"))
    print()
    print(f"Backed up to {BACKUP_DIR}")

    # The new stop copies everything from the original except the three
    # fields that make it a different place.
    new_stop = dict(original)
    new_stop["stop_id"] = new_id
    new_stop["stop_name"] = new_name
    new_stop["latitude"] = f"{latitude:.6f}"
    new_stop["longitude"] = f"{longitude:.6f}"

    # Insert next to the original rather than at the end, so the file
    # stays readable.
    index = stops.index(original)
    stops.insert(index + 1, new_stop)

    for row in route_stops:
        if row["stop_id"] == old_id and row["route_id"] in move_routes:
            row["stop_id"] = new_id
            if "stop_name" in row:
                row["stop_name"] = new_name

    write_csv(stops_path, stops_fields, stops)
    write_csv(route_stops_path, rs_fields, route_stops)

    print()
    print(f"Done. {len(stops)} stops in stops.csv.")
    print()
    print("NEXT:")
    print("  python scripts/audit_data.py")
    print("  python database.py")

    return 0


if __name__ == "__main__":
    sys.exit(main())