import pytest

from conftest import course, overrides, rows, user_overrides
from lib import compute, data_store, schedule_editor
from lib.resource_specs import COURSE_ACTIVITIES
from lib.schedule_editor import EditorError

BLOCK = "LOG430-02:0"
COURSE = "LOG430-02"
LAB = "LOG430-02:1"

PEDAGOGICAL_ORIGIN = "2026-02-23"
PEDAGOGICAL_TARGET = "2026-02-24"


def activity_dates(session, course_group):
    return {
        item["dateDebut"][:10]
        for item in data_store.load_session(COURSE_ACTIVITIES.filename, session)
        if item["coursGroupe"] == course_group
    }


def assert_overrides_are_readable(session, course_id):
    entry = course(session, course_id)
    window = schedule_editor._course_window(session)
    blocks = schedule_editor._blocks_of(entry)
    for override in entry.get("occurrenceOverrides", []):
        schedule = blocks[override["block"]]
        origins = compute.weekly_dates(
            window[0], window[1], int(schedule["jour"])
        )
        assert override["date"] in {d.isoformat() for d in origins}, (
            f"override {override} is orphaned: {override['date']} is not a "
            f"weekly slot of block {override['block']}"
        )


def test_replaced_day_displaces_the_monday_seance_onto_tuesday(session):
    state = schedule_editor.get_state(session)
    block = next(b for b in state["blocks"] if b["id"] == BLOCK)
    assert block["jour"] == "1"

    week = rows(state, BLOCK, "2026-02-23", "2026-02-28")
    assert [(r["date"], r["jour"]) for r in week] == [(PEDAGOGICAL_TARGET, "2")]


def test_series_move_to_the_blocks_own_slot_is_refused(session):
    with pytest.raises(EditorError, match="already on Lundi"):
        schedule_editor.move_block(session, BLOCK, "1", "09:00")

    assert schedule_editor.get_state(session)["canUndo"] is False


def test_series_move_to_the_same_slot_is_refused_after_an_occurrence_move(session):
    schedule_editor.set_occurrence(session, BLOCK, "2026-03-02", "3", "09:00", "12:00")

    with pytest.raises(EditorError, match="already on Lundi"):
        schedule_editor.move_block(session, BLOCK, "1", "09:00")


def test_a_displaced_seance_is_flagged_for_the_front_end(session):
    state = schedule_editor.get_state(session)
    row = rows(state, BLOCK, "2026-02-23", "2026-02-28")[0]
    block = next(b for b in state["blocks"] if b["id"] == BLOCK)

    assert row["overridden"] is True
    assert row["jour"] != block["jour"]


def test_a_real_series_move_still_goes_through(session):
    state = schedule_editor.move_block(session, BLOCK, "3", "14:00")
    block = next(b for b in state["blocks"] if b["id"] == BLOCK)
    assert (block["jour"], block["heureDebut"], block["heureFin"]) == (
        "3",
        "14:00",
        "17:00",
    )


def test_resize_to_the_same_hours_is_refused(session):
    with pytest.raises(EditorError, match="already spans"):
        schedule_editor.resize_block(session, BLOCK, "09:00", "12:00")


def test_occurrence_edits_survive_a_series_move(session):
    schedule_editor.set_occurrence(session, BLOCK, "2026-03-02", "3", "09:00", "12:00")
    assert overrides(session, COURSE, block=0)[-1]["date"] == "2026-03-02"

    schedule_editor.move_block(session, BLOCK, "3", "09:00")
    assert_overrides_are_readable(session, COURSE)

    state = schedule_editor.set_occurrence(
        session, BLOCK, "2026-03-04", "5", "09:00", "12:00"
    )
    week = rows(state, BLOCK, "2026-03-02", "2026-03-07")
    assert [(r["date"], r["overridden"]) for r in week] == [("2026-03-06", True)]
    assert "2026-03-06" in activity_dates(session, COURSE)


def test_series_move_rekeys_an_occurrence_edit_onto_the_new_weekday(session):
    schedule_editor.set_occurrence(session, BLOCK, "2026-03-02", "2", "14:00", "17:00")
    schedule_editor.move_block(session, BLOCK, "3", "09:00")

    kept = [ov for ov in overrides(session, COURSE, block=0) if not ov.get("source")]
    assert [ov["date"] for ov in kept] == ["2026-03-04"]
    assert kept[0]["targetDate"] == "2026-03-03"
    assert_overrides_are_readable(session, COURSE)


def test_series_move_drops_an_edit_it_makes_redundant(session):
    schedule_editor.set_occurrence(session, BLOCK, "2026-03-02", "3", "09:00", "12:00")
    state = schedule_editor.move_block(session, BLOCK, "3", "09:00")

    assert overrides(session, COURSE, block=0) == []
    assert [r["overridden"] for r in rows(state, BLOCK, "2026-03-02", "2026-03-07")] == [
        False
    ]


def test_an_occurrence_dragged_back_onto_its_series_slot_clears_the_override(session):
    schedule_editor.set_occurrence(session, BLOCK, "2026-03-02", "3", "09:00", "12:00")
    state = schedule_editor.set_occurrence(
        session, BLOCK, "2026-03-04", "1", "09:00", "12:00"
    )

    assert user_overrides(session, COURSE, block=0) == []
    assert [(r["date"], r["overridden"]) for r in
            rows(state, BLOCK, "2026-03-02", "2026-03-07")] == [("2026-03-02", False)]


def test_setting_an_occurrence_to_where_it_already_is_is_refused(session):
    with pytest.raises(EditorError, match="already where the series"):
        schedule_editor.set_occurrence(
            session, BLOCK, "2026-03-02", "1", "09:00", "12:00"
        )


def test_an_occurrence_is_addressed_by_the_date_it_is_drawn_on(session):
    state = schedule_editor.set_occurrence(
        session, BLOCK, PEDAGOGICAL_TARGET, "4", "13:30", "16:30"
    )

    stored = overrides(session, COURSE, block=0)
    assert [ov["date"] for ov in stored] == [PEDAGOGICAL_ORIGIN]
    assert stored[0]["targetDate"] == "2026-02-26"
    assert [(r["date"], r["heureDebut"]) for r in
            rows(state, BLOCK, "2026-02-23", "2026-02-28")] == [("2026-02-26", "13:30")]
    assert "2026-02-26" in activity_dates(session, COURSE)


def test_a_cross_week_relocation_is_still_addressable(session):
    entry = course(session, COURSE)
    entry.setdefault("occurrenceOverrides", []).append(
        {"block": 0, "date": "2026-03-02", "targetDate": "2026-03-11"}
    )
    schedule_editor._persist(session)

    state = schedule_editor.set_occurrence(
        session, BLOCK, "2026-03-11", "4", "14:00", "17:00"
    )

    relocated = [ov for ov in overrides(session, COURSE, block=0)
                 if ov["date"] == "2026-03-02"]
    assert relocated[0]["targetDate"] == "2026-03-12"
    assert [r["date"] for r in rows(state, BLOCK, "2026-03-09", "2026-03-14")] == [
        "2026-03-09",
        "2026-03-12",
    ]


def second_lecture(session):
    entry = course(session, COURSE)
    entry.setdefault("extraActivities", []).append(
        {
            "jour": "4",
            "journee": "Jeudi",
            "heureDebut": "18:00",
            "heureFin": "21:00",
            "codeActivite": "C",
            "nomActivite": "Activité de cours",
            "room": "B-2222",
        }
    )
    schedule_editor._persist(session)


def test_a_second_lecture_gets_its_own_block_id(session):
    second_lecture(session)
    state = schedule_editor.get_state(session)

    assert [b["id"] for b in state["blocks"] if b["courseId"] == COURSE] == [
        BLOCK,
        LAB,
        "LOG430-02:2",
    ]
    thursday = [
        r for r in state["occurrences"]
        if r["courseId"] == COURSE and r["date"] == "2026-03-12"
    ]
    assert [r["blockId"] for r in thursday] == ["LOG430-02:2"]


def test_moving_the_second_lecture_leaves_the_first_alone(session):
    second_lecture(session)
    state = schedule_editor.move_block(session, "LOG430-02:2", "4", "19:00")

    blocks = {b["id"]: b for b in state["blocks"]}
    assert (blocks[BLOCK]["jour"], blocks[BLOCK]["heureDebut"]) == ("1", "09:00")
    assert (blocks["LOG430-02:2"]["jour"], blocks["LOG430-02:2"]["heureDebut"]) == (
        "4",
        "19:00",
    )


def test_occurrence_edits_address_the_right_one_of_two_lectures(session):
    second_lecture(session)
    schedule_editor.cancel_occurrence(session, "LOG430-02:2", "2026-03-12")

    assert [ov["block"] for ov in overrides(session, COURSE)
            if ov.get("canceled")] == [2]
    assert "2026-03-12" not in activity_dates(session, COURSE)
    assert "2026-03-09" in activity_dates(session, COURSE)


def test_a_cancelled_seance_follows_its_series(session):
    schedule_editor.cancel_occurrence(session, BLOCK, "2026-03-09")
    state = schedule_editor.move_block(session, BLOCK, "3", "09:00")

    week = rows(state, BLOCK, "2026-03-09", "2026-03-14")
    assert [(r["date"], r["canceled"]) for r in week] == [("2026-03-11", True)]
    assert "2026-03-11" not in activity_dates(session, COURSE)
    assert_overrides_are_readable(session, COURSE)


def test_cancelling_twice_is_refused(session):
    schedule_editor.cancel_occurrence(session, BLOCK, "2026-03-09")
    with pytest.raises(EditorError, match="already cancelled"):
        schedule_editor.cancel_occurrence(session, BLOCK, "2026-03-09")


def test_a_cancelled_seance_is_restored_by_the_date_it_is_drawn_on(session):
    schedule_editor.cancel_occurrence(session, BLOCK, PEDAGOGICAL_TARGET)
    state = schedule_editor.reset_occurrence(session, BLOCK, PEDAGOGICAL_TARGET)

    week = rows(state, BLOCK, "2026-02-23", "2026-02-28")
    assert [(r["date"], r["canceled"]) for r in week] == [(PEDAGOGICAL_TARGET, False)]


def test_no_row_is_marked_overridden_by_an_orphaned_override(session):
    schedule_editor.set_occurrence(session, BLOCK, "2026-03-02", "3", "09:00", "12:00")
    state = schedule_editor.move_block(session, BLOCK, "5", "09:00")

    marked = [r["date"] for r in rows(state, BLOCK) if r["overridden"]]
    assert marked == ["2026-03-04"]
    assert [ov["date"] for ov in user_overrides(session, COURSE, block=0)] == [
        "2026-03-06"
    ]
    assert_overrides_are_readable(session, COURSE)


def test_reset_refuses_a_date_with_nothing_to_reset(session):
    with pytest.raises(EditorError, match="No override"):
        schedule_editor.reset_occurrence(session, BLOCK, "2026-03-09")


def test_reset_puts_a_moved_seance_back_on_the_series_slot(session):
    schedule_editor.set_occurrence(session, BLOCK, "2026-03-02", "3", "14:00", "17:00")
    state = schedule_editor.reset_occurrence(session, BLOCK, "2026-03-04")

    assert user_overrides(session, COURSE, block=0) == []
    assert [(r["date"], r["heureDebut"]) for r in
            rows(state, BLOCK, "2026-03-02", "2026-03-07")] == [("2026-03-02", "09:00")]


def test_moving_the_series_off_the_replaced_weekday_says_so(session):
    state = schedule_editor.move_block(session, BLOCK, "3", "09:00")

    assert any("pédagogique" in notice for notice in state.get("notices", []))
    assert overrides(session, COURSE, block=0) == []
    assert [r["date"] for r in rows(state, BLOCK, "2026-02-23", "2026-02-28")] == [
        "2026-02-25"
    ]


def test_a_series_move_that_keeps_the_weekday_keeps_the_relocation(session):
    state = schedule_editor.move_block(session, BLOCK, "1", "13:30")

    assert state.get("notices") is None
    assert [ov["date"] for ov in overrides(session, COURSE, block=0)] == [
        PEDAGOGICAL_ORIGIN
    ]
    assert [(r["date"], r["heureDebut"]) for r in
            rows(state, BLOCK, "2026-02-23", "2026-02-28")] == [
        (PEDAGOGICAL_TARGET, "13:30")
    ]


def test_editing_the_relocated_seance_takes_it_out_of_the_seeded_swap(session):
    schedule_editor.set_occurrence(
        session, BLOCK, PEDAGOGICAL_TARGET, "2", "14:00", "17:00"
    )
    state = schedule_editor.move_block(session, BLOCK, "3", "09:00")

    assert state.get("notices") is None
    stored = overrides(session, COURSE, block=0)
    assert [ov["date"] for ov in stored] == ["2026-02-25"]
    assert "source" not in stored[0]


def test_the_public_activity_fixture_keeps_its_shape(session):
    items = data_store.load_session(COURSE_ACTIVITIES.filename, session)
    assert items
    assert set(items[0]) == {
        "dateDebut",
        "dateFin",
        "coursGroupe",
        "nomActivite",
        "local",
        "descriptionActivite",
        "libelleCours",
    }


def test_editor_rows_and_the_api_agree_on_dates(session):
    schedule_editor.set_occurrence(session, BLOCK, "2026-03-02", "3", "10:00", "13:00")
    schedule_editor.cancel_occurrence(session, BLOCK, "2026-03-09")
    state = schedule_editor.get_state(session)

    visible = {r["date"] for r in rows(state, BLOCK) if not r["canceled"]}
    served = {
        item["dateDebut"][:10]
        for item in data_store.load_session(COURSE_ACTIVITIES.filename, session)
        if item["coursGroupe"] == COURSE and item["nomActivite"] == "Cours"
    }
    assert visible == served
