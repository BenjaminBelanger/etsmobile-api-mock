"""In-memory + persisted editable weekly schedule for the /editor UI.

The editor keeps, per session, an editable document::

    {"courses": [<seed-format course record>, ...],
     "trash":   [<seed-format course record>, ...]}

The ``courses`` list overrides what the mock API serves for that session
(written to ``seed/schedule_overrides.json`` and picked up by ``data_store``).
Undo/redo history is kept in memory and resets when the server restarts.
"""

import copy
import json
import random
import threading

from . import data_store
from ._paths import SEED
from .data_store import OVERRIDES_FILENAME

# Week grid bounds and granularity (minutes).
DAY_START_MIN = 8 * 60  # 08:00
DAY_END_MIN = 22 * 60  # 22:00
SNAP_MIN = 15
MIN_DURATION_MIN = 30
MAX_HISTORY = 100

DAY_NAMES = {
    "1": "Lundi",
    "2": "Mardi",
    "3": "Mercredi",
    "4": "Jeudi",
    "5": "Vendredi",
    "6": "Samedi",
    "7": "Dimanche",
}
DAY_SHORT = {
    "1": "LUN",
    "2": "MAR",
    "3": "MER",
    "4": "JEU",
    "5": "VEN",
    "6": "SAM",
    "7": "DIM",
}
EDITABLE_DAYS = ["1", "2", "3", "4", "5", "6"]

_lock = threading.RLock()
# session -> {"courses": [...], "trash": [...]} (source of truth in memory)
_docs: dict[str, dict] = {}
_undo: dict[str, list] = {}
_redo: dict[str, list] = {}


class EditorError(ValueError):
    """Raised for invalid editor operations (mapped to HTTP 400)."""


# --------------------------------------------------------------------------- #
# Time helpers
# --------------------------------------------------------------------------- #
def _to_min(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def _to_hhmm(total: int) -> str:
    return f"{total // 60:02d}:{total % 60:02d}"


def _snap(total: int) -> int:
    return int(round(total / SNAP_MIN)) * SNAP_MIN


def _clamp_range(start: int, end: int) -> tuple[int, int]:
    """Keep a start/end pair inside the grid with a minimum duration."""
    duration = max(MIN_DURATION_MIN, end - start)
    start = max(DAY_START_MIN, min(start, DAY_END_MIN - MIN_DURATION_MIN))
    end = min(DAY_END_MIN, start + duration)
    start = min(start, end - MIN_DURATION_MIN)
    return start, end


# --------------------------------------------------------------------------- #
# Document lifecycle
# --------------------------------------------------------------------------- #
def _persist() -> None:
    """Write all materialized docs to the overrides file and reload the API."""
    payload = {
        session: {"courses": doc["courses"], "trash": doc["trash"]}
        for session, doc in _docs.items()
    }
    path = SEED / OVERRIDES_FILENAME
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    data_store.reload()


def _load_doc(session: str) -> dict:
    """Return the editable doc for a session, materializing it on first use.

    Materializing does not persist; the doc only hits disk once it is mutated.
    """
    if session in _docs:
        return _docs[session]

    overrides = data_store._load_overrides()  # noqa: SLF001 - internal helper
    if session in overrides:
        entry = overrides[session]
        doc = {
            "courses": copy.deepcopy(entry.get("courses", [])),
            "trash": copy.deepcopy(entry.get("trash", [])),
        }
    else:
        doc = {"courses": data_store.get_session_courses(session), "trash": []}
    _docs[session] = doc
    _undo.setdefault(session, [])
    _redo.setdefault(session, [])
    return doc


def _snapshot(session: str) -> None:
    """Push the current doc onto the undo stack and clear redo."""
    doc = _docs[session]
    stack = _undo.setdefault(session, [])
    stack.append(copy.deepcopy(doc))
    if len(stack) > MAX_HISTORY:
        del stack[0]
    _redo[session] = []


# --------------------------------------------------------------------------- #
# Course / block lookup
# --------------------------------------------------------------------------- #
def _course_key(course: dict) -> str:
    return f"{course['sigle']}-{course['groupe']}"


def _find_course(doc: dict, course_id: str) -> dict:
    for course in doc["courses"]:
        if _course_key(course) == course_id:
            return course
    raise EditorError(f"Course '{course_id}' not found")


def _blocks_of(course: dict) -> list[dict]:
    """A course's schedule dicts: index 0 = primary, 1.. = extraActivities."""
    blocks = []
    if course.get("schedule"):
        blocks.append(course["schedule"])
    else:
        blocks.append(None)
    blocks.extend(course.get("extraActivities", []))
    return blocks


def _resolve_block(doc: dict, block_id: str) -> tuple[dict, dict]:
    """Return (course, schedule-dict) for a block id ``courseId:index``."""
    course_id, _, raw_index = block_id.rpartition(":")
    course = _find_course(doc, course_id)
    try:
        index = int(raw_index)
    except ValueError as exc:
        raise EditorError(f"Invalid block id '{block_id}'") from exc

    if index == 0:
        schedule = course.get("schedule")
        if schedule is None:
            raise EditorError(f"Block '{block_id}' has no schedule")
        return course, schedule

    extras = course.get("extraActivities", [])
    if index - 1 >= len(extras):
        raise EditorError(f"Block '{block_id}' not found")
    return course, extras[index - 1]


# --------------------------------------------------------------------------- #
# Normalized view for the frontend
# --------------------------------------------------------------------------- #
def _normalize_block(course: dict, index: int, schedule: dict) -> dict:
    code = schedule.get("codeActivite", "C")
    kind = {"C": "cours", "L": "labo", "TP": "tp"}.get(code, "cours")
    return {
        "id": f"{_course_key(course)}:{index}",
        "courseId": _course_key(course),
        "sigle": course["sigle"],
        "groupe": course["groupe"],
        "titre": course.get("titreCours", ""),
        "room": schedule.get("room", course.get("room", "")),
        "codeActivite": code,
        "kind": kind,
        "nomActivite": schedule.get("nomActivite", "Activité de cours"),
        "isPrimary": index == 0,
        "jour": str(schedule.get("jour", "1")),
        "journee": schedule.get("journee", DAY_NAMES.get(str(schedule.get("jour")), "")),
        "heureDebut": schedule.get("heureDebut", "09:00"),
        "heureFin": schedule.get("heureFin", "12:00"),
    }


def _normalize_course(course: dict) -> dict:
    blocks = []
    for index, schedule in enumerate(_blocks_of(course)):
        if schedule is None:
            continue
        blocks.append(_normalize_block(course, index, schedule))
    return {
        "courseId": _course_key(course),
        "sigle": course["sigle"],
        "groupe": course["groupe"],
        "titre": course.get("titreCours", ""),
        "room": course.get("room", ""),
        "hasSchedule": course.get("schedule") is not None,
        "blocks": blocks,
    }


def get_state(session: str) -> dict:
    with _lock:
        if not session or session not in data_store.get_sessions_with_courses():
            session = data_store.resolve_default_session()
        doc = _load_doc(session)
        courses = [_normalize_course(c) for c in doc["courses"]]
        blocks = [b for c in courses for b in c["blocks"]]
        trash = [
            {
                "courseId": _course_key(c),
                "sigle": c["sigle"],
                "groupe": c["groupe"],
                "titre": c.get("titreCours", ""),
            }
            for c in doc["trash"]
        ]
        pools = data_store.get_pools()
        return {
            "session": session,
            "sessions": data_store.get_sessions_with_courses(),
            "courses": courses,
            "blocks": blocks,
            "trash": trash,
            "canUndo": bool(_undo.get(session)),
            "canRedo": bool(_redo.get(session)),
            "meta": {
                "dayStart": _to_hhmm(DAY_START_MIN),
                "dayEnd": _to_hhmm(DAY_END_MIN),
                "snapMin": SNAP_MIN,
                "minDuration": MIN_DURATION_MIN,
                "days": [
                    {"jour": d, "name": DAY_NAMES[d], "short": DAY_SHORT[d]}
                    for d in EDITABLE_DAYS
                ],
                "catalog": [
                    {"sigle": c["sigle"], "titre": c["titre"]}
                    for c in pools.get("courseCatalog", [])
                ],
            },
        }


# --------------------------------------------------------------------------- #
# Mutations
# --------------------------------------------------------------------------- #
def _apply_time(schedule: dict, jour: str, start_min: int, end_min: int) -> None:
    start_min, end_min = _clamp_range(_snap(start_min), _snap(end_min))
    schedule["jour"] = str(jour)
    schedule["journee"] = DAY_NAMES.get(str(jour), schedule.get("journee", ""))
    schedule["heureDebut"] = _to_hhmm(start_min)
    schedule["heureFin"] = _to_hhmm(end_min)


def move_block(session: str, block_id: str, jour: str, heure_debut: str) -> dict:
    with _lock:
        doc = _load_doc(session)
        _, schedule = _resolve_block(doc, block_id)
        if str(jour) not in DAY_NAMES:
            raise EditorError(f"Invalid day '{jour}'")
        duration = _to_min(schedule["heureFin"]) - _to_min(schedule["heureDebut"])
        start = _snap(_to_min(heure_debut))
        _snapshot(session)
        _apply_time(schedule, jour, start, start + duration)
        _persist()
    return get_state(session)


def resize_block(session: str, block_id: str, heure_debut: str, heure_fin: str) -> dict:
    with _lock:
        doc = _load_doc(session)
        course, schedule = _resolve_block(doc, block_id)
        start = _snap(_to_min(heure_debut))
        end = _snap(_to_min(heure_fin))
        if end - start < MIN_DURATION_MIN:
            raise EditorError("Block is too short")
        _snapshot(session)
        _apply_time(schedule, schedule.get("jour", "1"), start, end)
        _persist()
    return get_state(session)


def delete_course(session: str, course_id: str) -> dict:
    with _lock:
        doc = _load_doc(session)
        course = _find_course(doc, course_id)
        _snapshot(session)
        doc["courses"].remove(course)
        doc["trash"].append(course)
        _persist()
    return get_state(session)


def restore_course(session: str, course_id: str) -> dict:
    with _lock:
        doc = _load_doc(session)
        course = next(
            (c for c in doc["trash"] if _course_key(c) == course_id), None
        )
        if course is None:
            raise EditorError(f"Course '{course_id}' not in trash")
        _snapshot(session)
        doc["trash"].remove(course)
        doc["courses"].append(course)
        _persist()
    return get_state(session)


def _next_group(doc: dict, sigle: str) -> str:
    used = [
        int(c["groupe"])
        for c in doc["courses"] + doc["trash"]
        if c["sigle"] == sigle and str(c["groupe"]).isdigit()
    ]
    return f"{max(used, default=0) + 1:02d}"


def add_course(
    session: str,
    sigle: str,
    titre: str,
    jour: str,
    heure_debut: str,
    heure_fin: str,
    kind: str = "cours",
) -> dict:
    with _lock:
        doc = _load_doc(session)
        sigle = (sigle or "").strip().upper()
        if not sigle:
            raise EditorError("A course code (sigle) is required")
        if str(jour) not in DAY_NAMES:
            raise EditorError(f"Invalid day '{jour}'")

        pools = data_store.get_pools()
        professors = data_store.get_professors()
        rng = random.Random(f"{session}-{sigle}-{len(doc['courses'])}")
        catalog = {c["sigle"]: c for c in pools.get("courseCatalog", [])}
        title = titre.strip() or catalog.get(sigle, {}).get("titre", sigle)

        start = _snap(_to_min(heure_debut))
        end = _snap(_to_min(heure_fin))
        if end - start < MIN_DURATION_MIN:
            end = start + 180
        start, end = _clamp_range(start, end)
        code = "L" if kind == "labo" else "C"

        record = {
            "sigle": sigle,
            "groupe": _next_group(doc, sigle),
            "session": session,
            "titreCours": title,
            "nbCredits": catalog.get(sigle, {}).get("nbCredits", 3),
            "programmeEtudes": "7084",
            "cote": "",
            "professorId": (
                rng.choice(list(professors.keys())) if professors else "last1-first1"
            ),
            "room": rng.choice(pools["rooms"]) if pools.get("rooms") else "A-1302",
            "examRoom": (
                rng.choice(pools["examRooms"]) if pools.get("examRooms") else "A-1518"
            ),
            "schedule": {
                "jour": str(jour),
                "journee": DAY_NAMES[str(jour)],
                "heureDebut": _to_hhmm(start),
                "heureFin": _to_hhmm(end),
                "codeActivite": code,
                "nomActivite": "Laboratoire" if code == "L" else "Activité de cours",
            },
            "extraActivities": [],
            "evaluations": (
                rng.choice(pools["evalTemplates"])
                if pools.get("evalTemplates")
                else []
            ),
            "teammates": {},
            "gradePublishRatio": 0.6,
            "gradeSeed": rng.randint(1000, 9999),
        }
        _snapshot(session)
        doc["courses"].append(record)
        _persist()
    return get_state(session)


def undo(session: str) -> dict:
    with _lock:
        stack = _undo.get(session, [])
        if not stack:
            raise EditorError("Nothing to undo")
        _redo.setdefault(session, []).append(copy.deepcopy(_docs[session]))
        _docs[session] = stack.pop()
        _persist()
    return get_state(session)


def redo(session: str) -> dict:
    with _lock:
        stack = _redo.get(session, [])
        if not stack:
            raise EditorError("Nothing to redo")
        _undo.setdefault(session, []).append(copy.deepcopy(_docs[session]))
        _docs[session] = stack.pop()
        _persist()
    return get_state(session)


def reset_session(session: str) -> dict:
    """Revert a session to its pristine generated/seed schedule."""
    with _lock:
        _load_doc(session)
        _snapshot(session)
        _docs[session] = {
            "courses": data_store.get_session_courses(session, base=True),
            "trash": [],
        }
        _persist()
    return get_state(session)
