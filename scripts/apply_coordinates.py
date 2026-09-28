"""
Transit AI - Write approved coordinates into stops.csv.

Reads data/review/geocode_candidates.csv and copies across only the rows
marked approved. Everything else is left alone, so an unreviewed guess
can never reach the dataset.

stops.csv is backed up first. Coordinates are the hardest part of this
dataset to rebuild, so the file is never overwritten without a copy.

    cd backend
    python scripts/apply_coordinates.py
"""

import csv
import os
import shutil
import sys
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
REVIEW_DIR = os.path.join(DATA_DIR, "review")
BACKUP_DIR = os.path.join(DATA_DIR, "backup")

LAT_MIN, LAT_MAX = 31.20, 31.80
LON_MIN, LON_MAX = 74.00, 74.70

APPROVED = {"y", "yes", "1", "true", "ok"}


def valid_point(lat_text, lon_text):
    """Returns (lat, lon) or None. Rejects anything outside Lahore."""
    try:
        lat = float(lat_text)
        lon = float(lon_text)
    except (TypeError, ValueError):
        return None

    if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
        return None

    return lat, lon


def main():
    review_path = os.path.join(REVIEW_DIR, "geocode_candidates.csv")
    stops_path = os.path.join(DATA_DIR, "stops.csv")

    if not os.path.exists(review_path):
        print(f"Not found: {review_path}")
        print("Run scripts/geocode_stops.py first.")
        return 1

    with open(review_path, "r", encoding="utf-8-sig", newline="") as handle:
        review = list(csv.DictReader(handle))

    accepted = {}
    rejected = 0
    unreviewed = 0

    for row in review:
        if str(row.get("approved", "")).strip().lower() not in APPROVED:
            unreviewed += 1
            continue

        point = valid_point(row.get("latitude"), row.get("longitude"))

        if point is None:
            # Approved but the numbers are missing or outside Lahore.
            # Refusing it is the whole point of this check.
            print(f"  rejected {row['stop_id']} {row['stop_name']}: "
                  f"coordinates are not valid for Lahore "
                  f"({row.get('latitude')}, {row.get('longitude')})")
            rejected += 1
            continue

        accepted[row["stop_id"]] = point

    print(f"{len(review)} candidate rows")
    print(f"  approved and valid : {len(accepted)}")
    print(f"  approved but bad   : {rejected}")
    print(f"  not reviewed yet   : {unreviewed}")

    if not accepted:
        print()
        print("Nothing to apply. Mark rows with 'y' in the approved column.")
        return 0

    with open(stops_path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        stops = list(reader)

    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"stops_{stamp}.csv")
    shutil.copy2(stops_path, backup_path)
    print()
    print(f"Backed up to {backup_path}")

    updated = 0
    for stop in stops:
        point = accepted.get(stop["stop_id"])
        if point is None:
            continue
        stop["latitude"] = f"{point[0]:.6f}"
        stop["longitude"] = f"{point[1]:.6f}"
        updated += 1

    with open(stops_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(stops)

    still_empty = sum(
        1 for s in stops
        if not str(s.get("latitude", "")).strip()
    )

    print(f"Updated {updated} stop(s) in stops.csv")
    print(f"{still_empty} stop(s) still have no coordinates")
    print()
    print("NEXT:")
    print("  python scripts/audit_data.py     check what changed")
    print("  python database.py               reload the database")

    return 0


if __name__ == "__main__":
    sys.exit(main())