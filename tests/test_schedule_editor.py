import json
from datetime import date

import pytest

from conftest import course, overrides
from lib import data_store, schedule_editor
from lib.schedule_editor import EditorError

BLOCK = "LOG430-02:0"
LAB = "LOG430-02:1"
COURSE = "LOG430-02"
TEAM_COURSE = "LOG410-01"
CATALOG_SIGLE = "ATE100"


def block_of(state, block_id):
    return next(b for b in state["blocks"] if b["id"] == block_id)


def course_of(state, course_id):
    return next(c for c in state["courses"] if c["courseId"] == course_id)


def evals_of(state, course_id):
    return course_of(state, course_id)["evaluations"]


def test_the_state_answers_with_the_requested_session(session):
    assert schedule_editor.get_state(session)["session"] == session


def test_an_empty_session_falls_back_to_the_default_one():
    assert schedule_editor.get_state("")["session"] == data_store.resolve_default_session()


def test_an_unknown_session_falls_back_to_the_default_one():
    assert (
        schedule_editor.get_state("H2099")["session"]
        == data_store.resolve_default_session()
    )


def test_the_state_lists_every_session_that_has_courses(session):
    state = schedule_editor.get_state(session)
    assert state["sessions"] == data_store.get_sessions_with_courses()


def test_the_state_describes_the_grid(session):
    meta = schedule_editor.get_state(session)["meta"]

    assert meta["dayStart"] == "08:00"
    assert meta["dayEnd"] == "22:00"
    assert meta["snapMin"] == 15
    assert meta["minDuration"] == 30
    assert [d["jour"] for d in meta["days"]] == ["1", "2", "3", "4", "5", "6"]
    assert meta["days"][0] == {"jour": "1", "name": "Lundi", "short": "LUN"}


def test_the_state_carries_the_course_catalog(session):
    catalog = schedule_editor.get_state(session)["meta"]["catalog"]
    assert {"sigle", "titre"} == set(catalog[0])
    assert CATALOG_SIGLE in {c["sigle"] for c in catalog}


def test_the_semester_is_split_into_numbered_weeks(session):
    semester = schedule_editor.get_state(session)["meta"]["semester"]

    assert semester["dateDebut"] == "2026-01-05"
    assert [w["index"] for w in semester["weeks"]] == list(
        range(1, len(semester["weeks"]) + 1)
    )
    first = semester["weeks"][0]
    assert first["label"] == "Semaine 1"
    assert first["range"] == "5 janv. - 10 janv."
    assert first["dates"]["1"] == "2026-01-05"
    assert first["dates"]["6"] == "2026-01-10"


def test_every_week_starts_on_a_monday(session):
    semester = schedule_editor.get_state(session)["meta"]["semester"]
    for week in semester["weeks"]:
        assert date.fromisoformat(week["start"]).isoweekday() == 1
        assert date.fromisoformat(week["end"]).isoweekday() == 6


def test_the_weeks_cover_the_whole_session(session):
    semester = schedule_editor.get_state(session)["meta"]["semester"]
    assert semester["weeks"][0]["start"] <= semester["dateDebut"]
    assert semester["weeks"][-1]["end"] >= semester["dateFin"]


def test_a_session_without_dates_has_no_semester():
    assert schedule_editor._build_semester("H2099") is None


def test_a_course_is_normalized_for_the_front_end(session):
    entry = course_of(schedule_editor.get_state(session), COURSE)

    assert entry["sigle"] == "LOG430"
    assert entry["groupe"] == "02"
    assert entry["hasSchedule"] is True
    assert entry["canResetGrades"] is False
    assert [b["id"] for b in entry["blocks"]] == [BLOCK, LAB]
    assert set(entry["summary"]) == {
        "noteACeJour",
        "scoreFinalSur100",
        "moyenneClasse",
        "medianeClasse",
        "ecartTypeClasse",
        "rangCentileClasse",
        "tauxPublication",
    }


def test_a_block_carries_what_the_grid_needs(session):
    block = block_of(schedule_editor.get_state(session), LAB)

    assert block == {
        "id": LAB,
        "courseId": COURSE,
        "sigle": "LOG430",
        "groupe": "02",
        "titre": "Architecture logicielle",
        "room": "A-4209",
        "codeActivite": "L",
        "kind": "labo",
        "nomActivite": "Activité de laboratoire",
        "isPrimary": False,
        "jour": "5",
        "journee": "Vendredi",
        "heureDebut": "09:00",
        "heureFin": "12:00",
    }


def test_an_evaluation_is_normalized_with_numbers(session):
    evaluation = evals_of(schedule_editor.get_state(session), COURSE)[0]

    assert evaluation["index"] == 0
    assert isinstance(evaluation["ponderation"], int)
    assert isinstance(evaluation["note"], float)
    assert isinstance(evaluation["publie"], bool)
    assert evaluation["pinned"] == []


def test_an_unpublished_evaluation_has_no_numbers(session):
    hidden = [e for e in evals_of(schedule_editor.get_state(session), COURSE) if not e["publie"]]
    assert hidden
    assert hidden[0]["note"] is None
    assert hidden[0]["rangCentile"] is None


def test_the_exam_row_is_offered_beside_the_seances(session):
    state = schedule_editor.get_state(session)
    exams = [r for r in state["occurrences"] if r["kind"] == "exam"]

    assert exams
    assert exams[0]["blockId"].endswith(":exam")
    assert exams[0]["overridden"] is False
    assert exams[0]["canceled"] is False


def test_occurrences_are_sorted_by_date_then_hour(session):
    rows = schedule_editor.get_state(session)["occurrences"]
    keys = [(r["date"], r["heureDebut"], r["blockId"]) for r in rows]
    assert keys == sorted(keys)


def test_a_course_without_a_schedule_has_no_occurrences(session):
    entry = course(session, COURSE)
    entry["schedule"] = None
    schedule_editor._persist(session)

    state = schedule_editor.get_state(session)

    assert course_of(state, COURSE)["hasSchedule"] is False
    assert [b["id"] for b in course_of(state, COURSE)["blocks"]] == [LAB]
    assert [r for r in state["occurrences"] if r["courseId"] == COURSE] == []


@pytest.mark.parametrize(
    "value,expected", [("08:00", 480), ("09:30", 570), ("22:00", 1320), ("00:00", 0)]
)
def test_hours_convert_to_minutes(value, expected):
    assert schedule_editor._to_min(value) == expected
    assert schedule_editor._to_hhmm(expected) == value


@pytest.mark.parametrize(
    "raw,expected", [(540, 540), (547, 540), (548, 555), (555, 555), (0, 0)]
)
def test_minutes_snap_to_the_grid(raw, expected):
    assert schedule_editor._snap(raw) == expected


def test_a_range_is_clamped_into_the_day():
    assert schedule_editor._clamp_range(400, 600) == (480, 680)
    assert schedule_editor._clamp_range(1260, 1440) == (1260, 1320)
    assert schedule_editor._clamp_range(600, 600) == (600, 630)


def test_moving_a_block_snaps_the_start(session):
    state = schedule_editor.move_block(session, BLOCK, "2", "09:07")
    block = block_of(state, BLOCK)

    assert (block["jour"], block["journee"]) == ("2", "Mardi")
    assert (block["heureDebut"], block["heureFin"]) == ("09:00", "12:00")


def test_moving_a_block_keeps_its_duration(session):
    block = block_of(schedule_editor.move_block(session, BLOCK, "3", "14:00"), BLOCK)
    assert (block["heureDebut"], block["heureFin"]) == ("14:00", "17:00")


def test_a_block_cannot_be_moved_past_the_end_of_the_day(session):
    block = block_of(schedule_editor.move_block(session, BLOCK, "3", "21:00"), BLOCK)
    assert (block["heureDebut"], block["heureFin"]) == ("21:00", "22:00")


def test_a_block_cannot_be_moved_before_the_start_of_the_day(session):
    block = block_of(schedule_editor.move_block(session, BLOCK, "3", "06:00"), BLOCK)
    assert block["heureDebut"] == "08:00"


def test_moving_a_block_records_an_undo_step(session):
    state = schedule_editor.move_block(session, BLOCK, "3", "14:00")
    assert state["canUndo"] is True
    assert state["canRedo"] is False


@pytest.mark.parametrize("jour", ["0", "8", "abc", ""])
def test_a_block_cannot_be_moved_to_a_day_that_is_not_a_day(session, jour):
    with pytest.raises(EditorError, match="Jour .+ invalide"):
        schedule_editor.move_block(session, BLOCK, jour, "09:00")


def test_an_unknown_course_cannot_be_moved(session):
    with pytest.raises(EditorError, match="Cours « LOG999-99 » introuvable"):
        schedule_editor.move_block(session, "LOG999-99:0", "2", "09:00")


def test_an_unknown_block_index_cannot_be_moved(session):
    with pytest.raises(EditorError, match="introuvable"):
        schedule_editor.move_block(session, "LOG430-02:9", "2", "09:00")


def test_a_block_id_without_an_index_is_refused(session):
    with pytest.raises(EditorError, match="Identifiant de bloc"):
        schedule_editor.move_block(session, "LOG430-02:x", "2", "09:00")


def test_a_course_without_a_schedule_has_no_block_to_move(session):
    entry = course(session, COURSE)
    entry["schedule"] = None
    schedule_editor._persist(session)

    with pytest.raises(EditorError, match="n'a pas d'horaire"):
        schedule_editor.move_block(session, BLOCK, "2", "09:00")


def test_resizing_a_block_snaps_both_edges(session):
    block = block_of(
        schedule_editor.resize_block(session, BLOCK, "09:07", "11:52"), BLOCK
    )
    assert (block["heureDebut"], block["heureFin"]) == ("09:00", "11:45")


def test_a_block_cannot_be_resized_below_the_minimum(session):
    with pytest.raises(EditorError, match="trop court"):
        schedule_editor.resize_block(session, BLOCK, "09:00", "09:15")


def test_resizing_past_the_end_of_the_day_is_clamped(session):
    block = block_of(
        schedule_editor.resize_block(session, BLOCK, "20:00", "23:30"), BLOCK
    )
    assert (block["heureDebut"], block["heureFin"]) == ("20:00", "22:00")


def test_resizing_only_touches_its_own_block(session):
    state = schedule_editor.resize_block(session, LAB, "09:00", "13:00")
    assert block_of(state, LAB)["heureFin"] == "13:00"
    assert block_of(state, BLOCK)["heureFin"] == "12:00"


def test_a_course_is_added_from_the_catalog(session):
    state = schedule_editor.add_course(
        session, CATALOG_SIGLE, "", "3", "13:30", "17:00"
    )
    added = course_of(state, f"{CATALOG_SIGLE}-01")

    assert added["titre"] == "Intégrité intellectuelle"
    assert added["blocks"][0]["jour"] == "3"
    assert added["blocks"][0]["heureDebut"] == "13:30"
    assert added["blocks"][0]["heureFin"] == "17:00"
    assert added["blocks"][0]["codeActivite"] == "C"


def test_an_added_sigle_is_upper_cased_and_trimmed(session):
    state = schedule_editor.add_course(session, "  log999 ", "", "2", "09:00", "12:00")
    assert course_of(state, "LOG999-01")["sigle"] == "LOG999"


def test_an_unknown_sigle_is_its_own_title(session):
    state = schedule_editor.add_course(session, "ZZZ999", "", "2", "09:00", "12:00")
    assert course_of(state, "ZZZ999-01")["titre"] == "ZZZ999"


def test_an_explicit_title_wins(session):
    state = schedule_editor.add_course(
        session, CATALOG_SIGLE, "  Mon titre ", "2", "09:00", "12:00"
    )
    assert course_of(state, f"{CATALOG_SIGLE}-01")["titre"] == "Mon titre"


def test_a_second_group_of_the_same_course_is_numbered(session):
    schedule_editor.add_course(session, "ZZZ999", "", "2", "09:00", "12:00")
    state = schedule_editor.add_course(session, "ZZZ999", "", "3", "09:00", "12:00")

    assert {c["courseId"] for c in state["courses"] if c["sigle"] == "ZZZ999"} == {
        "ZZZ999-01",
        "ZZZ999-02",
    }


def test_a_deleted_group_number_is_not_reused(session):
    schedule_editor.add_course(session, "ZZZ999", "", "2", "09:00", "12:00")
    schedule_editor.delete_course(session, "ZZZ999-01")
    state = schedule_editor.add_course(session, "ZZZ999", "", "3", "09:00", "12:00")

    assert [c["courseId"] for c in state["courses"] if c["sigle"] == "ZZZ999"] == [
        "ZZZ999-02"
    ]


def test_a_lab_can_be_added(session):
    state = schedule_editor.add_course(
        session, "ZZZ999", "", "4", "14:00", "17:00", "labo"
    )
    block = course_of(state, "ZZZ999-01")["blocks"][0]

    assert block["codeActivite"] == "L"
    assert block["kind"] == "labo"
    assert block["nomActivite"] == "Laboratoire"


def test_an_added_course_gets_a_sensible_duration(session):
    state = schedule_editor.add_course(session, "ZZZ999", "", "2", "09:00", "09:10")
    assert course_of(state, "ZZZ999-01")["blocks"][0]["heureFin"] == "12:00"


def test_an_added_course_is_pushed_into_the_day(session):
    state = schedule_editor.add_course(session, "ZZZ999", "", "2", "06:00", "07:00")
    block = course_of(state, "ZZZ999-01")["blocks"][0]
    assert (block["heureDebut"], block["heureFin"]) == ("08:00", "09:00")


def test_an_added_course_shows_up_in_the_week(session):
    state = schedule_editor.add_course(session, "ZZZ999", "", "2", "09:00", "12:00")
    rows = [
        r
        for r in state["occurrences"]
        if r["courseId"] == "ZZZ999-01" and r["kind"] != "exam"
    ]
    assert rows
    assert {r["jour"] for r in rows} == {"2"}


def test_an_added_course_gets_grades_and_an_exam(session):
    state = schedule_editor.add_course(session, "ZZZ999", "", "2", "09:00", "12:00")
    added = course_of(state, "ZZZ999-01")

    assert added["evaluations"]
    assert added["exam"] is not None


def test_a_course_needs_a_sigle(session):
    with pytest.raises(EditorError, match="sigle"):
        schedule_editor.add_course(session, "   ", "", "2", "09:00", "12:00")


def test_a_course_needs_a_real_day(session):
    with pytest.raises(EditorError, match="Jour .+ invalide"):
        schedule_editor.add_course(session, "ZZZ999", "", "9", "09:00", "12:00")


def test_deleting_a_course_moves_it_to_the_trash(session):
    state = schedule_editor.delete_course(session, COURSE)

    assert [t["courseId"] for t in state["trash"]] == [COURSE]
    assert COURSE not in {c["courseId"] for c in state["courses"]}
    assert [r for r in state["occurrences"] if r["courseId"] == COURSE] == []


def test_a_trashed_course_can_be_restored(session):
    schedule_editor.delete_course(session, COURSE)
    state = schedule_editor.restore_course(session, COURSE)

    assert state["trash"] == []
    assert COURSE in {c["courseId"] for c in state["courses"]}


def test_deleting_an_unknown_course_is_refused(session):
    with pytest.raises(EditorError, match="introuvable"):
        schedule_editor.delete_course(session, "LOG999-99")


def test_restoring_a_course_that_was_never_deleted_is_refused(session):
    with pytest.raises(EditorError, match="corbeille"):
        schedule_editor.restore_course(session, COURSE)


def test_the_trash_entry_names_the_course(session):
    entry = schedule_editor.delete_course(session, COURSE)["trash"][0]
    assert entry == {
        "courseId": COURSE,
        "sigle": "LOG430",
        "groupe": "02",
        "titre": "Architecture logicielle",
    }


def test_an_evaluation_can_be_renamed(session):
    state = schedule_editor.set_evaluation(session, COURSE, 0, "nom", "  Intra  ")
    assert evals_of(state, COURSE)[0]["nom"] == "Intra"


def test_renaming_an_evaluation_renames_its_team(session):
    old = evals_of(schedule_editor.get_state(session), TEAM_COURSE)[0]["nom"]

    schedule_editor.set_evaluation(session, TEAM_COURSE, 0, "nom", "TP1 renommé")

    teammates = course(session, TEAM_COURSE)["teammates"]
    assert old not in teammates
    assert "TP1 renommé" in teammates


def test_an_evaluation_name_cannot_be_empty(session):
    with pytest.raises(EditorError, match="nom d'élément d'évaluation est requis"):
        schedule_editor.set_evaluation(session, COURSE, 0, "nom", "   ")


def test_two_evaluations_cannot_share_a_name(session):
    second = evals_of(schedule_editor.get_state(session), COURSE)[1]["nom"]
    with pytest.raises(EditorError, match="existe déjà"):
        schedule_editor.set_evaluation(session, COURSE, 0, "nom", second)


def test_an_evaluation_keeps_its_own_name(session):
    own = evals_of(schedule_editor.get_state(session), COURSE)[0]["nom"]
    state = schedule_editor.set_evaluation(session, COURSE, 0, "nom", own)
    assert evals_of(state, COURSE)[0]["nom"] == own


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("ponderation", "35", 35),
        ("ponderation", "12,4", 12),
        ("ponderation", 12.6, 13),
        ("ponderation", "0", 0),
        ("corrigeSur", "40", 40),
    ],
)
def test_weightings_are_stored_as_whole_numbers(session, field, value, expected):
    state = schedule_editor.set_evaluation(session, COURSE, 0, field, value)
    assert evals_of(state, COURSE)[0][field] == expected


@pytest.mark.parametrize(
    "field,value", [("ponderation", "-1"), ("corrigeSur", "0"), ("ponderation", "abc")]
)
def test_an_impossible_weighting_is_refused(session, field, value):
    with pytest.raises(EditorError):
        schedule_editor.set_evaluation(session, COURSE, 0, field, value)


def test_the_team_flag_is_a_boolean(session):
    state = schedule_editor.set_evaluation(session, COURSE, 0, "isTeam", 1)
    assert evals_of(state, COURSE)[0]["isTeam"] is True


def test_a_grade_can_be_pinned(session):
    state = schedule_editor.set_evaluation(session, COURSE, 0, "note", "12,75")

    evaluation = evals_of(state, COURSE)[0]
    assert evaluation["note"] == 12.8
    assert "note" in evaluation["pinned"]
    assert course_of(state, COURSE)["canResetGrades"] is True


def test_clearing_a_pinned_grade_gives_the_generated_one_back(session):
    generated = evals_of(schedule_editor.get_state(session), COURSE)[0]["note"]

    schedule_editor.set_evaluation(session, COURSE, 0, "note", "1,0")
    state = schedule_editor.set_evaluation(session, COURSE, 0, "note", "")

    evaluation = evals_of(state, COURSE)[0]
    assert evaluation["note"] == generated
    assert "note" not in evaluation["pinned"]


def test_a_percentile_is_clamped_to_a_hundred(session):
    state = schedule_editor.set_evaluation(session, COURSE, 0, "rangCentile", "150")
    assert evals_of(state, COURSE)[0]["rangCentile"] == 100

    state = schedule_editor.set_evaluation(session, COURSE, 0, "rangCentile", "-5")
    assert evals_of(state, COURSE)[0]["rangCentile"] == 0


def test_a_target_date_must_be_a_date(session):
    with pytest.raises(EditorError, match="Date .+ invalide"):
        schedule_editor.set_evaluation(session, COURSE, 0, "dateCible", "32 mars")


def test_a_target_date_can_be_pinned(session):
    state = schedule_editor.set_evaluation(
        session, COURSE, 0, "dateCible", "2026-03-02"
    )
    assert evals_of(state, COURSE)[0]["dateCible"] == "2026-03-02"


def test_publication_can_be_turned_off(session):
    state = schedule_editor.set_evaluation(session, COURSE, 0, "publie", False)

    evaluation = evals_of(state, COURSE)[0]
    assert evaluation["publie"] is False
    assert "publie" in evaluation["pinned"]


def test_publishing_an_evaluation_fills_its_summary(session):
    schedule_editor.set_evaluation(session, COURSE, 3, "publie", True)
    state = schedule_editor.get_state(session)

    assert evals_of(state, COURSE)[3]["publie"] is True
    assert course_of(state, COURSE)["summary"]["noteACeJour"]


def test_an_unknown_evaluation_field_is_refused(session):
    with pytest.raises(EditorError, match="Champ .+ inconnu"):
        schedule_editor.set_evaluation(session, COURSE, 0, "inconnu", "x")


@pytest.mark.parametrize("index", [-1, 99])
def test_an_evaluation_index_out_of_range_is_refused(session, index):
    with pytest.raises(EditorError, match="introuvable"):
        schedule_editor.set_evaluation(session, COURSE, index, "note", "10")


def test_an_evaluation_can_be_added(session):
    before = len(evals_of(schedule_editor.get_state(session), COURSE))

    state = schedule_editor.add_evaluation(session, COURSE)

    added = evals_of(state, COURSE)[-1]
    assert len(evals_of(state, COURSE)) == before + 1
    assert added["nom"] == "Nouvel élément"
    assert added["ponderation"] == 0
    assert added["corrigeSur"] == 100
    assert added["isTeam"] is False


def test_added_evaluations_get_unique_names(session):
    schedule_editor.add_evaluation(session, COURSE)
    state = schedule_editor.add_evaluation(session, COURSE)

    assert [e["nom"] for e in evals_of(state, COURSE)][-2:] == [
        "Nouvel élément",
        "Nouvel élément 2",
    ]


def test_an_evaluation_can_be_deleted(session):
    names = [e["nom"] for e in evals_of(schedule_editor.get_state(session), COURSE)]

    state = schedule_editor.delete_evaluation(session, COURSE, 1)

    assert [e["nom"] for e in evals_of(state, COURSE)] == names[:1] + names[2:]


def test_deleting_an_evaluation_drops_its_team(session):
    name = evals_of(schedule_editor.get_state(session), TEAM_COURSE)[0]["nom"]

    schedule_editor.delete_evaluation(session, TEAM_COURSE, 0)

    assert name not in course(session, TEAM_COURSE)["teammates"]


def test_deleting_an_unknown_evaluation_is_refused(session):
    with pytest.raises(EditorError, match="introuvable"):
        schedule_editor.delete_evaluation(session, COURSE, 99)


def test_evaluations_can_be_reordered(session):
    names = [e["nom"] for e in evals_of(schedule_editor.get_state(session), COURSE)]

    state = schedule_editor.move_evaluation(session, COURSE, 0, 2)

    assert [e["nom"] for e in evals_of(state, COURSE)] == [
        names[1],
        names[2],
        names[0],
        names[3],
    ]


def test_reordering_carries_the_grades_along(session):
    before = evals_of(schedule_editor.get_state(session), COURSE)
    moved = {"nom": before[0]["nom"], "note": before[0]["note"]}

    state = schedule_editor.move_evaluation(session, COURSE, 0, 2)

    landed = evals_of(state, COURSE)[2]
    assert landed["nom"] == moved["nom"]
    assert landed["note"] == moved["note"]


def test_reordering_keeps_the_summary_stable(session):
    before = course_of(schedule_editor.get_state(session), COURSE)["summary"]
    state = schedule_editor.move_evaluation(session, COURSE, 0, 2)
    assert course_of(state, COURSE)["summary"] == before


def test_reordering_to_the_same_place_changes_nothing(session):
    state = schedule_editor.move_evaluation(session, COURSE, 1, 1)
    assert state["canUndo"] is False


@pytest.mark.parametrize("to_index", [-1, 99])
def test_reordering_outside_the_list_is_refused(session, to_index):
    with pytest.raises(EditorError, match="introuvable"):
        schedule_editor.move_evaluation(session, COURSE, 0, to_index)


def test_grades_can_be_regenerated(session):
    generated = evals_of(schedule_editor.get_state(session), COURSE)[0]["note"]
    schedule_editor.set_evaluation(session, COURSE, 0, "note", "1,0")

    state = schedule_editor.reset_grades(session, COURSE)

    evaluation = evals_of(state, COURSE)[0]
    assert evaluation["note"] == generated
    assert evaluation["pinned"] == []
    assert course_of(state, COURSE)["canResetGrades"] is False


def test_regenerating_untouched_grades_is_refused(session):
    with pytest.raises(EditorError, match="aucune note enregistrée"):
        schedule_editor.reset_grades(session, COURSE)


def test_a_cote_is_stored_upper_cased(session):
    state = schedule_editor.set_cote(session, COURSE, "  a+ ")
    assert course_of(state, COURSE)["cote"] == "A+"


def test_a_cote_can_be_cleared(session):
    schedule_editor.set_cote(session, COURSE, "B")
    state = schedule_editor.set_cote(session, COURSE, "")
    assert course_of(state, COURSE)["cote"] == ""


def test_the_exam_date_can_be_pinned(session):
    state = schedule_editor.set_final_exam(session, COURSE, exam_date="2026-04-22")

    exam = course_of(state, COURSE)["exam"]
    assert exam["dateExamen"] == "2026-04-22"
    assert exam["pinned"] == ["dateExamen"]


def test_the_exam_hours_are_snapped_and_clamped(session):
    state = schedule_editor.set_final_exam(
        session, COURSE, heure_debut="09:07", heure_fin="12:52"
    )

    exam = course_of(state, COURSE)["exam"]
    assert (exam["heureDebut"], exam["heureFin"]) == ("09:00", "12:45")
    assert set(exam["pinned"]) == {"heureDebut", "heureFin"}


def test_only_one_exam_hour_is_needed(session):
    before = course_of(schedule_editor.get_state(session), COURSE)["exam"]
    later = schedule_editor._to_hhmm(schedule_editor._to_min(before["heureDebut"]) + 120)

    state = schedule_editor.set_final_exam(session, COURSE, heure_fin=later)

    exam = course_of(state, COURSE)["exam"]
    assert exam["heureDebut"] == before["heureDebut"]
    assert exam["heureFin"] == later


def test_an_exam_start_after_its_end_keeps_the_minimum_duration(session):
    before = course_of(schedule_editor.get_state(session), COURSE)["exam"]
    later = schedule_editor._to_hhmm(schedule_editor._to_min(before["heureFin"]) + 120)

    state = schedule_editor.set_final_exam(session, COURSE, heure_debut=later)

    exam = course_of(state, COURSE)["exam"]
    assert exam["heureDebut"] == later
    assert schedule_editor._to_min(exam["heureFin"]) - schedule_editor._to_min(
        exam["heureDebut"]
    ) == schedule_editor.MIN_DURATION_MIN


def test_the_exam_room_can_be_pinned_and_cleared(session):
    state = schedule_editor.set_final_exam(session, COURSE, local=" Z-9999 ")
    assert course_of(state, COURSE)["exam"]["local"] == "Z-9999"

    state = schedule_editor.set_final_exam(session, COURSE, local="")
    assert "local" not in course_of(state, COURSE)["exam"]["pinned"]


def test_clearing_the_exam_hours_restores_the_generated_ones(session):
    generated = course_of(schedule_editor.get_state(session), COURSE)["exam"]

    schedule_editor.set_final_exam(session, COURSE, heure_debut="14:00", heure_fin="17:00")
    state = schedule_editor.set_final_exam(session, COURSE, heure_debut="", heure_fin="")

    exam = course_of(state, COURSE)["exam"]
    assert exam["heureDebut"] == generated["heureDebut"]
    assert exam["pinned"] == []


def test_clearing_every_exam_field_drops_the_override(session):
    schedule_editor.set_final_exam(session, COURSE, exam_date="2026-04-22")
    schedule_editor.set_final_exam(session, COURSE, exam_date="")

    assert "finalExam" not in course(session, COURSE)


def test_an_exam_update_with_nothing_in_it_is_refused(session):
    with pytest.raises(EditorError, match="Rien à modifier"):
        schedule_editor.set_final_exam(session, COURSE)


def test_a_course_without_a_schedule_has_no_exam_to_set(session):
    entry = course(session, COURSE)
    entry["schedule"] = None
    schedule_editor._persist(session)

    with pytest.raises(EditorError, match="n'a pas d'examen final"):
        schedule_editor.set_final_exam(session, COURSE, exam_date="2026-04-22")


def test_an_exam_override_can_be_reset(session):
    generated = course_of(schedule_editor.get_state(session), COURSE)["exam"]
    schedule_editor.set_final_exam(session, COURSE, exam_date="2026-04-22")

    state = schedule_editor.reset_final_exam(session, COURSE)

    assert course_of(state, COURSE)["exam"] == generated


def test_resetting_an_untouched_exam_is_refused(session):
    with pytest.raises(EditorError, match="aucune modification d'examen"):
        schedule_editor.reset_final_exam(session, COURSE)


def test_a_pinned_exam_shows_up_as_overridden_in_the_week(session):
    state = schedule_editor.set_final_exam(session, COURSE, exam_date="2026-04-22")
    row = next(
        r for r in state["occurrences"] if r["blockId"] == f"{COURSE}:exam"
    )
    assert row["date"] == "2026-04-22"
    assert row["overridden"] is True


def test_an_edit_can_be_undone(session):
    schedule_editor.move_block(session, BLOCK, "3", "14:00")

    state = schedule_editor.undo(session)

    block = block_of(state, BLOCK)
    assert (block["jour"], block["heureDebut"]) == ("1", "09:00")
    assert state["canUndo"] is False
    assert state["canRedo"] is True


def test_an_undone_edit_can_be_redone(session):
    schedule_editor.move_block(session, BLOCK, "3", "14:00")
    schedule_editor.undo(session)

    state = schedule_editor.redo(session)

    block = block_of(state, BLOCK)
    assert (block["jour"], block["heureDebut"]) == ("3", "14:00")
    assert state["canRedo"] is False


def test_undo_walks_back_several_edits(session):
    schedule_editor.move_block(session, BLOCK, "3", "14:00")
    schedule_editor.resize_block(session, BLOCK, "14:00", "16:00")

    schedule_editor.undo(session)
    state = schedule_editor.undo(session)

    block = block_of(state, BLOCK)
    assert (block["jour"], block["heureDebut"], block["heureFin"]) == (
        "1",
        "09:00",
        "12:00",
    )


def test_a_new_edit_drops_the_redo_stack(session):
    schedule_editor.move_block(session, BLOCK, "3", "14:00")
    schedule_editor.undo(session)

    state = schedule_editor.resize_block(session, BLOCK, "09:00", "11:00")

    assert state["canRedo"] is False


def test_undo_without_history_is_refused(session):
    schedule_editor.get_state(session)
    with pytest.raises(EditorError, match="Rien à annuler"):
        schedule_editor.undo(session)


def test_redo_without_history_is_refused(session):
    schedule_editor.get_state(session)
    with pytest.raises(EditorError, match="Rien à rétablir"):
        schedule_editor.redo(session)


def test_the_undo_history_is_capped(session):
    for step in range(schedule_editor.MAX_HISTORY + 5):
        schedule_editor.resize_block(
            session, BLOCK, "09:00", "11:00" if step % 2 else "11:30"
        )

    assert len(schedule_editor._undo[session]) == schedule_editor.MAX_HISTORY


def test_undo_is_kept_per_session(session):
    schedule_editor.move_block(session, BLOCK, "3", "14:00")
    other = "H2025"

    assert schedule_editor.get_state(other)["canUndo"] is False
    assert schedule_editor.get_state(session)["canUndo"] is True


def test_resetting_a_session_brings_every_course_back(session):
    schedule_editor.move_block(session, LAB, "2", "14:00")
    schedule_editor.delete_course(session, COURSE)

    state = schedule_editor.reset_session(session)

    assert COURSE in {c["courseId"] for c in state["courses"]}
    assert state["trash"] == []
    assert block_of(state, LAB)["jour"] == "5"


def test_resetting_a_session_can_be_undone(session):
    schedule_editor.delete_course(session, COURSE)
    schedule_editor.reset_session(session)

    state = schedule_editor.undo(session)

    assert [t["courseId"] for t in state["trash"]] == [COURSE]


def test_resetting_a_session_forgets_its_stored_edits(session, sandbox_overrides):
    schedule_editor.move_block(session, BLOCK, "3", "14:00")
    assert sandbox_overrides.exists()

    schedule_editor.reset_session(session)

    assert not sandbox_overrides.exists()


def test_an_edit_is_written_to_the_overrides_file(session, sandbox_overrides):
    schedule_editor.move_block(session, BLOCK, "3", "14:00")

    stored = json.loads(sandbox_overrides.read_text(encoding="utf-8"))
    entry = next(
        c for c in stored[session]["courses"] if c["sigle"] == "LOG430"
    )
    assert entry["schedule"]["jour"] == "3"
    assert entry["schedule"]["heureDebut"] == "14:00"


def test_an_edit_survives_a_cache_clear(session):
    schedule_editor.move_block(session, BLOCK, "3", "14:00")

    schedule_editor.clear_cache()

    assert block_of(schedule_editor.get_state(session), BLOCK)["jour"] == "3"


def test_the_api_serves_the_edited_schedule(session):
    schedule_editor.move_block(session, BLOCK, "3", "14:00")

    served = data_store.load_session("course_schedule.json", session)
    entry = next(c for c in served if c["sigle"] == "LOG430")

    assert entry["jour"] == "3"
    assert entry["heureDebut"] == "14:00"


def test_the_api_serves_an_added_course(session):
    schedule_editor.add_course(session, "ZZZ999", "Ajouté", "2", "09:00", "12:00")

    served = data_store.load("courses.json")

    assert any(c["sigle"] == "ZZZ999" and c["session"] == session for c in served)


def test_the_api_stops_serving_a_deleted_course(session):
    schedule_editor.delete_course(session, COURSE)

    served = data_store.load_session("course_schedule.json", session)

    assert all(c["sigle"] != "LOG430" for c in served)


def test_an_occurrence_edit_lands_in_the_overrides_file(session, sandbox_overrides):
    schedule_editor.set_occurrence(session, BLOCK, "2026-03-02", "3", "09:00", "12:00")

    stored = json.loads(sandbox_overrides.read_text(encoding="utf-8"))
    entry = next(c for c in stored[session]["courses"] if c["sigle"] == "LOG430")

    assert any(
        ov["date"] == "2026-03-02" and ov["targetDate"] == "2026-03-04"
        for ov in entry["occurrenceOverrides"]
    )


def test_an_occurrence_can_only_be_addressed_on_a_day_it_is_drawn(session):
    with pytest.raises(EditorError, match="aucune séance le"):
        schedule_editor.cancel_occurrence(session, BLOCK, "2026-03-03")


@pytest.mark.parametrize("day", ["pas-une-date", "2026-13-01", ""])
def test_an_occurrence_needs_a_real_date(session, day):
    with pytest.raises(EditorError, match="Date .+ invalide"):
        schedule_editor.cancel_occurrence(session, BLOCK, day)


def test_a_cancelled_occurrence_keeps_its_week_specific_edit(session):
    schedule_editor.set_occurrence(session, BLOCK, "2026-03-02", "3", "14:00", "17:00")
    schedule_editor.cancel_occurrence(session, BLOCK, "2026-03-04")

    state = schedule_editor.reset_occurrence(session, BLOCK, "2026-03-04")

    row = next(
        r
        for r in state["occurrences"]
        if r["blockId"] == BLOCK and r["date"] == "2026-03-04"
    )
    assert row["canceled"] is False
    assert row["heureDebut"] == "14:00"
    assert overrides(session, COURSE, block=0)


def test_editing_a_session_leaves_the_others_untouched(session):
    other = "H2025"
    before = schedule_editor.get_state(other)["blocks"]

    schedule_editor.move_block(session, BLOCK, "3", "14:00")

    assert schedule_editor.get_state(other)["blocks"] == before
