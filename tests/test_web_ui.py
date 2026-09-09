import json
import shutil
import subprocess
from pathlib import Path

import pytest

from lib import schedule_editor
from lib._paths import ROOT

WEB = ROOT / "web"
UI_TESTS = WEB / "tests"
FIXTURE = UI_TESTS / "fixtures" / "state.json"
SESSION = "H2026"


def fixture_state():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def keys_of(value):
    return set(value) if isinstance(value, dict) else set()


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.skipif(
    not (WEB / "node_modules" / "jsdom").exists(),
    reason="run 'npm install' in web/ to enable the editor UI tests",
)
def test_the_editor_ui_suite_passes():
    result = subprocess.run(
        ["node", "--test", "tests/**/*.test.mjs"],
        cwd=WEB,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "# fail 0" in result.stdout


def test_the_ui_fixture_matches_the_state_the_server_sends():
    served = schedule_editor.get_state(SESSION)
    fixture = fixture_state()

    assert keys_of(fixture) == keys_of(served)
    assert keys_of(fixture["meta"]) == keys_of(served["meta"])
    assert keys_of(fixture["meta"]["semester"]) == keys_of(served["meta"]["semester"])
    assert keys_of(fixture["meta"]["semester"]["weeks"][0]) == keys_of(
        served["meta"]["semester"]["weeks"][0]
    )
    assert keys_of(fixture["meta"]["catalog"][0]) == keys_of(
        served["meta"]["catalog"][0]
    )
    assert keys_of(fixture["meta"]["days"][0]) == keys_of(served["meta"]["days"][0])


def test_the_ui_fixture_courses_match_the_served_shape():
    served = schedule_editor.get_state(SESSION)["courses"][0]
    fixture = fixture_state()["courses"][0]

    assert keys_of(fixture) == keys_of(served)
    assert keys_of(fixture["blocks"][0]) == keys_of(served["blocks"][0])
    assert keys_of(fixture["evaluations"][0]) == keys_of(served["evaluations"][0])
    assert keys_of(fixture["summary"]) == keys_of(served["summary"])
    assert keys_of(fixture["exam"]) == keys_of(served["exam"])


def test_the_ui_fixture_occurrences_match_the_served_shape():
    served = schedule_editor.get_state(SESSION)["occurrences"]
    fixture = fixture_state()["occurrences"]

    assert keys_of(fixture[0]) == keys_of(served[0])
    exam_served = next(row for row in served if row["kind"] == "exam")
    exam_fixture = next(row for row in fixture if row["kind"] == "exam")
    assert keys_of(exam_fixture) == keys_of(exam_served)
    assert {row["kind"] for row in fixture} <= {row["kind"] for row in served}


def test_the_ui_fixture_trash_matches_the_served_shape(session):
    served = schedule_editor.delete_course(session, "LOG430-02")["trash"][0]
    assert keys_of(served) == {"courseId", "sigle", "groupe", "titre"}


def test_the_editor_page_holds_every_element_the_script_looks_up():
    page = (WEB / "index.html").read_text(encoding="utf-8")
    script = (WEB / "assets" / "app.js").read_text(encoding="utf-8")

    for line in script.splitlines():
        if "document.getElementById(" not in line:
            continue
        element_id = line.split('document.getElementById("')[1].split('"')[0]
        assert f'id="{element_id}"' in page, f"#{element_id} is missing from index.html"


def test_the_editor_script_only_talks_to_routes_the_server_serves():
    from lib import editor_routes

    script = (WEB / "assets" / "app.js").read_text(encoding="utf-8")
    served = {
        route.path.replace("/editor/api", "")
        for route in editor_routes.router.routes
        if route.path.startswith("/editor/api")
    }

    called = set()
    for part in script.split('apiPost("')[1:]:
        called.add(part.split('"')[0])

    assert called
    assert called <= served, f"the UI calls routes the server does not serve: {called - served}"
