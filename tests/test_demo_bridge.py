import asyncio
import importlib.util
import json

import anyio.to_thread
import pytest

from lib._paths import ROOT

SPEC = importlib.util.spec_from_file_location("bridge", ROOT / "web" / "demo" / "bridge.py")
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)

JSON_HEADERS = json.dumps([["content-type", "application/json"]])


@pytest.fixture
def app():
    import main

    return main.app


def call(app, method, url, body="", headers=JSON_HEADERS):
    response = json.loads(asyncio.run(bridge.handle(app, method, url, headers, body)))
    return response["status"], response


def test_the_bridge_serves_the_editor_state(app):
    status, response = call(app, "GET", "/editor/api/state?session=H2026")

    assert status == 200
    assert ["content-type", "application/json"] in response["headers"]
    assert json.loads(response["body"])["session"] == "H2026"


def test_the_bridge_decodes_an_encoded_session(app):
    status, response = call(app, "GET", "/editor/api/state?session=%C3%892024")

    assert status == 200
    assert json.loads(response["body"])["session"] == "É2024"


def test_the_bridge_passes_the_request_body(app):
    status, response = call(app, "PATCH", "/admin/failures", json.dumps({"latencyMs": "100-200"}))

    assert status == 200
    assert json.loads(response["body"])["latencyMs"] == "100-200"


def test_the_bridge_returns_validation_errors(app):
    status, _ = call(app, "POST", "/editor/api/block/move", json.dumps({"session": "H2026"}))

    assert status == 422


def test_the_bridge_runs_the_failure_middleware(app):
    call(app, "PATCH", "/admin/failures", json.dumps({"failEndpoints": ["listeCours"]}))

    status, response = call(app, "GET", "/api/Etudiant/listeCours", headers="[]")

    assert status == 503
    assert "listeCours" in json.loads(response["body"])["error"]


def test_the_bridge_answers_a_crash_with_a_server_error(app, monkeypatch):
    from lib import schedule_editor

    def crash(_session):
        raise RuntimeError("boom")

    monkeypatch.setattr(schedule_editor, "get_state", crash)

    status, response = call(app, "GET", "/editor/api/state?session=H2026")

    assert status == 500
    assert response["body"] == "Internal Server Error"


def test_blocking_calls_run_inline():
    assert asyncio.run(bridge.run_sync_inline(lambda a, b: a + b, 2, 3)) == 5


def test_loading_the_app_stops_it_from_starting_threads(app, monkeypatch):
    monkeypatch.setattr(anyio.to_thread, "run_sync", anyio.to_thread.run_sync)

    assert bridge.load_app() is app
    assert anyio.to_thread.run_sync is bridge.run_sync_inline
