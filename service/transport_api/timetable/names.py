"""Text and modes, shared by the importer and the routes that query its tables."""

import re
import unicodedata

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
