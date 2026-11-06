import json

import pytest

from lib import data_store, schedule_editor
from lib.schedule_editor import EditorError

API = "/api/Etudiant"
REMOVABLE = "H2025"
NEW = "A2023"


def served_codes(client):
    return [entry["abrege"] for entry in client.get(f"{API}/listeSessions").json()["liste"]]


def served_course_sessions(client):
    return {entry["session"] for entry in client.get(f"{API}/listeCours").json()["liste"]}


def post(client, path, **body):
    return client.post(f"/editor/api{path}", json=body)


def ok(client, path, **body):
    response = post(client, path, **body)
    assert response.status_code == 200, response.text
    return response.json()


def stored_all(sandbox):
    return json.loads(sandbox.read_text(encoding="utf-8"))


def stored(sandbox, session):
    return stored_all(sandbox)[session]


def test_a_past_session_can_be_removed():
    state = schedule_editor.remove_session(REMOVABLE)

    assert state["session"] == REMOVABLE
    assert state["sessionStatus"] == {"added": False, "removed": True, "removable": False}
    assert state["removedSessions"] == [REMOVABLE]
    assert state["canUndo"] is True


def test_a_removed_session_stays_in_the_editor_but_leaves_the_api(client):
    schedule_editor.remove_session(REMOVABLE)

    assert REMOVABLE in schedule_editor.get_state(REMOVABLE)["sessions"]
    assert REMOVABLE not in served_codes(client)
    assert REMOVABLE not in served_course_sessions(client)
    horaire = client.get(f"{API}/listeHoraireEtProf", params={"session": REMOVABLE})
    assert horaire.json()["listeActivites"] == []


def test_a_removed_session_is_saved_with_its_courses(sandbox_overrides):
    before = schedule_editor.get_state(REMOVABLE)["courses"]
    schedule_editor.remove_session(REMOVABLE)

    entry = stored(sandbox_overrides, REMOVABLE)
    assert entry["removed"] is True
    assert len(entry["courses"]) == len(before)


def test_removing_a_session_can_be_undone(client):
    schedule_editor.remove_session(REMOVABLE)
    state = schedule_editor.undo(REMOVABLE)

    assert state["sessionStatus"]["removed"] is False
    assert REMOVABLE in served_codes(client)


def test_a_removed_session_can_be_restored(client):
    courses = schedule_editor.get_state(REMOVABLE)["courses"]
    schedule_editor.remove_session(REMOVABLE)
    state = schedule_editor.restore_session(REMOVABLE)

    assert state["sessionStatus"]["removed"] is False
    assert state["removedSessions"] == []
    assert state["courses"] == courses
    assert REMOVABLE in served_codes(client)


def test_resetting_a_removed_session_serves_it_again(client):
    schedule_editor.remove_session(REMOVABLE)
    schedule_editor.reset_session(REMOVABLE)

    assert REMOVABLE in served_codes(client)


def test_the_active_session_cannot_be_removed():
    code = data_store.ACTIVE_SESSION

    assert schedule_editor.get_state(code)["sessionStatus"]["removable"] is False
    with pytest.raises(EditorError, match="can't be removed"):
        schedule_editor.remove_session(code)


def test_the_next_session_can_be_removed(client):
    code = data_store.NEXT_SESSION

    assert schedule_editor.get_state(code)["sessionStatus"]["removable"] is True
    schedule_editor.remove_session(code)

    assert code not in served_codes(client)
    assert code not in served_course_sessions(client)


def test_removing_twice_is_refused():
    schedule_editor.remove_session(REMOVABLE)
    with pytest.raises(EditorError, match="already removed"):
        schedule_editor.remove_session(REMOVABLE)


def test_restoring_a_served_session_is_refused():
    with pytest.raises(EditorError, match="not removed"):
        schedule_editor.restore_session(REMOVABLE)


@pytest.mark.parametrize("action", ["remove_session", "restore_session"])
def test_an_unknown_session_is_refused(action):
    with pytest.raises(EditorError, match="not found"):
        getattr(schedule_editor, action)("H2099")


def test_the_default_session_skips_removed_ones(monkeypatch):
    schedule_editor.remove_session(REMOVABLE)
    monkeypatch.setattr(data_store, "ACTIVE_SESSION", REMOVABLE)

    assert data_store.resolve_default_session() != REMOVABLE


def test_the_state_offers_sessions_that_do_not_exist_yet():
    state = schedule_editor.get_state("")
    addable = state["meta"]["addableSessions"]

    assert NEW in addable
    assert not set(addable) & set(state["sessions"])
    assert addable == sorted(addable, key=data_store.sessions.session_rank, reverse=True)


def test_a_session_can_be_added_without_courses():
    state = schedule_editor.add_session(NEW)

    assert state["session"] == NEW
    assert state["courses"] == []
    assert state["sessionStatus"] == {"added": True, "removed": False, "removable": True}
    assert NEW in state["sessions"]
    assert NEW not in state["meta"]["addableSessions"]
    assert state["canUndo"] is False


def test_an_added_session_is_served_in_order(client):
    schedule_editor.add_session(NEW)

    codes = served_codes(client)
    assert NEW in codes
    assert codes == sorted(codes, key=data_store.sessions.session_rank)


def test_an_added_session_copies_the_dates_of_its_term():
    state = schedule_editor.add_session(NEW)

    assert state["meta"]["semester"]["dateDebut"].startswith("2023-0")
    assert state["dates"] and not any(row["modified"] for row in state["dates"])


def test_an_added_session_takes_courses_and_dates(client):
    schedule_editor.add_session(NEW)
    schedule_editor.add_course(NEW, "LOG999", "Cours ajouté", "2", "09:00", "12:00")
    schedule_editor.set_session_date(NEW, "dateFin", "2023-12-22")

    assert NEW in served_course_sessions(client)
    served = next(
        s for s in client.get(f"{API}/listeSessions").json()["liste"] if s["abrege"] == NEW
    )
    assert served["dateFin"] == "2023-12-22"


def test_an_added_session_survives_a_reload(sandbox_overrides):
    schedule_editor.add_session(NEW)
    schedule_editor.clear_cache()
    data_store.reload()

    assert stored(sandbox_overrides, NEW)["added"] is True
    assert schedule_editor.get_state(NEW)["sessionStatus"]["added"] is True


def test_resetting_an_added_session_keeps_it_empty():
    schedule_editor.add_session(NEW)
    schedule_editor.add_course(NEW, "LOG999", "", "2", "09:00", "12:00")
    state = schedule_editor.reset_session(NEW)

    assert state["session"] == NEW
    assert state["courses"] == []
    assert state["sessionStatus"]["added"] is True


def test_removing_an_added_session_deletes_it(client, sandbox_overrides):
    schedule_editor.add_session(NEW)
    state = schedule_editor.remove_session(NEW)

    assert state["session"] == data_store.resolve_default_session()
    assert NEW not in state["sessions"]
    assert NEW in state["meta"]["addableSessions"]
    assert NEW not in served_codes(client)
    assert not sandbox_overrides.exists() or NEW not in stored_all(sandbox_overrides)


def test_a_deleted_session_comes_back_empty_when_added_again():
    schedule_editor.add_session(NEW)
    schedule_editor.add_course(NEW, "LOG999", "", "2", "09:00", "12:00")
    schedule_editor.remove_session(NEW)

    assert schedule_editor.add_session(NEW)["courses"] == []


@pytest.mark.parametrize("code", [NEW, "Automne 2023", "20233"])
def test_any_session_format_can_be_added(code):
    assert schedule_editor.add_session(code)["session"] == NEW


@pytest.mark.parametrize(
    "code,message",
    [
        (REMOVABLE, "already exists"),
        ("H1990", "can't be added"),
        ("X2023", "can't be added"),
        ("", "can't be added"),
    ],
)
def test_adding_a_session_is_refused(code, message):
    with pytest.raises(EditorError, match=message):
        schedule_editor.add_session(code)


def test_sessions_hidden_by_no_next_session_cannot_be_added(reconfigure):
    reconfigure(NO_NEXT_SESSION="1")

    assert data_store.NEXT_SESSION not in schedule_editor.addable_sessions()
    with pytest.raises(EditorError, match="can't be added"):
        schedule_editor.add_session(data_store.NEXT_SESSION)


def test_sessions_are_added_removed_and_restored_over_http(client):
    added = ok(client, "/session/add", session=NEW)
    assert added["session"] == NEW

    deleted = ok(client, "/session/remove", session=NEW)
    assert NEW not in deleted["sessions"]

    removed = ok(client, "/session/remove", session=REMOVABLE)
    assert removed["sessionStatus"]["removed"] is True

    restored = ok(client, "/session/restore", session=REMOVABLE)
    assert restored["sessionStatus"]["removed"] is False


@pytest.mark.parametrize(
    "path,session,message",
    [
        ("/session/add", REMOVABLE, "already exists"),
        ("/session/remove", "H2099", "not found"),
        ("/session/restore", REMOVABLE, "not removed"),
    ],
)
def test_a_refused_session_change_comes_back_as_a_400(client, path, session, message):
    response = post(client, path, session=session)

    assert response.status_code == 400
    assert message in response.json()["error"]
