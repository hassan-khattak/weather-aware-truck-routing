import pytest

from api.polyline import decode, encode

# The canonical example from Google's polyline documentation.
GOOGLE_POINTS = [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]
GOOGLE_ENCODED = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"


def assert_close(actual: list[tuple[float, float]], expected: list[tuple[float, float]]) -> None:
    assert len(actual) == len(expected)
    for got, want in zip(actual, expected, strict=True):
        assert got == pytest.approx(want, abs=1e-5)


def test_encodes_the_documented_example() -> None:
    assert encode(GOOGLE_POINTS) == GOOGLE_ENCODED


def test_decodes_the_documented_example() -> None:
    assert_close(decode(GOOGLE_ENCODED), GOOGLE_POINTS)


def test_an_empty_route_is_an_empty_string() -> None:
    assert encode([]) == ""
    assert decode("") == []


@pytest.mark.parametrize(
    "points",
    [
        [(0.0, 0.0)],
        [(-33.8688, 151.2093), (-33.87, 151.21)],
        [(47.6062, -122.3321), (41.8781, -87.6298), (32.7767, -96.797)],
        [(35.00001, -100.00001), (35.00002, -100.00003)],
    ],
)
def test_round_trip_is_accurate_to_five_decimals(points: list[tuple[float, float]]) -> None:
    assert_close(decode(encode(points)), points)
