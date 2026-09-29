import base64
import json
import re
import zlib
from datetime import date, timedelta

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

WEEK_4 = {"week": 4, "gap": 16}
BETWEEN = {"betweenSessions": True, "gap": 10}
LONG_BREAK = {"week": 14, "gap": 60}
NO_NEXT = {"week": 6, "noNextSession": True}


@pytest.fixture
def today(monkeypatch):
    def freeze(iso):
        frozen = date.fromisoformat(iso)

        class FrozenDate(date):
            @classmethod
            def today(cls):
                return frozen

        for module in (sessions, snapshots, snapshot_editor):
            monkeypatch.setattr(module, "date", FrozenDate)
        return frozen

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


def anchor(position=WEEK_4, session="A2026", day="2026-09-25"):
    return {"session": session, "date": day, **position}


def snapshot(**changes):
    body = {
        "format": snapshots.FORMAT,
        "name": "Mi-session",
        "savedAt": "2026-09-25T10:00",
        "anchor": anchor(),
        "setup": {"profile": "normal", "scenario": "none"},
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


def calendar_of(plan):
    return {key: plan.setup[key] for key in snapshots.CALENDAR_SETUP if key in plan.setup}


def planned(code, field):
    return date.fromisoformat(sessions.session_metadata(code)[field])


def test_a_name_becomes_a_file_friendly_id():
    assert snapshots.slugify("  Été: examen final! ") == "ete-examen-final"


@pytest.mark.parametrize("name", ["", "   ", "!!!", "x" * 81])
def test_an_unusable_name_is_refused(name):
    with pytest.raises(SnapshotError):
        snapshots.clean_name(name)


def test_a_snapshot_is_written_listed_and_read_back(sandbox_snapshots):
    snapshot_id = snapshots.write(snapshot(name="Examen final"))

    assert snapshot_id == "examen-final"
    assert (sandbox_snapshots / "examen-final.json").exists()
    listed = snapshots.list_all()
    assert [(item["id"], item["name"]) for item in listed] == [
        ("examen-final", "Examen final")
    ]
    assert listed[0]["anchor"] == anchor()
    assert listed[0]["sessions"] == ["A2026"]
    assert listed[0]["student"] == ["prenom"]
    assert snapshots.read("examen-final")["student"] == {"prenom": "Marie"}


def test_snapshots_are_listed_by_name():
    snapshots.write(snapshot(name="C"))
    snapshots.write(snapshot(name="a"))
    snapshots.write(snapshot(name="B"))

    assert [i["name"] for i in snapshots.list_all()] == ["a", "B", "C"]


def test_an_existing_name_is_not_replaced_unless_asked():
    snapshots.write(snapshot(name="Démo"))

    with pytest.raises(SnapshotConflict):
        snapshots.write(snapshot(name="demo", student={}))

    snapshots.write(snapshot(name="demo", student={}), overwrite=True)
    assert snapshots.read("demo")["student"] == {}


def test_a_snapshot_can_be_deleted():
    snapshots.write(snapshot())
    snapshots.delete("mi-session")

    assert snapshots.list_all() == []
    with pytest.raises(SnapshotError):
        snapshots.delete("mi-session")


@pytest.mark.parametrize("snapshot_id", ["../escape", "shared/demo", ""])
def test_paths_stay_inside_the_snapshot_folder(snapshot_id):
    with pytest.raises(SnapshotError):
        snapshots.read(snapshot_id)


def test_unreadable_files_are_left_out_of_the_list(sandbox_snapshots):
    snapshots.write(snapshot())
    (sandbox_snapshots / "broken.json").write_text("{", encoding="utf-8")
    (sandbox_snapshots / "other.json").write_text("[]", encoding="utf-8")

    assert [item["id"] for item in snapshots.list_all()] == ["mi-session"]


@pytest.mark.parametrize(
    "broken",
    [
        [],
        {**snapshot(), "format": 1},
        {**snapshot(), "name": ""},
        {**snapshot(), "anchor": {"session": "A2026", "week": 4, "gap": 16}},
        {**snapshot(), "anchor": anchor({"gap": 16})},
        {**snapshot(), "anchor": anchor({"week": 4, "betweenSessions": True, "gap": 16})},
        {**snapshot(), "anchor": anchor({"week": True, "gap": 16})},
        {**snapshot(), "anchor": anchor({"week": 4})},
        {**snapshot(), "anchor": anchor({"week": 4, "gap": 16, "noNextSession": True})},
        {**snapshot(), "anchor": anchor({"week": 4, "gap": -1})},
        {**snapshot(), "setup": {}},
        {**snapshot(), "sessions": {"A2026": []}},
        {**snapshot(), "student": []},
    ],
)
def test_malformed_snapshots_are_rejected(broken):
    with pytest.raises(SnapshotError):
        snapshots.validate(broken)


@pytest.mark.parametrize("position", [WEEK_4, BETWEEN, NO_NEXT, {"week": 0, "gap": 0}])
def test_every_calendar_position_is_a_valid_anchor(position):
    assert snapshots.validate(snapshot(anchor=anchor(position)))["anchor"] == anchor(position)


def test_a_snapshot_is_found_by_name_or_id():
    snapshots.write(snapshot(name="Examen final"))

    assert snapshots.find("Examen final") == "examen-final"
    assert snapshots.find("examen-final") == "examen-final"
    assert snapshots.find("examen") is None


@pytest.mark.parametrize(
    "calendar_env, calendar_setup",
    [
        ({"SEMESTER_WEEK": "3", "SEMESTER_GAP": "10"}, {"semesterWeek": 3, "semesterGap": 10}),
        (
            {"BETWEEN_SESSIONS": "true", "NO_NEXT_SESSION": "true"},
            {"betweenSessions": True, "noNextSession": True},
        ),
    ],
)
def test_the_setup_round_trips_through_the_environment(calendar_env, calendar_setup):
    env = {
        "PROFILE": "generated-busy",
        "SCENARIO": "friday-off",
        **calendar_env,
        "COURSE_COUNT": "2",
        "SCHEDULE_DAYS": "1,3",
        "TIME_PREFERENCE": "",
    }

    setup = snapshots.setup_from_env(env)

    assert setup == {
        "profile": "generated-busy",
        "scenario": "friday-off",
        **calendar_setup,
        "courses": 2,
        "days": ["1", "3"],
        "time": "",
    }
    assert snapshots.setup_to_env(setup) == env


def test_a_default_setup_only_sets_the_profile():
    setup = snapshots.setup_from_env({})

    assert setup == {"profile": "normal", "scenario": "none"}
    assert snapshots.setup_to_env(setup) == {"PROFILE": "normal"}


def test_realigning_shifts_every_date_by_whole_weeks(today):
    today("2026-10-09")

    plan = snapshots.plan(snapshot(), "week")

    assert calendar_of(plan) == {"semesterWeek": 4, "semesterGap": 16}
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


def test_a_snapshot_saved_in_week_n_puts_today_in_week_n(today):
    now = today("2026-10-09")

    snapshots.plan(snapshot(), "week")

    start = planned("A2026", "dateDebut")
    assert sessions.week_index(start, now) == 4
    assert start.weekday() == date(2026, 9, 1).weekday()


def test_loading_on_the_saved_day_changes_nothing(today):
    today("2026-09-25")

    plan = snapshots.plan(snapshot(), "week")

    assert calendar_of(plan) == {"semesterWeek": 4, "semesterGap": 16}
    assert plan.schedule["A2026"]["courses"] == [edited_course()]
    assert plan.schedule["A2026"]["dates"] == {"dateFin": "2026-12-22"}
    assert planned("A2026", "dateDebut") == date(2026, 9, 1)


def test_a_snapshot_saved_between_sessions_ends_the_active_session_yesterday(today):
    now = today("2027-02-10")

    plan = snapshots.plan(snapshot(anchor=anchor(BETWEEN, day="2026-12-22")), "week")

    assert calendar_of(plan) == {"betweenSessions": True, "semesterGap": 10}
    assert plan.notices == []
    assert planned("H2027", "dateFin") == now - timedelta(days=1)
    assert planned("É2027", "dateDebut") == now + timedelta(days=10)


@pytest.mark.parametrize("gap", [0, 10, 60])
def test_the_next_session_starts_the_saved_gap_after_the_active_one(today, gap):
    today("2026-10-09")

    plan = snapshots.plan(snapshot(anchor=anchor({"week": 14, "gap": gap})), "week")

    assert calendar_of(plan) == {"semesterWeek": 14, "semesterGap": gap}
    days_off = (planned("H2027", "dateDebut") - planned("A2026", "dateFin")).days - 1
    assert days_off == gap


def test_a_snapshot_without_a_next_session_hides_it_again(today):
    today("2026-10-09")

    plan = snapshots.plan(snapshot(anchor=anchor(NO_NEXT)), "week")

    assert calendar_of(plan) == {"semesterWeek": 6, "noNextSession": True}


@pytest.mark.parametrize("position", [WEEK_4, BETWEEN, LONG_BREAK, NO_NEXT])
def test_the_plan_and_the_served_calendar_agree(today, position):
    today("2027-02-10")
    plan = snapshots.plan(snapshot(anchor=anchor(position)), "week")
    expected = {
        code: sessions.session_metadata(code) for code in ("H2027", "É2027")
    }

    data_store.set_setup(snapshots.setup_to_env(plan.setup))
    data_store.reload()

    for code, dates in expected.items():
        assert data_store.get_base_session(code) == dates


def test_the_active_session_is_remapped_to_the_current_one(today):
    today("2027-02-10")

    plan = snapshots.plan(snapshot(), "week")

    assert set(plan.schedule) == {"H2027"}
    saved = stored_courses(plan.schedule, "H2027")[0]
    assert saved["session"] == "H2027"
    start = planned("H2027", "dateDebut")
    origin = date.fromisoformat(saved["occurrenceOverrides"][0]["date"])
    assert origin.isoweekday() == 1
    assert sessions.week_index(start, origin) == 5
    assert sessions.week_index(start, date(2027, 2, 10)) == 4


def test_the_next_session_follows_the_active_one(today):
    today("2027-02-10")
    upcoming = course("H2027")
    upcoming["occurrenceOverrides"] = [{"block": 0, "date": "2027-01-11", "canceled": True}]
    body = snapshot()
    body["sessions"]["H2027"] = {
        "calendar": {"dateDebut": "2027-01-04", "dateFin": "2027-04-26"},
        "courses": [upcoming],
        "trash": [],
    }

    plan = snapshots.plan(body, "week")

    assert set(plan.schedule) == {"H2027", "É2027"}
    moved = stored_courses(plan.schedule, "É2027")[0]
    assert moved["session"] == "É2027"
    assert stored_courses(plan.schedule, "H2027")[0]["sigle"] == "LOG100"
    start = planned("É2027", "dateDebut")
    assert sessions.week_index(start, date.fromisoformat(moved["occurrenceOverrides"][0]["date"])) == 2


def test_other_sessions_keep_their_code_and_dates(today):
    today("2027-02-10")
    body = snapshot()
    past = edited_course(PAST)
    body["sessions"][PAST] = {"calendar": {}, "courses": [past], "trash": []}

    plan = snapshots.plan(body, "week")

    assert stored_courses(plan.schedule, PAST) == [past]


def test_a_week_past_the_end_of_a_shorter_session_is_clamped(today):
    today("2026-10-09")
    body = snapshot(anchor=anchor({"week": 17, "gap": 6}, session="H2026", day="2026-04-24"))

    plan = snapshots.plan(body, "week")

    assert plan.setup["semesterWeek"] == 16
    assert plan.notices == [
        "A2026 n'a que 16 semaines: la semaine 16 est utilisée au lieu de la semaine 17."
    ]


def test_a_snapshot_saved_before_its_session_started_lands_on_week_one(today):
    today("2026-10-09")

    plan = snapshots.plan(snapshot(anchor=anchor({"week": 0, "gap": 16})), "week")

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
        anchor=anchor({"week": 3, "gap": 6}, session="H2026", day="2026-01-23"),
        sessions={
            "H2026": {"calendar": {"dateDebut": "2026-01-05"}, "courses": [winter], "trash": []}
        },
    )

    plan = snapshots.plan(body, "week")

    kept = stored_courses(plan.schedule, "A2026")[0]["occurrenceOverrides"]
    assert kept == [{"block": 0, "date": "2026-09-28", "canceled": True}]
    assert plan.notices == ["1 modification(s) de séance hors de la session A2026 ignorée(s)."]


def test_exact_dates_keep_every_date_and_the_real_calendar(today):
    today("2026-10-09")

    plan = snapshots.plan(snapshot(anchor=anchor(LONG_BREAK)), "exact")

    assert calendar_of(plan) == {}
    assert plan.notices == []
    assert plan.schedule["A2026"]["courses"] == [edited_course()]
    assert plan.schedule["A2026"]["dates"] == {"dateFin": "2026-12-22"}
    assert planned("A2026", "dateDebut") == date(2026, 9, 1)


def test_exact_dates_still_hide_a_next_session_that_was_not_published(today):
    today("2026-10-09")

    plan = snapshots.plan(snapshot(anchor=anchor(NO_NEXT)), "exact")

    assert calendar_of(plan) == {"noNextSession": True}


def test_exact_dates_pin_a_calendar_that_was_shifted_when_saved(today):
    today("2026-10-09")
    body = snapshot(anchor=anchor(BETWEEN, day="2026-09-25"))
    body["sessions"]["A2026"]["calendar"] = {
        "dateDebut": "2026-06-09",
        "dateFinCours": "2026-09-14",
        "dateFin": "2026-09-24",
    }

    plan = snapshots.plan(body, "exact")

    assert calendar_of(plan) == {}
    assert plan.schedule["A2026"]["dates"] == {
        "dateDebut": "2026-06-09",
        "dateFinCours": "2026-09-14",
        "dateFin": "2026-12-22",
    }


def test_a_plan_carries_every_part_of_the_snapshot(today):
    today("2027-02-10")
    body = snapshot(
        anchor=anchor(BETWEEN),
        setup={"profile": "generated-busy", "scenario": "friday-off"},
    )

    plan = snapshots.plan(body, "week")

    assert plan.schedule
    assert plan.setup == {
        "profile": "generated-busy",
        "scenario": "friday-off",
        "betweenSessions": True,
        "semesterGap": 10,
    }
    assert plan.student == {"prenom": "Marie"}
    assert plan.failures == {"latencyMs": "100-800", "errorRate": 0.3}


def test_calendar_options_left_in_a_saved_setup_are_ignored(today):
    today("2026-10-09")
    body = snapshot(setup={"profile": "normal", "semesterWeek": 9, "noNextSession": True})

    plan = snapshots.plan(body, "week")

    assert calendar_of(plan) == {"semesterWeek": 4, "semesterGap": 16}


def test_an_unknown_date_mode_is_refused():
    with pytest.raises(SnapshotError):
        snapshots.plan(snapshot(), "setup")


def test_writing_empty_parts_removes_the_old_overrides(tmp_path):
    schedule_path = tmp_path / "schedule.json"
    student_path = tmp_path / "student.json"
    schedule_path.write_text('{"A2026": {}}', encoding="utf-8")
    student_path.write_text('{"nom": "Ancien"}', encoding="utf-8")

    snapshots.write_overrides({}, {}, schedule_path, student_path)

    assert not schedule_path.exists()
    assert not student_path.exists()


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


@pytest.mark.parametrize(
    "day, env, position",
    [
        ("2026-09-25", {}, WEEK_4),
        ("2026-12-22", {}, {"betweenSessions": True, "gap": 13}),
        ("2026-09-25", {"BETWEEN_SESSIONS": "true", "SEMESTER_GAP": "10"}, BETWEEN),
        ("2026-09-25", {"SEMESTER_WEEK": "14", "SEMESTER_GAP": "60"}, LONG_BREAK),
        ("2026-10-09", {"NO_NEXT_SESSION": "true"}, NO_NEXT),
    ],
)
def test_the_calendar_position_is_captured(today, reconfigure, day, env, position):
    today(day)
    reconfigure(**env)

    captured = snapshot_editor.capture("Démo")

    assert captured["anchor"] == {"session": "A2026", "date": day, **position}
    assert not set(captured["setup"]) & set(snapshots.CALENDAR_SETUP)


def days_until_next_session(now):
    start = data_store.get_base_session(data_store.NEXT_SESSION)["dateDebut"]
    return (date.fromisoformat(start) - now).days


def test_a_break_saved_partway_through_comes_back_with_the_same_countdown(client, today):
    saved_on = today("2026-12-22")
    data_store.reload()
    countdown = days_until_next_session(saved_on)
    snapshots.write(snapshot_editor.capture("Congé"))

    loaded_on = today("2027-02-10")
    api(client, "/load", id="conge")

    assert countdown == 13
    assert days_until_next_session(loaded_on) == countdown
    assert data_store.BETWEEN_SESSIONS is True


def test_the_current_calendar_is_listed_with_the_snapshots(client, today, reconfigure):
    today("2026-09-25")
    reconfigure(BETWEEN_SESSIONS="true", NO_NEXT_SESSION="true")

    current = client.get("/editor/api/snapshots").json()["current"]

    assert current["session"] == "A2026"
    assert current["nextSession"] == "H2027"
    assert current["weeks"] == 16
    assert current["position"] == {"betweenSessions": True, "noNextSession": True}
    assert current["setup"] == {
        "profile": "normal",
        "scenario": "none",
        "betweenSessions": True,
        "noNextSession": True,
    }


def test_a_snapshot_is_saved_from_the_editor(client, sandbox_snapshots):
    state = api(client, "/save", name="Démo")

    assert state["saved"] == "demo"
    assert [item["name"] for item in state["snapshots"]] == ["Démo"]
    assert state["current"]["session"] == data_store.ACTIVE_SESSION
    assert json.loads((sandbox_snapshots / "demo.json").read_text("utf-8"))


def test_saving_over_an_existing_name_asks_first(client):
    api(client, "/save", name="Démo")

    response = client.post("/editor/api/snapshots/save", json={"name": "Démo"})

    assert response.status_code == 409
    assert response.json()["name"] == "Démo"
    assert api(client, "/save", name="Démo", overwrite=True)["saved"] == "demo"


def test_loading_brings_every_edit_back(client):
    move_block()
    student_editor.set_field("prenom", "Marie")
    failures.update_config(failures.FailureConfigUpdate(errorRate=0.5))
    api(client, "/save", name="Démo")
    saved_overrides = data_store._load_overrides()

    schedule_editor.reset_session(PAST)
    student_editor.reset()
    failures.reset_config()

    result = api(client, "/load", id="demo")

    assert result["notices"] == []
    assert data_store._load_overrides()[PAST] == saved_overrides[PAST]
    assert data_store.load_student_overrides() == {"prenom": "Marie"}
    assert failures.get_config().error_rate == 0.5
    assert schedule_editor.get_state(PAST)["canUndo"] is False
    assert student_editor.get_state()["canUndo"] is False


@pytest.mark.parametrize("position", [WEEK_4, BETWEEN, LONG_BREAK, NO_NEXT])
def test_a_loaded_snapshot_is_saved_again_in_the_same_situation(client, today, position):
    today("2027-02-10")
    snapshots.write(snapshot(anchor=anchor(position)))

    api(client, "/load", id="mi-session")

    again = snapshot_editor.capture("Encore")["anchor"]
    assert again == {"session": "H2027", "date": "2027-02-10", **position}


@pytest.mark.parametrize(
    "position, expected",
    [
        (WEEK_4, (4, False, 16, False)),
        (BETWEEN, (None, True, 10, False)),
        (NO_NEXT, (6, False, None, True)),
    ],
)
def test_loading_replaces_the_startup_calendar_options(client, reconfigure, position, expected):
    reconfigure(BETWEEN_SESSIONS="true", NO_NEXT_SESSION="true")
    snapshots.write(snapshot(anchor=anchor(position)))

    result = api(client, "/load", id="mi-session")

    served = (
        data_store.SEMESTER_WEEK,
        data_store.BETWEEN_SESSIONS,
        data_store.SEMESTER_GAP,
        data_store.NO_NEXT_SESSION,
    )
    assert served == expected
    assert result["current"]["position"] == position


def test_exact_dates_only_keep_the_hidden_next_session(client, reconfigure):
    reconfigure(SEMESTER_WEEK="3", SEMESTER_GAP="45")
    snapshots.write(snapshot(anchor=anchor(NO_NEXT)))

    api(client, "/load", id="mi-session", dates="exact")

    assert data_store.SEMESTER_WEEK is None
    assert data_store.SEMESTER_GAP is None
    assert data_store.NO_NEXT_SESSION is True


def test_loading_changes_the_setup_without_a_restart(client):
    body = snapshot(setup={"profile": "semester-off", "scenario": "friday-off"}, sessions={})
    snapshots.write(body)

    result = api(client, "/load", id="mi-session")

    assert data_store.PROFILE_NAME == "semester-off"
    assert data_store.SCENARIO_NAME == "friday-off"
    assert result["current"]["setup"]["profile"] == "semester-off"
    assert data_store.get_session_courses(data_store.ACTIVE_SESSION) == []


def test_the_loaded_setup_survives_a_data_reload(client):
    snapshots.write(snapshot(setup={"profile": "semester-off"}, sessions={}))
    api(client, "/load", id="mi-session")

    assert client.post("/reload").status_code == 200

    assert data_store.PROFILE_NAME == "semester-off"


def test_a_snapshot_without_schedule_edits_clears_the_current_ones(client):
    move_block()
    snapshots.write(snapshot(sessions={}))

    api(client, "/load", id="mi-session")

    assert data_store._load_overrides() == {}
    assert data_store.load_student_overrides() == {"prenom": "Marie"}
    assert failures.get_config().error_rate == 0.3


def test_loading_replaces_the_student_profile_and_its_undo_history(client):
    student_editor.set_field("prenom", "Luc")
    snapshots.write(snapshot())

    api(client, "/load", id="mi-session")

    assert data_store.load_student_overrides() == {"prenom": "Marie"}
    assert student_editor.get_state()["canUndo"] is False


def test_loading_replaces_the_pannes_set_after_the_save(client):
    api(client, "/save", name="Démo")
    failures.update_config(failures.FailureConfigUpdate(malformed=True))

    api(client, "/load", id="demo")

    assert failures.get_config().is_default()


def test_a_snapshot_that_cannot_load_leaves_everything_as_it_was(client):
    move_block()
    before = data_store._load_overrides()
    snapshots.write(snapshot(setup={"profile": "gone"}))

    response = client.post("/editor/api/snapshots/load", json={"id": "mi-session"})

    assert response.status_code == 400
    assert "gone" in response.json()["error"]
    assert data_store.PROFILE_NAME == "normal"
    assert data_store._load_overrides() == before


def test_a_snapshot_can_be_exported_and_imported(client):
    api(client, "/save", name="Démo")

    exported = client.get("/editor/api/snapshots/export", params={"id": "demo"})

    assert exported.status_code == 200
    assert 'filename="demo.json"' in exported.headers["content-disposition"]
    body = exported.json()
    api(client, "/delete", id="demo")
    state = api(client, "/import", snapshot=body)
    assert state["saved"] == "demo"
    assert snapshots.read("demo") == body


def test_importing_something_else_than_a_snapshot_is_refused(client):
    response = client.post("/editor/api/snapshots/import", json={"snapshot": {"hello": 1}})

    assert response.status_code == 400


def test_importing_needs_a_snapshot_or_a_code(client):
    response = client.post("/editor/api/snapshots/import", json={})

    assert response.status_code == 400


def test_a_code_decodes_to_the_same_snapshot():
    body = snapshots.validate(snapshot())

    assert snapshots.decode(snapshots.encode(body)) == body


def test_a_code_is_plain_url_safe_text():
    code = snapshots.encode(snapshot(name="Élève à l'examen"))

    assert re.fullmatch(r"[A-Za-z0-9_-]+", code)


def test_a_code_wrapped_on_several_lines_still_decodes():
    code = snapshots.encode(snapshot())
    wrapped = "  " + "\n".join(code[i : i + 40] for i in range(0, len(code), 40)) + "\r\n"

    assert snapshots.decode(wrapped)["name"] == "Mi-session"


@pytest.mark.parametrize(
    "code",
    [
        "",
        "pas un code!",
        base64.urlsafe_b64encode(b"not compressed").decode(),
        base64.urlsafe_b64encode(zlib.compress(b"not json")).decode(),
        base64.urlsafe_b64encode(zlib.compress(b'{"hello": 1}')).decode(),
    ],
)
def test_anything_else_than_a_code_is_refused(code):
    with pytest.raises(SnapshotError):
        snapshots.decode(code)


def test_a_snapshot_can_be_shared_as_a_code(client):
    api(client, "/save", name="Démo")
    saved = snapshots.read("demo")

    response = client.get("/editor/api/snapshots/code", params={"id": "demo"})
    assert response.status_code == 200
    code = response.json()["code"]
    api(client, "/delete", id="demo")
    state = api(client, "/import", code=code)

    assert state["saved"] == "demo"
    assert snapshots.read("demo") == saved


def test_a_missing_snapshot_has_no_code(client):
    response = client.get("/editor/api/snapshots/code", params={"id": "absent"})

    assert response.status_code == 400


def test_importing_a_code_over_an_existing_name_asks_first(client):
    api(client, "/save", name="Démo")
    code = client.get("/editor/api/snapshots/code", params={"id": "demo"}).json()["code"]

    response = client.post("/editor/api/snapshots/import", json={"code": code})

    assert response.status_code == 409
    assert response.json() == {
        "error": "A snapshot named 'Démo' already exists",
        "name": "Démo",
    }
    assert api(client, "/import", code=code, overwrite=True)["saved"] == "demo"


def test_importing_a_broken_code_is_refused(client):
    response = client.post("/editor/api/snapshots/import", json={"code": "abc"})

    assert response.status_code == 400
    assert response.json()["error"] == "This is not a snapshot code"


def test_exact_dates_bring_back_an_edited_session_date(client):
    schedule_editor.set_session_date(PAST, "dateFin", "2026-05-01")
    api(client, "/save", name="Démo")
    schedule_editor.reset_session_dates(PAST)

    api(client, "/load", id="demo", dates="exact")

    assert data_store._load_overrides()[PAST]["dates"] == {"dateFin": "2026-05-01"}
    assert sessions.session_metadata(PAST)["dateFin"] == "2026-05-01"
