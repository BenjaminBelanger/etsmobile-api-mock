import json
from datetime import date, timedelta

from . import sessions
from ._paths import SEED
from .resource_specs import REPLACED_DAYS

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


def _course_window(session_code: str) -> tuple[date, date] | None:
    for entry in sessions.get_raw_sessions():
        if entry.get("abrege") != session_code:
            continue
        start = entry.get("dateDebut")
        end = entry.get("dateFinCours") or entry.get("dateFin")
        if not start or not end:
            return None
        return date.fromisoformat(start), date.fromisoformat(end)
    return None


def _add_override(course: dict, entry: dict) -> None:
    overrides = course.setdefault("occurrenceOverrides", [])
    if not any(
        o.get("block") == entry["block"] and o.get("date") == entry["date"]
        for o in overrides
    ):
        overrides.append(entry)


def _scheduled_courses(
    session_code: str, courses: list[dict]
) -> list[tuple[dict, list[dict]]]:
    return [
        (course, [course["schedule"]] + course.get("extraActivities", []))
        for course in courses
        if course.get("session") == session_code and course.get("schedule") is not None
    ]


def _parse_moves(entries: list[dict]) -> list[tuple[date, date]]:
    return [
        (
            date.fromisoformat(entry["dateOrigine"]),
            date.fromisoformat(entry["dateRemplacement"]),
        )
        for entry in entries
    ]


def _apply_swaps(
    session_code: str, courses: list[dict], moves: list[tuple[date, date]]
) -> None:
    window = _course_window(session_code)

    def in_window(day: date) -> bool:
        return window is None or window[0] <= day <= window[1]

    moves = [(o, r) for o, r in moves if in_window(o) and in_window(r)]
    if not moves:
        return

    scheduled = _scheduled_courses(session_code, courses)
    for origin, replacement in moves:
        relocating = [
            (course, index)
            for course, blocks in scheduled
            for index, block in enumerate(blocks)
            if int(block["jour"]) == origin.isoweekday()
        ]
        if not relocating:
            continue
        for course, index in relocating:
            _add_override(
                course,
                {
                    "block": index,
                    "date": origin.isoformat(),
                    "targetDate": replacement.isoformat(),
                },
            )
        for course, blocks in scheduled:
            for index, block in enumerate(blocks):
                if int(block["jour"]) == replacement.isoweekday():
                    _add_override(
                        course,
                        {
                            "block": index,
                            "date": replacement.isoformat(),
                            "canceled": True,
                        },
                    )


def seed_replaced_day_overrides(courses: list[dict]) -> list[dict]:
    entries = json.loads((SEED / REPLACED_DAYS.filename).read_text(encoding="utf-8"))
    for session_code, days in entries.items():
        _apply_swaps(session_code, courses, _parse_moves(days))
    return courses


def seed_occurrence_overrides(
    scenario_name: str, active_session: str, courses: list[dict]
):
    skip_dates, replaced_days = _resolve_and_cache(scenario_name)
    if not skip_dates and not replaced_days:
        return courses

    _apply_swaps(active_session, courses, _parse_moves(replaced_days))

    window = _course_window(active_session)
    skip_dates = {
        day for day in skip_dates if window is None or window[0] <= day <= window[1]
    }
    if not skip_dates:
        return courses

    for course, blocks in _scheduled_courses(active_session, courses):
        for index, block in enumerate(blocks):
            weekday = int(block["jour"])
            for day in sorted(skip_dates):
                if day.isoweekday() != weekday:
                    continue
                _add_override(
                    course,
                    {"block": index, "date": day.isoformat(), "canceled": True},
                )
    return courses


def apply_scenario(scenario_name: str, active_session: str, filename: str, data):
    _, replaced_days = _resolve_and_cache(scenario_name)

    if filename == REPLACED_DAYS.filename and replaced_days:
        session_list = data.setdefault(active_session, [])
        session_list.extend(replaced_days)

    return data


reload_scenarios()
