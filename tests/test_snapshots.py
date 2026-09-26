import json
from datetime import date

import pytest

from lib import (
    data_store,
    failures,
    schedule_editor,
    sessions,
    snapshot_editor,
    snapshots,
    student_editor,
)
from lib.snapshots import SnapshotConflict, SnapshotError

COURSE = "LOG430-02"
BLOCK = "LOG430-02:0"
PAST = "H2026"


@pytest.fixture
def today(monkeypatch):
    def freeze(iso):
        frozen = date.fromisoformat(iso)

        class FrozenDate(date):
            @classmethod
            def today(cls):
                return frozen

        monkeypatch.setattr(sessions, "date", FrozenDate)
        monkeypatch.setattr(snapshots, "date", FrozenDate)

    return freeze


def course(code="A2026", **extra):
    return {
        "sigle": "LOG100",
        "groupe": "01",
        "session": code,
        "titreCours": "Programmation",
        "nbCredits": 3,
        "programmeEtudes": "7084",
        "cote": "",
        "professorId": "last1-first1",
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
            {"nom": "Intra", "ponderation": 40, "corrigeSur": 100, "isTeam": False}
        ],
        "teammates": {},
        "gradePublishRatio": 0.5,
        "gradeSeed": 1234,
        **extra,
    }


def edited_course(code="A2026"):
    record = course(code)
    record["occurrenceOverrides"] = [
        {"block": 0, "date": "2026-09-28", "canceled": True},
        {
            "block": 0,
            "date": "2026-10-05",
            "jour": "2",
            "journee": "Mardi",
            "targetDate": "2026-10-06",
            "heureDebut": "13:00",
            "heureFin": "16:00",
            "canceled": False,
        },
    ]
    record["evaluations"][0]["dateCible"] = "2026-10-14"
    record["evaluations"][0]["generated"] = {"dateCible": "2026-10-15", "note": 80.0}
    record["finalExam"] = {"dateExamen": "2026-12-10"}
    return record


def snapshot(**changes):
    body = {
        "format": snapshots.FORMAT,
        "name": "Mi-session",
        "savedAt": "2026-09-25T10:00",
        "anchor": {"session": "A2026", "week": 4, "date": "2026-09-25"},
        "setup": {"profile": "normal", "scenario": "none", "semesterWeek": None},
        "failures": {"latencyMs": "100-800", "errorRate": 0.3},
        "sessions": {
            "A2026": {
                "calendar": {
                    "dateDebut": "2026-09-01",
                    "dateFinCours": "2026-12-07",
                    "dateFin": "2026-12-18",
                },
                "courses": [edited_course()],
                "trash": [],
                "dates": {"dateFin": "2026-12-22"},
            }
        },
        "student": {"prenom": "Marie"},
    }
    body.update(changes)
    return body


def stored_courses(schedule, code):
    return schedule[code]["courses"]


def test_a_name_becomes_a_file_friendly_id():
    assert snapshots.slugify("  Été: examen final! ") == "ete-examen-final"


@pytest.mark.parametrize("name", ["", "   ", "!!!", "x" * 81])
def test_an_unusable_name_is_refused(name):
    with pytest.raises(SnapshotError):
        snapshots.clean_name(name)


def test_a_snapshot_is_written_listed_and_read_back(sandbox_snapshots):
    snapshot_id = snapshots.write("shared", snapshot(name="Examen final"))

    assert snapshot_id == "examen-final"
    assert (sandbox_snapshots / "shared" / "examen-final.json").exists()
    listed = snapshots.list_all()
    assert [(item["scope"], item["id"], item["name"]) for item in listed] == [
        ("shared", "examen-final", "Examen final")
    ]
    assert listed[0]["sessions"] == ["A2026"]
    assert listed[0]["student"] == ["prenom"]
    assert snapshots.read("shared", "examen-final")["student"] == {"prenom": "Marie"}


def test_personal_snapshots_are_listed_before_shared_ones():
    snapshots.write("shared", snapshot(name="B"))
    snapshots.write("personal", snapshot(name="C"))
    snapshots.write("personal", snapshot(name="A"))

    assert [(i["scope"], i["name"]) for i in snapshots.list_all()] == [
        ("personal", "A"),
        ("personal", "C"),
        ("shared", "B"),
    ]


def test_an_existing_name_is_not_replaced_unless_asked():
    snapshots.write("personal", snapshot(name="Démo"))

    with pytest.raises(SnapshotConflict):
        snapshots.write("personal", snapshot(name="demo", student={}))

    snapshots.write("personal", snapshot(name="demo", student={}), overwrite=True)
    assert snapshots.read("personal", "demo")["student"] == {}


def test_a_snapshot_moves_between_personal_and_shared(sandbox_snapshots):
    snapshots.write("personal", snapshot(name="Démo"))

    assert snapshots.move("personal", "demo", "shared") == "demo"

    assert not (sandbox_snapshots / "personal" / "demo.json").exists()
    assert snapshots.read("shared", "demo")["name"] == "Démo"


def test_a_snapshot_can_be_deleted():
    snapshots.write("personal", snapshot())
    snapshots.delete("personal", "mi-session")

    assert snapshots.list_all() == []
    with pytest.raises(SnapshotError):
        snapshots.delete("personal", "mi-session")


@pytest.mark.parametrize(
    "scope, snapshot_id", [("elsewhere", "demo"), ("shared", "../escape"), ("shared", "")]
)
def test_paths_stay_inside_the_snapshot_folders(scope, snapshot_id):
    with pytest.raises(SnapshotError):
        snapshots.read(scope, snapshot_id)


def test_unreadable_files_are_left_out_of_the_list(sandbox_snapshots):
    snapshots.write("shared", snapshot())
    (sandbox_snapshots / "shared" / "broken.json").write_text("{", encoding="utf-8")
    (sandbox_snapshots / "shared" / "other.json").write_text("[]", encoding="utf-8")

    assert [item["id"] for item in snapshots.list_all()] == ["mi-session"]


@pytest.mark.parametrize(
    "broken",
    [
        [],
        {**snapshot(), "format": 99},
        {**snapshot(), "name": ""},
        {**snapshot(), "anchor": {"session": "A2026"}},
        {**snapshot(), "setup": {}},
        {**snapshot(), "setup": {"profile": "normal", "semesterWeek": 0}},
        {**snapshot(), "sessions": {"A2026": []}},
        {**snapshot(), "student": []},
    ],
)
def test_malformed_snapshots_are_rejected(broken):
    with pytest.raises(SnapshotError):
        snapshots.validate(broken)


def test_a_snapshot_is_found_by_name_or_id():
    snapshots.write("shared", snapshot(name="Examen final"))

    assert snapshots.find("Examen final") == [("shared", "examen-final")]
    assert snapshots.find("examen-final") == [("shared", "examen-final")]
    assert snapshots.find("shared/examen-final") == [("shared", "examen-final")]
    assert snapshots.find("personal/examen-final") == []


def test_a_name_used_in_both_scopes_is_ambiguous():
    snapshots.write("shared", snapshot(name="Démo"))
    snapshots.write("personal", snapshot(name="Démo"))

    assert snapshots.find("demo") == [("personal", "demo"), ("shared", "demo")]


def test_the_setup_round_trips_through_the_environment():
    env = {
        "PROFILE": "generated-busy",
        "SCENARIO": "friday-off",
        "SEMESTER_WEEK": "3",
        "COURSE_COUNT": "2",
        "SCHEDULE_DAYS": "1,3",
        "TIME_PREFERENCE": "",
    }

    setup = snapshots.setup_from_env(env)

    assert setup == {
        "profile": "generated-busy",
        "scenario": "friday-off",
        "semesterWeek": 3,
        "courses": 2,
        "days": ["1", "3"],
        "time": "",
    }
    assert snapshots.setup_to_env(setup) == env


def test_a_default_setup_only_sets_the_profile():
    setup = snapshots.setup_from_env({})

    assert setup == {"profile": "normal", "scenario": "none", "semesterWeek": None}
    assert snapshots.setup_to_env(setup) == {"PROFILE": "normal"}


def test_the_same_week_mode_shifts_every_date_by_whole_weeks(today):
    today("2026-10-09")

    plan = snapshots.plan(snapshot(), "week")

    assert plan.setup["semesterWeek"] == 4
    assert plan.notices == []
    saved = stored_courses(plan.schedule, "A2026")[0]
    assert saved["session"] == "A2026"
    assert saved["occurrenceOverrides"][0]["date"] == "2026-10-12"
    assert saved["occurrenceOverrides"][1]["date"] == "2026-10-19"
    assert saved["occurrenceOverrides"][1]["targetDate"] == "2026-10-20"
    assert saved["evaluations"][0]["dateCible"] == "2026-10-28"
    assert saved["evaluations"][0]["generated"]["dateCible"] == "2026-10-29"
    assert saved["finalExam"]["dateExamen"] == "2026-12-24"
    assert plan.schedule["A2026"]["dates"] == {"dateFin": "2027-01-05"}


def test_the_session_is_placed_so_today_falls_in_the_saved_week(today):
    today("2026-10-09")
    plan = snapshots.plan(snapshot(), "week")

    start = sessions.session_metadata("A2026")["dateDebut"]
    assert sessions.week_index(date.fromisoformat(start), date(2026, 10, 9)) == 4
    assert plan.setup["semesterWeek"] == 4


def test_loading_on_the_saved_day_changes_nothing(today):
    today("2026-09-25")

    plan = snapshots.plan(snapshot(), "week")

    assert plan.setup["semesterWeek"] is None
    assert plan.schedule["A2026"]["courses"] == [edited_course()]
    assert plan.schedule["A2026"]["dates"] == {"dateFin": "2026-12-22"}


def test_the_active_session_is_remapped_to_the_current_one(today):
    today("2027-02-10")

    plan = snapshots.plan(snapshot(), "week")

    assert set(plan.schedule) == {"H2027"}
    saved = stored_courses(plan.schedule, "H2027")[0]
    assert saved["session"] == "H2027"
    start = date.fromisoformat(sessions.session_metadata("H2027")["dateDebut"])
    origin = date.fromisoformat(saved["occurrenceOverrides"][0]["date"])
    assert origin.isoweekday() == 1
    assert sessions.week_index(start, origin) == 5
    assert sessions.week_index(start, date(2027, 2, 10)) == 4


def test_the_next_session_follows_the_active_one(today):
    today("2027-02-10")
    upcoming = course("H2027")
    body = snapshot()
    body["sessions"]["H2027"] = {
        "calendar": {"dateDebut": "2027-01-04", "dateFin": "2027-04-23"},
        "courses": [upcoming],
        "trash": [],
    }

    plan = snapshots.plan(body, "week")

    assert set(plan.schedule) == {"H2027", "É2027"}
    assert stored_courses(plan.schedule, "É2027")[0]["session"] == "É2027"
    assert stored_courses(plan.schedule, "H2027")[0]["sigle"] == "LOG100"


def test_other_sessions_keep_their_code_and_dates(today):
    today("2027-02-10")
    body = snapshot()
    past = edited_course(PAST)
    body["sessions"][PAST] = {"calendar": {}, "courses": [past], "trash": []}

    plan = snapshots.plan(body, "week")

    assert stored_courses(plan.schedule, PAST) == [past]


def test_a_week_past_the_end_of_a_shorter_session_is_clamped(today):
    today("2026-10-09")
    body = snapshot(anchor={"session": "H2026", "week": 17, "date": "2026-04-30"})

    plan = snapshots.plan(body, "week")

    assert plan.setup["semesterWeek"] == 16
    assert plan.notices == [
        "A2026 n'a que 16 semaines: la semaine 16 est utilisée au lieu de la semaine 17."
    ]


def test_a_snapshot_saved_before_its_session_started_lands_on_week_one(today):
    today("2026-10-09")

    plan = snapshots.plan(snapshot(anchor={**snapshot()["anchor"], "week": 0}), "week")

    assert plan.setup["semesterWeek"] == 1
    assert "semaine 1" in plan.notices[0]


def test_seance_edits_past_the_end_of_a_shorter_session_are_dropped(today):
    today("2026-10-09")
    winter = course("H2026")
    winter["occurrenceOverrides"] = [
        {"block": 0, "date": "2026-01-12", "canceled": True},
        {"block": 0, "date": "2026-04-20", "canceled": True},
    ]
    body = snapshot(
        anchor={"session": "H2026", "week": 3, "date": "2026-01-23"},
        sessions={
            "H2026": {"calendar": {"dateDebut": "2026-01-05"}, "courses": [winter], "trash": []}
        },
    )

    plan = snapshots.plan(body, "week")

    kept = stored_courses(plan.schedule, "A2026")[0]["occurrenceOverrides"]
    assert kept == [{"block": 0, "date": "2026-09-28", "canceled": True}]
    assert plan.notices == ["1 modification(s) de séance hors de la session A2026 ignorée(s)."]


def test_exact_dates_keep_every_date_and_pin_the_session_calendar(today):
    today("2026-10-09")

    plan = snapshots.plan(snapshot(), "exact")

    assert plan.setup["semesterWeek"] is None
    assert plan.schedule["A2026"]["courses"] == [edited_course()]
    assert plan.schedule["A2026"]["dates"] == {"dateFin": "2026-12-22"}


def test_exact_dates_pin_a_calendar_that_moved_since_the_save(today):
    today("2026-10-09")
    body = snapshot(setup={"profile": "normal", "scenario": "none", "semesterWeek": 4})
    body["sessions"]["A2026"]["calendar"] = {
        "dateDebut": "2026-09-01",
        "dateFinCours": "2026-12-07",
        "dateFin": "2026-12-18",
    }

    plan = snapshots.plan(body, "exact")

    assert plan.setup["semesterWeek"] == 4
    assert plan.schedule["A2026"]["dates"] == {
        "dateDebut": "2026-09-01",
        "dateFinCours": "2026-12-07",
        "dateFin": "2026-12-22",
    }


def test_setup_only_drops_the_schedule_but_keeps_the_rest(today):
    today("2027-02-10")
    body = snapshot(setup={"profile": "generated-busy", "scenario": "friday-off", "semesterWeek": 2})

    plan = snapshots.plan(body, "setup")

    assert plan.schedule == {}
    assert plan.setup == body["setup"]
    assert plan.student == {"prenom": "Marie"}
    assert plan.failures == {"latencyMs": "100-800", "errorRate": 0.3}


def test_failures_can_be_left_out_of_a_plan():
    assert snapshots.plan(snapshot(), "setup", failures=False).failures is None


def test_an_unknown_date_mode_is_refused():
    with pytest.raises(SnapshotError):
        snapshots.plan(snapshot(), "tomorrow")


def api(client, path, **body):
    response = client.post(f"/editor/api/snapshots{path}", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def move_block():
    return schedule_editor.move_block(PAST, BLOCK, "3", "14:00")


def test_the_current_state_is_captured():
    move_block()
    student_editor.set_field("prenom", "Marie")
    failures.update_config(failures.FailureConfigUpdate(latencyMs="100-800"))

    captured = snapshot_editor.capture("Démo")

    active = data_store.ACTIVE_SESSION
    assert captured["anchor"]["session"] == active
    assert captured["anchor"]["date"] == date.today().isoformat()
    assert captured["setup"]["profile"] == data_store.PROFILE_NAME
    assert captured["failures"] == {"latencyMs": "100-800"}
    assert captured["student"] == {"prenom": "Marie"}
    assert PAST in captured["sessions"]
    assert captured["sessions"][PAST]["calendar"]["dateDebut"]
    assert captured["sessions"][active]["courses"] == data_store.get_session_courses(active)


def test_a_snapshot_is_saved_from_the_editor(client, sandbox_snapshots):
    state = api(client, "/save", name="Démo", scope="shared")

    assert state["saved"] == {"scope": "shared", "id": "demo"}
    assert [item["name"] for item in state["snapshots"]] == ["Démo"]
    assert state["current"]["session"] == data_store.ACTIVE_SESSION
    assert json.loads((sandbox_snapshots / "shared" / "demo.json").read_text("utf-8"))


def test_saving_over_an_existing_name_asks_first(client):
    api(client, "/save", name="Démo")

    response = client.post("/editor/api/snapshots/save", json={"name": "Démo"})

    assert response.status_code == 409
    assert api(client, "/save", name="Démo", overwrite=True)["saved"]["id"] == "demo"


def test_loading_brings_every_edit_back(client):
    move_block()
    student_editor.set_field("prenom", "Marie")
    failures.update_config(failures.FailureConfigUpdate(errorRate=0.5))
    api(client, "/save", name="Démo")
    saved_overrides = data_store._load_overrides()

    schedule_editor.reset_session(PAST)
    student_editor.reset()
    failures.reset_config()

    result = api(client, "/load", scope="personal", id="demo")

    assert result["notices"] == []
    assert data_store._load_overrides()[PAST] == saved_overrides[PAST]
    assert data_store.load_student_overrides() == {"prenom": "Marie"}
    assert failures.get_config().error_rate == 0.5
    assert schedule_editor.get_state(PAST)["canUndo"] is False
    assert student_editor.get_state()["canUndo"] is False


def test_the_pannes_can_be_skipped_when_loading(client):
    failures.update_config(failures.FailureConfigUpdate(errorRate=0.5))
    api(client, "/save", name="Démo")
    failures.update_config(failures.FailureConfigUpdate(errorRate=0.1, malformed=True))

    api(client, "/load", scope="personal", id="demo", failures=False)

    assert failures.get_config().error_rate == 0.1
    assert failures.get_config().malformed is True


def test_loading_replaces_the_pannes_set_after_the_save(client):
    api(client, "/save", name="Démo")
    failures.update_config(failures.FailureConfigUpdate(malformed=True))

    api(client, "/load", scope="personal", id="demo")

    assert failures.get_config().is_default()


def test_loading_changes_the_setup_without_a_restart(client):
    body = snapshot(setup={"profile": "semester-off", "scenario": "friday-off", "semesterWeek": 3})
    snapshots.write("personal", body)

    result = api(client, "/load", scope="personal", id="mi-session", dates="setup")

    assert data_store.PROFILE_NAME == "semester-off"
    assert data_store.SCENARIO_NAME == "friday-off"
    assert data_store.SEMESTER_WEEK == 3
    assert result["current"]["setup"]["profile"] == "semester-off"
    assert result["current"]["week"] == 3
    assert data_store.get_session_courses(data_store.ACTIVE_SESSION) == []


def test_the_loaded_setup_survives_a_data_reload(client):
    snapshots.write("personal", snapshot(setup={"profile": "semester-off"}))
    api(client, "/load", scope="personal", id="mi-session", dates="setup")

    assert client.post("/reload").status_code == 200

    assert data_store.PROFILE_NAME == "semester-off"


def test_setup_only_keeps_the_student_edits_and_clears_the_schedule(client):
    move_block()
    snapshots.write("personal", snapshot())

    api(client, "/load", scope="personal", id="mi-session", dates="setup")

    assert data_store._load_overrides() == {}
    assert data_store.load_student_overrides() == {"prenom": "Marie"}


def test_a_snapshot_that_cannot_load_leaves_everything_as_it_was(client):
    move_block()
    before = data_store._load_overrides()
    snapshots.write("personal", snapshot(setup={"profile": "gone"}))

    response = client.post(
        "/editor/api/snapshots/load", json={"scope": "personal", "id": "mi-session"}
    )

    assert response.status_code == 400
    assert "gone" in response.json()["error"]
    assert data_store.PROFILE_NAME == "normal"
    assert data_store._load_overrides() == before


def test_a_snapshot_can_be_exported_and_imported(client):
    api(client, "/save", name="Démo", scope="shared")

    exported = client.get("/editor/api/snapshots/export", params={"scope": "shared", "id": "demo"})

    assert exported.status_code == 200
    assert 'filename="demo.json"' in exported.headers["content-disposition"]
    body = exported.json()
    api(client, "/delete", scope="shared", id="demo")
    state = api(client, "/import", snapshot=body)
    assert state["saved"] == {"scope": "personal", "id": "demo"}
    assert snapshots.read("personal", "demo") == body


def test_importing_something_else_than_a_snapshot_is_refused(client):
    response = client.post("/editor/api/snapshots/import", json={"snapshot": {"hello": 1}})

    assert response.status_code == 400


def test_a_snapshot_can_be_shared_from_the_editor(client):
    api(client, "/save", name="Démo")

    state = api(client, "/move", scope="personal", id="demo", to="shared")

    assert [(i["scope"], i["id"]) for i in state["snapshots"]] == [("shared", "demo")]


def test_exact_dates_bring_back_an_edited_session_date(client):
    schedule_editor.set_session_date(PAST, "dateFin", "2026-05-01")
    api(client, "/save", name="Démo")
    schedule_editor.reset_session_dates(PAST)

    api(client, "/load", scope="personal", id="demo", dates="exact")

    assert data_store._load_overrides()[PAST]["dates"] == {"dateFin": "2026-05-01"}
    assert sessions.session_metadata(PAST)["dateFin"] == "2026-05-01"
