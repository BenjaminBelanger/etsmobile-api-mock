"""Applies calendar modifications (skipped days, replacements) for the active session."""

import json
from datetime import date, timedelta

from ._paths import SEED
from .resource_specs import COURSE_ACTIVITIES, REPLACED_DAYS

_SCENARIOS: dict = {}

VALID_SCENARIOS: set[str] = set()


def reload_scenarios() -> dict:
    scenarios = json.loads((SEED / "scenarios.json").read_text(encoding="utf-8"))
    _SCENARIOS.clear()
    _SCENARIOS.update(scenarios)
    VALID_SCENARIOS.clear()
    VALID_SCENARIOS.update(scenarios.keys())
    _scenario_cache.clear()
    return _SCENARIOS


def get_valid_scenarios() -> set[str]:
    return VALID_SCENARIOS


def _next_weekday_from(start: date, target_isoweekday: int) -> date:
    current = start
    while current.isoweekday() != target_isoweekday:
        current += timedelta(days=1)
    return current


def _resolve_date(rule: dict) -> date:
    today = date.today()
    rule_type = rule["rule"]

    if rule_type == "absolute":
        return date.fromisoformat(rule["date"])

    if rule_type == "relative_days":
        return today + timedelta(days=rule["days"])

    if rule_type == "next_weekday":
        weekday = rule["weekday"]
        offset = rule.get("offset", 0)
        anchor = _next_weekday_from(today, weekday)
        return anchor + timedelta(weeks=offset)

    if rule_type == "week_of":
        weekday = rule["weekday"]
        offset = rule.get("offset", 0)
        anchor = _next_weekday_from(today, weekday) + timedelta(weeks=offset)
        monday = anchor - timedelta(days=anchor.isoweekday() - 1)
        return monday

    raise ValueError(f"Unknown date rule: {rule_type}")


def _resolve_skip_dates(scenario: dict) -> set[date]:
    skip: set[date] = set()
    for rule in scenario.get("skipDates", []):
        if rule["rule"] == "week_of":
            monday = _resolve_date(rule)
            skip.update(monday + timedelta(days=i) for i in range(5))
        else:
            skip.add(_resolve_date(rule))
    return skip


def _resolve_replaced_days(scenario: dict) -> list[dict]:
    entries = []
    for replaced_day in scenario.get("replacedDays", []):
        origin = _resolve_date(replaced_day["origin"])
        replacement = _resolve_date(replaced_day["replacement"])
        entries.append(
            {
                "dateOrigine": origin.isoformat(),
                "dateRemplacement": replacement.isoformat(),
                "description": replaced_day.get("description", ""),
            }
        )
    return entries


_scenario_cache: dict[tuple[str, str], tuple[set[date], list[dict]]] = {}


def _resolve_and_cache(scenario_name: str) -> tuple[set[date], list[dict]]:
    cache_key = (scenario_name, date.today().isoformat())
    if cache_key not in _scenario_cache:
        scenario = _SCENARIOS.get(scenario_name, {})
        _scenario_cache[cache_key] = (
            _resolve_skip_dates(scenario),
            _resolve_replaced_days(scenario),
        )
    return _scenario_cache[cache_key]


def apply_scenario(scenario_name: str, active_session: str, filename: str, data):
    skip_dates, replaced_days = _resolve_and_cache(scenario_name)

    if filename == COURSE_ACTIVITIES.filename and skip_dates:
        if active_session in data:
            data[active_session] = [
                act
                for act in data[active_session]
                if date.fromisoformat(act["dateDebut"][:10]) not in skip_dates
            ]

    if filename == REPLACED_DAYS.filename and replaced_days:
        session_list = data.setdefault(active_session, [])
        session_list.extend(replaced_days)

    return data


reload_scenarios()
