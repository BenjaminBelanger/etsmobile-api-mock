import pytest
from fastapi.testclient import TestClient

import start
from lib import compute, data_store, profiles, schedule_editor
from lib.resource_specs import COURSE_SCHEDULE, EVALUATIONS
from main import app

PROFILE = "edge-cases"
SIGLES = ("LOG795", "ATE100", "MAT350", "GTI619", "GIA400", "ENT301", "ELE144")

SESSION_META = {
    "abrege": "H2026",
    "dateDebut": "2026-01-05",
    "dateFinCours": "2026-04-17",
    "dateFin": "2026-04-30",
}


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def edge_cases(monkeypatch):
    """Reload the store on the edge-cases profile and return the active session."""
    monkeypatch.setenv("PROFILE", PROFILE)
    schedule_editor.clear_cache()
    data_store.reload()
    return data_store.ACTIVE_SESSION


def seeded_courses(session):
    return {c["sigle"]: c for c in data_store.get_session_courses(session)}


def evaluation(client, session, sigle):
    response = client.get(
        "/api/Etudiant/listeElementsEvaluation",
        params={"session": session, "sigle": sigle, "groupe": "01"},
    )
    assert response.status_code == 200
    return response.json()


def endpoints(session):
    return [
        ("/api/Etudiant/listeCours", {}),
        (
            "/api/Etudiant/listeCoursIntervalleSessions",
            {"sessionDebut": session, "sessionFin": session},
        ),
        ("/api/Etudiant/listeProgrammes", {}),
        ("/api/Etudiant/listeSessions", {}),
        ("/api/Etudiant/lireEvaluationCours", {"session": session}),
        ("/api/Etudiant/lireHoraireDesSeances", {"session": session}),
        ("/api/Etudiant/listeHoraireEtProf", {"session": session}),
        ("/api/Etudiant/lireHoraire", {"session": session, "prefixe": "LOG"}),
        ("/api/Etudiant/listeHoraireExamensFin", {"session": session}),
        ("/api/Etudiant/lireJoursRemplaces", {"session": session}),
        (
            "/api/Etudiant/listeCoequipiers",
            {
                "session": session,
                "sigle": "MAT350",
                "groupe": "01",
                "nomElementEval": "Examen intra",
            },
        ),
        ("/editor/api/state", {"session": session}),
    ]


def test_the_profile_is_selectable_and_described():
    assert PROFILE in profiles.get_valid_profiles()
    assert start.PROFILE_DESCRIPTIONS[PROFILE]


def test_every_profile_is_described_in_the_cli():
    missing = profiles.get_valid_profiles() - set(start.PROFILE_DESCRIPTIONS)
    assert not missing, f"undescribed profiles: {sorted(missing)}"


def test_the_profile_replaces_the_generated_courses(edge_cases):
    assert set(seeded_courses(edge_cases)) == set(SIGLES)


def test_each_course_carries_its_own_pathology(edge_cases):
    courses = seeded_courses(edge_cases)

    title = courses["LOG795"]["titreCours"]
    assert 110 <= len(title) <= 130
    assert "-" in title and "é" in title

    assert courses["ATE100"]["nbCredits"] == 0

    graded = courses["MAT350"]["evaluations"]
    assert sum(ev["ponderation"] for ev in graded) > 100
    assert any(ev["note"] > ev["corrigeSur"] for ev in graded)

    assert courses["GTI619"]["evaluations"] == []

    assert courses["GIA400"]["professorId"] == ""

    assert courses["ENT301"]["schedule"] is None
    assert courses["ENT301"]["room"] == ""
    assert courses["ENT301"]["examRoom"] == ""

    assert [ev["corrigeSur"] for ev in courses["ELE144"]["evaluations"]].count(0) == 1


def test_every_endpoint_serves_the_profile(edge_cases, client):
    for path, params in endpoints(edge_cases):
        response = client.get(path, params=params)
        assert response.status_code == 200, f"{path} answered {response.status_code}"


@pytest.mark.parametrize("sigle", SIGLES)
def test_the_evaluation_endpoint_serves_every_course(edge_cases, client, sigle):
    assert evaluation(client, edge_cases, sigle)["erreur"] == ""


def test_the_bonus_marks_push_the_grade_past_100(edge_cases, client):
    summary = evaluation(client, edge_cases, "MAT350")
    assert compute._parse_french(summary["noteACeJour"]) > 100
    assert compute._parse_french(summary["scoreFinalSur100"]) > 100


def test_a_course_without_evaluations_serves_a_blank_summary(edge_cases, client):
    summary = evaluation(client, edge_cases, "GTI619")
    assert summary["liste"] == []
    assert summary["noteACeJour"] == ""
    assert summary["tauxPublication"] == "0,0"


def test_the_ungraded_item_is_served_and_scores_nothing(edge_cases, client):
    summary = evaluation(client, edge_cases, "ELE144")
    ungraded = next(item for item in summary["liste"] if item["corrigeSur"] == "0")
    assert ungraded["nom"] == "Présence aux laboratoires"
    assert compute._parse_french(summary["noteACeJour"]) > 0


def test_the_course_without_a_professor_is_served_with_empty_teacher_fields(
    edge_cases, client
):
    response = client.get(
        "/api/Etudiant/lireHoraire", params={"session": edge_cases, "prefixe": "GIA"}
    )
    assert response.status_code == 200
    entry = response.json()["listeCours"][0]
    assert entry["sigle"] == "GIA400"
    assert entry["listeProf"] == [
        {
            "localBureau": "",
            "telephone": "",
            "enseignantPrincipal": "Oui",
            "nom": "",
            "prenom": "",
            "courriel": "",
        }
    ]


def seed_course(**overrides):
    course = {
        "sigle": "LOG100",
        "groupe": "01",
        "session": SESSION_META["abrege"],
        "titreCours": "Cours de test",
        "nbCredits": 3,
        "programmeEtudes": "7084",
        "cote": "",
        "professorId": "last1-first1",
        "room": "A-1302",
        "examRoom": "A-1518",
        "schedule": {
            "jour": "2",
            "journee": "Mardi",
            "heureDebut": "09:00",
            "heureFin": "12:30",
            "codeActivite": "C",
            "nomActivite": "Activité de cours",
        },
        "extraActivities": [],
        "evaluations": [
            {"nom": "Examen final", "ponderation": 100, "corrigeSur": 100, "isTeam": False}
        ],
        "teammates": {},
        "gradePublishRatio": 1.0,
        "gradeSeed": 1,
    }
    course.update(overrides)
    return course


def build(course):
    return compute.build_all_course_data(
        [SESSION_META], [course], data_store.get_professors(), {}
    )


def test_a_course_without_a_professor_id_still_builds():
    course = seed_course()
    del course["professorId"]

    schedule = build(course)[COURSE_SCHEDULE.filename][SESSION_META["abrege"]]

    assert schedule[0]["listeProf"] == [
        {
            "localBureau": "",
            "telephone": "",
            "enseignantPrincipal": "Oui",
            "nom": "",
            "prenom": "",
            "courriel": "",
        }
    ]


def test_an_evaluation_marked_out_of_zero_scores_nothing():
    course = seed_course(
        evaluations=[
            {
                "nom": "Présence aux laboratoires",
                "ponderation": 0,
                "corrigeSur": 0,
                "isTeam": False,
            },
            {
                "nom": "Examen final",
                "ponderation": 100,
                "corrigeSur": 100,
                "isTeam": False,
                "note": 80,
                "moyenne": 70,
                "mediane": 71,
                "ecartType": 5,
                "rangCentile": 90,
                "publie": True,
            },
        ]
    )

    session = build(course)[EVALUATIONS.filename][SESSION_META["abrege"]]
    summary = session["LOG100-01"]

    assert summary["liste"][0]["corrigeSur"] == "0"
    assert summary["noteACeJour"] == "80,0"
    assert summary["scoreFinalSur100"] == "80,0"
    assert summary["moyenneClasse"] == "70,0"
