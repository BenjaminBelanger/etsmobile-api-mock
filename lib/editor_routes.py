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


class OccurrenceSetBody(BaseModel):
    session: str
    blockId: str
    date: str
    jour: str
    heureDebut: str
    heureFin: str


class OccurrenceBody(BaseModel):
    session: str
    blockId: str
    date: str


class EvaluationBody(BaseModel):
    session: str
    courseId: str
    index: int


class EvaluationSetBody(BaseModel):
    session: str
    courseId: str
    index: int
    field: str
    value: bool | str | None = None


class EvaluationMoveBody(BaseModel):
    session: str
    courseId: str
    index: int
    toIndex: int


class ExamBody(BaseModel):
    session: str
    courseId: str
    date: str | None = None
    heureDebut: str | None = None
    heureFin: str | None = None
    local: str | None = None


class CoteBody(BaseModel):
    session: str
    courseId: str
    cote: str = ""


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


@router.post("/api/occurrence/set")
def occurrence_set(body: OccurrenceSetBody):
    return _guard(
        schedule_editor.set_occurrence,
        body.session,
        body.blockId,
        body.date,
        body.jour,
        body.heureDebut,
        body.heureFin,
    )


@router.post("/api/occurrence/cancel")
def occurrence_cancel(body: OccurrenceBody):
    return _guard(
        schedule_editor.cancel_occurrence, body.session, body.blockId, body.date
    )


@router.post("/api/occurrence/reset")
def occurrence_reset(body: OccurrenceBody):
    return _guard(
        schedule_editor.reset_occurrence, body.session, body.blockId, body.date
    )


@router.post("/api/evaluation/set")
def evaluation_set(body: EvaluationSetBody):
    return _guard(
        schedule_editor.set_evaluation,
        body.session,
        body.courseId,
        body.index,
        body.field,
        body.value,
    )


@router.post("/api/evaluation/add")
def evaluation_add(body: CourseBody):
    return _guard(schedule_editor.add_evaluation, body.session, body.courseId)


@router.post("/api/evaluation/delete")
def evaluation_delete(body: EvaluationBody):
    return _guard(
        schedule_editor.delete_evaluation, body.session, body.courseId, body.index
    )


@router.post("/api/evaluation/move")
def evaluation_move(body: EvaluationMoveBody):
    return _guard(
        schedule_editor.move_evaluation,
        body.session,
        body.courseId,
        body.index,
        body.toIndex,
    )


@router.post("/api/grades/reset")
def grades_reset(body: CourseBody):
    return _guard(schedule_editor.reset_grades, body.session, body.courseId)


@router.post("/api/course/cote")
def course_cote(body: CoteBody):
    return _guard(schedule_editor.set_cote, body.session, body.courseId, body.cote)


@router.post("/api/exam/set")
def exam_set(body: ExamBody):
    return _guard(
        schedule_editor.set_final_exam,
        body.session,
        body.courseId,
        body.date,
        body.heureDebut,
        body.heureFin,
        body.local,
    )


@router.post("/api/exam/reset")
def exam_reset(body: CourseBody):
    return _guard(schedule_editor.reset_final_exam, body.session, body.courseId)


@router.post("/api/undo")
def undo(body: SessionBody):
    return _guard(schedule_editor.undo, body.session)


@router.post("/api/redo")
def redo(body: SessionBody):
    return _guard(schedule_editor.redo, body.session)


@router.post("/api/reset")
def reset(body: SessionBody):
    return _guard(schedule_editor.reset_session, body.session)
