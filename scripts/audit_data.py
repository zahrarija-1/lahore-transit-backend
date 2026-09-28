"""
Transit AI - Dataset audit.

Run this before and after every data fix. It reports what is broken and
what is clean, so progress is measurable rather than a guess.

The output also belongs in the FYP report: a dataset chapter that says
"318 stops, 0 missing coordinates, 0 orphan references, verified by
scripts/audit_data.py" is far stronger than "we cleaned the data".

    cd backend
    python scripts/audit_data.py

Plain ASCII only in the output. Windows consoles default to cp1252, which
cannot encode arrows or dashes, and the script would crash halfway through
a report about broken data.
"""

import csv
import os
import sys
from collections import Counter, defaultdict

# Lahore's bounding box. Anything outside this is a data-entry error,
# not a real stop. Generous on purpose - the city keeps growing.
LAT_MIN, LAT_MAX = 31.20, 31.80
LON_MIN, LON_MAX = 74.00, 74.70

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

problems = 0
warnings = 0


def head(title):
    print()
    print("=" * 64)
    print(title)
    print("=" * 64)


def ok(message):
    print(f"  [ok]   {message}")


def bad(message):
    global problems
    problems += 1
    print(f"  [FAIL] {message}")


def warn(message):
    global warnings
    warnings += 1
    print(f"  [warn] {message}")


def load(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        bad(f"{filename} is missing")
        return []
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def is_number(value):
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def main():
    stops = load("stops.csv")
    routes = load("routes.csv")
    route_stops = load("route_stops.csv")

    # ------------------------------------------------------------------
    head("STOPS")
    # ------------------------------------------------------------------
    print(f"  {len(stops)} rows")

    no_coords = [s for s in stops
                 if not is_number(s.get("latitude"))
                 or not is_number(s.get("longitude"))]

    if no_coords:
        bad(f"{len(no_coords)} stops have no usable coordinates")
        print("         -> the map, nearby stops and every distance")
        print("            calculation are blocked until these are filled")
        for s in no_coords[:3]:
            print(f"            {s['stop_id']}  {s['stop_name']}")
        if len(no_coords) > 3:
            print(f"            ... and {len(no_coords) - 3} more")
    else:
        ok("every stop has coordinates")

    out_of_bounds = [
        s for s in stops
        if is_number(s.get("latitude")) and is_number(s.get("longitude"))
        and not (LAT_MIN <= float(s["latitude"]) <= LAT_MAX
                 and LON_MIN <= float(s["longitude"]) <= LON_MAX)
    ]
    if out_of_bounds:
        bad(f"{len(out_of_bounds)} stops sit outside Lahore")
        for s in out_of_bounds[:5]:
            print(f"           {s['stop_id']} {s['stop_name']}: "
                  f"{s['latitude']}, {s['longitude']}")
    elif not no_coords:
        ok("all coordinates fall inside Lahore")

    # Two stops at the same point are usually one stop entered twice.
    located = defaultdict(list)
    for s in stops:
        if is_number(s.get("latitude")) and is_number(s.get("longitude")):
            key = (round(float(s["latitude"]), 5),
                   round(float(s["longitude"]), 5))
            located[key].append(s["stop_name"])
    stacked = {k: v for k, v in located.items() if len(v) > 1}
    if stacked:
        warn(f"{len(stacked)} coordinate(s) shared by more than one stop")
        for names in list(stacked.values())[:5]:
            print(f"           {' / '.join(names)}")

    ids = Counter(s["stop_id"] for s in stops)
    dupe_ids = [i for i, n in ids.items() if n > 1]
    if dupe_ids:
        bad(f"{len(dupe_ids)} duplicate stop_id(s): {dupe_ids[:5]}")
    else:
        ok("stop_id values are unique")

    blank_names = [s for s in stops if not s.get("stop_name", "").strip()]
    if blank_names:
        bad(f"{len(blank_names)} stops have no name")
    else:
        ok("every stop has a name")

    # ------------------------------------------------------------------
    head("ROUTES")
    # ------------------------------------------------------------------
    print(f"  {len(routes)} rows")

    by_route = defaultdict(int)
    for rs in route_stops:
        by_route[rs["route_id"]] += 1

    empty = [r for r in routes if by_route[r["route_id"]] == 0]
    if empty:
        bad(f"{len(empty)} route(s) have no stops at all")
        for r in empty:
            print(f"           {r['route_id']} ({r.get('route_type')}): "
                  f"{r.get('origin')} to {r.get('destination')}, "
                  f"declares {r.get('stop_count')} stops")
    else:
        ok("every route has stops")

    mismatched = [
        r for r in routes
        if by_route[r["route_id"]] > 0
        and str(r.get("stop_count", "")).strip().isdigit()
        and int(r["stop_count"]) != by_route[r["route_id"]]
    ]
    if mismatched:
        bad(f"{len(mismatched)} route(s) where stop_count is wrong")
        for r in mismatched[:5]:
            print(f"           {r['route_id']}: says {r['stop_count']}, "
                  f"has {by_route[r['route_id']]}")
    else:
        ok("stop_count matches the actual stop rows")

    types = Counter(r.get("route_type", "?") for r in routes)
    print(f"  route types: {dict(types)}")

    # ------------------------------------------------------------------
    head("ROUTE_STOPS")
    # ------------------------------------------------------------------
    print(f"  {len(route_stops)} rows")

    stop_ids = {s["stop_id"] for s in stops}
    route_ids = {r["route_id"] for r in routes}

    bad_stop_ref = [rs for rs in route_stops if rs["stop_id"] not in stop_ids]
    bad_route_ref = [rs for rs in route_stops
                     if rs["route_id"] not in route_ids]

    if bad_stop_ref:
        bad(f"{len(bad_stop_ref)} row(s) point at a stop that does not exist")
    else:
        ok("every stop reference resolves")

    if bad_route_ref:
        bad(f"{len(bad_route_ref)} row(s) point at a route that does not exist")
    else:
        ok("every route reference resolves")

    used = {rs["stop_id"] for rs in route_stops}
    orphans = stop_ids - used
    if orphans:
        warn(f"{len(orphans)} stop(s) belong to no route")
    else:
        ok("every stop is used by at least one route")

    # A sequence that skips or repeats a number means the order is wrong,
    # and route order is what a journey is built from.
    seq_problems = []
    per_route = defaultdict(list)
    for rs in route_stops:
        if str(rs.get("stop_sequence", "")).strip().isdigit():
            per_route[rs["route_id"]].append(int(rs["stop_sequence"]))
    for route_id, seq in per_route.items():
        seq.sort()
        expected = list(range(seq[0], seq[0] + len(seq)))
        if seq != expected:
            seq_problems.append(route_id)
    if seq_problems:
        bad(f"{len(seq_problems)} route(s) have a broken stop_sequence: "
            f"{seq_problems[:5]}")
    else:
        ok("stop_sequence is continuous on every route")

    routes_at_stop = defaultdict(set)
    for rs in route_stops:
        routes_at_stop[rs["stop_id"]].add(rs["route_id"])
    interchange = [s for s, r in routes_at_stop.items() if len(r) > 1]
    print(f"  interchange stops (served by 2+ routes): {len(interchange)}")

    # ------------------------------------------------------------------
    head("SUMMARY")
    # ------------------------------------------------------------------
    if problems == 0 and warnings == 0:
        print("  Dataset is clean.")
    else:
        print(f"  {problems} problem(s), {warnings} warning(s)")
        print()
        print("  Problems block features. Warnings are worth a look but")
        print("  will not stop the app from running.")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())