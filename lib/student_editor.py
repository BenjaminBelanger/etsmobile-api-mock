import json
import math
import threading

from . import data_store
from .schedule_editor import EditorError

MAX_HISTORY = 100
AMOUNT_FIELDS = {"soldeTotal"}

_REVERT = object()

_lock = threading.RLock()
_undo: list[dict] = []
_redo: list[dict] = []


def clear_history() -> None:
    with _lock:
        _undo.clear()
        _redo.clear()


def get_state() -> dict:
    with _lock:
        base = data_store.get_student_info(base=True)
        current = data_store.get_student_info()
        return {
            "student": [
                {"key": key, "value": current[key], "modified": current[key] != value}
                for key, value in base.items()
            ],
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


def _commit(payload: dict) -> None:
    _undo.append(data_store.load_student_overrides())
    if len(_undo) > MAX_HISTORY:
        del _undo[0]
    _redo.clear()
    _write(payload)


def _format_amount(value: str) -> str:
    text = value.replace("$", "").replace("\u00a0", "").replace(" ", "")
    try:
        amount = float(text.replace(",", "."))
    except ValueError as exc:
        raise EditorError(f"Invalid amount '{value}'") from exc
    if not math.isfinite(amount):
        raise EditorError(f"Invalid amount '{value}'")
    return f"{amount:.2f}".replace(".", ",") + "$"


def _normalize(field: str, base_value, value):
    if isinstance(base_value, bool):
        return _REVERT if value is None else bool(value)
    text = "" if value is None else str(value).strip()
    if not text:
        return _REVERT
    if field in AMOUNT_FIELDS:
        return _format_amount(text)
    return text


def set_field(field: str, value) -> dict:
    with _lock:
        base = data_store.get_student_info(base=True)
        if field not in base:
            raise EditorError(f"Unknown field '{field}'")
        resolved = _normalize(field, base[field], value)
        wanted = base[field] if resolved is _REVERT else resolved
        edits = data_store.load_student_overrides()
        if wanted != edits.get(field, base[field]):
            changed = {key: value for key, value in edits.items() if key != field}
            if wanted != base[field]:
                changed[field] = wanted
            _commit(changed)
    return get_state()


def _step(source: list, target: list, empty: str) -> dict:
    with _lock:
        if not source:
            raise EditorError(empty)
        target.append(data_store.load_student_overrides())
        _write(source.pop())
    return get_state()


def undo() -> dict:
    return _step(_undo, _redo, "Nothing to undo")


def redo() -> dict:
    return _step(_redo, _undo, "Nothing to redo")


def reset() -> dict:
    with _lock:
        if not data_store.load_student_overrides():
            raise EditorError("Nothing to reset")
        _commit({})
    return get_state()
