import json

import pytest

from lib import data_store, schedule_editor, student_editor
from lib.schedule_editor import EditorError

API = "/api/Etudiant"
OTHER_SESSION = "H2025"


def date_of(state, key):
    return next(row for row in state["dates"] if row["key"] == key)


def field_of(state, key):
    return next(row for row in state["student"] if row["key"] == key)


def base_date(session, key):
    return data_store.get_base_session(session)[key]


def base_field(key):
    return data_store.get_student_info(base=True)[key]


def served_session(client, session):
    listed = client.get(f"{API}/listeSessions").json()["liste"]
    return next(entry for entry in listed if entry["abrege"] == session)


def post(client, path, **body):
    return client.post(f"/editor/api/student{path}", json=body)


def ok(client, path, **body):
    response = post(client, path, **body)
    assert response.status_code == 200, response.text
    return response.json()


def test_the_state_answers_with_the_requested_session(session):
    assert student_editor.get_state(session)["session"] == session


def test_an_unknown_session_falls_back_to_the_active_one():
    assert student_editor.get_state("H2099")["session"] == data_store.ACTIVE_SESSION


def test_the_state_lists_the_sessions_the_api_serves(client):
    listed = {entry["abrege"] for entry in client.get(f"{API}/listeSessions").json()["liste"]}

    assert set(student_editor.get_state()["sessions"]) == listed


def test_every_date_of_the_session_is_listed_and_nothing_else(session):
    state = student_editor.get_state(session)
    raw = next(s for s in data_store.load("sessions.json") if s["abrege"] == session)

    assert [row["key"] for row in state["dates"]] == [
        key for key in raw if key not in ("abrege", "auLong")
    ]
    assert [row["value"] for row in state["dates"]] == [
        raw[row["key"]] for row in state["dates"]
    ]
    assert not any(row["modified"] for row in state["dates"])


def test_the_profile_is_listed_field_by_field():
    state = student_editor.get_state()
    info = data_store.get_student_info(base=True)

    assert [row["key"] for row in state["student"]] == list(info)
    assert [row["value"] for row in state["student"]] == list(info.values())
    assert not any(row["modified"] for row in state["student"])


def test_nothing_can_be_undone_redone_or_reset_at_first(session):
    state = student_editor.get_state(session)

    assert (state["canUndo"], state["canRedo"], state["canReset"]) == (False, False, False)


def test_a_session_date_can_be_changed(session):
    state = student_editor.set_session_date(session, "dateFin", "2026-05-01")

    assert date_of(state, "dateFin") == {
        "key": "dateFin",
        "value": "2026-05-01",
        "modified": True,
    }
    assert state["canUndo"] is True
    assert state["canReset"] is True


def test_a_changed_session_date_is_served_by_the_api(client, session):
    student_editor.set_session_date(session, "dateFinCours", "2026-04-01")

    assert served_session(client, session)["dateFinCours"] == "2026-04-01"


def test_a_changed_session_date_is_saved_to_the_overrides_file(
    session, student_overrides_file
):
    student_editor.set_session_date(session, "dateDebut", "2026-01-12")

    saved = json.loads(student_overrides_file.read_text(encoding="utf-8"))
    assert saved == {"sessions": {session: {"dateDebut": "2026-01-12"}}}


def test_a_changed_session_date_survives_a_reload(session):
    student_editor.set_session_date(session, "dateDebut", "2026-01-12")
    data_store.reload()

    assert date_of(student_editor.get_state(session), "dateDebut")["value"] == "2026-01-12"


def test_the_schedule_calendar_follows_the_session_dates(session):
    before = schedule_editor.get_state(session)["meta"]["semester"]
    student_editor.set_session_date(session, "dateFin", "2026-02-27")
    after = schedule_editor.get_state(session)["meta"]["semester"]

    assert after["dateFin"] == "2026-02-27"
    assert len(after["weeks"]) < len(before["weeks"])


def test_the_classes_stay_inside_the_new_course_window(client, session):
    student_editor.set_session_date(session, "dateFinCours", "2026-02-27")

    seances = client.get(
        f"{API}/lireHoraireDesSeances", params={"session": session}
    ).json()["ListeDesSeances"]
    classes = [s for s in seances if s["nomActivite"] != "Final"]
    assert classes
    assert max(s["dateDebut"][:10] for s in classes) <= "2026-02-27"


def test_a_date_set_back_to_its_original_value_drops_the_override(
    session, student_overrides_file
):
    original = base_date(session, "dateFin")
    student_editor.set_session_date(session, "dateFin", "2026-05-01")
    state = student_editor.set_session_date(session, "dateFin", original)

    assert date_of(state, "dateFin") == {
        "key": "dateFin",
        "value": original,
        "modified": False,
    }
    assert state["canReset"] is False
    assert not student_overrides_file.exists()


@pytest.mark.parametrize("cleared", ["", "  ", None])
def test_clearing_a_date_restores_the_original_value(session, cleared):
    student_editor.set_session_date(session, "dateFin", "2026-05-01")
    state = student_editor.set_session_date(session, "dateFin", cleared)

    assert date_of(state, "dateFin")["value"] == base_date(session, "dateFin")
    assert date_of(state, "dateFin")["modified"] is False


def test_an_unchanged_date_records_nothing(session):
    state = student_editor.set_session_date(
        session, "dateFin", base_date(session, "dateFin")
    )

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
def test_a_session_date_edit_is_refused(session, field, value, message):
    with pytest.raises(EditorError, match=message):
        student_editor.set_session_date(session, field, value)

    assert student_editor.get_state(session)["canUndo"] is False


def test_a_session_the_api_does_not_serve_is_refused():
    with pytest.raises(EditorError, match="not found"):
        student_editor.set_session_date("H2099", "dateFin", "2099-04-30")


def test_a_date_edit_only_touches_its_own_session(session):
    before = date_of(student_editor.get_state(OTHER_SESSION), "dateFin")
    student_editor.set_session_date(session, "dateFin", "2026-05-01")

    assert date_of(student_editor.get_state(OTHER_SESSION), "dateFin") == before


def test_a_changed_date_is_applied_after_the_semester_week_shift(reconfigure):
    reconfigure(SEMESTER_WEEK="3")
    active = data_store.ACTIVE_SESSION
    shifted_start = base_date(active, "dateDebut")

    student_editor.set_session_date(active, "dateFin", "2030-12-20")
    state = student_editor.get_state(active)

    assert date_of(state, "dateFin")["value"] == "2030-12-20"
    assert date_of(state, "dateDebut")["value"] == shifted_start


def test_a_profile_field_can_be_changed(client):
    state = student_editor.set_student_field("", "nom", "  Tremblay ")

    assert field_of(state, "nom") == {"key": "nom", "value": "Tremblay", "modified": True}
    assert client.get(f"{API}/infoEtudiant").json()["nom"] == "Tremblay"


def test_a_changed_profile_field_is_saved_to_the_overrides_file(student_overrides_file):
    student_editor.set_student_field("", "prenom", "Marie")

    saved = json.loads(student_overrides_file.read_text(encoding="utf-8"))
    assert saved == {"student": {"prenom": "Marie"}}


@pytest.mark.parametrize(
    "typed, stored",
    [
        ("250", "250,00$"),
        ("12.5", "12,50$"),
        ("1 234,5 $", "1234,50$"),
        ("1\u00a0234,5\u00a0$", "1234,50$"),
        ("-40,1", "-40,10$"),
    ],
)
def test_the_balance_is_stored_in_the_api_format(typed, stored):
    state = student_editor.set_student_field("", "soldeTotal", typed)

    assert field_of(state, "soldeTotal")["value"] == stored


@pytest.mark.parametrize("typed", ["beaucoup", "nan", "inf", "1,2,3"])
def test_a_balance_that_is_not_an_amount_is_refused(typed):
    with pytest.raises(EditorError, match="Invalid amount"):
        student_editor.set_student_field("", "soldeTotal", typed)


def test_a_boolean_profile_field_takes_a_boolean(client):
    state = student_editor.set_student_field("", "masculin", False)

    assert field_of(state, "masculin") == {
        "key": "masculin",
        "value": False,
        "modified": True,
    }
    assert client.get(f"{API}/infoEtudiant").json()["masculin"] is False


def test_clearing_a_profile_field_restores_the_original_value():
    student_editor.set_student_field("", "prenom", "Marie")
    state = student_editor.set_student_field("", "prenom", "")

    assert field_of(state, "prenom") == {
        "key": "prenom",
        "value": base_field("prenom"),
        "modified": False,
    }


def test_an_unknown_profile_field_is_refused():
    with pytest.raises(EditorError, match="Unknown field"):
        student_editor.set_student_field("", "age", "20")


def test_a_profile_edit_answers_with_the_requested_session(session):
    assert student_editor.set_student_field(session, "nom", "Tremblay")["session"] == session


def test_undo_and_redo_walk_through_every_kind_of_edit(session):
    student_editor.set_student_field(session, "nom", "Tremblay")
    student_editor.set_session_date(session, "dateFin", "2026-05-01")

    state = student_editor.undo(session)
    assert date_of(state, "dateFin")["value"] == base_date(session, "dateFin")
    assert field_of(state, "nom")["value"] == "Tremblay"

    state = student_editor.undo(session)
    assert field_of(state, "nom")["value"] == base_field("nom")
    assert (state["canUndo"], state["canRedo"]) == (False, True)

    student_editor.redo(session)
    state = student_editor.redo(session)
    assert field_of(state, "nom")["value"] == "Tremblay"
    assert date_of(state, "dateFin")["value"] == "2026-05-01"
    assert (state["canUndo"], state["canRedo"]) == (True, False)


def test_undoing_a_date_shows_the_session_it_changed(session):
    student_editor.set_session_date(OTHER_SESSION, "dateFin", "2025-05-02")

    assert student_editor.undo(session)["session"] == OTHER_SESSION


def test_undoing_a_profile_edit_keeps_the_requested_session(session):
    student_editor.set_student_field(OTHER_SESSION, "nom", "Tremblay")

    assert student_editor.undo(session)["session"] == session


def test_a_new_edit_clears_the_redo_history(session):
    student_editor.set_student_field(session, "nom", "Tremblay")
    student_editor.undo(session)
    state = student_editor.set_student_field(session, "prenom", "Marie")

    assert state["canRedo"] is False


@pytest.mark.parametrize("step, message", [("undo", "Nothing to undo"), ("redo", "Nothing to redo")])
def test_an_empty_history_is_refused(session, step, message):
    with pytest.raises(EditorError, match=message):
        getattr(student_editor, step)(session)


def test_reset_puts_everything_back_and_can_be_undone(session, student_overrides_file):
    student_editor.set_student_field(session, "nom", "Tremblay")
    student_editor.set_session_date(OTHER_SESSION, "dateFin", "2025-05-02")

    state = student_editor.reset(session)
    assert not any(row["modified"] for row in state["student"] + state["dates"])
    assert date_of(student_editor.get_state(OTHER_SESSION), "dateFin")["modified"] is False
    assert state["canReset"] is False
    assert not student_overrides_file.exists()

    state = student_editor.undo(session)
    assert field_of(state, "nom")["value"] == "Tremblay"
    assert date_of(student_editor.get_state(OTHER_SESSION), "dateFin")["value"] == "2025-05-02"


def test_reset_with_nothing_changed_is_refused(session):
    with pytest.raises(EditorError, match="Nothing to reset"):
        student_editor.reset(session)


def test_the_reload_endpoint_forgets_the_history(client, session):
    student_editor.set_student_field(session, "nom", "Tremblay")
    client.post("/reload")

    state = student_editor.get_state(session)
    assert state["canUndo"] is False
    assert field_of(state, "nom")["value"] == "Tremblay"


def test_the_student_state_travels_over_http(client, session):
    response = client.get("/editor/api/student/state", params={"session": session})

    assert response.status_code == 200
    assert set(response.json()) == {
        "session",
        "sessions",
        "dates",
        "student",
        "canUndo",
        "canRedo",
        "canReset",
    }
    assert response.json()["session"] == session


def test_student_edits_travel_over_http(client, session):
    state = ok(client, "/session-date", session=session, field="dateFin", value="2026-05-01")
    assert date_of(state, "dateFin")["value"] == "2026-05-01"

    state = ok(client, "/profile", session=session, field="masculin", value=False)
    assert field_of(state, "masculin")["value"] is False

    state = ok(client, "/undo", session=session)
    assert field_of(state, "masculin")["value"] is True

    state = ok(client, "/redo", session=session)
    assert field_of(state, "masculin")["value"] is False

    state = ok(client, "/reset", session=session)
    assert state["canReset"] is False


@pytest.mark.parametrize(
    "path, body, message",
    [
        ("/session-date", {"field": "abrege", "value": "2026-01-01"}, "Unknown date"),
        ("/session-date", {"field": "dateFin", "value": "31/12/2026"}, "Invalid date"),
        ("/profile", {"field": "soldeTotal", "value": "gratuit"}, "Invalid amount"),
        ("/undo", {}, "Nothing to undo"),
    ],
)
def test_a_refused_student_edit_comes_back_as_a_400(client, session, path, body, message):
    response = post(client, path, session=session, **body)

    assert response.status_code == 400
    assert message in response.json()["error"]
