import pytest

from conftest import xml_root
from lib import data_store
from lib.resource_specs import (
    COURSE_ACTIVITIES,
    COURSE_SCHEDULE,
    COURSES,
    EVALUATIONS,
    FINAL_EXAMS,
    TEAMMATES,
)

API = "/api/Etudiant"
XML = {"Accept": "application/xml"}
MISSING = "Un des paramètres obligatoires est absent de la requête."


def json_of(client, path, **params):
    response = client.get(f"{API}/{path}", params=params)
    assert response.status_code == 200
    return response.json()


def xml_of(client, path, **params):
    response = client.get(f"{API}/{path}", params=params, headers=XML)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/xml; charset=utf-8"
    return xml_root(response)


def test_hello_world_answers_in_both_formats(client):
    assert json_of(client, "helloWorld") == "Hello World"

    response = client.get(f"{API}/helloWorld", headers=XML)
    assert response.text == "<string>Hello World</string>"


def test_echo_returns_the_string_it_was_given(client):
    assert json_of(client, "echo", chaine="bonjour") == "bonjour"
    assert xml_of(client, "echo", chaine="bonjour").text == "bonjour"


def test_student_info_is_served_flat_with_an_error_field(client):
    body = json_of(client, "infoEtudiant")
    assert body["codePerm"] == "ABCD12345678"
    assert body["erreur"] == ""

    root = xml_of(client, "infoEtudiant")
    assert root.tag == "Etudiant"
    assert root.find("codePerm").text == "ABCD12345678"
    assert root.find("masculin").text == "true"


def test_course_list_matches_the_computed_fixture(client):
    body = json_of(client, "listeCours")
    assert body["liste"] == data_store.load(COURSES.filename)
    assert body["erreur"] == ""

    root = xml_of(client, "listeCours")
    assert root.tag == "ListeCours"
    assert len(root.find("liste")) == len(body["liste"])


def test_a_course_entry_keeps_its_public_shape(client):
    entry = json_of(client, "listeCours")["liste"][0]
    assert set(entry) == {
        "sigle",
        "groupe",
        "session",
        "cote",
        "nbCredits",
        "titreCours",
        "programmeEtudes",
    }


def test_courses_can_be_filtered_to_a_session_range(client):
    body = json_of(
        client, "listeCoursIntervalleSessions", sessionDebut="H2024", sessionFin="H2024"
    )
    assert {c["session"] for c in body["liste"]} == {"H2024"}


def test_a_session_range_that_spans_nothing_is_empty(client):
    body = json_of(
        client, "listeCoursIntervalleSessions", sessionDebut="H2030", sessionFin="H2031"
    )
    assert body["liste"] == []


def test_programs_are_served(client):
    codes = [p["code"] for p in json_of(client, "listeProgrammes")["liste"]]
    assert "7084" in codes


def test_only_sessions_that_have_courses_are_listed(client):
    listed = {s["abrege"] for s in json_of(client, "listeSessions")["liste"]}
    registered = {c["session"] for c in data_store.load(COURSES.filename)}
    assert listed == registered


def test_course_reviews_are_served_per_session(client, session):
    body = json_of(client, "lireEvaluationCours", session=session)
    assert body["listeEvaluations"]
    assert {e["Sigle"] for e in body["listeEvaluations"]} == {
        c["sigle"] for c in data_store.get_session_courses(session) if c["schedule"]
    }


def test_an_unknown_session_yields_an_empty_review_list(client):
    assert json_of(client, "lireEvaluationCours", session="H2099") == {
        "listeEvaluations": [],
        "erreur": "",
    }


def test_seances_can_be_filtered_by_course_group(client, session):
    body = json_of(
        client, "lireHoraireDesSeances", session=session, coursGroupe="LOG430-02"
    )
    assert body["ListeDesSeances"]
    assert {s["coursGroupe"] for s in body["ListeDesSeances"]} == {"LOG430-02"}


def test_seances_can_be_filtered_by_date_window(client, session):
    body = json_of(
        client,
        "lireHoraireDesSeances",
        session=session,
        dateDebut="2026-02-01",
        dateFin="2026-02-28",
    )
    dates = [s["dateDebut"][:10] for s in body["ListeDesSeances"]]
    assert dates
    assert all("2026-02-01" <= d <= "2026-02-28" for d in dates)


def test_the_date_window_includes_activities_ending_late_on_the_last_day(
    client, session
):
    items = data_store.load_session(COURSE_ACTIVITIES.filename, session)
    last = max(item["dateFin"] for item in items)
    body = json_of(
        client, "lireHoraireDesSeances", session=session, dateFin=last[:10]
    )
    assert any(s["dateFin"] == last for s in body["ListeDesSeances"])


def test_seances_are_served_sorted_by_start(client, session):
    body = json_of(client, "lireHoraireDesSeances", session=session)
    starts = [s["dateDebut"] for s in body["ListeDesSeances"]]
    assert starts == sorted(starts)


def test_schedule_and_professors_come_back_together(client, session):
    body = json_of(client, "listeHoraireEtProf", session=session)
    assert body["listeActivites"]
    assert body["listeEnseignants"]
    assert set(body["listeEnseignants"][0]) == {
        "localBureau",
        "telephone",
        "enseignantPrincipal",
        "nom",
        "prenom",
        "courriel",
    }

    root = xml_of(client, "listeHoraireEtProf", session=session)
    assert root.tag == "ListeActivitesEtProfs"
    assert [e.tag for e in root.find("listeActivites")][:1] == ["HoraireActivite"]
    assert [e.tag for e in root.find("listeEnseignants")][:1] == ["Enseignant"]


def test_teachers_are_deduplicated_in_the_schedule_response(client, session):
    body = json_of(client, "listeHoraireEtProf", session=session)
    keys = [(t["nom"], t["prenom"], t["courriel"]) for t in body["listeEnseignants"]]
    assert len(keys) == len(set(keys))


def test_an_unknown_session_yields_empty_schedule_lists(client):
    assert json_of(client, "listeHoraireEtProf", session="H2099") == {
        "listeActivites": [],
        "listeEnseignants": [],
        "erreur": "",
    }


def test_evaluation_elements_are_served_for_a_course(client, session):
    body = json_of(
        client, "listeElementsEvaluation", session=session, sigle="LOG430", groupe="02"
    )
    stored = data_store.load_session(EVALUATIONS.filename, session, {})["LOG430-02"]
    assert body["liste"] == stored["liste"]
    assert body["noteACeJour"] == stored["noteACeJour"]


def test_an_unknown_course_yields_the_empty_evaluation_summary(client, session):
    body = json_of(
        client, "listeElementsEvaluation", session=session, sigle="XXX999", groupe="99"
    )
    assert body["liste"] == []
    assert body["tauxPublication"] == "0,0"
    assert body["noteACeJour"] == ""


def test_evaluation_elements_are_served_as_xml(client, session):
    root = xml_of(
        client, "listeElementsEvaluation", session=session, sigle="LOG430", groupe="02"
    )
    assert root.tag == "ListeElementsEvaluation"
    assert root.find("liste/ElementEvaluation/nom") is not None


def test_the_schedule_is_filtered_by_course_prefix(client, session):
    body = json_of(client, "lireHoraire", session=session, prefixe="LOG")
    assert body["listeCours"]
    assert all(c["sigle"].startswith("LOG") for c in body["listeCours"])
    assert body["listeCours"][0]["listeProf"]


def test_a_prefix_that_matches_nothing_is_empty(client, session):
    assert json_of(client, "lireHoraire", session=session, prefixe="ZZZ") == {
        "listeCours": [],
        "erreur": "",
    }


def test_final_exams_are_served_per_session(client, session):
    body = json_of(client, "listeHoraireExamensFin", session=session)
    assert body["listeHoraire"] == data_store.load_session(
        FINAL_EXAMS.filename, session
    )
    assert set(body["listeHoraire"][0]) == {
        "sigle",
        "groupe",
        "dateExamen",
        "heureDebut",
        "heureFin",
        "local",
    }


def test_replaced_days_are_served_per_session(client, session):
    body = json_of(client, "lireJoursRemplaces", session=session)
    assert body["listeJours"] == [
        {
            "dateOrigine": "2026-02-23",
            "dateRemplacement": "2026-02-24",
            "description": "Journée pédagogique",
        }
    ]


def test_teammates_are_served_per_evaluation(client, session):
    stored = data_store.load_session(TEAMMATES.filename, session, {})
    course_group, evaluations = next(iter(stored.items()))
    name, members = next(iter(evaluations.items()))
    sigle, groupe = course_group.split("-")

    body = json_of(
        client,
        "listeCoequipiers",
        session=session,
        sigle=sigle,
        groupe=groupe,
        nomElementEval=name,
    )
    assert body["liste"] == members
    assert set(body["liste"][0]) == {"nom", "prenom", "courriel"}


def test_teammates_of_an_unknown_evaluation_are_empty(client, session):
    body = json_of(
        client,
        "listeCoequipiers",
        session=session,
        sigle="LOG430",
        groupe="02",
        nomElementEval="Inexistant",
    )
    assert body["liste"] == []


@pytest.mark.parametrize(
    "path,params",
    [
        ("echo", {}),
        ("listeCoursIntervalleSessions", {"sessionDebut": "H2024"}),
        ("listeCoursIntervalleSessions", {"sessionFin": "H2024"}),
        ("lireEvaluationCours", {}),
        ("lireHoraireDesSeances", {}),
        ("listeHoraireEtProf", {}),
        ("listeElementsEvaluation", {"sigle": "LOG430", "groupe": "02"}),
        ("listeElementsEvaluation", {"session": "H2026", "groupe": "02"}),
        ("listeElementsEvaluation", {"session": "H2026", "sigle": "LOG430"}),
        ("lireHoraire", {"session": "H2026"}),
        ("lireHoraire", {"prefixe": "LOG"}),
        ("listeHoraireExamensFin", {}),
        ("lireJoursRemplaces", {}),
        ("listeCoequipiers", {"session": "H2026", "sigle": "LOG430", "groupe": "02"}),
    ],
)
def test_a_missing_parameter_is_a_400(client, path, params):
    response = client.get(f"{API}/{path}", params=params)
    assert response.status_code == 400
    assert response.json() == {"error": MISSING}


def test_an_empty_parameter_counts_as_missing(client):
    response = client.get(f"{API}/echo", params={"chaine": ""})
    assert response.status_code == 400


@pytest.mark.parametrize(
    "path,params,root_tag,list_tag",
    [
        ("listeCours", {}, "ListeCours", "liste"),
        ("listeProgrammes", {}, "ListeProgrammes", "liste"),
        ("listeSessions", {}, "ListeSessions", "liste"),
        ("lireEvaluationCours", {"session": "H2026"}, "ListeEvaluationsCours", "listeEvaluations"),
        ("lireHoraireDesSeances", {"session": "H2026"}, "ListeSeances", "ListeDesSeances"),
        ("lireHoraire", {"session": "H2026", "prefixe": "LOG"}, "ListeCoursHoraire", "listeCours"),
        ("listeHoraireExamensFin", {"session": "H2026"}, "ListeHoraireExamensFinaux", "listeHoraire"),
        ("lireJoursRemplaces", {"session": "H2026"}, "ListeJoursRemplaces", "listeJours"),
    ],
)
def test_list_endpoints_keep_their_xml_envelope(client, path, params, root_tag, list_tag):
    root = xml_of(client, path, **params)
    assert root.tag == root_tag
    assert root.find(list_tag) is not None
    assert root.find("erreur") is not None


def test_text_xml_is_accepted_too(client):
    response = client.get(f"{API}/listeCours", headers={"Accept": "text/xml"})
    assert response.text.startswith('<?xml version="1.0" encoding="utf-8"?>')


def test_json_is_the_default_format(client):
    response = client.get(f"{API}/listeCours")
    assert response.headers["content-type"].startswith("application/json")


def test_the_xml_and_json_bodies_carry_the_same_courses(client, session):
    body = json_of(client, "lireHoraire", session=session, prefixe="LOG")
    root = xml_of(client, "lireHoraire", session=session, prefixe="LOG")
    assert [c.find("sigle").text for c in root.find("listeCours")] == [
        c["sigle"] for c in body["listeCours"]
    ]


def test_the_schedule_endpoint_serves_the_computed_fixture(client, session):
    served = json_of(client, "lireHoraire", session=session, prefixe="LOG")["listeCours"]
    assert served == [
        item
        for item in data_store.load_session(COURSE_SCHEDULE.filename, session)
        if item["sigle"].startswith("LOG")
    ]


def test_an_empty_prefix_counts_as_missing(client, session):
    response = client.get(f"{API}/lireHoraire", params={"session": session, "prefixe": ""})
    assert response.status_code == 400
