"""Open-Meteo adapter against a real response (no live calls)."""

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from providers.base import GridPoint, ProviderError, ProviderUnavailable, WeatherProvider
from providers.openmeteo import OpenMeteoWeatherProvider

FIXTURE = Path(__file__).resolve().parents[2] / "providers/fixtures/openmeteo_two_points.json"
URL = "https://api.open-meteo.com/v1/forecast"
START = datetime(2026, 11, 23, 0, 0, tzinfo=UTC)
END = datetime(2026, 11, 25, 23, 0, tzinfo=UTC)
POINTS = [GridPoint(35.2, -101.8), GridPoint(46.8, -100.7)]


@pytest.fixture
def payload() -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads(FIXTURE.read_text())
    return data


def provider(batch_size: int = 200) -> OpenMeteoWeatherProvider:
    return OpenMeteoWeatherProvider(batch_size=batch_size)


def location(hours: int = 3, **overrides: list[float | None]) -> dict[str, Any]:
    """A minimal location object shaped like the real response."""
    times = [f"2026-11-23T{h:02d}:00" for h in range(hours)]
    zeros = [0.0] * hours
    hourly: dict[str, Any] = {
        "time": times,
        "wind_speed_10m": [10.0] * hours,
        "wind_gusts_10m": [15.0] * hours,
        "rain": list(zeros),
        "showers": list(zeros),
        "snowfall": list(zeros),
        "precipitation": list(zeros),
    }
    hourly.update(overrides)
    return {"hourly": hourly}


def test_the_adapter_satisfies_the_weather_provider_protocol() -> None:
    adapter: WeatherProvider = provider()
    assert adapter is not None


@respx.mock
def test_parses_a_real_response_into_one_series_per_point(payload: list[dict[str, Any]]) -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, json=payload))
    result = provider().hourly(POINTS, START, END)

    assert set(result) == set(POINTS)
    series = result[POINTS[0]]
    assert series.start_utc == START
    assert len(series.wind_mph) == 72
    assert series.wind_mph[:2] == (5.2, 4.0)
    assert series.gust_mph[0] == 8.3
    assert result[POINTS[1]].wind_mph != series.wind_mph  # mapped by request order


@respx.mock
def test_requests_imperial_units_in_gmt_with_the_agreed_variables(
    payload: list[dict[str, Any]],
) -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(200, json=payload))
    provider().hourly(POINTS, START, END)

    params = dict(route.calls.last.request.url.params)
    assert params["latitude"] == "35.2,46.8"
    assert params["longitude"] == "-101.8,-100.7"
    assert params["hourly"] == "wind_speed_10m,wind_gusts_10m,rain,showers,snowfall"
    assert params["wind_speed_unit"] == "mph"
    assert params["precipitation_unit"] == "inch"
    assert params["timezone"] == "GMT"
    assert params["start_date"] == "2026-11-23"
    assert params["end_date"] == "2026-11-25"
    assert "precipitation" not in params["hourly"].split(",")


@respx.mock
def test_rain_is_rain_plus_showers_and_never_the_precipitation_total() -> None:
    item = location(rain=[0.1, 0.0, 0.0], showers=[0.15, 0.0, 0.0], precipitation=[9.0, 9.0, 9.0])
    respx.get(URL).mock(return_value=httpx.Response(200, json=item))
    series = provider().hourly(POINTS[:1], START, END)[POINTS[0]]
    assert series.rain_in_hr == (0.25, 0.0, 0.0)


@respx.mock
def test_snow_is_the_snowfall_depth_not_water_equivalent() -> None:
    item = location(snowfall=[0.0, 1.5, 0.0], precipitation=[0.0, 0.15, 0.0])
    respx.get(URL).mock(return_value=httpx.Response(200, json=item))
    series = provider().hourly(POINTS[:1], START, END)[POINTS[0]]
    assert series.snow_in_hr == (0.0, 1.5, 0.0)
    assert series.rain_in_hr == (0.0, 0.0, 0.0)


@respx.mock
def test_values_are_rounded_on_ingest_so_float_noise_cannot_cross_a_threshold() -> None:
    item = location(
        wind_speed_10m=[12.345, 34.9999999, 10.0],
        rain=[0.1, 0.0, 0.0],
        showers=[0.1499999, 0.0, 0.0],
        snowfall=[0.4999999, 0.0, 0.0],
    )
    respx.get(URL).mock(return_value=httpx.Response(200, json=item))
    series = provider().hourly(POINTS[:1], START, END)[POINTS[0]]
    assert series.wind_mph[:2] == (12.3, 35.0)
    assert series.rain_in_hr[0] == 0.25  # exactly the High boundary, not 0.2499999
    assert series.snow_in_hr[0] == 0.5


@respx.mock
def test_missing_values_stay_missing_and_never_become_zero() -> None:
    item = location(
        wind_speed_10m=[None, 10.0, 10.0],
        rain=[0.0, None, 0.0],
        showers=[0.0, 0.0, None],
        snowfall=[0.0, 0.0, None],
    )
    respx.get(URL).mock(return_value=httpx.Response(200, json=item))
    series = provider().hourly(POINTS[:1], START, END)[POINTS[0]]
    assert series.wind_mph == (None, 10.0, 10.0)
    assert series.rain_in_hr == (0.0, None, None)  # either part missing -> unknown
    assert series.snow_in_hr == (0.0, 0.0, None)


@respx.mock
def test_a_single_location_comes_back_as_an_object_not_a_list() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, json=location()))
    result = provider().hourly(POINTS[:1], START, END)
    assert list(result) == [POINTS[0]]


@respx.mock
def test_large_requests_are_split_into_batches() -> None:
    points = [GridPoint(30 + i / 10, -100.0) for i in range(450)]

    def respond(request: httpx.Request) -> httpx.Response:
        count = len(request.url.params["latitude"].split(","))
        return httpx.Response(200, json=[location() for _ in range(count)])

    route = respx.get(URL).mock(side_effect=respond)
    result = provider(batch_size=200).hourly(points, START, END)

    sizes = [len(c.request.url.params["latitude"].split(",")) for c in route.calls]
    assert sizes == [200, 200, 50]
    assert len(result) == 450


@respx.mock
def test_no_points_means_no_request() -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(200, json=[]))
    assert provider().hourly([], START, END) == {}
    assert route.call_count == 0


@respx.mock
@pytest.mark.parametrize("status", [429, 500, 503])
def test_rate_limits_and_server_errors_are_unavailable(status: int) -> None:
    body = {"error": True, "reason": "Minutely API request limit exceeded."}
    respx.get(URL).mock(return_value=httpx.Response(status, json=body))
    with pytest.raises(ProviderUnavailable):
        provider().hourly(POINTS, START, END)


@respx.mock
def test_bad_requests_surface_the_reason_as_a_provider_error() -> None:
    body = {"error": True, "reason": "Latitude must be in range of -90 to 90°."}
    respx.get(URL).mock(return_value=httpx.Response(400, json=body))
    with pytest.raises(ProviderError, match="Latitude must be in range"):
        provider().hourly(POINTS, START, END)


@respx.mock
def test_network_failures_are_unavailable() -> None:
    respx.get(URL).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(ProviderUnavailable):
        provider().hourly(POINTS, START, END)


@respx.mock
def test_a_location_count_mismatch_is_an_error(payload: list[dict[str, Any]]) -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, json=payload[:1]))
    with pytest.raises(ProviderError, match="number of locations"):
        provider().hourly(POINTS, START, END)


@respx.mock
def test_a_non_hourly_series_is_rejected(payload: list[dict[str, Any]]) -> None:
    broken = copy.deepcopy(payload)
    broken[0]["hourly"]["time"][1] = "2026-11-23T03:00"
    respx.get(URL).mock(return_value=httpx.Response(200, json=broken))
    with pytest.raises(ProviderError, match="hourly"):
        provider().hourly(POINTS, START, END)


def test_naive_datetimes_are_rejected() -> None:
    with pytest.raises(ValueError, match="timezone"):
        provider().hourly(POINTS, datetime(2026, 11, 23), END)  # noqa: DTZ001
