"""Risk classification: thresholds, worst-of, then raise-only load rules.

Every number comes from rules.yaml (see core/rules.py); nothing is hard-coded here.
"""

from core.models import Classification, Level, Weather
from core.rules import Band, LoadRule, Rules


def _band_level(value: float, bands: list[Band]) -> Level:
    """Highest band whose lower bound the value reaches; otherwise LOW.

    A band with `inclusive` includes its boundary value; otherwise the value must exceed it.
    """
    level = Level.LOW
    for band in bands:
        reached = value > band.from_ or (band.inclusive and value == band.from_)
        if reached:
            level = max(level, Level.from_name(band.level))
    return level


def _load_rule_applies(rule: LoadRule, wind_mph: float, load_lb: float) -> bool:
    if wind_mph < rule.from_:
        return False
    if rule.to_exclusive is not None and wind_mph >= rule.to_exclusive:
        return False
    return rule.load_gt_lb is None or load_lb > rule.load_gt_lb


def _load_reason(rule: LoadRule, wind_mph: float, load_lb: float) -> str:
    label = Level.from_name(rule.level).label
    if rule.load_gt_lb is None:
        return f"Wind {wind_mph:g} mph ≥ {rule.from_:g} → {label}"
    top = f"{rule.to_exclusive - 1:g}" if rule.to_exclusive is not None else "+"
    return (
        f"Load {load_lb:,.0f} lb > {rule.load_gt_lb:,.0f} "
        f"with wind {rule.from_:g}–{top} mph → {label}"
    )


def classify(weather: Weather, load_lb: float, rules: Rules) -> Classification:
    """Classify one checkpoint. `load_lb` is the cargo weight as entered."""
    use_gusts = rules.classification.wind_source == "gust"
    wind = weather.gust_mph if use_gusts else weather.wind_mph
    wind_name = "Gust" if use_gusts else "Wind"

    conditions = (
        (wind_name, wind, "mph", _band_level(wind, rules.thresholds.wind_mph)),
        (
            "Rain",
            weather.rain_in_hr,
            "in/hr",
            _band_level(weather.rain_in_hr, rules.thresholds.rain_in_hr),
        ),
        (
            "Snow",
            weather.snow_in_hr,
            "in/hr",
            _band_level(weather.snow_in_hr, rules.thresholds.snow_in_hr),
        ),
    )
    base = max(level for *_, level in conditions)
    reasons = [
        f"{name} {value:g} {unit} → {level.label}"
        for name, value, unit, level in conditions
        if level > Level.LOW
    ]

    # Load rules only ever raise the level (never lower it), and only for wind.
    level = base
    for rule in rules.load_rules:
        rule_level = Level.from_name(rule.level)
        if rule_level > base and _load_rule_applies(rule, wind, load_lb):
            reasons.append(_load_reason(rule, wind, load_lb))
            level = max(level, rule_level)

    return Classification(level=level, reasons=tuple(reasons))
