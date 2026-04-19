"""Reads profiles.json and strips/adds/generates courses for the active session."""

import json
import os

from ._paths import SEED
from .resource_specs import (
    COURSES,
    FIXTURE_SPECS,
    PROGRAMS,
    SESSION_KEYED_FILENAMES,
    sigle_from_item,
    sigle_from_key,
)
from .schedule_activities import flatten_teachers_by_course

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


def _filter_flat_list(
    spec, data: list, active_session: str, keep_sigles: set[str] | None
) -> list:
    session_key = spec.session_field
    sigle_key = spec.sigle_field or "sigle"
    if keep_sigles is None:
        return [c for c in data if c.get(session_key) != active_session]
    return [
        c
        for c in data
        if c.get(session_key) != active_session or c.get(sigle_key) in keep_sigles
    ]


def _filter_session_grouped_dict(
    spec, data: dict, active_session: str, keep_sigles: set[str] | None
) -> dict:
    if active_session not in data:
        return data
    if keep_sigles is None:
        data.pop(active_session, None)
    else:
        data[active_session] = {
            k: v
            for k, v in data[active_session].items()
            if sigle_from_key(spec, k) in keep_sigles
        }
    return data


def _filter_session_list(
    spec, data: dict, active_session: str, keep_sigles: set[str] | None
) -> dict:
    if active_session not in data:
        return data
    if keep_sigles is None:
        data.pop(active_session, None)
    else:
        data[active_session] = [
            item
            for item in data[active_session]
            if sigle_from_item(spec, item) in keep_sigles
        ]
    return data


def _filter_schedule_activities(
    spec, data: dict, active_session: str, keep_sigles: set[str] | None
) -> dict:
    if active_session not in data:
        return data
    session_data = data[active_session]
    list_key = "listeActivites"
    sigle_field = spec.sigle_field or "sigle"

    if keep_sigles is None:
        data.pop(active_session, None)
    else:
        session_data[list_key] = [
            a
            for a in session_data.get(list_key, [])
            if a.get(sigle_field) in keep_sigles
        ]
        teachers_by_course = {
            course_key: teachers
            for course_key, teachers in session_data.get(
                "enseignantsParCours", {}
            ).items()
            if course_key.split("-")[0] in keep_sigles
        }
        session_data["enseignantsParCours"] = teachers_by_course
        session_data["listeEnseignants"] = flatten_teachers_by_course(
            teachers_by_course
        )
    return data


_FILTER_DISPATCH = {
    "flat_list": _filter_flat_list,
    "session_dict": _filter_session_grouped_dict,
    "session_list": _filter_session_list,
    "schedule_activities": _filter_schedule_activities,
}


def _strip_courses_from_file(
    filename: str, data, active_session: str, keep_sigles: set | None
):
    spec = FIXTURE_SPECS.get(filename)
    if spec is None:
        return data
    handler = _FILTER_DISPATCH.get(spec.shape)
    if handler is None:
        return data
    return handler(spec, data, active_session, keep_sigles)


def _strip_session_keyed_data(filename: str, data, active_session: str):
    if filename in SESSION_KEYED_FILENAMES and isinstance(data, dict):
        data.pop(active_session, None)
    return data


def apply_profile(profile_name: str, active_session: str, filename: str, data):
    profile = _PROFILES.get(profile_name, {})
    if not profile:
        return data

    global_cfg = profile.get("global", {})
    if global_cfg:
        if global_cfg.get("stripCourses") and filename == COURSES.filename:
            data = []
        if (
            global_cfg.get("stripSessionKeyedData")
            and filename in SESSION_KEYED_FILENAMES
        ):
            data = {}
        replace_programs = global_cfg.get("replacePrograms")
        if filename == PROGRAMS.filename and replace_programs is not None:
            data = [_interpolate(p, active_session) for p in replace_programs]

    active_cfg = profile.get("activeSession", {})
    if not active_cfg:
        return data

    strip_courses = active_cfg.get("stripCourses", False)
    keep_courses = active_cfg.get("keepCourses")
    strip_session = active_cfg.get("stripSessionKeyedData", False)
    add_courses = active_cfg.get("addCourses", [])
    add_programs = active_cfg.get("addPrograms", [])

    if keep_courses is not None:
        data = _strip_courses_from_file(
            filename, data, active_session, set(keep_courses)
        )
    elif strip_courses:
        if filename == COURSES.filename:
            data = _strip_courses_from_file(filename, data, active_session, None)
        if strip_session:
            data = _strip_session_keyed_data(filename, data, active_session)

    if filename == COURSES.filename and add_courses:
        data = data + [_interpolate(c, active_session) for c in add_courses]

    if filename == PROGRAMS.filename and add_programs:
        data = data + [_interpolate(p, active_session) for p in add_programs]

    return data


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
