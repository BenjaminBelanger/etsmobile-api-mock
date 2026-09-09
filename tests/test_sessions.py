import json
from datetime import date, timedelta

import pytest

from lib import sessions
from lib._paths import SEED


@pytest.fixture
def today(monkeypatch):
    def apply(iso):
        frozen = date.fromisoformat(iso)

        class FrozenDate(date):
            @classmethod
            def today(cls):
                return frozen

        monkeypatch.setattr(sessions, "date", FrozenDate)
        return frozen

    return apply


@pytest.fixture
def pools():
    return json.loads((SEED / "pools.json").read_text(encoding="utf-8"))


@pytest.fixture
def professors():
    return json.loads((SEED / "professors.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "iso,expected",
    [
        ("2026-01-01", "H2026"),
        ("2026-04-30", "H2026"),
        ("2026-05-01", "H2026"),
        ("2026-05-02", "É2026"),
        ("2026-08-31", "É2026"),
        ("2026-09-01", "A2026"),
        ("2026-12-31", "A2026"),
    ],
)
def test_the_active_session_follows_the_calendar(today, iso, expected):
    today(iso)
    assert sessions.compute_active_session() == expected


@pytest.mark.parametrize(
    "active,expected",
    [("H2026", "É2026"), ("É2026", "A2026"), ("E2026", "A2026"), ("A2026", "H2027")],
)
def test_the_next_session_follows_the_active_one(active, expected):
    assert sessions.compute_next_session(active) == expected


def test_the_next_session_defaults_to_the_active_one(today):
    today("2026-09-09")
    assert sessions.compute_next_session() == "H2027"


def test_session_codes_sort_chronologically():
    codes = ["A2025", "H2024", "É2024", "H2025", "A2024", "É2025"]
    assert sorted(codes, key=sessions.session_rank) == [
        "H2024",
        "É2024",
        "A2024",
        "H2025",
        "É2025",
        "A2025",
    ]


def test_the_two_spellings_of_ete_rank_the_same():
    assert sessions.session_rank("É2025") == sessions.session_rank("E2025")


@pytest.mark.parametrize("code", ["", "X", "H26", "inconnu"])
def test_an_unreadable_session_code_ranks_last(code):
    assert sessions.session_rank(code) == 9999


def test_the_course_window_runs_from_the_start_to_the_last_class_day():
    assert sessions.course_window("H2026") == (
        date(2026, 1, 5),
        date(2026, 4, 15),
    )


def test_an_unknown_session_has_no_course_window():
    assert sessions.course_window("H2099") is None


def test_a_session_without_dates_has_no_course_window():
    sessions.get_raw_sessions().append({"abrege": "X2099", "auLong": "Inconnu"})
    assert sessions.course_window("X2099") is None


def test_a_missing_session_is_cloned_from_the_latest_one_of_its_kind():
    sessions.ensure_session_metadata("H2027")

    cloned = next(s for s in sessions.get_raw_sessions() if s["abrege"] == "H2027")
    source = next(s for s in sessions.get_raw_sessions() if s["abrege"] == "H2026")

    assert cloned["auLong"] == "Hiver 2027"
    assert date.fromisoformat(cloned["dateDebut"]).weekday() == (
        date.fromisoformat(source["dateDebut"]).weekday()
    )
    assert date.fromisoformat(cloned["dateDebut"]).year == 2027
    assert set(cloned) == set(source)


def test_cloning_shifts_every_date_field_by_the_same_amount():
    sessions.ensure_session_metadata("A2026")

    cloned = next(s for s in sessions.get_raw_sessions() if s["abrege"] == "A2026")
    source = next(s for s in sessions.get_raw_sessions() if s["abrege"] == "A2025")
    deltas = {
        (date.fromisoformat(cloned[key][:10]) - date.fromisoformat(value[:10])).days
        for key, value in source.items()
        if key not in ("abrege", "auLong")
    }
    assert len(deltas) == 1


def test_an_existing_session_is_not_cloned_again():
    before = json.dumps(sessions.get_raw_sessions(), ensure_ascii=False)
    sessions.ensure_session_metadata("H2026")
    assert json.dumps(sessions.get_raw_sessions(), ensure_ascii=False) == before


def test_a_session_with_no_relative_is_left_alone():
    sessions.ensure_session_metadata("X2099")
    assert all(s["abrege"] != "X2099" for s in sessions.get_raw_sessions())


def test_cloning_without_a_source_is_an_error():
    with pytest.raises(ValueError, match="No source session"):
        sessions._clone_session_dates("X2099")


def session_start(code="H2026"):
    entry = next(s for s in sessions.get_raw_sessions() if s["abrege"] == code)
    return date.fromisoformat(entry["dateDebut"])


def test_the_week_shift_puts_today_in_the_requested_week(today):
    now = today("2026-09-09")
    original_weekday = session_start().weekday()

    sessions.shift_session_metadata(
        "H2026", sessions.compute_week_shift_delta("H2026", 3)
    )

    start = session_start()
    this_monday = now - timedelta(days=now.weekday())
    start_monday = start - timedelta(days=start.weekday())
    assert (this_monday - start_monday).days == 14
    assert start.weekday() == original_weekday


def test_the_first_week_starts_on_the_current_week(today):
    now = today("2026-09-09")

    sessions.shift_session_metadata(
        "H2026", sessions.compute_week_shift_delta("H2026", 1)
    )

    start = session_start()
    assert start - timedelta(days=start.weekday()) == now - timedelta(days=now.weekday())


def test_the_week_shift_moves_every_date_field(today):
    today("2026-09-09")
    before = dict(
        next(s for s in sessions.get_raw_sessions() if s["abrege"] == "H2026")
    )
    delta = sessions.compute_week_shift_delta("H2026", 5)
    sessions.shift_session_metadata("H2026", delta)
    after = next(s for s in sessions.get_raw_sessions() if s["abrege"] == "H2026")

    assert after["abrege"] == before["abrege"]
    assert after["auLong"] == before["auLong"]
    for key, value in before.items():
        if key in ("abrege", "auLong"):
            continue
        assert (
            date.fromisoformat(after[key][:10]) - date.fromisoformat(value[:10])
        ).days == delta


def test_a_zero_shift_changes_nothing():
    before = json.dumps(sessions.get_raw_sessions(), ensure_ascii=False)
    sessions.shift_session_metadata("H2026", 0)
    assert json.dumps(sessions.get_raw_sessions(), ensure_ascii=False) == before


def test_shifting_an_unknown_session_changes_nothing():
    before = json.dumps(sessions.get_raw_sessions(), ensure_ascii=False)
    sessions.shift_session_metadata("H2099", 30)
    assert json.dumps(sessions.get_raw_sessions(), ensure_ascii=False) == before


@pytest.mark.parametrize("week", [0, -1])
def test_a_week_before_the_first_one_is_refused(week):
    with pytest.raises(ValueError, match="target_week must be >= 1"):
        sessions.compute_week_shift_delta("H2026", week)


def test_the_week_shift_needs_a_known_session():
    with pytest.raises(ValueError, match="No metadata"):
        sessions.compute_week_shift_delta("X2099", 3)


def test_a_session_that_already_has_courses_generates_none(pools, professors):
    seed = [{"session": "H2026", "sigle": "LOG430"}]
    assert sessions.generate_random_courses("H2026", seed, pools, professors) == []


def test_an_empty_session_is_filled_from_the_catalog(pools, professors):
    generated = sessions.generate_random_courses("A2027", [], pools, professors)

    assert len(generated) == pools["generatedCoursesPerSemester"]
    assert {c["session"] for c in generated} == {"A2027"}
    assert all(c["schedule"]["codeActivite"] == "C" for c in generated)


def test_generation_is_stable_for_a_given_session(pools, professors):
    first = sessions.generate_random_courses("A2027", [], pools, professors)
    second = sessions.generate_random_courses("A2027", [], pools, professors)
    assert first == second


def test_two_sessions_do_not_generate_the_same_schedule(pools, professors):
    first = sessions.generate_random_courses("A2027", [], pools, professors)
    second = sessions.generate_random_courses("H2028", [], pools, professors)
    assert [c["sigle"] for c in first] != [c["sigle"] for c in second]


def test_generation_avoids_sigles_already_taken(pools, professors):
    taken = {c["sigle"] for c in pools["courseCatalog"][:40]}
    seed = [{"session": "H2020", "sigle": sigle} for sigle in taken]

    generated = sessions.generate_random_courses("A2027", seed, pools, professors)

    assert not {c["sigle"] for c in generated} & taken


def test_a_generated_course_carries_everything_the_builder_needs(pools, professors):
    course = sessions.generate_random_courses("A2027", [], pools, professors)[0]

    assert set(course) == {
        "sigle",
        "groupe",
        "session",
        "titreCours",
        "nbCredits",
        "programmeEtudes",
        "cote",
        "professorId",
        "room",
        "examRoom",
        "schedule",
        "extraActivities",
        "evaluations",
        "teammates",
        "gradePublishRatio",
        "gradeSeed",
    }
    assert course["professorId"] in professors
    assert course["room"] in pools["rooms"]
    assert course["examRoom"] in pools["examRooms"]


def test_a_generated_course_gets_a_lab_on_another_day(pools, professors):
    for course in sessions.generate_random_courses("A2027", [], pools, professors):
        labs = course["extraActivities"]
        assert len(labs) == 1
        assert labs[0]["codeActivite"] == "L"
        assert labs[0]["jour"] != course["schedule"]["jour"]
        assert labs[0]["room"] in pools["rooms"]


def test_a_lab_lasts_three_hours(pools, professors):
    lab = sessions.generate_random_courses("A2027", [], pools, professors)[0][
        "extraActivities"
    ][0]
    start_hour = int(lab["heureDebut"][:2])
    assert lab["heureFin"] == f"{start_hour + sessions.LAB_DURATION_HOURS:02d}:{lab['heureDebut'][3:]}"


def test_a_profile_generates_the_requested_number_of_courses(pools, professors):
    seed = [{"session": "H2024", "sigle": "LOG121"}]
    config = {"count": 2, "allowedDays": None, "timePreference": None}

    result = sessions.generate_profile_courses("A2027", seed, pools, professors, config)

    assert len([c for c in result if c["session"] == "A2027"]) == 2
    assert seed[0] in result


def test_a_profile_replaces_the_courses_of_the_active_session(pools, professors):
    seed = [{"session": "A2027", "sigle": "LOG430"}]
    config = {"count": 1, "allowedDays": None, "timePreference": None}

    result = sessions.generate_profile_courses("A2027", seed, pools, professors, config)

    assert [c["sigle"] for c in result] != ["LOG430"]
    assert len(result) == 1


def test_a_profile_keeps_generated_courses_on_the_allowed_days(pools, professors):
    config = {"count": 3, "allowedDays": ["1", "3"], "timePreference": None}

    result = sessions.generate_profile_courses("A2027", [], pools, professors, config)

    assert {c["schedule"]["jour"] for c in result} <= {"1", "3"}
    for course in result:
        assert {a["jour"] for a in course["extraActivities"]} <= {"1", "3"}


def test_a_profile_keeps_generated_courses_in_the_requested_time_range(pools, professors):
    config = {"count": 3, "allowedDays": None, "timePreference": "evening"}

    result = sessions.generate_profile_courses("A2027", [], pools, professors, config)

    assert all(c["schedule"]["heureDebut"] >= "18:00" for c in result)


def test_several_time_ranges_can_be_combined(pools, professors):
    config = {"count": 4, "allowedDays": None, "timePreference": "morning,evening"}

    result = sessions.generate_profile_courses("A2027", [], pools, professors, config)

    for course in result:
        start = course["schedule"]["heureDebut"]
        assert "08:00" <= start < "13:00" or "18:00" <= start < "22:00"


def test_profile_generation_spreads_courses_across_days(pools, professors):
    config = {"count": 4, "allowedDays": ["1", "2", "3", "4", "5"], "timePreference": None}

    result = sessions.generate_profile_courses("A2027", [], pools, professors, config)

    assert len({c["schedule"]["jour"] for c in result}) == 4


def test_generation_never_asks_for_more_courses_than_the_catalog_holds(pools, professors):
    small = {**pools, "courseCatalog": pools["courseCatalog"][:2]}
    config = {"count": 5, "allowedDays": None, "timePreference": None}

    result = sessions.generate_profile_courses("A2027", [], small, professors, config)

    assert len(result) == 2


def test_an_empty_catalog_generates_nothing(pools, professors):
    empty = {**pools, "courseCatalog": []}
    assert sessions.generate_random_courses("A2027", [], empty, professors) == []


def test_an_unknown_time_preference_falls_back_to_every_slot(pools, professors):
    config = {"count": 2, "allowedDays": None, "timePreference": "midnight"}
    result = sessions.generate_profile_courses("A2027", [], pools, professors, config)
    assert len(result) == 2


def test_reloading_sessions_restores_the_file_contents():
    sessions.get_raw_sessions().clear()
    reloaded = sessions.reload_sessions()
    assert [s["abrege"] for s in reloaded] == [
        "H2024",
        "É2024",
        "A2024",
        "H2025",
        "É2025",
        "A2025",
        "H2026",
    ]
