"""FastAPI app entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from lib import failures
from lib.data_store import (
    ACTIVE_SESSION,
    DEFAULT_SCENARIO,
    GENERATION_CONFIG,
    PROFILE_NAME,
    SCENARIO_NAME,
    reload as reload_data,
)
from lib.routes import router

failures.load_from_env()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger = logging.getLogger("uvicorn")
    logger.info("Active session: %s (computed from current date)", ACTIVE_SESSION)
    logger.info("Active profile: %s", PROFILE_NAME)
    if SCENARIO_NAME != DEFAULT_SCENARIO:
        logger.info("Active scenario: %s", SCENARIO_NAME)
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


app.middleware("http")(failures.failure_middleware)

app.include_router(router)
app.include_router(failures.router)


@app.post("/reload")
async def reload_seed_data():
    reload_data()
    return {"status": "ok"}
