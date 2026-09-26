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


def _current_week() -> tuple[int | None, int | None]:
    base = data_store.get_base_session(data_store.ACTIVE_SESSION)
    if not base:
        return None, None
    week = sessions.week_index(date.fromisoformat(base["dateDebut"]), date.today())
    return week, sessions.week_count(base)


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

    week, _ = _current_week()
    return snapshots.validate(
        {
            "format": snapshots.FORMAT,
            "name": name,
            "savedAt": datetime.now().isoformat(timespec="minutes"),
            "anchor": {
                "session": active,
                "week": 1 if week is None else week,
                "date": date.today().isoformat(),
            },
            "setup": snapshots.setup_from_env(data_store.setup_env()),
            "failures": _active_failures(),
            "sessions": saved,
            "student": data_store.load_student_overrides(),
        }
    )


def current() -> dict:
    week, weeks = _current_week()
    return {
        "session": data_store.ACTIVE_SESSION,
        "week": week,
        "weeks": weeks,
        "setup": snapshots.setup_from_env(data_store.setup_env()),
        "failures": _active_failures(),
    }


def get_state() -> dict:
    return {"snapshots": snapshots.list_all(), "current": current()}


def save(name: str, scope: str, overwrite: bool = False) -> dict:
    snapshot = capture(snapshots.clean_name(name))
    snapshot_id = snapshots.write(scope, snapshot, overwrite=overwrite)
    return {**get_state(), "saved": {"scope": scope, "id": snapshot_id}}


def import_snapshot(raw, scope: str, overwrite: bool = False) -> dict:
    snapshot_id = snapshots.write(scope, raw, overwrite=overwrite)
    return {**get_state(), "saved": {"scope": scope, "id": snapshot_id}}


def delete(scope: str, snapshot_id: str) -> dict:
    snapshots.delete(scope, snapshot_id)
    return get_state()


def move(scope: str, snapshot_id: str, target: str) -> dict:
    new_id = snapshots.move(scope, snapshot_id, target)
    return {**get_state(), "saved": {"scope": target, "id": new_id}}


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
    if failure_config is not None:
        failures.reset_config()
        failures.update_config(failures.FailureConfigUpdate(**failure_config))
    data_store.reload()


def load(scope: str, snapshot_id: str, mode: str, include_failures: bool = True) -> dict:
    snapshot = snapshots.read(scope, snapshot_id)
    with schedule_editor._lock, student_editor._lock:
        previous = (
            data_store.runtime_setup(),
            data_store._load_overrides(),
            data_store.load_student_overrides(),
            failures.get_config().to_dict(),
        )
        try:
            plan = snapshots.plan(snapshot, mode, failures=include_failures)
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
