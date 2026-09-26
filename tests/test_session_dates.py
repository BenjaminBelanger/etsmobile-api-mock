import json

import pytest

from lib import data_store, schedule_editor
from lib.schedule_editor import EditorError

API = "/api/Etudiant"
COURSE = "LOG430-02"
OTHER_SESSION = "H2025"


def date_of(state, key):
    return next(row for row in state["dates"] if row["key"] == key)


def base_date(session, key):
    return data_store.get_base_session(session)[key]


def served_session(client, session):
    listed = client.get(f"{API}/listeSessions").json()["liste"]
    return next(entry for entry in listed if entry["abrege"] == session)


def post(client, path, **body):
    return client.post(f"/editor/api{path}", json=body)


def ok(client, path, **body):
    response = post(client, path, **body)
    assert response.status_code == 200, response.text
    return response.json()


def test_the_state_lists_every_date_of_the_session_and_nothing_else(session):
    state = schedule_editor.get_state(session)
    raw = next(s for s in data_store.load("sessions.json") if s["abrege"] == session)

    assert [row["key"] for row in state["dates"]] == [
        key for key in raw if key not in ("abrege", "auLong")
    ]
    assert [row["value"] for row in state["dates"]] == [
        raw[row["key"]] for row in state["dates"]
    ]
    assert not any(row["modified"] for row in state["dates"])


def test_a_session_date_can_be_changed(session):
    state = schedule_editor.set_session_date(session, "dateFin", "2026-05-01")

    assert date_of(state, "dateFin") == {
        "key": "dateFin",
        "value": "2026-05-01",
        "modified": True,
    }
    assert state["canUndo"] is True


def test_a_changed_date_is_served_by_the_api(client, session):
    schedule_editor.set_session_date(session, "dateFinCours", "2026-04-01")

    assert served_session(client, session)["dateFinCours"] == "2026-04-01"


def test_a_changed_date_is_saved_with_the_session(session, sandbox_overrides):
    schedule_editor.set_session_date(session, "dateDebut", "2026-01-12")

    saved = json.loads(sandbox_overrides.read_text(encoding="utf-8"))
    assert saved[session]["dates"] == {"dateDebut": "2026-01-12"}


def test_a_changed_date_survives_a_reload(session):
    schedule_editor.set_session_date(session, "dateDebut", "2026-01-12")
    schedule_editor.clear_cache()
    data_store.reload()

    state = schedule_editor.get_state(session)
    assert date_of(state, "dateDebut") == {
        "key": "dateDebut",
        "value": "2026-01-12",
        "modified": True,
    }


def test_the_calendar_follows_the_session_dates(session):
    before = schedule_editor.get_state(session)["meta"]["semester"]
    after = schedule_editor.set_session_date(session, "dateFin", "2026-02-27")["meta"][
        "semester"
    ]

    assert after["dateFin"] == "2026-02-27"
    assert len(after["weeks"]) < len(before["weeks"])


def test_the_classes_stay_inside_the_new_course_window(client, session):
    state = schedule_editor.set_session_date(session, "dateFinCours", "2026-02-27")

    classes = [row for row in state["occurrences"] if row["kind"] != "exam"]
    assert classes
    assert max(row["date"] for row in classes) <= "2026-02-27"

    seances = client.get(
        f"{API}/lireHoraireDesSeances", params={"session": session}
    ).json()["ListeDesSeances"]
    served = [s for s in seances if s["nomActivite"] != "Final"]
    assert max(s["dateDebut"][:10] for s in served) <= "2026-02-27"


def test_a_date_set_back_to_its_original_value_is_no_longer_stored(
    session, sandbox_overrides
):
    original = base_date(session, "dateFin")
    schedule_editor.set_session_date(session, "dateFin", "2026-05-01")
    state = schedule_editor.set_session_date(session, "dateFin", original)

    assert date_of(state, "dateFin")["modified"] is False
    saved = json.loads(sandbox_overrides.read_text(encoding="utf-8"))
    assert "dates" not in saved[session]


@pytest.mark.parametrize("cleared", ["", "  ", None])
def test_clearing_a_date_restores_the_original_value(session, cleared):
    schedule_editor.set_session_date(session, "dateFin", "2026-05-01")
    state = schedule_editor.set_session_date(session, "dateFin", cleared)

    assert date_of(state, "dateFin")["value"] == base_date(session, "dateFin")
    assert date_of(state, "dateFin")["modified"] is False


def test_an_unchanged_date_records_nothing(session):
    state = schedule_editor.set_session_date(session, "dateFin", "")

    assert state["canUndo"] is False


@pytest.mark.parametrize(
    "field, value, message",
    [
        ("dateFin", "2026-02-30", "Invalid date"),
        ("dateFin", "demain", "Invalid date"),
        ("abrege", "2026-01-01", "Unknown date"),
        ("auLong", "2026-01-01", "Unknown date"),
        ("dateInconnue", "2026-01-01", "Unknown date"),
    ],
)
def test_a_date_edit_is_refused(session, field, value, message):
    with pytest.raises(EditorError, match=message):
        schedule_editor.set_session_date(session, field, value)

    assert schedule_editor.get_state(session)["canUndo"] is False


@pytest.mark.parametrize("code", ["H2099", "É2025"])
def test_a_session_without_courses_is_refused(code):
    with pytest.raises(EditorError, match="not found"):
        schedule_editor.set_session_date(code, "dateFin", "2025-08-01")


def test_a_date_edit_only_touches_its_own_session(session):
    before = date_of(schedule_editor.get_state(OTHER_SESSION), "dateFin")
    schedule_editor.set_session_date(session, "dateFin", "2026-05-01")

    assert date_of(schedule_editor.get_state(OTHER_SESSION), "dateFin") == before


def test_a_changed_date_is_applied_after_the_semester_week_shift(reconfigure):
    reconfigure(SEMESTER_WEEK="3")
    active = data_store.ACTIVE_SESSION
    shifted_start = base_date(active, "dateDebut")

    state = schedule_editor.set_session_date(active, "dateFin", "2030-12-20")

    assert date_of(state, "dateFin")["value"] == "2030-12-20"
    assert date_of(state, "dateDebut")["value"] == shifted_start


def test_a_date_change_is_undone_and_redone_with_the_schedule(session):
    original = base_date(session, "dateFin")
    schedule_editor.move_block(session, f"{COURSE}:0", "3", "14:00")
    schedule_editor.set_session_date(session, "dateFin", "2026-05-01")

    state = schedule_editor.undo(session)
    assert date_of(state, "dateFin")["value"] == original
    assert state["meta"]["semester"]["dateFin"] == original
    assert next(b for b in state["blocks"] if b["id"] == f"{COURSE}:0")["jour"] == "3"

    state = schedule_editor.redo(session)
    assert date_of(state, "dateFin")["value"] == "2026-05-01"
    assert state["meta"]["semester"]["dateFin"] == "2026-05-01"


def test_resetting_the_session_restores_its_dates(session):
    schedule_editor.set_session_date(session, "dateFin", "2026-05-01")
    state = schedule_editor.reset_session(session)

    assert not any(row["modified"] for row in state["dates"])
    assert state["meta"]["semester"]["dateFin"] == base_date(session, "dateFin")


def test_the_dates_can_be_restored_without_touching_the_courses(session):
    schedule_editor.move_block(session, f"{COURSE}:0", "3", "14:00")
    schedule_editor.set_session_date(session, "dateFin", "2026-05-01")
    schedule_editor.set_session_date(session, "dateDebut", "2026-01-12")

    state = schedule_editor.reset_session_dates(session)
    assert not any(row["modified"] for row in state["dates"])
    assert next(b for b in state["blocks"] if b["id"] == f"{COURSE}:0")["jour"] == "3"

    state = schedule_editor.undo(session)
    assert date_of(state, "dateFin")["value"] == "2026-05-01"
    assert date_of(state, "dateDebut")["value"] == "2026-01-12"


def test_restoring_unchanged_dates_is_refused(session):
    with pytest.raises(EditorError, match="no changed dates"):
        schedule_editor.reset_session_dates(session)


def test_session_dates_travel_over_http(client, session):
    state = ok(client, "/session/date", session=session, field="dateFin", value="2026-05-01")
    assert date_of(state, "dateFin")["value"] == "2026-05-01"

    state = ok(client, "/session/dates/reset", session=session)
    assert date_of(state, "dateFin")["modified"] is False


@pytest.mark.parametrize(
    "path, body, message",
    [
        ("/session/date", {"field": "abrege", "value": "2026-01-01"}, "Unknown date"),
        ("/session/date", {"field": "dateFin", "value": "31/12/2026"}, "Invalid date"),
        ("/session/dates/reset", {}, "no changed dates"),
    ],
)
def test_a_refused_date_edit_comes_back_as_a_400(client, session, path, body, message):
    response = post(client, path, session=session, **body)

    assert response.status_code == 400
    assert message in response.json()["error"]
