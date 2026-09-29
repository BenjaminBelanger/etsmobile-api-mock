import copy
from datetime import date, datetime

from . import (
    data_store,
    failures,
    profiles,
    scenarios,
    schedule_editor,
    sessions,
    snapshots,
    student_editor,
)
from .schedule_editor import EditorError


def _active_failures() -> dict:
    current = failures.get_config().to_dict()
    defaults = failures.FailureConfig().to_dict()
    return {key: value for key, value in current.items() if value != defaults[key]}


def _calendar(code: str) -> dict:
    base = data_store.get_base_session(code)
    return {key: base[key] for key in sessions.date_fields(base)} if base else {}


def _position() -> dict:
    active = data_store.get_base_session(data_store.ACTIVE_SESSION)
    if not active:
        return {"week": 1, "noNextSession": True}
    upcoming = (
        None
        if data_store.NO_NEXT_SESSION
        else data_store.get_base_session(data_store.NEXT_SESSION)
    )
    return snapshots.position(active, upcoming, date.today())


def _week_count() -> int | None:
    active = data_store.get_base_session(data_store.ACTIVE_SESSION)
    return sessions.week_count(active) if active else None


def capture(name: str) -> dict:
    active = data_store.ACTIVE_SESSION
    overrides = data_store._load_overrides()
    codes = set(overrides) | {
        code
        for code in (active, data_store.NEXT_SESSION)
        if data_store.get_session_courses(code)
    }
    saved = {}
    for code in sorted(codes, key=sessions.session_rank):
        entry = overrides.get(code) or {
            "courses": data_store.get_session_courses(code),
            "trash": [],
        }
        record = {"calendar": _calendar(code)}
        record["courses"] = copy.deepcopy(entry.get("courses", []))
        record["trash"] = copy.deepcopy(entry.get("trash", []))
        if entry.get("dates"):
            record["dates"] = dict(entry["dates"])
        saved[code] = record

    return snapshots.validate(
        {
            "format": snapshots.FORMAT,
            "name": name,
            "savedAt": datetime.now().isoformat(timespec="minutes"),
            "anchor": {
                "session": active,
                "date": date.today().isoformat(),
                **_position(),
            },
            "setup": snapshots.without_calendar(
                snapshots.setup_from_env(data_store.setup_env())
            ),
            "failures": _active_failures(),
            "sessions": saved,
            "student": data_store.load_student_overrides(),
        }
    )


def current() -> dict:
    return {
        "session": data_store.ACTIVE_SESSION,
        "nextSession": data_store.NEXT_SESSION,
        "weeks": _week_count(),
        "position": _position(),
        "setup": snapshots.setup_from_env(data_store.setup_env()),
        "failures": _active_failures(),
    }


def get_state() -> dict:
    return {"snapshots": snapshots.list_all(), "current": current()}


def save(name: str, overwrite: bool = False) -> dict:
    snapshot = capture(snapshots.clean_name(name))
    snapshot_id = snapshots.write(snapshot, overwrite=overwrite)
    return {**get_state(), "saved": snapshot_id}


def import_snapshot(raw, overwrite: bool = False) -> dict:
    snapshot_id = snapshots.write(raw, overwrite=overwrite)
    return {**get_state(), "saved": snapshot_id}


def import_code(code: str, overwrite: bool = False) -> dict:
    return import_snapshot(snapshots.decode(code), overwrite)


def share_code(snapshot_id: str) -> dict:
    return {"code": snapshots.encode(snapshots.read(snapshot_id))}


def delete(snapshot_id: str) -> dict:
    snapshots.delete(snapshot_id)
    return get_state()


def _check_setup(setup: dict) -> None:
    if setup["profile"] not in profiles.get_valid_profiles():
        raise EditorError(f"Unknown profile '{setup['profile']}'")
    scenario = setup.get("scenario") or snapshots.DEFAULT_SCENARIO
    if scenario not in scenarios.get_valid_scenarios():
        raise EditorError(f"Unknown scenario '{scenario}'")


def _apply(setup_env, schedule, student, failure_config) -> None:
    data_store.set_setup(setup_env)
    snapshots.write_overrides(
        schedule,
        student,
        data_store.overrides_path(),
        data_store.student_overrides_path(),
    )
    failures.reset_config()
    failures.update_config(failures.FailureConfigUpdate(**failure_config))
    data_store.reload()


def load(snapshot_id: str, mode: str = snapshots.DEFAULT_DATE_MODE) -> dict:
    snapshot = snapshots.read(snapshot_id)
    with schedule_editor._lock, student_editor._lock:
        previous = (
            data_store.runtime_setup(),
            data_store._load_overrides(),
            data_store.load_student_overrides(),
            failures.get_config().to_dict(),
        )
        try:
            plan = snapshots.plan(snapshot, mode)
            _check_setup(plan.setup)
            _apply(
                snapshots.setup_to_env(plan.setup),
                plan.schedule,
                plan.student,
                plan.failures,
            )
        except ValueError as exc:
            _apply(*previous)
            raise EditorError(f"Could not load '{snapshot['name']}': {exc}") from exc
        finally:
            schedule_editor.clear_cache()
            student_editor.clear_history()
    return {**get_state(), "notices": plan.notices}
