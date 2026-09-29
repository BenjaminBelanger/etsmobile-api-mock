from datetime import date, timedelta

import pytest

from lib import scenarios, sessions
from lib.resource_specs import REPLACED_DAYS

SESSION = "H2026"
MONDAY = "2026-02-02"


@pytest.fixture(autouse=True)
def restore_scenarios():
    yield
    scenarios.reload_scenarios()


@pytest.fixture
def today(monkeypatch):
    def apply(iso):
        frozen = date.fromisoformat(iso)

        class FrozenDate(date):
            @classmethod
            def today(cls):
                return frozen

        monkeypatch.setattr(scenarios, "date", FrozenDate)
        scenarios._scenario_cache.clear()
        return frozen

    return apply


def course(jour="1", **overrides):
    record = {
        "sigle": "LOG430",
        "groupe": "02",
        "session": SESSION,
        "schedule": {
            "jour": jour,
            "journee": "Lundi",
            "heureDebut": "09:00",
            "heureFin": "12:00",
            "codeActivite": "C",
            "nomActivite": "Activité de cours",
        },
        "extraActivities": [],
    }
    record.update(overrides)
    return record


def test_the_seed_scenarios_are_all_valid():
    assert scenarios.get_valid_scenarios() == {
        "none",
        "friday-off",
        "semaine-relache",
        "monday-holiday",
        "long-weekend",
        "fin-de-session",
        "rentree-proche",
        "intra-demain",
        "examen-final-demain",
    }


def test_reloading_replaces_the_scenario_table():
    scenarios._SCENARIOS.clear()
    reloaded = scenarios.reload_scenarios()
    assert set(reloaded) == scenarios.get_valid_scenarios()


def test_an_absolute_rule_resolves_to_its_date(today):
    today("2026-02-02")
    assert scenarios._resolve_date({"rule": "absolute", "date": "2026-03-09"}) == date(
        2026, 3, 9
    )


def test_a_relative_rule_counts_from_today(today):
    today("2026-02-02")
    assert scenarios._resolve_date({"rule": "relative_days", "days": 10}) == date(
        2026, 2, 12
    )


def test_the_next_weekday_rule_can_land_on_today(today):
    today("2026-02-02")
    assert scenarios._resolve_date({"rule": "next_weekday", "weekday": 1}) == date(
        2026, 2, 2
    )


def test_the_next_weekday_rule_looks_forward(today):
    today("2026-02-02")
    assert scenarios._resolve_date({"rule": "next_weekday", "weekday": 5}) == date(
        2026, 2, 6
    )


def test_the_next_weekday_rule_takes_a_week_offset(today):
    today("2026-02-02")
    rule = {"rule": "next_weekday", "weekday": 5, "offset": 1}
    assert scenarios._resolve_date(rule) == date(2026, 2, 13)


def test_the_week_of_rule_resolves_to_a_monday(today):
    today("2026-02-04")
    resolved = scenarios._resolve_date({"rule": "week_of", "weekday": 1})
    assert resolved == date(2026, 2, 9)
    assert resolved.isoweekday() == 1


def test_an_unknown_rule_is_an_error(today):
    today("2026-02-02")
    with pytest.raises(ValueError, match="Unknown date rule"):
        scenarios._resolve_date({"rule": "inconnu"})


def test_a_week_off_skips_monday_to_friday(today):
    today("2026-02-02")
    skipped = scenarios._resolve_skip_dates(
        {"skipDates": [{"rule": "week_of", "weekday": 1}]}
    )
    assert sorted(skipped) == [date(2026, 2, day) for day in range(2, 7)]


def test_a_week_off_looks_ahead_when_the_week_has_started(today):
    today("2026-02-04")
    skipped = scenarios._resolve_skip_dates(
        {"skipDates": [{"rule": "week_of", "weekday": 1}]}
    )
    assert sorted(skipped) == [date(2026, 2, day) for day in range(9, 14)]


def test_replaced_days_resolve_to_a_pair_of_dates(today):
    today("2026-02-02")
    entries = scenarios._resolve_replaced_days(
        {
            "replacedDays": [
                {
                    "origin": {"rule": "next_weekday", "weekday": 1},
                    "replacement": {"rule": "next_weekday", "weekday": 2},
                    "description": "Jour férié",
                }
            ]
        }
    )
    assert entries == [
        {
            "dateOrigine": "2026-02-02",
            "dateRemplacement": "2026-02-03",
            "description": "Jour férié",
        }
    ]


def test_a_scenario_cancels_the_seances_of_a_skipped_day(today):
    today("2026-02-02")
    courses = [course(jour="5")]

    scenarios.seed_occurrence_overrides("friday-off", SESSION, courses)

    assert courses[0]["occurrenceOverrides"] == [
        {"block": 0, "date": "2026-02-06", "canceled": True}
    ]


def test_a_scenario_leaves_other_weekdays_alone(today):
    today("2026-02-02")
    courses = [course(jour="2")]

    scenarios.seed_occurrence_overrides("friday-off", SESSION, courses)

    assert "occurrenceOverrides" not in courses[0]


def test_a_reading_week_cancels_every_weekday_of_that_week(today):
    today("2026-02-02")
    courses = [course(jour="1"), course(jour="3")]

    scenarios.seed_occurrence_overrides("semaine-relache", SESSION, courses)

    assert courses[0]["occurrenceOverrides"] == [
        {"block": 0, "date": "2026-02-02", "canceled": True}
    ]
    assert courses[1]["occurrenceOverrides"] == [
        {"block": 0, "date": "2026-02-04", "canceled": True}
    ]


def test_extra_activities_are_cancelled_too(today):
    today("2026-02-02")
    courses = [
        course(
            jour="1",
            extraActivities=[
                {
                    "jour": "5",
                    "journee": "Vendredi",
                    "heureDebut": "14:00",
                    "heureFin": "17:00",
                    "codeActivite": "L",
                    "nomActivite": "Activité de laboratoire",
                }
            ],
        )
    ]

    scenarios.seed_occurrence_overrides("friday-off", SESSION, courses)

    assert [ov["block"] for ov in courses[0]["occurrenceOverrides"]] == [1]


def test_a_skipped_day_outside_the_session_is_ignored(today):
    today("2026-09-07")
    courses = [course(jour="5")]

    scenarios.seed_occurrence_overrides("friday-off", SESSION, courses)

    assert "occurrenceOverrides" not in courses[0]


def test_a_holiday_moves_its_seances_to_the_replacement_day(today):
    today("2026-02-02")
    courses = [course(jour="1"), course(jour="2", sigle="LOG410")]

    scenarios.seed_occurrence_overrides("monday-holiday", SESSION, courses)

    monday = courses[0]["occurrenceOverrides"]
    tuesday = courses[1]["occurrenceOverrides"]
    assert {
        "block": 0,
        "date": "2026-02-02",
        "targetDate": "2026-02-03",
        "source": "replaced-day",
    } in monday
    assert {
        "block": 0,
        "date": "2026-02-03",
        "canceled": True,
        "source": "replaced-day",
    } in tuesday


def test_a_relocated_seance_is_not_cancelled_on_top_of_the_move(today):
    today("2026-02-02")
    courses = [course(jour="1")]

    scenarios.seed_occurrence_overrides("monday-holiday", SESSION, courses)

    assert courses[0]["occurrenceOverrides"] == [
        {
            "block": 0,
            "date": "2026-02-02",
            "targetDate": "2026-02-03",
            "source": "replaced-day",
        }
    ]


def test_the_none_scenario_changes_nothing(today):
    today("2026-02-02")
    courses = [course(jour="1")]
    assert scenarios.seed_occurrence_overrides("none", SESSION, courses) == courses
    assert "occurrenceOverrides" not in courses[0]


def test_a_course_without_a_schedule_is_left_alone(today):
    today("2026-02-02")
    courses = [course(schedule=None)]

    scenarios.seed_occurrence_overrides("friday-off", SESSION, courses)

    assert "occurrenceOverrides" not in courses[0]


def test_an_override_is_never_added_twice(today):
    today("2026-02-02")
    courses = [course(jour="5")]

    scenarios.seed_occurrence_overrides("friday-off", SESSION, courses)
    scenarios.seed_occurrence_overrides("friday-off", SESSION, courses)

    assert len(courses[0]["occurrenceOverrides"]) == 1


def test_the_seeded_replaced_days_move_their_seances():
    courses = [course(jour="1")]

    scenarios.seed_replaced_day_overrides(courses)

    assert {
        "block": 0,
        "date": "2026-02-23",
        "targetDate": "2026-02-24",
        "source": "replaced-day",
    } in courses[0]["occurrenceOverrides"]


def test_a_replaced_day_of_another_session_is_ignored():
    courses = [course(jour="1", session="H2025")]
    courses[0]["session"] = "H2025"

    scenarios.seed_replaced_day_overrides(courses)

    dates = {ov["date"] for ov in courses[0].get("occurrenceOverrides", [])}
    assert "2026-02-23" not in dates


def test_a_replaced_day_outside_the_course_window_is_ignored():
    window = sessions.course_window(SESSION)
    assert window is not None
    courses = [course(jour="1")]

    scenarios._apply_swaps(
        SESSION,
        courses,
        [(date(2026, 12, 7), date(2026, 12, 8))],
    )

    assert "occurrenceOverrides" not in courses[0]


def test_a_swap_with_no_matching_weekday_adds_nothing():
    courses = [course(jour="3")]

    scenarios._apply_swaps(SESSION, courses, [(date(2026, 2, 2), date(2026, 2, 3))])

    assert "occurrenceOverrides" not in courses[0]


def test_the_scenario_adds_its_replaced_days_to_the_public_fixture(today):
    today("2026-02-02")
    data = {SESSION: []}

    scenarios.apply_scenario("monday-holiday", SESSION, REPLACED_DAYS.filename, data)

    assert data[SESSION] == [
        {
            "dateOrigine": "2026-02-02",
            "dateRemplacement": "2026-02-03",
            "description": "Jour férié",
        }
    ]


def test_a_scenario_without_replaced_days_leaves_the_fixture_alone(today):
    today("2026-02-02")
    data = {SESSION: []}

    scenarios.apply_scenario("friday-off", SESSION, REPLACED_DAYS.filename, data)

    assert data == {SESSION: []}


def test_other_fixtures_are_passed_through_untouched(today):
    today("2026-02-02")
    data = [{"sigle": "LOG430"}]
    assert scenarios.apply_scenario("monday-holiday", SESSION, "courses.json", data) is data


def test_resolved_scenarios_are_cached_per_day(today):
    today("2026-02-02")
    first = scenarios._resolve_and_cache("friday-off")
    second = scenarios._resolve_and_cache("friday-off")
    assert first is second


def test_the_cache_is_dropped_when_scenarios_reload(today):
    today("2026-02-02")
    scenarios._resolve_and_cache("friday-off")
    scenarios.reload_scenarios()
    assert scenarios._scenario_cache == {}


TOMORROW = {"rule": "relative_days", "days": 1}


def evaluations():
    return [
        {"nom": "TP1", "ponderation": 20, "corrigeSur": 20, "isTeam": True},
        {"nom": "Examen intra", "ponderation": 30, "corrigeSur": 50, "isTeam": False},
    ]


def with_scenario(**body):
    scenarios._SCENARIOS["test"] = body
    return "test"


def test_a_final_exam_rule_moves_the_exam_of_the_nth_course(today):
    today("2026-02-02")
    courses = [course(sigle="LOG100"), course(sigle="LOG200")]

    scenarios.seed_evaluation_dates(
        with_scenario(finalExams=[{"course": 2, "date": TOMORROW}]), SESSION, courses
    )

    assert "finalExam" not in courses[0]
    assert courses[1]["finalExam"] == {"dateExamen": "2026-02-03"}


def test_a_final_exam_rule_keeps_the_other_exam_fields(today):
    today("2026-02-02")
    courses = [course(finalExam={"dateExamen": "2026-04-20", "local": "B-1234"})]

    scenarios.seed_evaluation_dates(
        with_scenario(finalExams=[{"course": 1, "date": TOMORROW}]), SESSION, courses
    )

    assert courses[0]["finalExam"] == {"dateExamen": "2026-02-03", "local": "B-1234"}


def test_courses_are_counted_in_the_active_session_only(today):
    today("2026-02-02")
    courses = [course(session="A2025"), course(sigle="LOG200")]

    scenarios.seed_evaluation_dates(
        with_scenario(finalExams=[{"course": 1, "date": TOMORROW}]), SESSION, courses
    )

    assert "finalExam" not in courses[0]
    assert courses[1]["finalExam"]["dateExamen"] == "2026-02-03"


@pytest.mark.parametrize("position", [0, 2])
def test_a_rule_for_a_missing_course_is_ignored(today, position):
    today("2026-02-02")
    courses = [course(evaluations=evaluations())]
    name = with_scenario(
        finalExams=[{"course": position, "date": TOMORROW}],
        evaluations=[{"course": position, "evaluation": "TP1", "date": TOMORROW}],
    )

    scenarios.seed_evaluation_dates(name, SESSION, courses)

    assert courses == [course(evaluations=evaluations())]


def test_a_course_without_a_schedule_gets_no_final_exam(today):
    today("2026-02-02")
    courses = [course(schedule=None)]

    scenarios.seed_evaluation_dates(
        with_scenario(finalExams=[{"course": 1, "date": TOMORROW}]), SESSION, courses
    )

    assert "finalExam" not in courses[0]


def test_an_evaluation_rule_dates_the_named_evaluation(today):
    today("2026-02-02")
    courses = [course(evaluations=evaluations())]
    name = with_scenario(
        evaluations=[
            {
                "course": 1,
                "evaluation": "Examen intra",
                "date": TOMORROW,
                "published": False,
            }
        ]
    )

    scenarios.seed_evaluation_dates(name, SESSION, courses)

    tp1, intra = courses[0]["evaluations"]
    assert tp1 == evaluations()[0]
    assert intra == {**evaluations()[1], "dateCible": "2026-02-03", "publie": False}


def test_an_evaluation_rule_leaves_publication_alone_unless_asked(today):
    today("2026-02-02")
    courses = [course(evaluations=evaluations())]
    name = with_scenario(
        evaluations=[{"course": 1, "evaluation": "TP1", "date": TOMORROW}]
    )

    scenarios.seed_evaluation_dates(name, SESSION, courses)

    assert "publie" not in courses[0]["evaluations"][0]


def test_an_evaluation_rule_does_not_touch_a_shared_template(today):
    today("2026-02-02")
    template = evaluations()
    courses = [
        course(sigle="LOG100", evaluations=template),
        course(sigle="LOG200", evaluations=template),
    ]
    name = with_scenario(
        evaluations=[{"course": 1, "evaluation": "TP1", "date": TOMORROW}]
    )

    scenarios.seed_evaluation_dates(name, SESSION, courses)

    assert template == evaluations()
    assert courses[1]["evaluations"] is template
    assert courses[0]["evaluations"][0]["dateCible"] == "2026-02-03"


def test_an_unknown_evaluation_name_changes_nothing(today):
    today("2026-02-02")
    courses = [course(evaluations=evaluations())]
    name = with_scenario(
        evaluations=[{"course": 1, "evaluation": "Quiz", "date": TOMORROW}]
    )

    scenarios.seed_evaluation_dates(name, SESSION, courses)

    assert courses[0]["evaluations"] == evaluations()


def served_first_course(reconfigure, scenario):
    from lib import data_store
    from lib.resource_specs import COURSE_ACTIVITIES, EVALUATIONS, FINAL_EXAMS

    reconfigure(SCENARIO=scenario)
    session = data_store.ACTIVE_SESSION
    first = data_store.get_session_courses(session)[0]
    key = f"{first['sigle']}-{first['groupe']}"
    exam = next(
        e
        for e in data_store.load_session(FINAL_EXAMS.filename, session)
        if e["sigle"] == first["sigle"]
    )
    finals = [
        a
        for a in data_store.load_session(COURSE_ACTIVITIES.filename, session)
        if a["coursGroupe"] == key and a["nomActivite"] == "Final"
    ]
    sheet = data_store.load_session(EVALUATIONS.filename, session, {})[key]["liste"]
    return exam, finals, sheet


def test_the_final_exam_scenario_serves_an_exam_tomorrow(reconfigure):
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    exam, finals, sheet = served_first_course(reconfigure, "examen-final-demain")

    assert exam["dateExamen"] == tomorrow
    assert [a["dateDebut"][:10] for a in finals] == [tomorrow]
    assert sheet[-1]["dateCible"] == tomorrow


def test_the_midterm_scenario_serves_an_ungraded_midterm_tomorrow(reconfigure):
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    _, _, sheet = served_first_course(reconfigure, "intra-demain")

    intra = next(item for item in sheet if item["nom"] == "Examen intra")
    assert intra["dateCible"] == tomorrow
    assert intra["publie"] == "Non"
    assert intra["note"] == ""
