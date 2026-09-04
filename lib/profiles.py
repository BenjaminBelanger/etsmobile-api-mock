import json
import os

from ._paths import SEED

_PROFILES: dict = {}

VALID_PROFILES: set[str] = set()


def reload_profiles() -> dict:
    profiles = json.loads((SEED / "profiles.json").read_text(encoding="utf-8"))
    _PROFILES.clear()
    _PROFILES.update(profiles)
    VALID_PROFILES.clear()
    VALID_PROFILES.update(profiles.keys())
    return _PROFILES


def get_valid_profiles() -> set[str]:
    return VALID_PROFILES


def _interpolate(value, active_session_code: str):
    if isinstance(value, str):
        return value.replace("$ACTIVE_SESSION", active_session_code)
    if isinstance(value, dict):
        return {k: _interpolate(v, active_session_code) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate(v, active_session_code) for v in value]
    return value


def seed_courses(profile_name: str, active_session: str, courses: list[dict]):
    profile = _PROFILES.get(profile_name, {})
    if not profile:
        return courses

    if profile.get("global", {}).get("stripCourses"):
        courses = []

    active_cfg = profile.get("activeSession", {})
    if active_cfg.get("stripCourses"):
        courses = [c for c in courses if c.get("session") != active_session]

    add_courses = active_cfg.get("addCourses", [])
    if add_courses:
        courses = courses + [_interpolate(c, active_session) for c in add_courses]
    return courses


def seed_programs(profile_name: str, active_session: str, programs: list[dict]):
    profile = _PROFILES.get(profile_name, {})
    if not profile:
        return programs

    replace_programs = profile.get("global", {}).get("replacePrograms")
    if replace_programs is not None:
        programs = [_interpolate(p, active_session) for p in replace_programs]

    add_programs = profile.get("activeSession", {}).get("addPrograms", [])
    if add_programs:
        programs = programs + [_interpolate(p, active_session) for p in add_programs]
    return programs


def _parse_schedule_days(value: str) -> list[str]:
    """'1,3,5' -> ['1', '3', '5']."""
    return [p.strip() for p in value.split(",") if p.strip()]


def get_generation_config(profile_name: str) -> dict | None:
    """Merge the profile's generateCourses block. Returns None if generation is not active."""
    profile = _PROFILES.get(profile_name, {})
    base_config = profile.get("generateCourses")

    env_count = os.environ.get("COURSE_COUNT")
    env_days = os.environ.get("SCHEDULE_DAYS")
    env_time = os.environ.get("TIME_PREFERENCE")

    if (
        base_config is None
        and env_count is None
        and env_days is None
        and env_time is None
    ):
        return None

    config = {
        "count": 3,
        "allowedDays": None,
        "timePreference": None,
        "custom": env_count is not None or env_days is not None or env_time is not None,
    }
    if base_config:
        config.update(base_config)

    if env_count is not None:
        config["count"] = max(1, min(5, int(env_count)))
    if env_days is not None:
        config["allowedDays"] = _parse_schedule_days(env_days)
    if env_time is not None:
        valid_times = {"morning", "afternoon", "evening"}
        parsed = [t.strip() for t in env_time.split(",") if t.strip() in valid_times]
        config["timePreference"] = ",".join(parsed) if parsed else None

    return config


reload_profiles()
