import json
import shutil
import urllib.error

import pytest

import manage_seed
from lib import i18n
from lib._paths import SEED as REAL_SEED

REAL_NOTIFY = manage_seed._notify_server

SESSION = "H2026"
SCHEDULE = {
    "jour": "2",
    "journee": "Mardi",
    "heureDebut": "09:00",
    "heureFin": "12:30",
    "codeActivite": "C",
    "nomActivite": "Activité de cours",
}


@pytest.fixture(autouse=True)
def seed_copy(tmp_path, monkeypatch):
    sandbox = tmp_path / "seed"
    sandbox.mkdir()
    for name in ("courses.json", "pools.json", "professors.json", "sessions.json"):
        shutil.copy(REAL_SEED / name, sandbox / name)
    monkeypatch.setattr(manage_seed, "SEED", sandbox)
    return sandbox


@pytest.fixture(autouse=True)
def notifications(monkeypatch):
    calls = []
    monkeypatch.setattr(manage_seed, "_notify_server", lambda: calls.append("notify"))
    return calls


@pytest.fixture
def answers(monkeypatch):
    def apply(*responses):
        queue = list(responses)
        monkeypatch.setattr("builtins.input", lambda *_: queue.pop(0))
        return queue

    return apply


def stored(seed_copy):
    return json.loads((seed_copy / "courses.json").read_text(encoding="utf-8"))


def test_a_course_is_appended_to_the_seed_file(seed_copy, notifications):
    before = len(stored(seed_copy))

    record = manage_seed.add_course_to_seed(SESSION, "LOG999", "Mon cours", SCHEDULE)

    assert len(stored(seed_copy)) == before + 1
    assert stored(seed_copy)[-1] == record
    assert notifications == ["notify"]


def test_an_added_course_is_filled_in_from_the_pools(seed_copy):
    pools = json.loads((seed_copy / "pools.json").read_text(encoding="utf-8"))
    professors = json.loads((seed_copy / "professors.json").read_text(encoding="utf-8"))

    record = manage_seed.add_course_to_seed(SESSION, "LOG999", "Mon cours", SCHEDULE)

    assert record["room"] in pools["rooms"]
    assert record["examRoom"] in pools["examRooms"]
    assert record["evaluations"] in pools["evalTemplates"]
    assert record["professorId"] in professors
    assert 1000 <= record["gradeSeed"] <= 9999


def test_an_added_course_carries_the_expected_shape(seed_copy):
    record = manage_seed.add_course_to_seed(SESSION, "LOG999", "Mon cours", SCHEDULE)

    assert set(record) == {
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
    assert record["schedule"] == SCHEDULE
    assert record["cote"] == ""


def test_explicit_values_win_over_the_random_ones(seed_copy):
    record = manage_seed.add_course_to_seed(
        SESSION,
        "LOG999",
        "Mon cours",
        SCHEDULE,
        professor_id="last1-first1",
        room="Z-1000",
        exam_room="Z-2000",
        evaluations=[{"nom": "TP", "ponderation": 100, "corrigeSur": 20, "isTeam": False}],
        teammates={"TP": ["last10-first10"]},
        nb_credits=4,
        programme="0725",
        grade_publish_ratio=0.25,
        grade_seed=1234,
        extra_activities=[{"jour": "4"}],
    )

    assert record["professorId"] == "last1-first1"
    assert record["room"] == "Z-1000"
    assert record["examRoom"] == "Z-2000"
    assert record["nbCredits"] == 4
    assert record["programmeEtudes"] == "0725"
    assert record["gradePublishRatio"] == 0.25
    assert record["gradeSeed"] == 1234
    assert record["extraActivities"] == [{"jour": "4"}]
    assert record["teammates"] == {"TP": ["last10-first10"]}


def test_groups_are_numbered_per_session(seed_copy):
    first = manage_seed.add_course_to_seed(SESSION, "LOG999", "Un", SCHEDULE)
    second = manage_seed.add_course_to_seed(SESSION, "LOG999", "Deux", SCHEDULE)
    other = manage_seed.add_course_to_seed("H2025", "LOG999", "Trois", SCHEDULE)

    assert (first["groupe"], second["groupe"], other["groupe"]) == ("01", "02", "01")


def test_the_next_group_follows_the_highest_one():
    courses = [
        {"sigle": "LOG999", "groupe": "01", "session": SESSION},
        {"sigle": "LOG999", "groupe": "03", "session": SESSION},
        {"sigle": "LOG999", "groupe": "09", "session": "H2025"},
    ]
    assert manage_seed._next_group(courses, "LOG999", SESSION) == "04"
    assert manage_seed._next_group(courses, "LOG888", SESSION) == "01"


def test_a_course_can_be_removed(seed_copy, notifications):
    manage_seed.add_course_to_seed(SESSION, "LOG999", "Mon cours", SCHEDULE)
    notifications.clear()

    assert manage_seed.remove_course_from_seed(SESSION, "LOG999", "01") is True

    assert all(c["sigle"] != "LOG999" for c in stored(seed_copy))
    assert notifications == ["notify"]


def test_removing_something_that_is_not_there_changes_nothing(seed_copy, notifications):
    before = stored(seed_copy)

    assert manage_seed.remove_course_from_seed(SESSION, "LOG999", "01") is False

    assert stored(seed_copy) == before
    assert notifications == []


def test_removal_only_touches_the_named_session(seed_copy):
    manage_seed.add_course_to_seed(SESSION, "LOG999", "Un", SCHEDULE)
    manage_seed.add_course_to_seed("H2025", "LOG999", "Deux", SCHEDULE)

    manage_seed.remove_course_from_seed(SESSION, "LOG999", "01")

    remaining = [c for c in stored(seed_copy) if c["sigle"] == "LOG999"]
    assert [c["session"] for c in remaining] == ["H2025"]


def test_courses_can_be_listed_for_a_session(seed_copy):
    every = manage_seed.list_seed_courses()
    session_only = manage_seed.list_seed_courses(SESSION)

    assert len(session_only) < len(every)
    assert {c["session"] for c in session_only} == {SESSION}


def test_the_seed_file_stays_readable_json(seed_copy):
    manage_seed.add_course_to_seed(SESSION, "LOG999", "Accentué é", SCHEDULE)
    text = (seed_copy / "courses.json").read_text(encoding="utf-8")

    assert "Accentué é" in text
    assert text.endswith("\n")
    assert json.loads(text)


def test_a_session_can_be_picked_from_the_menu(answers):
    answers("1")
    assert manage_seed._select_session()["abrege"] == "H2024"


def test_the_session_menu_can_be_cancelled(answers):
    answers("0")
    assert manage_seed._select_session() is None


@pytest.mark.parametrize("raw", ["abc", "99"])
def test_an_invalid_session_choice_gives_up(answers, raw):
    answers(raw)
    assert manage_seed._select_session() is None


def test_the_interactive_add_walks_through_the_prompts(seed_copy, answers):
    answers("log999", "Mon cours", "1", "1")

    message = manage_seed._interactive_add(SESSION)

    added = [c for c in stored(seed_copy) if c["sigle"] == "LOG999"]
    assert added
    assert added[0]["schedule"]["jour"] == "1"
    assert "LOG999-01" in message


@pytest.mark.parametrize("responses", [("",), ("LOG999", "")])
def test_the_interactive_add_can_be_cancelled(seed_copy, answers, responses):
    answers(*responses)
    before = stored(seed_copy)

    assert manage_seed._interactive_add(SESSION) == "Annulé."
    assert stored(seed_copy) == before


@pytest.mark.parametrize(
    "responses", [("LOG999", "Titre", "abc"), ("LOG999", "Titre", "99")]
)
def test_the_interactive_add_refuses_an_invalid_day(seed_copy, answers, responses):
    answers(*responses)
    assert "Choix invalide" in manage_seed._interactive_add(SESSION)


def test_the_interactive_add_refuses_an_invalid_slot(seed_copy, answers):
    answers("LOG999", "Titre", "1", "99")
    assert "Choix invalide" in manage_seed._interactive_add(SESSION)


def test_the_interactive_remove_deletes_the_chosen_course(seed_copy, answers):
    courses = manage_seed.list_seed_courses(SESSION)
    answers("1")

    message = manage_seed._interactive_remove(SESSION)

    assert courses[0]["sigle"] in message
    assert len(manage_seed.list_seed_courses(SESSION)) == len(courses) - 1


def test_the_interactive_remove_can_be_cancelled(seed_copy, answers):
    before = stored(seed_copy)
    answers("0")

    assert manage_seed._interactive_remove(SESSION) == ""
    assert stored(seed_copy) == before


@pytest.mark.parametrize("raw,expected", [("abc", "Annulé."), ("99", "Choix invalide.")])
def test_the_interactive_remove_rejects_bad_input(seed_copy, answers, raw, expected):
    answers(raw)
    assert manage_seed._interactive_remove(SESSION) == expected


def test_removing_from_an_empty_session_says_so(seed_copy, answers):
    assert manage_seed._interactive_remove("H2099") == "Aucun cours dans cette session."


def test_the_interactive_list_names_every_course(seed_copy):
    listing = manage_seed._interactive_list(SESSION)
    for course in manage_seed.list_seed_courses(SESSION):
        assert f"{course['sigle']}-{course['groupe']}" in listing


def test_listing_an_empty_session_says_so(seed_copy):
    assert manage_seed._interactive_list("H2099") == "Aucun cours dans cette session."


def test_a_running_server_is_notified(monkeypatch):
    monkeypatch.setattr(manage_seed, "_notify_server", REAL_NOTIFY)
    requests = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout=None):
        requests.append((request.full_url, request.get_method()))
        return Response()

    monkeypatch.setattr(manage_seed.urllib.request, "urlopen", fake_urlopen)

    manage_seed._notify_server()

    assert requests == [("http://localhost:8080/reload", "POST")]


def test_an_unreachable_server_is_only_a_warning(monkeypatch, capsys):
    monkeypatch.setattr(manage_seed, "_notify_server", REAL_NOTIFY)

    def fake_urlopen(request, timeout=None):
        raise urllib.error.URLError("boom")

    monkeypatch.setattr(manage_seed.urllib.request, "urlopen", fake_urlopen)

    manage_seed._notify_server()

    assert i18n.t("cli.seed.server_offline") in capsys.readouterr().out
