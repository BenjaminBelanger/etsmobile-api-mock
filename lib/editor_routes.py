"""Routes for the schedule editor UI: JSON API under /editor/api and the SPA."""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import schedule_editor
from ._paths import ROOT

WEB_DIR = ROOT / "web"

router = APIRouter(prefix="/editor")


class MoveBody(BaseModel):
    session: str
    blockId: str
    jour: str
    heureDebut: str


class ResizeBody(BaseModel):
    session: str
    blockId: str
    heureDebut: str
    heureFin: str


class CourseBody(BaseModel):
    session: str
    courseId: str


class AddBody(BaseModel):
    session: str
    sigle: str
    titre: str = ""
    jour: str
    heureDebut: str
    heureFin: str
    kind: str = "cours"


class SessionBody(BaseModel):
    session: str


def _guard(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except schedule_editor.EditorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
def editor_index():
    return FileResponse(WEB_DIR / "index.html")


@router.get("/api/state")
def state(session: str = Query("")):
    return _guard(schedule_editor.get_state, session)


@router.post("/api/block/move")
def move(body: MoveBody):
    return _guard(
        schedule_editor.move_block,
        body.session,
        body.blockId,
        body.jour,
        body.heureDebut,
    )


@router.post("/api/block/resize")
def resize(body: ResizeBody):
    return _guard(
        schedule_editor.resize_block,
        body.session,
        body.blockId,
        body.heureDebut,
        body.heureFin,
    )


@router.post("/api/course/delete")
def delete(body: CourseBody):
    return _guard(schedule_editor.delete_course, body.session, body.courseId)


@router.post("/api/course/restore")
def restore(body: CourseBody):
    return _guard(schedule_editor.restore_course, body.session, body.courseId)


@router.post("/api/course/add")
def add(body: AddBody):
    return _guard(
        schedule_editor.add_course,
        body.session,
        body.sigle,
        body.titre,
        body.jour,
        body.heureDebut,
        body.heureFin,
        body.kind,
    )


@router.post("/api/undo")
def undo(body: SessionBody):
    return _guard(schedule_editor.undo, body.session)


@router.post("/api/redo")
def redo(body: SessionBody):
    return _guard(schedule_editor.redo, body.session)


@router.post("/api/reset")
def reset(body: SessionBody):
    return _guard(schedule_editor.reset_session, body.session)
