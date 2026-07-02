"""Tests for the schedule editor: mutations persist and drive the mock API."""

import pytest
from fastapi.testclient import TestClient

from lib import data_store, schedule_editor
from lib._paths import SEED
from main import app

OVERRIDES = SEED / data_store.OVERRIDES_FILENAME


def _clear_editor_state():
    schedule_editor._docs.clear()
    schedule_editor._undo.clear()
    schedule_editor._redo.clear()


@pytest.fixture()
def client():
    """Fresh editor state per test; remove the override file before and after."""
    OVERRIDES.unlink(missing_ok=True)
    _clear_editor_state()
    data_store.reload()
    with TestClient(app) as test_client:
        yield test_client
    OVERRIDES.unlink(missing_ok=True)
    _clear_editor_state()
    data_store.reload()


def _state(client, session=""):
    res = client.get("/editor/api/state", params={"session": session})
    assert res.status_code == 200, res.text
    return res.json()


def _session_with_blocks(client):
    st = _state(client)
    assert st["blocks"], "active session should have generated courses"
    return st


def _dur(block):
    def m(s):
        h, mm = s.split(":")
        return int(h) * 60 + int(mm)

    return m(block["heureFin"]) - m(block["heureDebut"])


def _api_course_sigles(client, session):
    res = client.get("/api/Etudiant/listeCours")
    return [c["sigle"] for c in res.json()["liste"] if c["session"] == session]


def _api_course_keys(client, session):
    res = client.get("/api/Etudiant/listeCours")
    return [
        f"{c['sigle']}-{c['groupe']}"
        for c in res.json()["liste"]
        if c["session"] == session
    ]


def test_state_shape(client):
    st = _session_with_blocks(client)
    assert st["session"]
    assert st["session"] in st["sessions"]
    assert st["meta"]["days"][0]["jour"] == "1"
    block = st["blocks"][0]
    for key in ("id", "courseId", "sigle", "jour", "heureDebut", "heureFin", "kind"):
        assert key in block


def test_move_block_changes_day_and_time(client):
    st = _session_with_blocks(client)
    session = st["session"]
    block = st["blocks"][0]
    target_day = "6" if block["jour"] != "6" else "1"

    res = client.post(
        "/editor/api/block/move",
        json={
            "session": session,
            "blockId": block["id"],
            "jour": target_day,
            "heureDebut": "14:00",
        },
    )
    assert res.status_code == 200, res.text
    moved = next(b for b in res.json()["blocks"] if b["id"] == block["id"])
    assert moved["jour"] == target_day
    assert moved["heureDebut"] == "14:00"
    assert _dur(moved) == _dur(block)


def test_move_snaps_and_clamps(client):
    st = _session_with_blocks(client)
    block = st["blocks"][0]
    res = client.post(
        "/editor/api/block/move",
        json={
            "session": st["session"],
            "blockId": block["id"],
            "jour": block["jour"],
            "heureDebut": "07:07",
        },
    )
    moved = next(b for b in res.json()["blocks"] if b["id"] == block["id"])
    assert moved["heureDebut"] >= "08:00"
    assert int(moved["heureDebut"][3:]) % 15 == 0


def test_resize_block(client):
    st = _session_with_blocks(client)
    block = st["blocks"][0]
    res = client.post(
        "/editor/api/block/resize",
        json={
            "session": st["session"],
            "blockId": block["id"],
            "heureDebut": block["heureDebut"],
            "heureFin": "20:00",
        },
    )
    assert res.status_code == 200, res.text
    resized = next(b for b in res.json()["blocks"] if b["id"] == block["id"])
    assert resized["heureFin"] == "20:00"


def test_resize_rejects_too_short(client):
    st = _session_with_blocks(client)
    block = st["blocks"][0]
    res = client.post(
        "/editor/api/block/resize",
        json={
            "session": st["session"],
            "blockId": block["id"],
            "heureDebut": "10:00",
            "heureFin": "10:10",
        },
    )
    assert res.status_code == 400


def test_delete_and_restore(client):
    st = _session_with_blocks(client)
    session = st["session"]
    course_id = st["courses"][0]["courseId"]

    body = client.post(
        "/editor/api/course/delete",
        json={"session": session, "courseId": course_id},
    ).json()
    assert course_id not in [c["courseId"] for c in body["courses"]]
    assert course_id in [t["courseId"] for t in body["trash"]]

    body = client.post(
        "/editor/api/course/restore",
        json={"session": session, "courseId": course_id},
    ).json()
    assert course_id in [c["courseId"] for c in body["courses"]]
    assert course_id not in [t["courseId"] for t in body["trash"]]


def test_delete_reflected_in_liste_cours(client):
    st = _session_with_blocks(client)
    session = st["session"]
    course = st["courses"][0]

    assert course["courseId"] in _api_course_keys(client, session)
    client.post(
        "/editor/api/course/delete",
        json={"session": session, "courseId": course["courseId"]},
    )
    assert course["courseId"] not in _api_course_keys(client, session)


def test_move_reflected_in_horaire(client):
    st = _session_with_blocks(client)
    session = st["session"]
    block = st["blocks"][0]
    target_day = "6" if block["jour"] != "6" else "1"

    client.post(
        "/editor/api/block/move",
        json={
            "session": session,
            "blockId": block["id"],
            "jour": target_day,
            "heureDebut": "15:00",
        },
    )
    res = client.get("/api/Etudiant/listeHoraireEtProf", params={"session": session})
    activities = res.json()["listeActivites"]
    match = [
        a
        for a in activities
        if a["sigle"] == block["sigle"]
        and a["groupe"] == block["groupe"]
        and a.get("activitePrincipale") == "Oui"
    ]
    assert match
    assert match[0]["jour"] == target_day
    assert match[0]["heureDebut"] == "15:00"


def test_add_course(client):
    st = _session_with_blocks(client)
    session = st["session"]
    res = client.post(
        "/editor/api/course/add",
        json={
            "session": session,
            "sigle": "ZZZ999",
            "titre": "Cours de test",
            "jour": "3",
            "heureDebut": "13:30",
            "heureFin": "16:30",
            "kind": "cours",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert [c for c in body["courses"] if c["sigle"] == "ZZZ999"]
    assert "ZZZ999" in _api_course_sigles(client, session)


def test_undo_redo(client):
    st = _session_with_blocks(client)
    session = st["session"]
    block = st["blocks"][0]
    original_day = block["jour"]
    target_day = "6" if original_day != "6" else "1"

    client.post(
        "/editor/api/block/move",
        json={
            "session": session,
            "blockId": block["id"],
            "jour": target_day,
            "heureDebut": "16:00",
        },
    )
    undo = client.post("/editor/api/undo", json={"session": session}).json()
    reverted = next(b for b in undo["blocks"] if b["id"] == block["id"])
    assert reverted["jour"] == original_day
    assert reverted["heureDebut"] == block["heureDebut"]

    redo = client.post("/editor/api/redo", json={"session": session}).json()
    redone = next(b for b in redo["blocks"] if b["id"] == block["id"])
    assert redone["jour"] == target_day


def test_undo_empty_is_error(client):
    st = _session_with_blocks(client)
    res = client.post("/editor/api/undo", json={"session": st["session"]})
    assert res.status_code == 400


def test_reset_restores_generated(client):
    st = _session_with_blocks(client)
    session = st["session"]
    original_ids = sorted(c["courseId"] for c in st["courses"])

    client.post(
        "/editor/api/course/delete",
        json={"session": session, "courseId": st["courses"][0]["courseId"]},
    )
    reset = client.post("/editor/api/reset", json={"session": session}).json()
    assert sorted(c["courseId"] for c in reset["courses"]) == original_ids
    assert reset["trash"] == []


def test_index_served(client):
    res = client.get("/editor")
    assert res.status_code == 200
    assert "Horaire" in res.text
