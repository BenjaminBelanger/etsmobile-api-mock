import copy
import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from . import sessions
from ._paths import ROOT

FORMAT = 1
SCOPES = ("personal", "shared")
DATE_MODES = ("week", "exact", "setup")
DEFAULT_DATE_MODE = "week"
MAX_NAME_LENGTH = 80

DEFAULT_PROFILE = "normal"
DEFAULT_SCENARIO = "none"

_ID_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


class SnapshotError(ValueError):
    pass


class SnapshotConflict(SnapshotError):
    pass


@dataclass
class Plan:
    setup: dict
    failures: dict | None
    schedule: dict
    student: dict
    notices: list[str] = field(default_factory=list)


def snapshots_dir() -> Path:
    return ROOT / "snapshots"


def slugify(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    return slug[:60].strip("-")


def _folder(scope: str) -> Path:
    if scope not in SCOPES:
        raise SnapshotError(f"Unknown scope '{scope}'")
    return snapshots_dir() / scope


def _path(scope: str, snapshot_id: str) -> Path:
    folder = _folder(scope)
    if not _ID_RE.fullmatch(snapshot_id or ""):
        raise SnapshotError(f"Invalid snapshot id '{snapshot_id}'")
    return folder / f"{snapshot_id}.json"


def clean_name(name) -> str:
    text = " ".join(str(name or "").split())
    if not text:
        raise SnapshotError("A snapshot name is required")
    if len(text) > MAX_NAME_LENGTH:
        raise SnapshotError(f"A snapshot name is at most {MAX_NAME_LENGTH} characters")
    if not slugify(text):
        raise SnapshotError("A snapshot name needs at least one letter or digit")
    return text


def _is_iso_date(value) -> bool:
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value[:10])
    except ValueError:
        return False
    return True


def validate(raw) -> dict:
    if not isinstance(raw, dict):
        raise SnapshotError("A snapshot must be a JSON object")
    if raw.get("format") != FORMAT:
        raise SnapshotError(f"Unsupported snapshot format {raw.get('format')!r}")
    snapshot = copy.deepcopy(raw)
    snapshot["name"] = clean_name(snapshot.get("name"))

    anchor = snapshot.get("anchor")
    if (
        not isinstance(anchor, dict)
        or not isinstance(anchor.get("session"), str)
        or not isinstance(anchor.get("week"), int)
        or not _is_iso_date(anchor.get("date"))
    ):
        raise SnapshotError("The snapshot anchor needs a session, a week and a date")

    setup = snapshot.get("setup")
    if not isinstance(setup, dict) or not isinstance(setup.get("profile"), str):
        raise SnapshotError("The snapshot setup needs a profile")
    week = setup.get("semesterWeek")
    if week is not None and (not isinstance(week, int) or week < 1):
        raise SnapshotError("The snapshot semester week must be a number >= 1")

    saved = snapshot.setdefault("sessions", {})
    if not isinstance(saved, dict) or not all(
        isinstance(entry, dict) for entry in saved.values()
    ):
        raise SnapshotError("The snapshot sessions must be an object of sessions")
    for key in ("student", "failures"):
        if not isinstance(snapshot.setdefault(key, {}), dict):
            raise SnapshotError(f"The snapshot {key} must be an object")
    return snapshot


def summary(scope: str, snapshot_id: str, snapshot: dict) -> dict:
    return {
        "scope": scope,
        "id": snapshot_id,
        "name": snapshot["name"],
        "savedAt": snapshot.get("savedAt", ""),
        "anchor": snapshot["anchor"],
        "setup": snapshot["setup"],
        "failures": snapshot["failures"],
        "sessions": sorted(snapshot["sessions"], key=sessions.session_rank),
        "student": sorted(snapshot["student"]),
    }


def list_all() -> list[dict]:
    items = []
    for scope in SCOPES:
        for path in _folder(scope).glob("*.json"):
            try:
                snapshot = validate(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
            items.append(summary(scope, path.stem, snapshot))
    items.sort(key=lambda item: (SCOPES.index(item["scope"]), item["name"].lower()))
    return items


def read(scope: str, snapshot_id: str) -> dict:
    path = _path(scope, snapshot_id)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SnapshotError(f"Snapshot '{scope}/{snapshot_id}' not found") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise SnapshotError(f"Snapshot '{scope}/{snapshot_id}' is unreadable") from exc
    return validate(raw)


def write(scope: str, snapshot: dict, *, overwrite: bool = False) -> str:
    snapshot = validate(snapshot)
    snapshot_id = slugify(snapshot["name"])
    path = _path(scope, snapshot_id)
    if path.exists() and not overwrite:
        existing = read(scope, snapshot_id)["name"]
        raise SnapshotConflict(f"A snapshot named '{existing}' already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return snapshot_id


def delete(scope: str, snapshot_id: str) -> None:
    path = _path(scope, snapshot_id)
    if not path.exists():
        raise SnapshotError(f"Snapshot '{scope}/{snapshot_id}' not found")
    path.unlink()


def move(scope: str, snapshot_id: str, target: str) -> str:
    if target == scope:
        raise SnapshotError(f"Snapshot '{scope}/{snapshot_id}' is already {scope}")
    snapshot = read(scope, snapshot_id)
    new_id = write(target, snapshot)
    delete(scope, snapshot_id)
    return new_id


def find(reference: str) -> list[tuple[str, str]]:
    scope, _, name = reference.rpartition("/")
    scopes = [scope] if scope in SCOPES else list(SCOPES)
    wanted = {name.strip().lower(), slugify(name)}
    return [
        (item["scope"], item["id"])
        for item in list_all()
        if item["scope"] in scopes
        and (item["id"] in wanted or item["name"].lower() in wanted)
    ]


def setup_to_env(setup: Mapping) -> dict[str, str]:
    env = {"PROFILE": setup.get("profile") or DEFAULT_PROFILE}
    scenario = setup.get("scenario") or DEFAULT_SCENARIO
    if scenario != DEFAULT_SCENARIO:
        env["SCENARIO"] = scenario
    if setup.get("semesterWeek") is not None:
        env["SEMESTER_WEEK"] = str(setup["semesterWeek"])
    if "courses" in setup:
        env["COURSE_COUNT"] = str(setup["courses"])
    if "days" in setup:
        env["SCHEDULE_DAYS"] = ",".join(setup["days"] or [])
    if "time" in setup:
        env["TIME_PREFERENCE"] = setup["time"] or ""
    return env


def setup_from_env(env: Mapping[str, str]) -> dict:
    week = (env.get("SEMESTER_WEEK") or "").strip()
    setup = {
        "profile": env.get("PROFILE") or DEFAULT_PROFILE,
        "scenario": env.get("SCENARIO") or DEFAULT_SCENARIO,
        "semesterWeek": int(week) if week else None,
    }
    if "COURSE_COUNT" in env:
        setup["courses"] = int(env["COURSE_COUNT"])
    if "SCHEDULE_DAYS" in env:
        setup["days"] = [d.strip() for d in env["SCHEDULE_DAYS"].split(",") if d.strip()]
    if "TIME_PREFERENCE" in env:
        setup["time"] = env["TIME_PREFERENCE"]
    return setup


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _shift_course(course: dict, session_code: str, days: int) -> dict:
    shifted = copy.deepcopy(course)
    shifted["session"] = session_code
    if not days:
        return shifted

    def move(holder: dict, key: str) -> None:
        if isinstance(holder, dict) and _is_iso_date(holder.get(key)):
            holder[key] = sessions._shift_date_str(holder[key], days)

    for override in shifted.get("occurrenceOverrides", []):
        move(override, "date")
        move(override, "targetDate")
    for evaluation in shifted.get("evaluations", []):
        move(evaluation, "dateCible")
        move(evaluation.get("generated"), "dateCible")
    move(shifted.get("finalExam"), "dateExamen")
    return shifted


def _drop_outside(entry: dict, window: tuple[date, date]) -> int:
    dropped = 0
    for course in entry["courses"] + entry["trash"]:
        overrides = course.get("occurrenceOverrides")
        if not overrides:
            continue
        kept = [
            ov
            for ov in overrides
            if _is_iso_date(ov.get("date"))
            and window[0] <= date.fromisoformat(ov["date"]) <= window[1]
        ]
        dropped += len(overrides) - len(kept)
        if kept:
            course["occurrenceOverrides"] = kept
        else:
            course.pop("occurrenceOverrides", None)
    return dropped


def _schedule_entry(entry: dict, session_code: str, days: int) -> dict:
    result = {
        "courses": [_shift_course(c, session_code, days) for c in entry.get("courses", [])],
        "trash": [_shift_course(c, session_code, days) for c in entry.get("trash", [])],
    }
    dates = {
        key: sessions._shift_date_str(value, days) if days else value
        for key, value in entry.get("dates", {}).items()
    }
    if dates:
        result["dates"] = dates
    return result


def _target_week(active: str, saved_week: int, notices: list[str]) -> int | None:
    meta = sessions.session_metadata(active)
    if meta is None:
        raise SnapshotError(f"No dates known for session '{active}'")
    count = sessions.week_count(meta)
    week = min(max(saved_week, 1), count)
    if saved_week < 1:
        notices.append(
            f"L'instantané a été enregistré avant le début de sa session: "
            f"la semaine 1 de {active} est utilisée."
        )
    elif saved_week > count:
        notices.append(
            f"{active} n'a que {count} semaines: la semaine {count} est utilisée "
            f"au lieu de la semaine {saved_week}."
        )
    real_week = sessions.week_index(date.fromisoformat(meta["dateDebut"]), date.today())
    return None if week == real_week else week


def _shifted_schedule(snapshot: dict, active: str, notices: list[str]) -> dict:
    saved_active = snapshot["anchor"]["session"]
    mapping = {
        saved_active: active,
        sessions.compute_next_session(saved_active): sessions.compute_next_session(active),
    }
    schedule = {}
    for source, target in mapping.items():
        entry = snapshot["sessions"].get(source)
        if entry is None:
            continue
        meta = sessions.session_metadata(target)
        start = (entry.get("calendar") or {}).get("dateDebut")
        days = 0
        if meta and start:
            days = (
                _monday(date.fromisoformat(meta["dateDebut"]))
                - _monday(date.fromisoformat(start))
            ).days
        shifted = _schedule_entry(entry, target, days)
        if meta:
            dates = {**meta, **shifted.get("dates", {})}
            end = dates.get("dateFinCours") or dates["dateFin"]
            window = (date.fromisoformat(dates["dateDebut"]), date.fromisoformat(end))
            dropped = _drop_outside(shifted, window)
            if dropped:
                notices.append(
                    f"{dropped} modification(s) de séance hors de la session {target} "
                    f"ignorée(s)."
                )
        schedule[target] = shifted
    for code, entry in snapshot["sessions"].items():
        if code not in mapping and code not in schedule:
            schedule[code] = _schedule_entry(entry, code, 0)
    return schedule


def _exact_schedule(snapshot: dict) -> dict:
    schedule = {}
    for code, entry in snapshot["sessions"].items():
        result = _schedule_entry(entry, code, 0)
        saved_dates = {**entry.get("calendar", {}), **entry.get("dates", {})}
        base = sessions.session_metadata(code) or {}
        pinned = {
            key: value
            for key, value in saved_dates.items()
            if key in sessions.date_fields(base) and base[key] != value
        }
        result.pop("dates", None)
        if pinned:
            result["dates"] = pinned
        schedule[code] = result
    return schedule


def plan(snapshot: dict, mode: str = DEFAULT_DATE_MODE, *, failures: bool = True) -> Plan:
    if mode not in DATE_MODES:
        raise SnapshotError(f"Unknown date mode '{mode}'")
    snapshot = validate(snapshot)
    setup = copy.deepcopy(snapshot["setup"])
    notices: list[str] = []
    active = sessions.compute_active_session()
    upcoming = sessions.compute_next_session(active)

    sessions.reload_sessions()
    sessions.prepare(active, upcoming, None)
    if mode == "week":
        setup["semesterWeek"] = _target_week(active, snapshot["anchor"]["week"], notices)
    sessions.prepare(active, upcoming, setup.get("semesterWeek"))

    if mode == "week":
        schedule = _shifted_schedule(snapshot, active, notices)
    elif mode == "exact":
        schedule = _exact_schedule(snapshot)
    else:
        schedule = {}

    return Plan(
        setup=setup,
        failures=copy.deepcopy(snapshot["failures"]) if failures else None,
        schedule=schedule,
        student=copy.deepcopy(snapshot["student"]),
        notices=notices,
    )


def _write_json(path: Path, payload: dict) -> None:
    if payload:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    else:
        path.unlink(missing_ok=True)


def write_overrides(
    schedule: dict, student: dict, schedule_path: Path, student_path: Path
) -> None:
    _write_json(schedule_path, schedule)
    _write_json(student_path, student)
