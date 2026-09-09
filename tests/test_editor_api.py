import pytest

BLOCK = "LOG430-02:0"
COURSE = "LOG430-02"
STATE = "/editor/api/state"


def post(client, path, **body):
    return client.post(f"/editor/api{path}", json=body)


def ok(client, path, **body):
    response = post(client, path, **body)
    assert response.status_code == 200, response.text
    return response.json()


def state_of(client, session):
    response = client.get(STATE, params={"session": session})
    assert response.status_code == 200
    return response.json()


def course_of(state, course_id=COURSE):
    return next(c for c in state["courses"] if c["courseId"] == course_id)


def block_of(state, block_id=BLOCK):
    return next(b for b in state["blocks"] if b["id"] == block_id)


def test_the_state_endpoint_serves_the_whole_editor_state(client, session):
    state = state_of(client, session)
    assert set(state) == {
        "session",
        "sessions",
        "courses",
        "blocks",
        "occurrences",
        "trash",
        "canUndo",
        "canRedo",
        "meta",
    }
    assert state["session"] == session


def test_the_state_endpoint_falls_back_to_a_default_session(client):
    assert client.get(STATE).json()["session"]


def test_a_block_can_be_moved_over_http(client, session):
    state = ok(
        client,
        "/block/move",
        session=session,
        blockId=BLOCK,
        jour="3",
        heureDebut="14:00",
    )
    assert block_of(state)["jour"] == "3"


def test_a_block_can_be_resized_over_http(client, session):
    state = ok(
        client,
        "/block/resize",
        session=session,
        blockId=BLOCK,
        heureDebut="09:00",
        heureFin="11:00",
    )
    assert block_of(state)["heureFin"] == "11:00"


def test_a_course_can_be_deleted_and_restored_over_http(client, session):
    deleted = ok(client, "/course/delete", session=session, courseId=COURSE)
    assert [t["courseId"] for t in deleted["trash"]] == [COURSE]

    restored = ok(client, "/course/restore", session=session, courseId=COURSE)
    assert restored["trash"] == []


def test_a_course_can_be_added_over_http(client, session):
    state = ok(
        client,
        "/course/add",
        session=session,
        sigle="ZZZ999",
        titre="Ajouté",
        jour="2",
        heureDebut="09:00",
        heureFin="12:00",
        kind="cours",
    )
    assert course_of(state, "ZZZ999-01")["titre"] == "Ajouté"


def test_adding_a_course_only_needs_the_required_fields(client, session):
    state = ok(
        client,
        "/course/add",
        session=session,
        sigle="ZZZ999",
        jour="2",
        heureDebut="09:00",
        heureFin="12:00",
    )
    added = course_of(state, "ZZZ999-01")
    assert added["titre"] == "ZZZ999"
    assert added["blocks"][0]["kind"] == "cours"


def test_an_occurrence_can_be_moved_over_http(client, session):
    state = ok(
        client,
        "/occurrence/set",
        session=session,
        blockId=BLOCK,
        date="2026-03-02",
        jour="3",
        heureDebut="09:00",
        heureFin="12:00",
    )
    rows = [r for r in state["occurrences"] if r["blockId"] == BLOCK]
    assert any(r["date"] == "2026-03-04" and r["overridden"] for r in rows)


def test_an_occurrence_can_be_cancelled_and_reset_over_http(client, session):
    cancelled = ok(
        client, "/occurrence/cancel", session=session, blockId=BLOCK, date="2026-03-09"
    )
    row = next(
        r
        for r in cancelled["occurrences"]
        if r["blockId"] == BLOCK and r["date"] == "2026-03-09"
    )
    assert row["canceled"] is True

    reset = ok(
        client, "/occurrence/reset", session=session, blockId=BLOCK, date="2026-03-09"
    )
    row = next(
        r
        for r in reset["occurrences"]
        if r["blockId"] == BLOCK and r["date"] == "2026-03-09"
    )
    assert row["canceled"] is False


def test_an_evaluation_can_be_edited_over_http(client, session):
    state = ok(
        client,
        "/evaluation/set",
        session=session,
        courseId=COURSE,
        index=0,
        field="nom",
        value="Intra",
    )
    assert course_of(state)["evaluations"][0]["nom"] == "Intra"


def test_an_evaluation_field_can_be_cleared_over_http(client, session):
    ok(
        client,
        "/evaluation/set",
        session=session,
        courseId=COURSE,
        index=0,
        field="note",
        value="10",
    )
    state = ok(
        client,
        "/evaluation/set",
        session=session,
        courseId=COURSE,
        index=0,
        field="note",
        value=None,
    )
    assert "note" not in course_of(state)["evaluations"][0]["pinned"]


def test_a_boolean_evaluation_field_travels_as_json(client, session):
    state = ok(
        client,
        "/evaluation/set",
        session=session,
        courseId=COURSE,
        index=0,
        field="publie",
        value=False,
    )
    assert course_of(state)["evaluations"][0]["publie"] is False


def test_an_evaluation_can_be_added_deleted_and_moved_over_http(client, session):
    added = ok(client, "/evaluation/add", session=session, courseId=COURSE)
    count = len(course_of(added)["evaluations"])
    assert course_of(added)["evaluations"][-1]["nom"] == "Nouvel élément"

    moved = ok(
        client,
        "/evaluation/move",
        session=session,
        courseId=COURSE,
        index=count - 1,
        toIndex=0,
    )
    assert course_of(moved)["evaluations"][0]["nom"] == "Nouvel élément"

    deleted = ok(
        client, "/evaluation/delete", session=session, courseId=COURSE, index=0
    )
    assert len(course_of(deleted)["evaluations"]) == count - 1


def test_grades_can_be_regenerated_over_http(client, session):
    ok(
        client,
        "/evaluation/set",
        session=session,
        courseId=COURSE,
        index=0,
        field="note",
        value="1",
    )
    state = ok(client, "/grades/reset", session=session, courseId=COURSE)
    assert course_of(state)["canResetGrades"] is False


def test_a_cote_can_be_set_over_http(client, session):
    state = ok(client, "/course/cote", session=session, courseId=COURSE, cote="a+")
    assert course_of(state)["cote"] == "A+"


def test_the_exam_can_be_set_and_reset_over_http(client, session):
    state = ok(
        client,
        "/exam/set",
        session=session,
        courseId=COURSE,
        date="2026-04-22",
        local="Z-9999",
    )
    exam = course_of(state)["exam"]
    assert exam["dateExamen"] == "2026-04-22"
    assert exam["local"] == "Z-9999"

    state = ok(client, "/exam/reset", session=session, courseId=COURSE)
    assert course_of(state)["exam"]["pinned"] == []


def test_undo_and_redo_travel_over_http(client, session):
    ok(client, "/block/move", session=session, blockId=BLOCK, jour="3", heureDebut="14:00")

    undone = ok(client, "/undo", session=session)
    assert block_of(undone)["jour"] == "1"
    assert undone["canRedo"] is True

    redone = ok(client, "/redo", session=session)
    assert block_of(redone)["jour"] == "3"


def test_a_session_can_be_reset_over_http(client, session):
    ok(client, "/course/delete", session=session, courseId=COURSE)
    state = ok(client, "/reset", session=session)
    assert COURSE in {c["courseId"] for c in state["courses"]}


@pytest.mark.parametrize(
    "path,body,message",
    [
        (
            "/block/move",
            {"blockId": BLOCK, "jour": "1", "heureDebut": "09:00"},
            "déjà le Lundi",
        ),
        (
            "/block/resize",
            {"blockId": BLOCK, "heureDebut": "09:00", "heureFin": "12:00"},
            "couvre déjà",
        ),
        ("/course/delete", {"courseId": "LOG999-99"}, "introuvable"),
        ("/course/restore", {"courseId": COURSE}, "corbeille"),
        (
            "/course/add",
            {"sigle": "", "jour": "1", "heureDebut": "09:00", "heureFin": "12:00"},
            "sigle",
        ),
        (
            "/occurrence/cancel",
            {"blockId": BLOCK, "date": "2026-03-03"},
            "aucune séance le",
        ),
        (
            "/occurrence/reset",
            {"blockId": BLOCK, "date": "2026-03-09"},
            "Aucune modification",
        ),
        (
            "/evaluation/set",
            {"courseId": COURSE, "index": 0, "field": "inconnu", "value": "x"},
            "Champ",
        ),
        ("/evaluation/delete", {"courseId": COURSE, "index": 99}, "introuvable"),
        (
            "/evaluation/move",
            {"courseId": COURSE, "index": 0, "toIndex": 99},
            "introuvable",
        ),
        ("/grades/reset", {"courseId": COURSE}, "aucune note enregistrée"),
        ("/exam/reset", {"courseId": COURSE}, "aucune modification d'examen"),
        ("/exam/set", {"courseId": COURSE}, "Rien à modifier"),
        ("/undo", {}, "Rien à annuler"),
        ("/redo", {}, "Rien à rétablir"),
    ],
)
def test_a_refused_edit_comes_back_as_a_400(client, session, path, body, message):
    response = post(client, path, session=session, **body)
    assert response.status_code == 400
    assert message in response.json()["error"]


@pytest.mark.parametrize(
    "path,body",
    [
        ("/block/move", {"blockId": BLOCK, "jour": "3"}),
        ("/block/resize", {"blockId": BLOCK}),
        ("/course/delete", {}),
        ("/course/add", {"sigle": "ZZZ999"}),
        ("/occurrence/set", {"blockId": BLOCK, "date": "2026-03-02"}),
        ("/evaluation/set", {"courseId": COURSE, "index": 0}),
        ("/evaluation/move", {"courseId": COURSE, "index": 0}),
        ("/course/cote", {}),
    ],
)
def test_an_incomplete_body_is_a_422(client, session, path, body):
    assert post(client, path, session=session, **body).status_code == 422


def test_the_editor_state_reflects_edits_made_through_the_api(client, session):
    ok(client, "/block/move", session=session, blockId=BLOCK, jour="3", heureDebut="14:00")
    assert block_of(state_of(client, session))["jour"] == "3"


def test_the_public_api_reflects_edits_made_through_the_editor(client, session):
    ok(client, "/block/move", session=session, blockId=BLOCK, jour="3", heureDebut="14:00")

    served = client.get(
        "/api/Etudiant/lireHoraire", params={"session": session, "prefixe": "LOG430"}
    ).json()["listeCours"]

    assert served[0]["jour"] == "3"
    assert served[0]["heureDebut"] == "14:00"
