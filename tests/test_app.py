import json

from lib import data_store, schedule_editor
from lib.resource_specs import COURSES

BLOCK = "LOG430-02:0"


def test_the_root_redirects_to_the_editor(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/editor"


def test_the_editor_page_is_served(client):
    response = client.get("/editor")
    assert response.status_code == 200
    assert "<title>Horaire - ÉTS Mock</title>" in response.text
    assert '<div class="app" id="app">' in response.text


def test_the_editor_page_pulls_its_own_assets(client):
    page = client.get("/editor").text
    for asset in (
        "/editor/assets/vendor/fluent-theme.css",
        "/editor/assets/styles.css",
        "/editor/assets/app.js",
    ):
        assert asset in page
        assert client.get(asset).status_code == 200


def test_an_unknown_endpoint_is_a_404(client):
    assert client.get("/api/Etudiant/nexistePas").status_code == 404


def test_a_wrong_method_is_a_405(client):
    assert client.post("/api/Etudiant/listeCours").status_code == 405


def test_the_openapi_document_lists_every_public_endpoint(client):
    paths = client.get("/openapi.json").json()["paths"]
    for name in (
        "helloWorld",
        "echo",
        "infoEtudiant",
        "listeCours",
        "listeCoursIntervalleSessions",
        "listeProgrammes",
        "listeSessions",
        "lireEvaluationCours",
        "lireHoraireDesSeances",
        "listeHoraireEtProf",
        "listeElementsEvaluation",
        "lireHoraire",
        "listeHoraireExamensFin",
        "lireJoursRemplaces",
        "listeCoequipiers",
    ):
        assert f"/api/Etudiant/{name}" in paths


def test_the_docs_page_is_served(client):
    assert client.get("/docs").status_code == 200


def test_reload_rebuilds_the_fixtures_from_seed(client, session, tmp_path):
    before = len(data_store.load(COURSES.filename))
    extra = {
        "sigle": "TST100",
        "groupe": "01",
        "session": session,
        "titreCours": "Cours de test",
        "nbCredits": 3,
        "programmeEtudes": "7084",
        "cote": "",
        "professorId": "last1-first1",
        "room": "A-1302",
        "examRoom": "A-1518",
        "schedule": {
            "jour": "5",
            "journee": "Vendredi",
            "heureDebut": "09:00",
            "heureFin": "12:00",
            "codeActivite": "C",
            "nomActivite": "Activité de cours",
        },
        "extraActivities": [],
        "evaluations": [],
        "teammates": {},
        "gradePublishRatio": 0.6,
        "gradeSeed": 1234,
    }
    courses = data_store.get_session_courses(session) + [extra]
    data_store.overrides_path().write_text(
        json.dumps({session: {"courses": courses, "trash": []}}), encoding="utf-8"
    )

    assert client.post("/reload").json() == {"status": "ok"}

    sigles = {c["sigle"] for c in data_store.load(COURSES.filename)}
    assert "TST100" in sigles
    assert len(data_store.load(COURSES.filename)) == before + 1


def test_reload_drops_the_editor_document_cache(client, session):
    schedule_editor.get_state(session)
    assert session in schedule_editor._docs

    client.post("/reload")

    assert schedule_editor._docs == {}


def test_an_editor_error_is_reported_as_a_400_with_a_message(client, session):
    response = client.post(
        "/editor/api/block/move",
        json={"session": session, "blockId": BLOCK, "jour": "1", "heureDebut": "09:00"},
    )
    assert response.status_code == 400
    assert "already on Lundi" in response.json()["error"]


def test_a_malformed_editor_body_is_rejected(client, session):
    response = client.post("/editor/api/block/move", json={"session": session})
    assert response.status_code == 422
