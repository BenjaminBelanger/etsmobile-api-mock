import copy
import json
import math
import threading

from . import data_store, sessions
from .resource_specs import SESSIONS
from .schedule_editor import EditorError, _validate_date

MAX_HISTORY = 100
AMOUNT_FIELDS = {"soldeTotal"}

_REVERT = object()

_lock = threading.RLock()
_undo: list[tuple[dict, str | None]] = []
_redo: list[tuple[dict, str | None]] = []


def clear_history() -> None:
    with _lock:
        _undo.clear()
        _redo.clear()


def _served_sessions() -> list[str]:
    codes = {entry["abrege"] for entry in data_store.load(SESSIONS.filename)}
    return sorted(codes, key=sessions.session_rank, reverse=True)


def _resolve_session(session: str, served: list[str]) -> str:
    if session in served:
        return session
    if data_store.ACTIVE_SESSION in served:
        return data_store.ACTIVE_SESSION
    return served[0] if served else ""


def _current_session(code: str) -> dict:
    for entry in data_store.load(SESSIONS.filename):
        if entry["abrege"] == code:
            return entry
    return {}


def _student_rows() -> list[dict]:
    base = data_store.get_student_info(base=True)
    current = data_store.get_student_info()
    return [
        {"key": key, "value": current[key], "modified": current[key] != value}
        for key, value in base.items()
    ]


def _date_rows(code: str) -> list[dict]:
    base = data_store.get_base_session(code) or {}
    current = _current_session(code)
    return [
        {
            "key": key,
            "value": current.get(key, base[key]),
            "modified": current.get(key, base[key]) != base[key],
        }
        for key in sessions.date_fields(base)
    ]


def get_state(session: str = "") -> dict:
    with _lock:
        served = _served_sessions()
        session = _resolve_session(session, served)
        return {
            "session": session,
            "sessions": served,
            "dates": _date_rows(session) if session else [],
            "student": _student_rows(),
            "canUndo": bool(_undo),
            "canRedo": bool(_redo),
            "canReset": bool(data_store.load_student_overrides()),
        }


def _write(payload: dict) -> None:
    path = data_store.student_overrides_path()
    if payload:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    else:
        path.unlink(missing_ok=True)
    data_store.reload()


def _prune(payload: dict) -> dict:
    dates = {code: edits for code, edits in payload.get("sessions", {}).items() if edits}
    pruned = {"student": payload.get("student", {}), "sessions": dates}
    return {key: value for key, value in pruned.items() if value}


def _commit(payload: dict, session: str | None) -> None:
    previous = data_store.load_student_overrides()
    _undo.append((previous, session))
    if len(_undo) > MAX_HISTORY:
        del _undo[0]
    _redo.clear()
    _write(_prune(payload))


def _apply_edit(edits: dict, key: str, value, base_value) -> bool:
    current = edits.get(key, base_value)
    wanted = base_value if value is _REVERT else value
    if wanted == current:
        return False
    if wanted == base_value:
        edits.pop(key, None)
    else:
        edits[key] = wanted
    return True


def _format_amount(value: str) -> str:
    text = value.replace("$", "").replace("\u00a0", "").replace(" ", "")
    try:
        amount = float(text.replace(",", "."))
    except ValueError as exc:
        raise EditorError(f"Invalid amount '{value}'") from exc
    if not math.isfinite(amount):
        raise EditorError(f"Invalid amount '{value}'")
    return f"{amount:.2f}".replace(".", ",") + "$"


def _normalize_student_value(field: str, base_value, value):
    if isinstance(base_value, bool):
        if value is None:
            return _REVERT
        return bool(value)
    text = "" if value is None else str(value).strip()
    if not text:
        return _REVERT
    if field in AMOUNT_FIELDS:
        return _format_amount(text)
    return text


def set_student_field(session: str, field: str, value) -> dict:
    with _lock:
        base = data_store.get_student_info(base=True)
        if field not in base:
            raise EditorError(f"Unknown field '{field}'")
        resolved = _normalize_student_value(field, base[field], value)
        payload = data_store.load_student_overrides()
        edits = copy.deepcopy(payload.get("student", {}))
        if _apply_edit(edits, field, resolved, base[field]):
            _commit({**payload, "student": edits}, None)
    return get_state(session)


def set_session_date(session: str, field: str, value: str | None) -> dict:
    with _lock:
        if session not in _served_sessions():
            raise EditorError(f"Session '{session}' not found")
        base = data_store.get_base_session(session) or {}
        if field not in sessions.date_fields(base):
            raise EditorError(f"Unknown date '{field}'")
        text = (value or "").strip()
        resolved = _validate_date(text) if text else _REVERT
        payload = data_store.load_student_overrides()
        all_dates = copy.deepcopy(payload.get("sessions", {}))
        edits = all_dates.setdefault(session, {})
        if _apply_edit(edits, field, resolved, base[field]):
            _commit({**payload, "sessions": all_dates}, session)
    return get_state(session)


def _step(source: list, target: list, session: str, empty: str) -> dict:
    with _lock:
        if not source:
            raise EditorError(empty)
        snapshot, changed = source.pop()
        target.append((data_store.load_student_overrides(), changed))
        _write(snapshot)
    return get_state(changed or session)


def undo(session: str) -> dict:
    return _step(_undo, _redo, session, "Nothing to undo")


def redo(session: str) -> dict:
    return _step(_redo, _undo, session, "Nothing to redo")


def reset(session: str) -> dict:
    with _lock:
        if not data_store.load_student_overrides():
            raise EditorError("Nothing to reset")
        _commit({}, None)
    return get_state(session)
