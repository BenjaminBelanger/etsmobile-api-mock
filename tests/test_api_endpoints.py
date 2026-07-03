"""Tests for the /api/Etudiant/* endpoints (JSON and XML) plus app-level routes."""

import pytest

from conftest import api, first_active_course

XML_HEADERS = {"Accept": "application/xml"}


# --- Simple endpoints ---------------------------------------------------------


def test_hello_world(client):
    res = api(client, "helloWorld")
    assert res.status_code == 200
    assert res.json() == "Hello World"


def test_echo_returns_input(client):
    res = api(client, "echo", chaine="ping")
    assert res.status_code == 200
    assert res.json() == "ping"


def test_echo_missing_param_is_400(client):
    res = api(client, "echo")
    assert res.status_code == 400
    assert "error" in res.json()


def test_info_etudiant(client):
    res = api(client, "infoEtudiant")
    assert res.status_code == 200
    body = res.json()
    assert "erreur" in body
    # student_info.json is a flat object merged into the response
    assert len(body) > 1


# --- List endpoints -----------------------------------------------------------


def test_liste_cours_shape(client, active_session):
    res = api(client, "listeCours")
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body["liste"], list)
    assert body["liste"], "normal profile should generate courses"
    sessions = {c["session"] for c in body["liste"]}
    assert active_session in sessions
    for course in body["liste"]:
        assert "sigle" in course and "groupe" in course and "session" in course


def test_liste_programmes(client):
    res = api(client, "listeProgrammes")
    assert res.status_code == 200
    assert isinstance(res.json()["liste"], list)


def test_liste_sessions_only_registered(client):
    sessions = api(client, "listeSessions").json()["liste"]
    course_sessions = {c["session"] for c in api(client, "listeCours").json()["liste"]}
    listed = {s["abrege"] for s in sessions}
    # listeSessions is filtered down to sessions that actually have courses
    assert listed == course_sessions


def test_liste_cours_intervalle_filters(client, active_session):
    res = api(
        client,
        "listeCoursIntervalleSessions",
        sessionDebut=active_session,
        sessionFin=active_session,
    )
    assert res.status_code == 200
    for course in res.json()["liste"]:
        assert course["session"] == active_session


def test_liste_cours_intervalle_missing_param(client):
    res = api(client, "listeCoursIntervalleSessions", sessionDebut="H2026")
    assert res.status_code == 400


# --- Session-scoped endpoints -------------------------------------------------


@pytest.mark.parametrize(
    "name,list_key",
    [
        ("lireEvaluationCours", "listeEvaluations"),
        ("lireHoraireDesSeances", "ListeDesSeances"),
        ("listeHoraireExamensFin", "listeHoraire"),
        ("lireJoursRemplaces", "listeJours"),
    ],
)
def test_session_list_endpoints(client, active_session, name, list_key):
    res = api(client, name, session=active_session)
    assert res.status_code == 200
    assert isinstance(res.json()[list_key], list)


@pytest.mark.parametrize(
    "name",
    [
        "lireEvaluationCours",
        "lireHoraireDesSeances",
        "listeHoraireExamensFin",
        "lireJoursRemplaces",
        "listeHoraireEtProf",
    ],
)
def test_session_endpoints_require_session(client, name):
    res = api(client, name)
    assert res.status_code == 400


def test_liste_horaire_et_prof(client, active_session):
    res = api(client, "listeHoraireEtProf", session=active_session)
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body["listeActivites"], list)
    assert isinstance(body["listeEnseignants"], list)


def test_lire_horaire_by_prefix(client, active_session):
    course = first_active_course(client, active_session)
    assert course is not None
    sigle, _ = course
    prefix = sigle[:3]
    res = api(client, "lireHoraire", session=active_session, prefixe=prefix)
    assert res.status_code == 200
    for item in res.json()["listeCours"]:
        assert item["sigle"].startswith(prefix)


def test_liste_elements_evaluation(client, active_session):
    course = first_active_course(client, active_session)
    assert course is not None
    sigle, groupe = course
    res = api(
        client,
        "listeElementsEvaluation",
        session=active_session,
        sigle=sigle,
        groupe=groupe,
    )
    assert res.status_code == 200
    body = res.json()
    assert "liste" in body and "erreur" in body


def test_liste_elements_evaluation_missing_param(client, active_session):
    res = api(client, "listeElementsEvaluation", session=active_session, sigle="LOG100")
    assert res.status_code == 400


def test_liste_coequipiers(client, active_session):
    course = first_active_course(client, active_session)
    assert course is not None
    sigle, groupe = course
    res = api(
        client,
        "listeCoequipiers",
        session=active_session,
        sigle=sigle,
        groupe=groupe,
        nomElementEval="Laboratoire",
    )
    assert res.status_code == 200
    assert isinstance(res.json()["liste"], list)


def test_lire_horaire_des_seances_date_filter(client, active_session):
    all_seances = api(client, "lireHoraireDesSeances", session=active_session).json()[
        "ListeDesSeances"
    ]
    if not all_seances:
        pytest.skip("no course activities in the active session")
    cutoff = max(s["dateDebut"] for s in all_seances)[:10]
    res = api(
        client,
        "lireHoraireDesSeances",
        session=active_session,
        dateDebut=cutoff,
    )
    assert res.status_code == 200
    for seance in res.json()["ListeDesSeances"]:
        assert seance["dateDebut"] >= cutoff


# --- XML content negotiation --------------------------------------------------


def test_xml_string_response(client):
    res = client.get("/api/Etudiant/helloWorld", headers=XML_HEADERS)
    assert res.status_code == 200
    assert "xml" in res.headers["content-type"]
    assert res.text.strip().startswith("<")
    assert "Hello World" in res.text


def test_xml_list_response(client):
    res = client.get("/api/Etudiant/listeCours", headers=XML_HEADERS)
    assert res.status_code == 200
    assert "xml" in res.headers["content-type"]
    assert "<ListeCours" in res.text


# --- App-level routes ---------------------------------------------------------


def test_root_redirects_to_editor(client):
    res = client.get("/", follow_redirects=False)
    assert res.status_code in (302, 307)
    assert res.headers["location"] == "/editor"


def test_reload_endpoint(client):
    res = client.post("/reload")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}
