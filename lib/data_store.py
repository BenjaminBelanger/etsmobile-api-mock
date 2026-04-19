"""Loads seed files, applies profiles/scenarios, caches results."""

import json
import os

from . import profiles, scenarios, sessions
from ._paths import SEED
from .compute import build_all_course_data
from .resource_specs import COURSES, GENERATED_FILENAMES, SESSIONS

DEFAULT_PROFILE = "normal"
DEFAULT_SCENARIO = "none"

ACTIVE_SESSION = ""
NEXT_SESSION = ""
PROFILE_NAME = DEFAULT_PROFILE
SCENARIO_NAME = DEFAULT_SCENARIO
GENERATION_CONFIG = None
SEMESTER_WEEK: int | None = None

_EMPTY_EVALUATION_SUMMARY = {
    "noteACeJour": "",
    "scoreFinalSur100": "",
    "moyenneClasse": "",
    "ecartTypeClasse": "",
    "medianeClasse": "",
    "rangCentileClasse": "",
    "noteACeJourElementsIndividuels": "",
    "noteSur100PourElementsIndividuels": "",
    "tauxPublication": "0,0",
}


def _parse_semester_week(raw: str) -> int | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        week = int(raw)
    except ValueError as exc:
        raise ValueError(f"SEMESTER_WEEK must be an integer, got '{raw}'.") from exc
    if week < 1:
        raise ValueError(f"SEMESTER_WEEK must be >= 1, got {week}.")
    return week


def _refresh_config():
    global ACTIVE_SESSION, NEXT_SESSION, PROFILE_NAME, SCENARIO_NAME, GENERATION_CONFIG, SEMESTER_WEEK

    ACTIVE_SESSION = sessions.compute_active_session()
    NEXT_SESSION = sessions.compute_next_session(ACTIVE_SESSION)
    PROFILE_NAME = os.environ.get("PROFILE", DEFAULT_PROFILE)
    SCENARIO_NAME = os.environ.get("SCENARIO", DEFAULT_SCENARIO)
    SEMESTER_WEEK = _parse_semester_week(os.environ.get("SEMESTER_WEEK", ""))

    valid_profiles = profiles.get_valid_profiles()
    if PROFILE_NAME not in valid_profiles:
        raise ValueError(
            f"Unknown profile '{PROFILE_NAME}'. "
            f"Valid profiles: {', '.join(sorted(valid_profiles))}"
        )

    valid_scenarios = scenarios.get_valid_scenarios()
    if SCENARIO_NAME not in valid_scenarios:
        raise ValueError(
            f"Unknown scenario '{SCENARIO_NAME}'. "
            f"Valid scenarios: {', '.join(sorted(valid_scenarios))}"
        )

    GENERATION_CONFIG = profiles.get_generation_config(PROFILE_NAME)


def _build_courses(seed_courses, pools, professors):
    if GENERATION_CONFIG is not None:
        return sessions.generate_profile_courses(
            ACTIVE_SESSION, seed_courses, pools, professors, GENERATION_CONFIG
        )
    return seed_courses + sessions.generate_random_courses(
        ACTIVE_SESSION, seed_courses, pools, professors
    )


_seed_courses = None
_professors = None
_pools = None
_generated = None
_cache: dict[str, object] = {}


def _initialize():
    global _seed_courses, _professors, _pools, _generated
    _refresh_config()
    _seed_courses = json.loads((SEED / COURSES.filename).read_text(encoding="utf-8"))
    _professors = json.loads((SEED / "professors.json").read_text(encoding="utf-8"))
    _pools = json.loads((SEED / "pools.json").read_text(encoding="utf-8"))
    sessions.ensure_session_metadata(ACTIVE_SESSION)
    sessions.ensure_session_metadata(NEXT_SESSION)
    if SEMESTER_WEEK is not None:
        delta = sessions.compute_week_shift_delta(ACTIVE_SESSION, SEMESTER_WEEK)
        sessions.shift_session_metadata(ACTIVE_SESSION, delta)
        sessions.shift_session_metadata(NEXT_SESSION, delta)
    _seed_courses = _build_courses(_seed_courses, _pools, _professors)
    _seed_courses = _seed_courses + sessions.generate_random_courses(
        NEXT_SESSION, _seed_courses, _pools, _professors
    )
    _generated = build_all_course_data(
        sessions.get_raw_sessions(),
        _seed_courses,
        _professors,
        _pools,
    )


_initialize()


def reload():
    global _cache
    sessions.reload_sessions()
    profiles.reload_profiles()
    scenarios.reload_scenarios()
    _initialize()
    _cache = {}


def load(name: str):
    if name in _cache:
        return _cache[name]
    if name in GENERATED_FILENAMES and name in _generated:
        data = _generated[name]
    elif name == SESSIONS.filename:
        data = [dict(s) for s in sessions.get_raw_sessions()]
    else:
        data = json.loads((SEED / name).read_text(encoding="utf-8"))
    data = sessions.ensure_active_session_data(name, data, ACTIVE_SESSION)
    data = sessions.ensure_active_session_data(name, data, NEXT_SESSION)
    if PROFILE_NAME != DEFAULT_PROFILE:
        data = profiles.apply_profile(PROFILE_NAME, ACTIVE_SESSION, name, data)
    if SCENARIO_NAME != DEFAULT_SCENARIO:
        data = scenarios.apply_scenario(SCENARIO_NAME, ACTIVE_SESSION, name, data)
    _cache[name] = data
    return data


def load_session(name: str, session: str, default=None):
    return load(name).get(session, [] if default is None else default)


def empty_evaluation() -> dict:
    return {**_EMPTY_EVALUATION_SUMMARY, "liste": []}
