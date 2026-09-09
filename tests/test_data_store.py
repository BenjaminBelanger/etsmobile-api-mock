import json
from datetime import date, timedelta

import pytest

import conftest
from lib import data_store, sessions
from lib.resource_specs import (
    COURSE_ACTIVITIES,
    COURSES,
    GENERATED_FILENAMES,
    PROGRAMS,
    SESSIONS,
    TEAMMATES,
)

SESSION = "H2026"


def write_overrides(path, session, courses, trash=None):
    path.write_text(
        json.dumps({session: {"courses": courses, "trash": trash or []}}),
        encoding="utf-8",
    )
    data_store.reload()


def test_a_loaded_fixture_is_cached():
    assert data_store.load(COURSES.filename) is data_store.load(COURSES.filename)


def test_reloading_drops_the_cache():
    first = data_store.load(COURSES.filename)
    data_store.reload()
    assert data_store.load(COURSES.filename) is not first


def test_every_generated_fixture_can_be_loaded():
    for name in GENERATED_FILENAMES:
        assert data_store.load(name) is not None


def test_a_seed_only_fixture_is_read_from_disk():
    assert data_store.load("student_info.json")["codePerm"] == "ABCD12345678"


def test_only_sessions_with_courses_are_served():
    listed = {s["abrege"] for s in data_store.load(SESSIONS.filename)}
    assert listed == {c["session"] for c in data_store.load(COURSES.filename)}


def test_the_active_and_next_sessions_are_known():
    assert data_store.ACTIVE_SESSION == sessions.compute_active_session()
    assert data_store.NEXT_SESSION == sessions.compute_next_session(
        data_store.ACTIVE_SESSION
    )


def test_the_next_session_gets_generated_courses():
    listed = {c["session"] for c in data_store.load(COURSES.filename)}
    assert data_store.NEXT_SESSION in listed


def test_a_session_fixture_falls_back_to_its_default():
    assert data_store.load_session(COURSE_ACTIVITIES.filename, "H2099") == []
    assert data_store.load_session(TEAMMATES.filename, "H2099", {}) == {}
    assert data_store.load_session(COURSE_ACTIVITIES.filename, "H2099", "vide") == "vide"


def test_the_empty_evaluation_carries_the_full_summary():
    empty = data_store.empty_evaluation()
    assert empty["liste"] == []
    assert empty["tauxPublication"] == "0,0"
    assert set(empty) == {
        "noteACeJour",
        "scoreFinalSur100",
        "moyenneClasse",
        "ecartTypeClasse",
        "medianeClasse",
        "rangCentileClasse",
        "noteACeJourElementsIndividuels",
        "noteSur100PourElementsIndividuels",
        "tauxPublication",
        "liste",
    }


def test_the_empty_evaluation_is_a_fresh_object():
    first = data_store.empty_evaluation()
    first["liste"].append("x")
    assert data_store.empty_evaluation()["liste"] == []


def test_session_courses_are_handed_out_as_copies():
    courses = data_store.get_session_courses(SESSION)
    courses[0]["sigle"] = "MUTÉ"
    assert data_store.get_session_courses(SESSION)[0]["sigle"] != "MUTÉ"


def test_session_courses_are_filtered_by_session():
    assert {c["session"] for c in data_store.get_session_courses(SESSION)} == {SESSION}


def test_sessions_with_courses_are_listed_newest_first():
    listed = data_store.get_sessions_with_courses()
    assert listed == sorted(listed, key=sessions.session_rank, reverse=True)
    assert SESSION in listed


def test_the_default_session_is_the_active_one_when_it_has_courses():
    assert data_store.resolve_default_session() == data_store.ACTIVE_SESSION


def test_the_default_session_falls_back_to_the_newest_one(monkeypatch):
    monkeypatch.setattr(data_store, "ACTIVE_SESSION", "H2099")
    assert data_store.resolve_default_session() == data_store.get_sessions_with_courses()[0]


def test_pools_and_professors_are_handed_out_as_copies():
    pools = data_store.get_pools()
    pools["rooms"].append("Z-9999")
    assert "Z-9999" not in data_store.get_pools()["rooms"]

    professors = data_store.get_professors()
    professors.clear()
    assert data_store.get_professors()


def test_an_override_file_replaces_the_courses_of_its_session(sandbox_overrides):
    kept = [c for c in data_store.get_session_courses(SESSION)][:1]
    kept[0]["sigle"] = "OVR100"

    write_overrides(sandbox_overrides, SESSION, kept)

    session_courses = [
        c for c in data_store.load(COURSES.filename) if c["session"] == SESSION
    ]
    assert [c["sigle"] for c in session_courses] == ["OVR100"]


def test_an_override_file_leaves_other_sessions_alone(sandbox_overrides):
    before = [c for c in data_store.load(COURSES.filename) if c["session"] == "H2024"]

    write_overrides(sandbox_overrides, SESSION, [])

    assert [
        c for c in data_store.load(COURSES.filename) if c["session"] == "H2024"
    ] == before


def test_an_overridden_session_still_counts_as_having_courses(sandbox_overrides):
    write_overrides(sandbox_overrides, "H2020", [])
    assert "H2020" in data_store.get_sessions_with_courses()


def test_the_base_courses_ignore_the_override_file(sandbox_overrides):
    write_overrides(sandbox_overrides, SESSION, [])

    assert data_store.get_session_courses(SESSION) == []
    assert data_store.get_session_courses(SESSION, base=True)


def test_a_broken_override_file_is_ignored(sandbox_overrides):
    sandbox_overrides.write_text("{ pas du json", encoding="utf-8")
    data_store.reload()
    assert data_store.get_session_courses(SESSION)


def test_a_missing_override_file_is_fine(sandbox_overrides):
    assert not sandbox_overrides.exists()
    assert data_store._load_overrides() == {}


def test_the_overrides_file_lives_next_to_the_seed_data():
    assert conftest._REAL_OVERRIDES.name == "schedule_overrides.json"
    assert conftest._REAL_OVERRIDES.parent.name == "seed"


def test_a_profile_reshapes_the_active_session(reconfigure):
    reconfigure(PROFILE="semester-off")

    active = data_store.ACTIVE_SESSION
    assert [c for c in data_store.load(COURSES.filename) if c["session"] == active] == []


def test_a_profile_can_add_a_program(reconfigure):
    reconfigure(PROFILE="internship-only")

    codes = [p["code"] for p in data_store.load(PROGRAMS.filename)]
    assert "0726" in codes


def test_a_generation_profile_sets_the_generation_config(reconfigure):
    reconfigure(PROFILE="generated-light")
    assert data_store.GENERATION_CONFIG["count"] == 2


def test_generation_flags_reach_the_generated_courses(reconfigure):
    reconfigure(COURSE_COUNT="2", SCHEDULE_DAYS="1,3", TIME_PREFERENCE="evening")

    active = data_store.ACTIVE_SESSION
    generated = [c for c in data_store.get_session_courses(active)]

    assert len(generated) == 2
    assert {c["schedule"]["jour"] for c in generated} <= {"1", "3"}
    assert all(c["schedule"]["heureDebut"] >= "18:00" for c in generated)


def test_an_unknown_profile_stops_the_boot(reconfigure):
    with pytest.raises(ValueError, match="Unknown profile"):
        reconfigure(PROFILE="inconnu")


def test_an_unknown_scenario_stops_the_boot(reconfigure):
    with pytest.raises(ValueError, match="Unknown scenario"):
        reconfigure(SCENARIO="inconnu")


@pytest.mark.parametrize("raw", ["abc", "0", "-2"])
def test_an_impossible_semester_week_stops_the_boot(reconfigure, raw):
    with pytest.raises(ValueError, match="SEMESTER_WEEK"):
        reconfigure(SEMESTER_WEEK=raw)


def test_an_empty_semester_week_means_the_real_calendar(reconfigure):
    reconfigure(SEMESTER_WEEK="")
    assert data_store.SEMESTER_WEEK is None


def test_the_semester_week_shifts_the_active_session(reconfigure):
    reconfigure(SEMESTER_WEEK="3")

    window = sessions.course_window(data_store.ACTIVE_SESSION)
    today = date.today()
    this_monday = today - timedelta(days=today.weekday())
    start_monday = window[0] - timedelta(days=window[0].weekday())

    assert data_store.SEMESTER_WEEK == 3
    assert (this_monday - start_monday).days == 14


def test_the_semester_week_shifts_the_next_session_by_the_same_amount(reconfigure):
    before = sessions.course_window(data_store.NEXT_SESSION)
    active_before = sessions.course_window(data_store.ACTIVE_SESSION)

    reconfigure(SEMESTER_WEEK="3")

    after = sessions.course_window(data_store.NEXT_SESSION)
    active_after = sessions.course_window(data_store.ACTIVE_SESSION)

    assert (after[0] - before[0]).days == (active_after[0] - active_before[0]).days


def test_a_scenario_reaches_the_replaced_days_fixture(reconfigure):
    reconfigure(SCENARIO="monday-holiday")

    entries = data_store.load("replaced_days.json")[data_store.ACTIVE_SESSION]
    assert any(e["description"] == "Jour férié" for e in entries)


def test_a_scenario_cancels_seances_in_the_activity_fixture(reconfigure):
    active = data_store.ACTIVE_SESSION
    reconfigure(SCENARIO="none")
    before = len(data_store.load_session(COURSE_ACTIVITIES.filename, active))

    reconfigure(SCENARIO="semaine-relache")
    after = len(data_store.load_session(COURSE_ACTIVITIES.filename, active))

    assert after < before
