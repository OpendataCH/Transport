"""Write the operator names /v1 shows from the national HRDF timetable.

    python tools/operator_names.py oev_sammlung_ch_hrdf_5_40_41_2026.zip

GTFS names an operator in full ("BLS AG (bls)"); search.ch, and so /v1, shows
the long name of HAFAS ("BLS-bls"). HRDF's BETRIEB file has both and the
administration number GTFS uses as agency_id (`00071 : 000033`). The result
goes to transport_api/timetable/operators.csv, which the importer reads;
operators change rarely, so running this once a timetable year is enough.
"""

import csv
import re
import sys
import zipfile
from pathlib import Path

TARGET = Path(__file__).resolve().parent.parent / "transport_api" / "timetable" / "operators.csv"

NAMES = re.compile(r'^(\d{5}) K "(.*?)" L "(.*?)" V "(.*?)"')
ADMINISTRATIONS = re.compile(r"^(\d{5}) : (.+)$")


def main(hrdf: str) -> int:
    with zipfile.ZipFile(hrdf) as archive:
        text = archive.read("BETRIEB_DE").decode("utf-8")
    names, rows = {}, {}
    for line in text.splitlines():
        if match := NAMES.match(line):
            names[match[1]] = (match[3], match[4])
        elif match := ADMINISTRATIONS.match(line):
            for administration in match[2].split():
                long_name, full_name = names[match[1]]
                rows.setdefault(administration.lstrip("0"), (long_name, full_name))
    with TARGET.open("w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow(["agency_id", "name", "full_name"])
        for agency, (long_name, full_name) in sorted(rows.items(), key=lambda r: (len(r[0]), r[0])):
            writer.writerow([agency, long_name, full_name])
    print(f"{len(rows)} operators -> {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
