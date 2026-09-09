from datetime import date

import pytest

from lib import compute
from lib.resource_specs import (
    COURSE_ACTIVITIES,
    COURSE_REVIEWS,
    COURSE_SCHEDULE,
    COURSES,
    EVALUATIONS,
    FINAL_EXAMS,
    SCHEDULE_ACTIVITIES,
    TEAMMATES,
)

SESSION = {
    "abrege": "H2030",
    "auLong": "Hiver 2030",
    "dateDebut": "2030-01-07",
    "dateFinCours": "2030-04-12",
    "dateFin": "2030-04-26",
}

PROFESSORS = {
    "prof1": {
        "nom": "Last1",
        "prenom": "First1",
        "courriel": "first1.last1@etsmtl.ca",
        "localBureau": "A-4525",
        "telephone": "",
    }
}

POOLS = {
    "teammatePool": [
        {
            "id": "mate1",
            "nom": "Last10",
            "prenom": "First10",
            "courriel": "first10@ens.etsmtl.ca",
        }
    ]
}


def make_course(**overrides):
    course = {
        "sigle": "LOG999",
        "groupe": "01",
        "session": "H2030",
        "titreCours": "Cours de test",
        "nbCredits": 3,
        "programmeEtudes": "7084",
        "cote": "",
        "professorId": "prof1",
        "room": "A-1302",
        "examRoom": "A-1518",
        "schedule": {
            "jour": "1",
            "journee": "Lundi",
            "heureDebut": "09:00",
            "heureFin": "12:00",
            "codeActivite": "C",
            "nomActivite": "Activité de cours",
        },
        "extraActivities": [],
        "evaluations": [
            {"nom": "TP1", "ponderation": 40, "corrigeSur": 20, "isTeam": True},
            {"nom": "Examen final", "ponderation": 60, "corrigeSur": 100, "isTeam": False},
        ],
        "teammates": {},
        "gradePublishRatio": 1.0,
        "gradeSeed": 4242,
    }
    course.update(overrides)
    return course


def build(courses, sessions=None, pools=None):
    return compute.build_all_course_data(
        sessions or [SESSION], courses, PROFESSORS, pools or POOLS
    )


def test_weekly_dates_start_on_the_first_matching_weekday():
    dates = compute.weekly_dates(date(2030, 1, 7), date(2030, 2, 1), 3)
    assert dates[0] == date(2030, 1, 9)
    assert all((d - dates[0]).days % 7 == 0 for d in dates)


def test_weekly_dates_stop_at_the_end_of_the_window():
    dates = compute.weekly_dates(date(2030, 1, 7), date(2030, 1, 21), 1)
    assert dates == [date(2030, 1, 7), date(2030, 1, 14), date(2030, 1, 21)]


def test_weekly_dates_are_empty_when_the_window_holds_no_such_day():
    assert compute.weekly_dates(date(2030, 1, 8), date(2030, 1, 10), 1) == []


def test_an_override_can_target_an_explicit_date():
    target = compute.override_target_date(
        date(2030, 1, 7), {"targetDate": "2030-01-09"}
    )
    assert target == date(2030, 1, 9)


def test_an_override_can_target_a_weekday_of_the_same_week():
    assert compute.override_target_date(date(2030, 1, 7), {"jour": "4"}) == date(
        2030, 1, 10
    )


def test_an_override_without_a_target_stays_put():
    assert compute.override_target_date(date(2030, 1, 7), {}) == date(2030, 1, 7)


def test_an_override_is_found_by_block_and_date():
    overrides = [
        {"block": 0, "date": "2030-01-07", "canceled": True},
        {"block": 1, "date": "2030-01-07"},
    ]
    assert compute.find_override(overrides, 1, date(2030, 1, 7)) is overrides[1]
    assert compute.find_override(overrides, 0, "2030-01-07") is overrides[0]
    assert compute.find_override(overrides, 2, "2030-01-07") is None
    assert compute.find_override(overrides, 0, "2030-01-14") is None


def test_occurrences_are_produced_for_every_block():
    course = make_course(
        extraActivities=[
            {
                "jour": "3",
                "journee": "Mercredi",
                "heureDebut": "14:00",
                "heureFin": "17:00",
                "codeActivite": "L",
                "nomActivite": "Activité de laboratoire",
            }
        ]
    )
    blocks = [course["schedule"]] + course["extraActivities"]

    occurrences = list(
        compute.block_occurrences(
            course, blocks, date(2030, 1, 7), date(2030, 1, 20)
        )
    )

    assert [(o.block, o.date.isoformat()) for o in occurrences] == [
        (0, "2030-01-07"),
        (0, "2030-01-14"),
        (1, "2030-01-09"),
        (1, "2030-01-16"),
    ]


def test_a_block_without_a_schedule_yields_nothing():
    course = make_course()
    assert (
        list(
            compute.block_occurrences(
                course, [None], date(2030, 1, 7), date(2030, 1, 20)
            )
        )
        == []
    )


def test_an_override_moves_and_retimes_a_single_occurrence():
    course = make_course(
        occurrenceOverrides=[
            {
                "block": 0,
                "date": "2030-01-14",
                "targetDate": "2030-01-16",
                "heureDebut": "13:30",
                "heureFin": "16:30",
            }
        ]
    )

    occurrences = list(
        compute.block_occurrences(
            course, [course["schedule"]], date(2030, 1, 7), date(2030, 1, 20)
        )
    )

    assert occurrences[0].date == occurrences[0].origin
    assert occurrences[1].origin == date(2030, 1, 14)
    assert occurrences[1].date == date(2030, 1, 16)
    assert (occurrences[1].heureDebut, occurrences[1].heureFin) == ("13:30", "16:30")
    assert occurrences[1].canceled is False


def test_a_cancelled_occurrence_is_flagged():
    course = make_course(
        occurrenceOverrides=[{"block": 0, "date": "2030-01-14", "canceled": True}]
    )

    occurrences = list(
        compute.block_occurrences(
            course, [course["schedule"]], date(2030, 1, 7), date(2030, 1, 20)
        )
    )

    assert [o.canceled for o in occurrences] == [False, True]


def test_the_build_produces_every_fixture():
    built = build([make_course()])
    assert set(built) == {
        COURSES.filename,
        EVALUATIONS.filename,
        COURSE_ACTIVITIES.filename,
        COURSE_SCHEDULE.filename,
        SCHEDULE_ACTIVITIES.filename,
        FINAL_EXAMS.filename,
        COURSE_REVIEWS.filename,
        TEAMMATES.filename,
    }


def test_a_course_in_an_unknown_session_is_skipped():
    built = build([make_course(session="H2099")])
    assert built[COURSES.filename] == []


def test_the_course_entry_only_carries_public_fields():
    entry = build([make_course(cote="A+")])[COURSES.filename][0]
    assert entry == {
        "sigle": "LOG999",
        "groupe": "01",
        "session": "H2030",
        "cote": "A+",
        "nbCredits": 3,
        "titreCours": "Cours de test",
        "programmeEtudes": "7084",
    }


def test_a_course_without_a_schedule_only_gets_grades():
    built = build([make_course(schedule=None)])

    assert built[EVALUATIONS.filename]["H2030"]["LOG999-01"]["liste"]
    assert built[COURSE_ACTIVITIES.filename] == {}
    assert built[FINAL_EXAMS.filename] == {}
    assert built[COURSE_SCHEDULE.filename] == {}
    assert built[COURSE_REVIEWS.filename] == {}


def test_activities_cover_every_class_plus_the_exam():
    built = build([make_course()])
    activities = built[COURSE_ACTIVITIES.filename]["H2030"]

    mondays = compute.weekly_dates(date(2030, 1, 7), date(2030, 4, 12), 1)
    classes = [a for a in activities if a["nomActivite"] == "Cours"]
    exams = [a for a in activities if a["nomActivite"] == "Final"]

    assert len(classes) == len(mondays)
    assert len(exams) == 1
    assert exams[0]["descriptionActivite"] == "Examen final"


def test_activities_are_sorted_by_start():
    built = build([make_course(), make_course(sigle="LOG888", gradeSeed=7)])
    starts = [a["dateDebut"] for a in built[COURSE_ACTIVITIES.filename]["H2030"]]
    assert starts == sorted(starts)


def test_a_cancelled_class_is_not_served_as_an_activity():
    course = make_course(
        occurrenceOverrides=[{"block": 0, "date": "2030-01-14", "canceled": True}]
    )
    dates = {
        a["dateDebut"][:10]
        for a in build([course])[COURSE_ACTIVITIES.filename]["H2030"]
    }
    assert "2030-01-07" in dates
    assert "2030-01-14" not in dates


def test_a_lab_activity_is_labelled_as_a_lab():
    course = make_course(
        extraActivities=[
            {
                "jour": "3",
                "journee": "Mercredi",
                "heureDebut": "14:00",
                "heureFin": "17:00",
                "codeActivite": "L",
                "nomActivite": "Activité de laboratoire",
                "room": "B-2222",
            }
        ]
    )
    labs = [
        a
        for a in build([course])[COURSE_ACTIVITIES.filename]["H2030"]
        if a["nomActivite"] == "Labo"
    ]
    assert labs
    assert {lab["local"] for lab in labs} == {"B-2222"}


def test_the_final_exam_lands_on_a_weekday_after_the_last_class():
    exam = build([make_course()])[FINAL_EXAMS.filename]["H2030"][0]
    day = date.fromisoformat(exam["dateExamen"])

    assert date(2030, 4, 13) <= day <= date(2030, 4, 26)
    assert day.isoweekday() <= 5
    assert exam["local"] == "A-1518"


def test_an_evening_course_gets_an_evening_exam():
    course = make_course(
        schedule={
            "jour": "1",
            "journee": "Lundi",
            "heureDebut": "18:00",
            "heureFin": "21:00",
            "codeActivite": "C",
            "nomActivite": "Activité de cours",
        }
    )
    exam = build([course])[FINAL_EXAMS.filename]["H2030"][0]
    assert (exam["heureDebut"], exam["heureFin"]) == ("18:00", "21:00")


def test_an_exam_override_wins_over_the_generated_one():
    course = make_course(
        finalExam={
            "dateExamen": "2030-04-20",
            "heureDebut": "08:00",
            "heureFin": "11:00",
            "local": "Z-9999",
        }
    )
    exam = build([course])[FINAL_EXAMS.filename]["H2030"][0]
    assert exam == {
        "sigle": "LOG999",
        "groupe": "01",
        "dateExamen": "2030-04-20",
        "heureDebut": "08:00",
        "heureFin": "11:00",
        "local": "Z-9999",
    }


def test_a_partial_exam_override_keeps_the_generated_rest():
    course = make_course(finalExam={"local": "Z-9999"})
    exam = build([course])[FINAL_EXAMS.filename]["H2030"][0]
    generated = build([make_course()])[FINAL_EXAMS.filename]["H2030"][0]

    assert exam["local"] == "Z-9999"
    assert exam["dateExamen"] == generated["dateExamen"]


def test_evaluations_are_numbered_and_dated_in_order():
    sheet = build([make_course()])[EVALUATIONS.filename]["H2030"]["LOG999-01"]
    items = sheet["liste"]

    assert [item["ordre"] for item in items] == ["1", "2"]
    assert [item["nom"] for item in items] == ["TP1", "Examen final"]
    assert items[0]["dateCible"] < items[1]["dateCible"]


def test_target_dates_never_land_on_a_weekend():
    course = make_course(
        evaluations=[
            {"nom": f"TP{i}", "ponderation": 20, "corrigeSur": 20, "isTeam": False}
            for i in range(5)
        ]
    )
    sheet = build([course])[EVALUATIONS.filename]["H2030"]["LOG999-01"]
    for item in sheet["liste"][:-1]:
        assert date.fromisoformat(item["dateCible"]).isoweekday() <= 5


def test_the_last_evaluation_falls_on_the_exam_date():
    built = build([make_course()])
    sheet = built[EVALUATIONS.filename]["H2030"]["LOG999-01"]
    exam = built[FINAL_EXAMS.filename]["H2030"][0]
    assert sheet["liste"][-1]["dateCible"] == exam["dateExamen"]


def test_a_team_evaluation_names_the_team():
    items = build([make_course()])[EVALUATIONS.filename]["H2030"]["LOG999-01"]["liste"]
    assert items[0]["equipe"].startswith("Équipe ")
    assert items[1]["equipe"] == ""


def test_the_publish_ratio_decides_what_is_published():
    course = make_course(
        gradePublishRatio=0.5,
        evaluations=[
            {"nom": f"TP{i}", "ponderation": 25, "corrigeSur": 20, "isTeam": False}
            for i in range(4)
        ],
    )
    items = build([course])[EVALUATIONS.filename]["H2030"]["LOG999-01"]["liste"]
    assert [item["publie"] for item in items] == ["Oui", "Oui", "Non", "Non"]


def test_at_least_one_evaluation_is_always_published():
    course = make_course(gradePublishRatio=0.0)
    items = build([course])[EVALUATIONS.filename]["H2030"]["LOG999-01"]["liste"]
    assert items[0]["publie"] == "Oui"


def test_an_unpublished_evaluation_carries_no_grade():
    course = make_course(gradePublishRatio=0.5)
    items = build([course])[EVALUATIONS.filename]["H2030"]["LOG999-01"]["liste"]
    assert items[1]["publie"] == "Non"
    assert items[1]["note"] == ""
    assert items[1]["moyenne"] == ""


def test_grades_are_formatted_the_french_way():
    items = build([make_course()])[EVALUATIONS.filename]["H2030"]["LOG999-01"]["liste"]
    assert "," in items[0]["note"]
    assert "." not in items[0]["note"]


def test_a_pinned_grade_is_served_as_is():
    course = make_course()
    course["evaluations"][0].update({"note": 18.5, "publie": True})

    items = build([course])[EVALUATIONS.filename]["H2030"]["LOG999-01"]["liste"]

    assert items[0]["note"] == "18,5"


def test_a_pinned_publication_flag_is_honoured():
    course = make_course(gradePublishRatio=1.0)
    course["evaluations"][1]["publie"] = False

    items = build([course])[EVALUATIONS.filename]["H2030"]["LOG999-01"]["liste"]

    assert [item["publie"] for item in items] == ["Oui", "Non"]


def test_a_pinned_target_date_is_honoured():
    course = make_course()
    course["evaluations"][1]["dateCible"] = "2030-03-01"

    items = build([course])[EVALUATIONS.filename]["H2030"]["LOG999-01"]["liste"]

    assert items[1]["dateCible"] == "2030-03-01"


def test_a_frozen_grade_survives_a_rebuild():
    course = make_course()
    course["evaluations"][0]["generated"] = {"note": 12.5, "rangCentile": 80}

    items = build([course])[EVALUATIONS.filename]["H2030"]["LOG999-01"]["liste"]

    assert items[0]["note"] == "12,5"
    assert items[0]["rangCentile"] == "80"


def test_a_pinned_value_beats_a_frozen_one():
    course = make_course()
    course["evaluations"][0]["generated"] = {"note": 12.5}
    course["evaluations"][0]["note"] = 19.0

    items = build([course])[EVALUATIONS.filename]["H2030"]["LOG999-01"]["liste"]

    assert items[0]["note"] == "19,0"


def test_the_summary_is_the_weighted_average_of_published_grades():
    course = make_course(gradePublishRatio=1.0)
    course["evaluations"][0].update({"note": 10.0, "moyenne": 10.0, "mediane": 10.0})
    course["evaluations"][1].update({"note": 50.0, "moyenne": 50.0, "mediane": 50.0})

    sheet = build([course])[EVALUATIONS.filename]["H2030"]["LOG999-01"]

    assert sheet["noteACeJour"] == "50,0"
    assert sheet["scoreFinalSur100"] == "50,0"
    assert sheet["moyenneClasse"] == "50,0"
    assert sheet["medianeClasse"] == "50,0"
    assert sheet["tauxPublication"] == "100,0"


def test_the_summary_is_empty_when_nothing_is_published():
    course = make_course(gradePublishRatio=1.0)
    for evaluation in course["evaluations"]:
        evaluation["publie"] = False

    sheet = build([course])[EVALUATIONS.filename]["H2030"]["LOG999-01"]

    assert sheet["noteACeJour"] == ""
    assert sheet["tauxPublication"] == "0,0"
    assert sheet["liste"]


def test_individual_scores_ignore_team_work():
    course = make_course(gradePublishRatio=1.0)
    course["evaluations"][0].update({"note": 20.0, "moyenne": 20.0, "mediane": 20.0})
    course["evaluations"][1].update({"note": 50.0, "moyenne": 50.0, "mediane": 50.0})

    sheet = build([course])[EVALUATIONS.filename]["H2030"]["LOG999-01"]

    assert sheet["noteACeJourElementsIndividuels"] == "50,0"
    assert sheet["noteSur100PourElementsIndividuels"] == "30,0"


def test_grades_are_stable_for_a_given_seed():
    first = build([make_course()])[EVALUATIONS.filename]
    second = build([make_course()])[EVALUATIONS.filename]
    assert first == second


def test_a_different_seed_gives_different_grades():
    first = build([make_course()])[EVALUATIONS.filename]["H2030"]["LOG999-01"]
    second = build([make_course(gradeSeed=99)])[EVALUATIONS.filename]["H2030"][
        "LOG999-01"
    ]
    assert first["liste"][0]["note"] != second["liste"][0]["note"]


def test_a_zero_weighting_does_not_divide_by_zero():
    course = make_course(
        evaluations=[{"nom": "TP1", "ponderation": 0, "corrigeSur": 20, "isTeam": False}]
    )
    sheet = build([course])[EVALUATIONS.filename]["H2030"]["LOG999-01"]
    assert sheet["noteACeJour"] == ""


def test_the_schedule_entry_carries_the_professor():
    entry = build([make_course()])[COURSE_SCHEDULE.filename]["H2030"][0]

    assert entry["sigle"] == "LOG999"
    assert entry["activitePrincipale"] == "Oui"
    assert entry["listeProf"] == [
        {
            "localBureau": "A-4525",
            "telephone": "",
            "enseignantPrincipal": "Oui",
            "nom": "Last1",
            "prenom": "First1",
            "courriel": "first1.last1@etsmtl.ca",
        }
    ]


def test_extra_activities_are_secondary_in_the_activity_list():
    course = make_course(
        extraActivities=[
            {
                "jour": "3",
                "journee": "Mercredi",
                "heureDebut": "14:00",
                "heureFin": "17:00",
                "codeActivite": "L",
                "nomActivite": "Activité de laboratoire",
            }
        ]
    )
    activities = build([course])[SCHEDULE_ACTIVITIES.filename]["H2030"]["listeActivites"]

    assert [a["activitePrincipale"] for a in activities] == ["Oui", "Non"]
    assert [a["codeActivite"] for a in activities] == ["C", "L"]


def test_the_teacher_list_is_deduplicated_across_courses():
    built = build([make_course(), make_course(sigle="LOG888")])
    session_data = built[SCHEDULE_ACTIVITIES.filename]["H2030"]

    assert len(session_data["listeEnseignants"]) == 1
    assert set(session_data["enseignantsParCours"]) == {"LOG999-01", "LOG888-01"}


def test_an_unknown_professor_leaves_empty_fields():
    entry = build([make_course(professorId="inconnu")])[COURSE_SCHEDULE.filename][
        "H2030"
    ][0]
    assert entry["listeProf"][0]["nom"] == ""


def test_the_course_review_window_sits_before_the_end_of_classes():
    review = build([make_course()])[COURSE_REVIEWS.filename]["H2030"][0]

    assert review["Sigle"] == "LOG999"
    assert review["Enseignant"] == "First1 Last1"
    assert review["TypeEvaluation"] == "Cours"
    assert review["EstComplete"] is True
    assert review["DateDebutEvaluation"] < review["DateFinEvaluation"]
    assert review["DateFinEvaluation"][:10] < SESSION["dateFinCours"]


def test_teammates_are_resolved_from_the_pool():
    course = make_course(teammates={"TP1": ["mate1"]})
    built = build([course])

    assert built[TEAMMATES.filename]["H2030"]["LOG999-01"]["TP1"] == [
        {"nom": "Last10", "prenom": "First10", "courriel": "first10@ens.etsmtl.ca"}
    ]


def test_unknown_teammates_are_dropped():
    course = make_course(teammates={"TP1": ["inconnu"], "TP2": ["mate1"]})
    teammates = build([course])[TEAMMATES.filename]["H2030"]["LOG999-01"]

    assert "TP1" not in teammates
    assert "TP2" in teammates


def test_a_course_without_teammates_is_absent_from_the_fixture():
    assert build([make_course()])[TEAMMATES.filename] == {}


@pytest.mark.parametrize("ratio", [0.25, 0.5, 1.0])
def test_the_summary_publication_rate_matches_the_published_weighting(ratio):
    course = make_course(
        gradePublishRatio=ratio,
        evaluations=[
            {"nom": f"TP{i}", "ponderation": 25, "corrigeSur": 20, "isTeam": False}
            for i in range(4)
        ],
    )
    sheet = build([course])[EVALUATIONS.filename]["H2030"]["LOG999-01"]
    published = [item for item in sheet["liste"] if item["publie"] == "Oui"]
    assert sheet["tauxPublication"] == f"{float(25 * len(published)):.1f}".replace(
        ".", ","
    )
