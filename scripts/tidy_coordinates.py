"""
Transit AI - Tidy coordinate formatting in stops.csv.

Two things creep in when coordinates are pasted from a map:

  a space after the comma, which makes the value a string with
  whitespace rather than a number

  fifteen decimal places, which claims centimetre precision for a
  bus stop that occupies several metres of pavement

Neither breaks the app today. Both are the kind of thing that breaks
something six weeks from now, in a CAST or a string comparison, and is
hard to trace back.

Six decimal places is about 11 cm at this latitude - far more than a
stop location deserves, and the format the rest of the file already uses.

    python scripts/tidy_coordinates.py
"""

import csv
import os
import shutil
import sys
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
BACKUP_DIR = os.path.join(DATA_DIR, "backup")


def main():
    stops_path = os.path.join(DATA_DIR, "stops.csv")

    with open(stops_path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        stops = list(reader)

    changed = []

    for stop in stops:
        for field in ("latitude", "longitude"):
            raw = stop.get(field, "")

            if not str(raw).strip():
                continue

            try:
                value = float(raw)
            except (TypeError, ValueError):
                print(f"  cannot parse {stop['stop_id']} {field}: {raw!r}")
                continue

            tidy = f"{value:.6f}"

            if tidy != raw:
                changed.append((stop["stop_id"], field, raw, tidy))
                stop[field] = tidy

    if not changed:
        print("Nothing to tidy.")
        return 0

    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(stops_path, os.path.join(BACKUP_DIR, f"stops_{stamp}.csv"))

    with open(stops_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(stops)

    print(f"Tidied {len(changed)} value(s):")
    for stop_id, field, before, after in changed[:15]:
        print(f"  {stop_id} {field:<10} {before!r} -> {after}")
    if len(changed) > 15:
        print(f"  ... and {len(changed) - 15} more")

    return 0


if __name__ == "__main__":
    sys.exit(main())