import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib import data_store, i18n, schedule_editor  # noqa: E402

SESSION = "H2026"

_REAL_OVERRIDES = data_store.overrides_path()


@pytest.fixture(autouse=True)
def default_locale(monkeypatch):
    for name in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE", i18n.LANG_ENV):
        monkeypatch.delenv(name, raising=False)
    i18n.set_locale(i18n.DEFAULT_LOCALE)
    yield
    i18n.set_locale(i18n.DEFAULT_LOCALE)


@pytest.fixture(autouse=True)
def sandbox_overrides(tmp_path, monkeypatch):
    sandbox = tmp_path / "schedule_overrides.json"
    monkeypatch.setattr(data_store, "overrides_path", lambda: sandbox)
    assert data_store.overrides_path() != _REAL_OVERRIDES
    schedule_editor.clear_cache()
    data_store.reload()
    yield sandbox
    schedule_editor.clear_cache()
    monkeypatch.undo()
    data_store.reload()


@pytest.fixture
def session():
    return SESSION


def course(session_code, course_id):
    doc = schedule_editor._load_doc(session_code)
    for entry in doc["courses"]:
        if schedule_editor._course_key(entry) == course_id:
            return entry
    raise AssertionError(f"No course {course_id} in {session_code}")


def overrides(session_code, course_id, block=None):
    stored = course(session_code, course_id).get("occurrenceOverrides", [])
    if block is None:
        return stored
    return [ov for ov in stored if ov.get("block") == block]


def user_overrides(session_code, course_id, block=None):
    return [ov for ov in overrides(session_code, course_id, block) if "source" not in ov]


def rows(state, block_id, date_from=None, date_to=None):
    return [
        row
        for row in state["occurrences"]
        if row["blockId"] == block_id
        and (date_from is None or row["date"] >= date_from)
        and (date_to is None or row["date"] <= date_to)
    ]


def week_of(iso):
    day = date.fromisoformat(iso)
    monday = day - timedelta(days=day.isoweekday() - 1)
    return monday.isoformat(), (monday + timedelta(days=5)).isoformat()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    import main

    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clean_failures():
    from lib import failures

    failures.reset_config()
    yield
    failures.reset_config()


@pytest.fixture
def reconfigure(monkeypatch):
    def apply(**env):
        for name, value in env.items():
            if value is None:
                monkeypatch.delenv(name, raising=False)
            else:
                monkeypatch.setenv(name, str(value))
        schedule_editor.clear_cache()
        data_store.reload()

    return apply


def xml_root(response):
    from xml.etree.ElementTree import fromstring

    return fromstring(response.text)
