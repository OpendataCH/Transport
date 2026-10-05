"""Text and modes, shared by the importer and the routes that query its tables."""

import csv
import re
import unicodedata
from functools import cache
from importlib import resources

# Swiss stop names abbreviate where people do not: Ste-Croix, St-Cergue.
ABBREVIATIONS = [(re.compile(r"\bsainte\b"), "ste"), (re.compile(r"\b(saint|sankt)\b"), "st")]


def normalize(name: str) -> str:
    """What a name is searched by: lower case, accents and punctuation off.

    Punctuation goes because people and timetables place it differently -
    `Luzern Verkehrshaus` is the station, `Luzern, Verkehrshaus/Lido` the bus
    stop, and someone typing `Luzern, Verkehrshaus` means the first. Done in
    Python on both sides rather than with Postgres' `unaccent`, which is not
    immutable and so cannot back an index.
    """
    decomposed = unicodedata.normalize("NFKD", name)
    bare = "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()
    bare = re.sub(r"[,./()\-–'’]", " ", bare)
    for pattern, short in ABBREVIATIONS:
        bare = pattern.sub(short, bare)
    return " ".join(bare.split())


def mode_of(route_type: int) -> str | None:
    """The five means of transport /v1 knows, from a GTFS route type.

    The Swiss feed uses the extended types: 100-117 rail, 401 metro, 700-716
    bus, 900 tram, 1000 ship, 1300-1400 aerial lifts and funiculars. Basic
    types (0-7) are mapped as well, for a feed that uses them.
    """
    if 100 <= route_type < 200 or route_type in (1, 2):
        return "train"
    if 400 <= route_type < 500 or 900 <= route_type < 1000 or route_type == 0:
        return "tram"
    if 700 <= route_type < 800 or 200 <= route_type < 300 or route_type in (3, 1500):
        return "bus"
    if 1000 <= route_type < 1300 or route_type == 4:
        return "ship"
    if 1300 <= route_type < 1500 or route_type in (5, 6, 7):
        return "cableway"
    return None


@cache
def operators() -> tuple[dict[str, str], dict[str, str]]:
    """The names /v1 gives operators, by GTFS agency_id and by full name.

    GTFS has "BLS AG (bls)", search.ch "BLS-bls": the long name of HAFAS.
    operators.csv is written from HRDF by tools/operator_names.py.
    """
    by_id, by_full_name = {}, {}
    text = resources.files(__package__).joinpath("operators.csv").read_text(encoding="utf-8")
    for row in csv.DictReader(text.splitlines()):
        by_id[row["agency_id"]] = row["name"]
        by_full_name.setdefault(row["full_name"], row["name"])
    return by_id, by_full_name


def operator_name(agency_id: str | None, full_name: str | None) -> str | None:
    """The operator as /v1 names it; the GTFS name when HRDF does not know it."""
    by_id, by_full_name = operators()
    return by_id.get(agency_id or "") or by_full_name.get(full_name or "") or full_name
