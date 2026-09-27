"""FastAPI app entrypoint."""

import logging
import math
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse

from lib import call_log, failures
from lib._paths import ROOT
from lib.data_store import (
    ACTIVE_SESSION,
    BETWEEN_SESSIONS,
    DEFAULT_SCENARIO,
    GENERATION_CONFIG,
    NEXT_SESSION,
    NO_NEXT_SESSION,
    PROFILE_NAME,
    SCENARIO_NAME,
    SEMESTER_GAP,
    reload as reload_data,
)
from lib.editor_routes import EditorAssets, router as editor_router
from lib.routes import router
from lib.schedule_editor import clear_cache as clear_editor_cache
from lib.student_editor import clear_history as clear_student_history

failures.load_from_env()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger = logging.getLogger("uvicorn")
    logger.info("Active session: %s (computed from current date)", ACTIVE_SESSION)
    logger.info("Active profile: %s", PROFILE_NAME)
    if SCENARIO_NAME != DEFAULT_SCENARIO:
        logger.info("Active scenario: %s", SCENARIO_NAME)
    if BETWEEN_SESSIONS:
        logger.info("Between sessions: %s ended yesterday", ACTIVE_SESSION)
    if NO_NEXT_SESSION:
        logger.info("No session after %s", ACTIVE_SESSION)
    elif SEMESTER_GAP is not None:
        logger.info("Semester gap: %d days off before %s", SEMESTER_GAP, NEXT_SESSION)
    if GENERATION_CONFIG:
        days = GENERATION_CONFIG.get("allowedDays", "all")
        logger.info(
            "Course generation: %d courses, days=%s",
            GENERATION_CONFIG["count"],
            days if days else "all",
        )
    failure_cfg = failures.get_config()
    if not failure_cfg.is_default():
        logger.info("Failure injection: %s", failure_cfg.to_dict())
    yield


app = FastAPI(
    title="ETSMobileAPI - Local Mock",
    description="Local mock server for the ETSMobileAPI (Signets). "
    "Returns realistic sample data for a fictional ETS student.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


def _json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
):
    return JSONResponse(
        {"detail": _json_safe(jsonable_encoder(exc.errors()))}, status_code=422
    )


app.middleware("http")(failures.failure_middleware)
app.add_middleware(call_log.CallLogMiddleware)

app.include_router(router)
app.include_router(failures.router)
app.include_router(call_log.router)
app.include_router(editor_router)
app.mount(
    "/editor/assets",
    EditorAssets(directory=ROOT / "web" / "assets"),
    name="editor-assets",
)


@app.get("/")
async def root_redirect():
    return RedirectResponse(url="/editor")


@app.post("/reload")
async def reload_seed_data():
    reload_data()
    clear_editor_cache()
    clear_student_history()
    return {"status": "ok"}
