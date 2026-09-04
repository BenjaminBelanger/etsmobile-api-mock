"""Used for active session detection, date shifting, random course generation."""

import hashlib
import json
import random
import re
from datetime import date, timedelta

from ._paths import SEED

LAB_DURATION_HOURS = 3

_RAW_SESSIONS: list[dict] = []
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def reload_sessions() -> list[dict]:
    _RAW_SESSIONS[:] = json.loads((SEED / "sessions.json").read_text(encoding="utf-8"))
    return _RAW_SESSIONS


def get_raw_sessions() -> list[dict]:
    return _RAW_SESSIONS


def compute_active_session() -> str:
    """Map today's date to the current session code (e.g. 'H2026')."""
    today = date.today()
    year = today.year
    if today.month <= 4 or (today.month == 5 and today.day == 1):
        return f"H{year}"
    elif today.month <= 8:
        return f"É{year}"
    else:
        return f"A{year}"


def compute_next_session(active: str | None = None) -> str:
    """H -> É (same year), É -> A (same year), A -> H (year + 1)."""
    if active is None:
        active = compute_active_session()
    prefix = active[0]
    year = int(active[1:])
    if prefix == "H":
        return f"É{year}"
    if prefix in ("É", "E"):
        return f"A{year}"
    return f"H{year + 1}"


def session_rank(session_code: str) -> int:
    """Convert a session code to a sortable integer for range filtering."""
    prefix_map = {"H": 0, "E": 1, "É": 1, "A": 2}
    if len(session_code) >= 5 and session_code[0] in prefix_map:
        return int(session_code[1:]) * 3 + prefix_map[session_code[0]]
    return 9999


def _session_prefix(code: str) -> str:
    return code[0]


def _get_session_by_code(code: str) -> dict | None:
    return next((s for s in _RAW_SESSIONS if s["abrege"] == code), None)


def _find_source_session(target_code: str) -> str | None:
    """Find the most recent session with the same prefix (H/É/A)."""
    prefix = _session_prefix(target_code)
    candidates = [
        s["abrege"] for s in _RAW_SESSIONS if _session_prefix(s["abrege"]) == prefix
    ]
    return max(candidates, key=lambda session: int(session[1:])) if candidates else None


def _shift_date_str(date_str: str, day_delta: int) -> str:
    date_part = date_str[:10]
    suffix = date_str[10:]
    d = date.fromisoformat(date_part) + timedelta(days=day_delta)
    return d.isoformat() + suffix


def _clone_session_dates(target_code: str) -> dict:
    """Clone the latest same-type session, shifting dates by the year difference
    while preserving weekday alignment."""
    prefix = _session_prefix(target_code)
    target_year = int(target_code[1:])
    source_code = _find_source_session(target_code)
    if source_code is None:
        raise ValueError(
            f"No source session with prefix '{prefix}' "
            f"found to clone for {target_code}"
        )
    source_session = _get_session_by_code(source_code)
    source_year = int(source_code[1:])
    year_delta = target_year - source_year

    src_start = date.fromisoformat(source_session["dateDebut"])
    approximate_start = src_start.replace(year=src_start.year + year_delta)
    forward = (src_start.weekday() - approximate_start.weekday()) % 7
    weekday_adjustment = forward if forward <= 3 else forward - 7
    target_start = approximate_start + timedelta(days=weekday_adjustment)
    total_day_shift = (target_start - src_start).days

    new_session = {}
    semester_full_names = {"H": "Hiver", "É": "Été", "A": "Automne"}
    for key, value in source_session.items():
        if key == "abrege":
            new_session[key] = target_code
        elif key == "auLong":
            new_session[key] = (
                f"{semester_full_names.get(prefix, prefix)} {target_year}"
            )
        elif isinstance(value, str) and _DATE_RE.match(value):
            new_session[key] = _shift_date_str(value, total_day_shift)
        else:
            new_session[key] = value
    return new_session


def _get_session_dates(code: str) -> dict | None:
    existing = _get_session_by_code(code)
    if existing:
        return existing
    source = _find_source_session(code)
    if source:
        return _clone_session_dates(code)
    return None


def ensure_session_metadata(session_code: str) -> None:
    if any(s["abrege"] == session_code for s in _RAW_SESSIONS):
        return
    source = _find_source_session(session_code)
    if source:
        _RAW_SESSIONS.append(_clone_session_dates(session_code))


def compute_week_shift_delta(active_code: str, target_week: int) -> int:
    """Day delta that makes today fall in target_week of active_code.
    Preserves the original weekday of the session's dateDebut."""
    if target_week < 1:
        raise ValueError("target_week must be >= 1")
    active_meta = _get_session_dates(active_code)
    if active_meta is None:
        raise ValueError(f"No metadata for session '{active_code}'")
    original_start = date.fromisoformat(active_meta["dateDebut"])
    today = date.today()
    today_monday = today - timedelta(days=today.weekday())
    target_monday = today_monday - timedelta(weeks=target_week - 1)
    target_start = target_monday + timedelta(days=original_start.weekday())
    return (target_start - original_start).days


def shift_session_metadata(session_code: str, day_delta: int) -> None:
    """Shift every date field of the session record in _RAW_SESSIONS in place."""
    if day_delta == 0:
        return
    for entry in _RAW_SESSIONS:
        if entry["abrege"] != session_code:
            continue
        for key, value in entry.items():
            if key in ("abrege", "auLong"):
                continue
            if isinstance(value, str) and _DATE_RE.match(value):
                entry[key] = _shift_date_str(value, day_delta)
        return


reload_sessions()


def _generate_courses_pipeline(
    session_code: str,
    used_sigles: set[str],
    pools: dict,
    professors: dict,
    count: int,
    allowed_days: list[str] | None = None,
    time_preference: str | None = None,
    spread_days: bool = False,
) -> list[dict]:
    catalog = pools.get("courseCatalog", [])
    if not catalog:
        return []

    available = [c for c in catalog if c["sigle"] not in used_sigles]
    if len(available) < count:
        available = catalog

    seed_int = int(hashlib.sha256(session_code.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed_int)

    actual_count = min(count, len(available))
    chosen = rng.sample(available, actual_count)

    all_slots = pools["scheduleSlots"]
    day_filtered_slots = (
        [s for s in all_slots if s["jour"] in allowed_days]
        if allowed_days
        else list(all_slots)
    )

    eligible_slots = day_filtered_slots
    if time_preference:
        time_filtered = _filter_slots_by_time(day_filtered_slots, time_preference)
        if time_filtered:
            eligible_slots = time_filtered

    lab_eligible_slots = eligible_slots if time_preference else day_filtered_slots

    records = []
    occupied: set[tuple[str, str]] = set()
    used_days: list[str] = []
    prof_keys = list(professors.keys())

    for course_info in chosen:
        free_slots = [s for s in eligible_slots if _slot_key(s) not in occupied]
        if not free_slots:
            free_slots = eligible_slots

        if spread_days:
            new_day_slots = [s for s in free_slots if s["jour"] not in used_days]
            slot = rng.choice(new_day_slots if new_day_slots else free_slots)
            if slot["jour"] not in used_days:
                used_days.append(slot["jour"])
        else:
            slot = rng.choice(free_slots)

        occupied.add(_slot_key(slot))

        extra_activities = []
        lab = _generate_lab_slot(slot, lab_eligible_slots, occupied, rng, pools)
        if lab:
            extra_activities.append(lab)

        records.append(
            _build_course_record(
                course_info,
                session_code,
                slot,
                extra_activities,
                rng,
                pools,
                prof_keys,
            )
        )

    return records


def generate_random_courses(
    session_code: str,
    seed_courses: list[dict],
    pools: dict,
    professors: dict,
) -> list[dict]:
    """Fill sessions that have no seed data with random catalog courses."""
    if any(c["session"] == session_code for c in seed_courses):
        return []

    return _generate_courses_pipeline(
        session_code=session_code,
        used_sigles={c["sigle"] for c in seed_courses},
        pools=pools,
        professors=professors,
        count=pools.get("generatedCoursesPerSemester", 3),
    )


def _build_course_record(
    course_info: dict,
    session_code: str,
    slot: dict,
    extra_activities: list[dict],
    rng: random.Random,
    pools: dict,
    prof_keys: list[str],
) -> dict:
    return {
        "sigle": course_info["sigle"],
        "groupe": "01",
        "session": session_code,
        "titreCours": course_info["titre"],
        "nbCredits": course_info.get("nbCredits", 3),
        "programmeEtudes": "7084",
        "cote": "",
        "professorId": rng.choice(prof_keys),
        "room": rng.choice(pools["rooms"]),
        "examRoom": rng.choice(pools["examRooms"]),
        "schedule": {
            "jour": slot["jour"],
            "journee": slot["journee"],
            "heureDebut": slot["heureDebut"],
            "heureFin": slot["heureFin"],
            "codeActivite": "C",
            "nomActivite": "Activité de cours",
        },
        "extraActivities": extra_activities,
        "evaluations": rng.choice(pools["evalTemplates"]),
        "teammates": {},
        "gradePublishRatio": rng.choice([0.25, 0.5, 0.6]),
        "gradeSeed": rng.randint(1000, 9999),
    }


def _filter_slots_by_time(slots: list[dict], preference: str) -> list[dict]:
    ranges = {
        "morning": ("08:00", "13:00"),
        "afternoon": ("13:00", "18:00"),
        "evening": ("18:00", "22:00"),
    }
    prefs = [p.strip() for p in preference.split(",")]
    return [
        s
        for s in slots
        if any(
            ranges[p][0] <= s["heureDebut"] < ranges[p][1] for p in prefs if p in ranges
        )
    ]


def _slot_key(slot: dict) -> tuple[str, str]:
    return (slot["jour"], slot["heureDebut"])


def _generate_lab_slot(
    course_slot: dict,
    eligible_slots: list[dict],
    occupied: set[tuple[str, str]],
    rng: random.Random,
    pools: dict,
) -> dict | None:
    course_day = course_slot["jour"]
    other_day_slots = [
        s
        for s in eligible_slots
        if s["jour"] != course_day and _slot_key(s) not in occupied
    ]
    if not other_day_slots:
        other_day_slots = [s for s in eligible_slots if s["jour"] != course_day]
    if not other_day_slots:
        return None

    course_time = course_slot["heureDebut"]
    occupied_times_by_day: dict[str, set[str]] = {}
    for day_code, time_str in occupied:
        occupied_times_by_day.setdefault(day_code, set()).add(time_str)

    def _score_slot(s):
        day_times = occupied_times_by_day.get(s["jour"], set())
        on_free_time = s["heureDebut"] not in day_times
        diff_from_course = s["heureDebut"] != course_time
        return (on_free_time, diff_from_course)

    best_rank = max(_score_slot(s) for s in other_day_slots)
    best = [s for s in other_day_slots if _score_slot(s) == best_rank]
    selected_slot = rng.choice(best)
    occupied.add(_slot_key(selected_slot))
    start_hour, start_minute = int(selected_slot["heureDebut"][:2]), int(
        selected_slot["heureDebut"][3:]
    )
    end_hour = start_hour + LAB_DURATION_HOURS

    return {
        "jour": selected_slot["jour"],
        "journee": selected_slot["journee"],
        "heureDebut": selected_slot["heureDebut"],
        "heureFin": f"{end_hour:02d}:{start_minute:02d}",
        "codeActivite": "L",
        "nomActivite": "Activité de laboratoire",
        "room": rng.choice(pools["rooms"]),
    }


def generate_profile_courses(
    session_code: str,
    seed_courses: list[dict],
    pools: dict,
    professors: dict,
    config: dict,
) -> list[dict]:
    """Replace active-session seed courses with generated ones per profile config."""
    other_courses = [c for c in seed_courses if c["session"] != session_code]

    records = _generate_courses_pipeline(
        session_code=session_code,
        used_sigles={c["sigle"] for c in other_courses},
        pools=pools,
        professors=professors,
        count=config["count"],
        allowed_days=config.get("allowedDays"),
        time_preference=config.get("timePreference"),
        spread_days=True,
    )

    return other_courses + records
