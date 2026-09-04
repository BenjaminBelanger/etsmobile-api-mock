import copy
import json
import os
from pathlib import Path

from . import profiles, scenarios, sessions
from ._paths import SEED
from .compute import build_all_course_data
from .resource_specs import COURSES, GENERATED_FILENAMES, PROGRAMS, SESSIONS

OVERRIDES_FILENAME = "schedule_overrides.json"

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
_base_courses = None
_professors = None
_pools = None
_programs = None
_generated = None
_cache: dict[str, object] = {}


def overrides_path() -> Path:
    return SEED / OVERRIDES_FILENAME


def _load_overrides() -> dict:
    path = overrides_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _apply_overrides(built_courses: list[dict]) -> list[dict]:
    overrides = _load_overrides()
    if not overrides:
        return built_courses

    overridden_sessions = set(overrides.keys())
    result = [c for c in built_courses if c.get("session") not in overridden_sessions]
    for session_code, entry in overrides.items():
        result.extend(copy.deepcopy(entry.get("courses", [])))
    return result


def _initialize():
    global _seed_courses, _base_courses, _professors, _pools, _programs, _generated
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
    _programs = json.loads((SEED / PROGRAMS.filename).read_text(encoding="utf-8"))
    if PROFILE_NAME != DEFAULT_PROFILE:
        _seed_courses = profiles.seed_courses(
            PROFILE_NAME, ACTIVE_SESSION, _seed_courses
        )
        _programs = profiles.seed_programs(PROFILE_NAME, ACTIVE_SESSION, _programs)
    _seed_courses = scenarios.seed_replaced_day_overrides(_seed_courses)
    if SCENARIO_NAME != DEFAULT_SCENARIO:
        _seed_courses = scenarios.seed_occurrence_overrides(
            SCENARIO_NAME, ACTIVE_SESSION, _seed_courses
        )
    _base_courses = copy.deepcopy(_seed_courses)
    _seed_courses = _apply_overrides(_seed_courses)
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
    elif name == PROGRAMS.filename:
        data = copy.deepcopy(_programs)
    else:
        data = json.loads((SEED / name).read_text(encoding="utf-8"))
    if SCENARIO_NAME != DEFAULT_SCENARIO:
        data = scenarios.apply_scenario(SCENARIO_NAME, ACTIVE_SESSION, name, data)
    if name == SESSIONS.filename:
        registered = {c.get("session") for c in load(COURSES.filename)}
        data = [s for s in data if s.get("abrege") in registered]
    _cache[name] = data
    return data


def load_session(name: str, session: str, default=None):
    return load(name).get(session, [] if default is None else default)


def empty_evaluation() -> dict:
    return {**_EMPTY_EVALUATION_SUMMARY, "liste": []}


def get_session_courses(session: str, *, base: bool = False) -> list[dict]:
    source = _base_courses if base else _seed_courses
    return [copy.deepcopy(c) for c in (source or []) if c.get("session") == session]


def get_sessions_with_courses() -> list[str]:
    codes = {c.get("session") for c in (_base_courses or []) if c.get("session")}
    codes.update(k for k in _load_overrides().keys() if k)
    return sorted(codes, key=sessions.session_rank, reverse=True)


def resolve_default_session() -> str:
    available = get_sessions_with_courses()
    if ACTIVE_SESSION in available:
        return ACTIVE_SESSION
    return available[0] if available else ACTIVE_SESSION


def get_pools() -> dict:
    return copy.deepcopy(_pools or {})


def get_professors() -> dict:
    return copy.deepcopy(_professors or {})
