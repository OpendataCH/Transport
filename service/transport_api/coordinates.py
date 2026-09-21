"""The coordinate arithmetic of /v1, reproduced exactly.

search.ch answers with both the Swiss grid values (`x`, `y`) and WGS84 degrees
(`lat`, `lon`). The PHP application ignores the degrees and computes its own
from the grid with the swisstopo approximation below, which lands about a metre
from the upstream figure. Using the better numbers would mean /v2 and /v1
disagree in the sixth decimal of every coordinate, and the whole point of the
differential test is that they agree everywhere. So the old arithmetic stays.

The formula is the official approximate one, ported from
https://github.com/ValentinMinder/Swisstopo-WGS84-LV03 (MIT, Copyright (c) 2014
Federal Office of Topography swisstopo, Wabern, CH) - the same source the PHP
code names.
"""

from decimal import ROUND_HALF_UP, Decimal


def lv03_to_wgs84(easting: int, northing: int) -> tuple[float, float]:
    """Swiss grid to (latitude, longitude) in degrees.

    The variables are named after the fields they come from, as in the PHP:
    what search.ch calls `x` is the easting, `y` the northing.
    """
    y = (northing - 200000) / 1000000
    x = (easting - 600000) / 1000000

    lat = (
        16.9023892
        + 3.238272 * y
        - 0.270978 * x**2
        - 0.002528 * y**2
        - 0.0447 * x**2 * y
        - 0.0140 * y**3
    )

    lon = 2.6779094 + 4.728982 * x + 0.791484 * x * y + 0.1306 * x * y**2 - 0.0436 * x**3

    return _round6(lat * 100 / 36), _round6(lon * 100 / 36)


def _round6(value: float) -> float:
    """Six decimals, ties away from zero.

    PHP's round() rounds halves away from zero; Python's built-in round() sends
    them to the nearest even digit. On a coordinate that is one unit in the
    sixth decimal - a tenth of a millimetre on the ground and a failed
    comparison in the differential test.
    """
    return float(Decimal(repr(value)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))
