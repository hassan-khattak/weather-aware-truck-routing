"""Encoded polyline format (precision 5), as `@mapbox/polyline` decodes it in the browser.

Order is (latitude, longitude), matching the rest of the backend.
"""

from collections.abc import Sequence

from core.models import Point

_PRECISION = 1e5


def _encode_number(value: int) -> str:
    value = ~(value << 1) if value < 0 else value << 1
    chars = []
    while value >= 0x20:
        chars.append(chr((0x20 | (value & 0x1F)) + 63))
        value >>= 5
    chars.append(chr(value + 63))
    return "".join(chars)


def encode(points: Sequence[Point]) -> str:
    encoded: list[str] = []
    last_lat = last_lon = 0
    for lat, lon in points:
        lat_i, lon_i = round(lat * _PRECISION), round(lon * _PRECISION)
        encoded.append(_encode_number(lat_i - last_lat))
        encoded.append(_encode_number(lon_i - last_lon))
        last_lat, last_lon = lat_i, lon_i
    return "".join(encoded)


def decode(text: str) -> list[Point]:
    points: list[Point] = []
    index = lat = lon = 0
    while index < len(text):
        deltas = []
        for _ in range(2):
            shift = result = 0
            while True:
                byte = ord(text[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        lat += deltas[0]
        lon += deltas[1]
        points.append((lat / _PRECISION, lon / _PRECISION))
    return points
