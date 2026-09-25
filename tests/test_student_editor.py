import json

import pytest

from lib import data_store, student_editor
from lib.schedule_editor import EditorError

API = "/api/Etudiant"


def field_of(state, key):
    return next(row for row in state["student"] if row["key"] == key)


def base_field(key):
    return data_store.get_student_info(base=True)[key]


def post(client, path, **body):
    return client.post(f"/editor/api/student{path}", json=body)


def ok(client, path, **body):
    response = post(client, path, **body)
    assert response.status_code == 200, response.text
    return response.json()


def test_the_profile_is_listed_field_by_field():
    state = student_editor.get_state()
    info = data_store.get_student_info(base=True)

    assert [row["key"] for row in state["student"]] == list(info)
    assert [row["value"] for row in state["student"]] == list(info.values())
    assert not any(row["modified"] for row in state["student"])


def test_nothing_can_be_undone_redone_or_reset_at_first():
    state = student_editor.get_state()

    assert (state["canUndo"], state["canRedo"], state["canReset"]) == (False, False, False)


def test_a_profile_field_can_be_changed(client):
    state = student_editor.set_field("nom", "  Tremblay ")

    assert field_of(state, "nom") == {"key": "nom", "value": "Tremblay", "modified": True}
    assert state["canUndo"] is True
    assert state["canReset"] is True
    assert client.get(f"{API}/infoEtudiant").json()["nom"] == "Tremblay"


def test_a_changed_field_is_saved_to_the_overrides_file(student_overrides_file):
    student_editor.set_field("prenom", "Marie")

    saved = json.loads(student_overrides_file.read_text(encoding="utf-8"))
    assert saved == {"prenom": "Marie"}


def test_a_changed_field_survives_a_reload():
    student_editor.set_field("prenom", "Marie")
    data_store.reload()

    assert field_of(student_editor.get_state(), "prenom")["value"] == "Marie"


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
    state = student_editor.set_field("soldeTotal", typed)

    assert field_of(state, "soldeTotal")["value"] == stored


@pytest.mark.parametrize("typed", ["beaucoup", "nan", "inf", "1,2,3"])
def test_a_balance_that_is_not_an_amount_is_refused(typed):
    with pytest.raises(EditorError, match="Invalid amount"):
        student_editor.set_field("soldeTotal", typed)


def test_a_boolean_field_takes_a_boolean(client):
    state = student_editor.set_field("masculin", False)

    assert field_of(state, "masculin") == {
        "key": "masculin",
        "value": False,
        "modified": True,
    }
    assert client.get(f"{API}/infoEtudiant").json()["masculin"] is False


@pytest.mark.parametrize("cleared", ["", "  ", None])
def test_clearing_a_field_restores_the_original_value(cleared, student_overrides_file):
    student_editor.set_field("prenom", "Marie")
    state = student_editor.set_field("prenom", cleared)

    assert field_of(state, "prenom") == {
        "key": "prenom",
        "value": base_field("prenom"),
        "modified": False,
    }
    assert not student_overrides_file.exists()


def test_a_field_set_back_to_its_original_value_is_no_longer_marked():
    student_editor.set_field("masculin", False)
    state = student_editor.set_field("masculin", True)

    assert field_of(state, "masculin")["modified"] is False
    assert state["canReset"] is False


def test_an_unchanged_field_records_nothing():
    state = student_editor.set_field("nom", base_field("nom"))

    assert state["canUndo"] is False


def test_an_unknown_field_is_refused():
    with pytest.raises(EditorError, match="Unknown field"):
        student_editor.set_field("age", "20")


def test_undo_and_redo_walk_through_the_edits():
    student_editor.set_field("nom", "Tremblay")
    student_editor.set_field("prenom", "Marie")

    state = student_editor.undo()
    assert field_of(state, "prenom")["value"] == base_field("prenom")
    assert field_of(state, "nom")["value"] == "Tremblay"

    state = student_editor.undo()
    assert field_of(state, "nom")["value"] == base_field("nom")
    assert (state["canUndo"], state["canRedo"]) == (False, True)

    student_editor.redo()
    state = student_editor.redo()
    assert field_of(state, "nom")["value"] == "Tremblay"
    assert field_of(state, "prenom")["value"] == "Marie"
    assert (state["canUndo"], state["canRedo"]) == (True, False)


def test_a_new_edit_clears_the_redo_history():
    student_editor.set_field("nom", "Tremblay")
    student_editor.undo()
    state = student_editor.set_field("prenom", "Marie")

    assert state["canRedo"] is False


@pytest.mark.parametrize("step, message", [("undo", "Nothing to undo"), ("redo", "Nothing to redo")])
def test_an_empty_history_is_refused(step, message):
    with pytest.raises(EditorError, match=message):
        getattr(student_editor, step)()


def test_reset_puts_everything_back_and_can_be_undone(student_overrides_file):
    student_editor.set_field("nom", "Tremblay")
    student_editor.set_field("masculin", False)

    state = student_editor.reset()
    assert not any(row["modified"] for row in state["student"])
    assert state["canReset"] is False
    assert not student_overrides_file.exists()

    state = student_editor.undo()
    assert field_of(state, "nom")["value"] == "Tremblay"
    assert field_of(state, "masculin")["value"] is False


def test_reset_with_nothing_changed_is_refused():
    with pytest.raises(EditorError, match="Nothing to reset"):
        student_editor.reset()


def test_the_reload_endpoint_forgets_the_history(client):
    student_editor.set_field("nom", "Tremblay")
    client.post("/reload")

    state = student_editor.get_state()
    assert state["canUndo"] is False
    assert field_of(state, "nom")["value"] == "Tremblay"


def test_the_student_state_travels_over_http(client):
    response = client.get("/editor/api/student/state")

    assert response.status_code == 200
    assert set(response.json()) == {"student", "canUndo", "canRedo", "canReset"}


def test_student_edits_travel_over_http(client):
    state = ok(client, "/set", field="masculin", value=False)
    assert field_of(state, "masculin")["value"] is False

    state = ok(client, "/undo")
    assert field_of(state, "masculin")["value"] is True

    state = ok(client, "/redo")
    assert field_of(state, "masculin")["value"] is False

    state = ok(client, "/reset")
    assert state["canReset"] is False


@pytest.mark.parametrize(
    "path, body, message",
    [
        ("/set", {"field": "soldeTotal", "value": "gratuit"}, "Invalid amount"),
        ("/set", {"field": "age", "value": "20"}, "Unknown field"),
        ("/undo", {}, "Nothing to undo"),
        ("/reset", {}, "Nothing to reset"),
    ],
)
def test_a_refused_student_edit_comes_back_as_a_400(client, path, body, message):
    response = post(client, path, **body)

    assert response.status_code == 400
    assert message in response.json()["error"]
