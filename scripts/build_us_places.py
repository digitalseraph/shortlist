"""Build shortlist/data/us_places.txt from GeoNames cities1000.

    curl -O https://download.geonames.org/export/dump/cities1000.zip
    python scripts/build_us_places.py cities1000.zip

Writes one "City, ST" per line, largest population first. GeoNames data is
CC BY 4.0 (https://www.geonames.org/).
"""

from __future__ import annotations

import csv
import io
import sys
import zipfile
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "shortlist" / "data" / "us_places.txt"
# Column positions in the GeoNames dump format.
_NAME, _FEATURE_CODE, _COUNTRY, _ADMIN1, _POPULATION = 1, 7, 8, 10, 14


def main(zip_path: str) -> None:
    best: dict[str, int] = {}
    with zipfile.ZipFile(zip_path) as zf, zf.open("cities1000.txt") as raw:
        rows = csv.reader(io.TextIOWrapper(raw, "utf-8"), delimiter="\t", quoting=csv.QUOTE_NONE)
        for row in rows:
            # PPLQ marks an abandoned place.
            if row[_COUNTRY] != "US" or row[_FEATURE_CODE] == "PPLQ":
                continue
            place = f"{row[_NAME]}, {row[_ADMIN1]}"
            best[place] = max(best.get(place, 0), int(row[_POPULATION] or 0))
    ordered = sorted(best, key=lambda p: (-best[p], p))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(ordered) + "\n", encoding="utf-8")
    print(f"wrote {len(ordered)} places to {OUT}")


if __name__ == "__main__":
    main(sys.argv[1])
