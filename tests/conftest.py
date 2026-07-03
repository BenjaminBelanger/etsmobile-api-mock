"""Shared pytest fixtures for the mock server test suite."""

import pytest
from fastapi.testclient import TestClient

from lib import data_store, failures, schedule_editor
from lib._paths import SEED
from main import app

OVERRIDES = SEED / data_store.OVERRIDES_FILENAME


def _clear_editor_state():
    schedule_editor._docs.clear()
    schedule_editor._undo.clear()
    schedule_editor._redo.clear()


def _reset_all():
    OVERRIDES.unlink(missing_ok=True)
    _clear_editor_state()
    failures.reset_config()
    data_store.reload()


@pytest.fixture()
def client():
    """A TestClient with a clean data store, editor state, and failure config."""
    _reset_all()
    with TestClient(app) as test_client:
        yield test_client
    _reset_all()


@pytest.fixture()
def active_session():
    """The session computed as active from the current date."""
    return data_store.ACTIVE_SESSION


def api(client, name, **params):
    """GET an /api/Etudiant endpoint, returning the raw response."""
    return client.get(f"/api/Etudiant/{name}", params=params or None)


def first_active_course(client, session):
    """Return (sigle, groupe) of the first course in the given session, or None."""
    body = client.get("/api/Etudiant/listeCours").json()
    for course in body["liste"]:
        if course["session"] == session:
            return course["sigle"], course["groupe"]
    return None
