import time
from collections import deque
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from starlette.datastructures import QueryParams

from .failures import API_PREFIX, endpoint_name, injected_failures

CAPACITY = 100_000

_entries: deque[dict] = deque(maxlen=CAPACITY)
_next_id = 1


def _append(fields: dict) -> dict:
    global _next_id
    entry = {
        "id": _next_id,
        "time": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        **fields,
    }
    _next_id += 1
    _entries.append(entry)
    return entry


def start_call(scope) -> dict:
    path = scope["path"]
    return _append(
        {
            "kind": "call",
            "endpoint": endpoint_name(path),
            "path": path,
            "params": dict(QueryParams(scope.get("query_string", b""))),
            "status": None,
            "durationMs": None,
            "bytes": None,
            "failures": injected_failures(scope),
        }
    )


def finish_call(entry: dict, status: int, size: int, seconds: float) -> None:
    entry.update(status=status, bytes=size, durationMs=round(seconds * 1000, 1))


def add_marker(label: str) -> dict:
    return _append({"kind": "marker", "label": label})


def remove_marker(entry_id: int) -> dict | None:
    for entry in _entries:
        if entry["id"] == entry_id and entry["kind"] == "marker":
            _entries.remove(entry)
            return entry
    return None


def clear() -> None:
    _entries.clear()


def snapshot(after: int = 0) -> dict:
    return {
        "entries": [entry for entry in _entries if entry["id"] > after],
        "firstId": _entries[0]["id"] if _entries else _next_id,
    }


class CallLogMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith(API_PREFIX):
            await self.app(scope, receive, send)
            return

        entry = start_call(scope)
        started = time.perf_counter()
        sent = {"status": 500, "bytes": 0}

        async def observe(message):
            if message["type"] == "http.response.start":
                sent["status"] = message["status"]
            elif message["type"] == "http.response.body":
                sent["bytes"] += len(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, receive, observe)
        finally:
            finish_call(
                entry, sent["status"], sent["bytes"], time.perf_counter() - started
            )


router = APIRouter(prefix="/admin/calls", tags=["admin"])


@router.get("")
async def get_calls(after: int = 0):
    return snapshot(after)


@router.delete("")
async def delete_calls():
    clear()
    return snapshot()


class MarkerCreate(BaseModel):
    label: str = Field(min_length=1, max_length=120)

    model_config = {"extra": "forbid", "str_strip_whitespace": True}


@router.post("/marker")
async def post_marker(payload: MarkerCreate):
    return add_marker(payload.label)


@router.delete("/marker/{entry_id}")
async def delete_marker(entry_id: int):
    removed = remove_marker(entry_id)
    if removed is None:
        raise HTTPException(status_code=404, detail="Marqueur introuvable")
    return removed
