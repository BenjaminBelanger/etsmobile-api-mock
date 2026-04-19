"""Runtime failure injection (latency, errors, auth, malformed responses)."""

import asyncio
import os
import random
from dataclasses import dataclass, field

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ._env import env_bool

API_PREFIX = "/api/"
_ENDPOINT_PREFIX = "/api/Etudiant/"
_DEFAULT_TIMEOUT_S = 60.0


@dataclass
class FailureConfig:
    latency_ms: tuple[int, int] = (0, 0)
    error_rate: float = 0.0
    fail_endpoints: set[str] = field(default_factory=set)
    timeout_endpoints: set[str] = field(default_factory=set)
    timeout_duration_s: float = _DEFAULT_TIMEOUT_S
    malformed: bool = False
    auth_required: bool = False

    def is_default(self) -> bool:
        return (
            self.latency_ms == (0, 0)
            and self.error_rate == 0.0
            and not self.fail_endpoints
            and not self.timeout_endpoints
            and self.timeout_duration_s == _DEFAULT_TIMEOUT_S
            and not self.malformed
            and not self.auth_required
        )

    def to_dict(self) -> dict:
        lo, hi = self.latency_ms
        latency = lo if lo == hi else f"{lo}-{hi}"
        return {
            "latencyMs": latency,
            "errorRate": self.error_rate,
            "failEndpoints": sorted(self.fail_endpoints),
            "timeoutEndpoints": sorted(self.timeout_endpoints),
            "timeoutDurationS": self.timeout_duration_s,
            "malformed": self.malformed,
            "authRequired": self.auth_required,
        }


_config = FailureConfig()


def get_config() -> FailureConfig:
    return _config


def reset_config() -> None:
    global _config
    _config = FailureConfig()


def parse_latency(raw) -> tuple[int, int]:
    """Parse an int or 'min-max' string into a (min, max) ms range."""
    if raw is None or raw == "":
        return (0, 0)
    if isinstance(raw, int):
        if raw < 0:
            raise ValueError(f"latency must be >= 0, got {raw}")
        return (raw, raw)
    text = str(raw).strip()
    if not text:
        return (0, 0)
    if "-" in text:
        lo_s, hi_s = text.split("-", 1)
        lo, hi = int(lo_s), int(hi_s)
    else:
        lo = hi = int(text)
    if lo < 0 or hi < lo:
        raise ValueError(f"invalid latency range: {raw!r}")
    return (lo, hi)


def parse_endpoint_set(raw) -> set[str]:
    if raw is None:
        return set()
    if isinstance(raw, (list, tuple, set)):
        return {str(e).strip() for e in raw if str(e).strip()}
    return {e.strip() for e in str(raw).split(",") if e.strip()}


def endpoint_name(path: str) -> str:
    if path.startswith(_ENDPOINT_PREFIX):
        return path[len(_ENDPOINT_PREFIX) :].split("/", 1)[0]
    return path.lstrip("/").split("/", 1)[0]


def _matches(name: str, endpoints: set[str]) -> bool:
    return "*" in endpoints or name in endpoints


def load_from_env() -> FailureConfig:
    global _config
    cfg = FailureConfig()

    if "LATENCY_MS" in os.environ:
        try:
            cfg.latency_ms = parse_latency(os.environ["LATENCY_MS"])
        except ValueError:
            pass

    if "ERROR_RATE" in os.environ:
        try:
            r = float(os.environ["ERROR_RATE"])
            if 0.0 <= r <= 1.0:
                cfg.error_rate = r
        except ValueError:
            pass

    cfg.fail_endpoints = parse_endpoint_set(os.environ.get("FAIL_ENDPOINTS", ""))
    cfg.timeout_endpoints = parse_endpoint_set(os.environ.get("TIMEOUT_ENDPOINTS", ""))

    if "TIMEOUT_DURATION_S" in os.environ:
        try:
            d = float(os.environ["TIMEOUT_DURATION_S"])
            if d >= 0.0:
                cfg.timeout_duration_s = d
        except ValueError:
            pass

    cfg.malformed = env_bool("MALFORMED")
    cfg.auth_required = env_bool("AUTH_REQUIRED")

    _config = cfg
    return _config


class FailureConfigUpdate(BaseModel):
    latencyMs: int | str | None = None
    errorRate: float | None = Field(default=None, ge=0.0, le=1.0)
    failEndpoints: list[str] | None = None
    timeoutEndpoints: list[str] | None = None
    timeoutDurationS: float | None = Field(default=None, ge=0.0)
    malformed: bool | None = None
    authRequired: bool | None = None

    model_config = {"extra": "forbid"}


def update_config(payload: FailureConfigUpdate) -> FailureConfig:
    global _config
    data = payload.model_dump(exclude_unset=True)

    if "latencyMs" in data:
        _config.latency_ms = parse_latency(data["latencyMs"])
    if "errorRate" in data:
        _config.error_rate = float(data["errorRate"])
    if "failEndpoints" in data:
        _config.fail_endpoints = parse_endpoint_set(data["failEndpoints"])
    if "timeoutEndpoints" in data:
        _config.timeout_endpoints = parse_endpoint_set(data["timeoutEndpoints"])
    if "timeoutDurationS" in data:
        _config.timeout_duration_s = float(data["timeoutDurationS"])
    if "malformed" in data:
        _config.malformed = bool(data["malformed"])
    if "authRequired" in data:
        _config.auth_required = bool(data["authRequired"])

    return _config


async def _maybe_sleep_latency(cfg: FailureConfig) -> None:
    lo, hi = cfg.latency_ms
    if hi <= 0:
        return
    ms = random.randint(lo, hi) if hi > lo else lo
    if ms > 0:
        await asyncio.sleep(ms / 1000.0)


async def _truncate_response(response: Response) -> Response:
    body = b""
    async for chunk in response.body_iterator:
        body += chunk
    truncated = body[: max(1, len(body) // 2)] if len(body) > 1 else body
    headers = {
        k: v for k, v in response.headers.items() if k.lower() != "content-length"
    }
    return Response(
        content=truncated,
        status_code=response.status_code,
        headers=headers,
        media_type=response.media_type,
    )


async def failure_middleware(request: Request, call_next):
    path = request.url.path
    if not path.startswith(API_PREFIX):
        return await call_next(request)

    cfg = _config
    name = endpoint_name(path)

    if cfg.auth_required and not request.headers.get("authorization", "").strip():
        return JSONResponse({"error": "Authentification requise."}, status_code=401)

    if _matches(name, cfg.fail_endpoints):
        return JSONResponse(
            {"error": f"Endpoint '{name}' is configured to fail."},
            status_code=503,
        )

    if _matches(name, cfg.timeout_endpoints):
        await asyncio.sleep(cfg.timeout_duration_s)
        return JSONResponse({"error": f"Endpoint '{name}' timed out."}, status_code=504)

    if cfg.error_rate > 0.0 and random.random() < cfg.error_rate:
        return JSONResponse({"error": "Random failure injected."}, status_code=500)

    await _maybe_sleep_latency(cfg)

    response = await call_next(request)

    if cfg.malformed and 200 <= response.status_code < 300:
        response = await _truncate_response(response)

    return response


router = APIRouter(prefix="/admin/failures", tags=["admin"])


@router.get("")
def get_failures():
    return _config.to_dict()


@router.patch("")
def patch_failures(payload: FailureConfigUpdate):
    try:
        update_config(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _config.to_dict()


@router.delete("")
def delete_failures():
    reset_config()
    return _config.to_dict()
