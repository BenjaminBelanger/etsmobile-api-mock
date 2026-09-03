import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from lib import data_store, profiles, scenarios, schedule_editor, sessions
from lib._paths import SEED
from main import app


def _clear_editor_state():
    schedule_editor.clear_cache()


@pytest.fixture()
def overrides_file(tmp_path, monkeypatch):
    """Send the editor's persisted state to tmp for the duration of the test.

    The real seed/schedule_overrides.json is live state belonging to whatever
    server is running against this checkout, so the suite must never read,
    write or delete it: a run used to wipe an open /editor session's saved work.
    """
    path = tmp_path / data_store.OVERRIDES_FILENAME
    monkeypatch.setattr(data_store, "overrides_path", lambda: path)
    return path


@pytest.fixture()
def client(overrides_file):
    overrides_file.unlink(missing_ok=True)
    _clear_editor_state()
    data_store.reload()
    with TestClient(app) as test_client:
        yield test_client
    overrides_file.unlink(missing_ok=True)
    _clear_editor_state()
    data_store.reload()


def _state(client, session=""):
    res = client.get("/editor/api/state", params={"session": session})
    assert res.status_code == 200, res.text
    return res.json()


def _session_with_blocks(client):
    st = _state(client)
    assert st["blocks"], "active session should have generated courses"
    return st


def _dur(block):
    def m(s):
        h, mm = s.split(":")
        return int(h) * 60 + int(mm)

    return m(block["heureFin"]) - m(block["heureDebut"])


def _api_course_sigles(client, session):
    res = client.get("/api/Etudiant/listeCours")
    return [c["sigle"] for c in res.json()["liste"] if c["session"] == session]


def _api_course_keys(client, session):
    res = client.get("/api/Etudiant/listeCours")
    return [
        f"{c['sigle']}-{c['groupe']}"
        for c in res.json()["liste"]
        if c["session"] == session
    ]


def test_state_shape(client):
    st = _session_with_blocks(client)
    assert st["session"]
    assert st["session"] in st["sessions"]
    assert st["meta"]["days"][0]["jour"] == "1"
    block = st["blocks"][0]
    for key in ("id", "courseId", "sigle", "jour", "heureDebut", "heureFin", "kind"):
        assert key in block


def test_semester_weeks_exposed(client):
    st = _session_with_blocks(client)
    semester = st["meta"]["semester"]
    assert semester, "session should expose its semester calendar"
    assert semester["dateDebut"] <= semester["dateFin"]
    weeks = semester["weeks"]
    assert weeks, "semester should span at least one week"

    first = weeks[0]
    for key in ("index", "start", "end", "label", "range", "dates"):
        assert key in first
    assert first["index"] == 1
    for jour in ("1", "2", "3", "4", "5", "6"):
        assert jour in first["dates"]
        assert len(first["dates"][jour]) == 10
    from datetime import date

    assert date.fromisoformat(first["start"]).weekday() == 0
    assert date.fromisoformat(first["dates"]["2"]) - date.fromisoformat(
        first["dates"]["1"]
    ) == (date.fromisoformat(first["dates"]["3"]) - date.fromisoformat(first["dates"]["2"]))
    if len(weeks) > 1:
        assert weeks[1]["index"] == 2
        assert (
            date.fromisoformat(weeks[1]["start"])
            - date.fromisoformat(weeks[0]["start"])
        ).days == 7


def test_move_block_changes_day_and_time(client):
    st = _session_with_blocks(client)
    session = st["session"]
    block = st["blocks"][0]
    target_day = "6" if block["jour"] != "6" else "1"

    res = client.post(
        "/editor/api/block/move",
        json={
            "session": session,
            "blockId": block["id"],
            "jour": target_day,
            "heureDebut": "14:00",
        },
    )
    assert res.status_code == 200, res.text
    moved = next(b for b in res.json()["blocks"] if b["id"] == block["id"])
    assert moved["jour"] == target_day
    assert moved["heureDebut"] == "14:00"
    assert _dur(moved) == _dur(block)


def test_move_snaps_and_clamps(client):
    st = _session_with_blocks(client)
    block = st["blocks"][0]
    res = client.post(
        "/editor/api/block/move",
        json={
            "session": st["session"],
            "blockId": block["id"],
            "jour": block["jour"],
            "heureDebut": "07:07",
        },
    )
    moved = next(b for b in res.json()["blocks"] if b["id"] == block["id"])
    assert moved["heureDebut"] >= "08:00"
    assert int(moved["heureDebut"][3:]) % 15 == 0


def test_resize_block(client):
    st = _session_with_blocks(client)
    block = st["blocks"][0]
    res = client.post(
        "/editor/api/block/resize",
        json={
            "session": st["session"],
            "blockId": block["id"],
            "heureDebut": block["heureDebut"],
            "heureFin": "20:00",
        },
    )
    assert res.status_code == 200, res.text
    resized = next(b for b in res.json()["blocks"] if b["id"] == block["id"])
    assert resized["heureFin"] == "20:00"


def test_resize_rejects_too_short(client):
    st = _session_with_blocks(client)
    block = st["blocks"][0]
    res = client.post(
        "/editor/api/block/resize",
        json={
            "session": st["session"],
            "blockId": block["id"],
            "heureDebut": "10:00",
            "heureFin": "10:10",
        },
    )
    assert res.status_code == 400


def test_delete_and_restore(client):
    st = _session_with_blocks(client)
    session = st["session"]
    course_id = st["courses"][0]["courseId"]

    body = client.post(
        "/editor/api/course/delete",
        json={"session": session, "courseId": course_id},
    ).json()
    assert course_id not in [c["courseId"] for c in body["courses"]]
    assert course_id in [t["courseId"] for t in body["trash"]]

    body = client.post(
        "/editor/api/course/restore",
        json={"session": session, "courseId": course_id},
    ).json()
    assert course_id in [c["courseId"] for c in body["courses"]]
    assert course_id not in [t["courseId"] for t in body["trash"]]


def test_delete_reflected_in_liste_cours(client):
    st = _session_with_blocks(client)
    session = st["session"]
    course = st["courses"][0]

    assert course["courseId"] in _api_course_keys(client, session)
    client.post(
        "/editor/api/course/delete",
        json={"session": session, "courseId": course["courseId"]},
    )
    assert course["courseId"] not in _api_course_keys(client, session)


def test_move_reflected_in_horaire(client):
    st = _session_with_blocks(client)
    session = st["session"]
    block = st["blocks"][0]
    target_day = "6" if block["jour"] != "6" else "1"

    client.post(
        "/editor/api/block/move",
        json={
            "session": session,
            "blockId": block["id"],
            "jour": target_day,
            "heureDebut": "15:00",
        },
    )
    res = client.get("/api/Etudiant/listeHoraireEtProf", params={"session": session})
    activities = res.json()["listeActivites"]
    match = [
        a
        for a in activities
        if a["sigle"] == block["sigle"]
        and a["groupe"] == block["groupe"]
        and a.get("activitePrincipale") == "Oui"
    ]
    assert match
    assert match[0]["jour"] == target_day
    assert match[0]["heureDebut"] == "15:00"


def test_add_course(client):
    st = _session_with_blocks(client)
    session = st["session"]
    res = client.post(
        "/editor/api/course/add",
        json={
            "session": session,
            "sigle": "ZZZ999",
            "titre": "Cours de test",
            "jour": "3",
            "heureDebut": "13:30",
            "heureFin": "16:30",
            "kind": "cours",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert [c for c in body["courses"] if c["sigle"] == "ZZZ999"]
    assert "ZZZ999" in _api_course_sigles(client, session)


def test_undo_redo(client):
    st = _session_with_blocks(client)
    session = st["session"]
    block = st["blocks"][0]
    original_day = block["jour"]
    target_day = "6" if original_day != "6" else "1"

    client.post(
        "/editor/api/block/move",
        json={
            "session": session,
            "blockId": block["id"],
            "jour": target_day,
            "heureDebut": "16:00",
        },
    )
    undo = client.post("/editor/api/undo", json={"session": session}).json()
    reverted = next(b for b in undo["blocks"] if b["id"] == block["id"])
    assert reverted["jour"] == original_day
    assert reverted["heureDebut"] == block["heureDebut"]

    redo = client.post("/editor/api/redo", json={"session": session}).json()
    redone = next(b for b in redo["blocks"] if b["id"] == block["id"])
    assert redone["jour"] == target_day


def test_undo_empty_is_error(client):
    st = _session_with_blocks(client)
    res = client.post("/editor/api/undo", json={"session": st["session"]})
    assert res.status_code == 400


def test_reset_restores_generated(client):
    st = _session_with_blocks(client)
    session = st["session"]
    original_ids = sorted(c["courseId"] for c in st["courses"])

    client.post(
        "/editor/api/course/delete",
        json={"session": session, "courseId": st["courses"][0]["courseId"]},
    )
    reset = client.post("/editor/api/reset", json={"session": session}).json()
    assert sorted(c["courseId"] for c in reset["courses"]) == original_ids
    assert reset["trash"] == []


def _occurrence(state, block_id, day):
    return next(
        (
            o
            for o in state["occurrences"]
            if o["blockId"] == block_id and o["date"] == day
        ),
        None,
    )


def _editor_served(state):
    return sorted(
        (o["date"], o["heureDebut"], o["courseId"]) for o in state["occurrences"]
    )


def _api_served(client, session):
    res = client.get(
        "/api/Etudiant/lireHoraireDesSeances", params={"session": session}
    )
    assert res.status_code == 200, res.text
    return sorted(
        (a["dateDebut"][:10], a["dateDebut"][11:16], a["coursGroupe"])
        for a in res.json()["ListeDesSeances"]
    )


def test_editor_occurrences_match_served_activities(client):
    st = _session_with_blocks(client)
    assert st["occurrences"]
    assert _editor_served(st) == _api_served(client, st["session"])


# Profiles whose editor session carries a real schedule. Named so the matrix
# below cannot pass vacuously on the profiles that serve nothing at all
# (internship-only and new-student strip the active session down to courses
# with no schedule).
PROFILES_WITH_SCHEDULE = {
    "normal",
    "semester-off",
    "internship-courses",
    "generated-light",
    "generated-busy",
    "generated-evening",
}


@pytest.mark.parametrize("scenario", sorted(scenarios.get_valid_scenarios()))
@pytest.mark.parametrize("profile", sorted(profiles.get_valid_profiles()))
def test_editor_matches_served_for_every_profile_and_scenario(
    client, monkeypatch, profile, scenario
):
    """Profiles and scenarios are seed transforms, so the editor's projection and
    lireHoraireDesSeances read the same materialized data and cannot drift."""
    monkeypatch.setenv("PROFILE", profile)
    monkeypatch.setenv("SCENARIO", scenario)
    _clear_editor_state()
    data_store.reload()

    st = _state(client)
    served = _api_served(client, st["session"])
    assert _editor_served(st) == served
    if profile in PROFILES_WITH_SCHEDULE:
        assert served, f"{profile}/{scenario} should serve seances"


def _activate_scenario(monkeypatch, skip_date):
    real_reload = scenarios.reload_scenarios

    def reload_with_test_scenario():
        loaded = real_reload()
        loaded["test-off"] = {"skipDates": [{"rule": "absolute", "date": skip_date}]}
        scenarios.VALID_SCENARIOS.add("test-off")
        return loaded

    monkeypatch.setattr(scenarios, "reload_scenarios", reload_with_test_scenario)
    monkeypatch.setenv("SCENARIO", "test-off")
    _clear_editor_state()
    data_store.reload()


def test_scenario_is_materialized_into_the_seed(client, monkeypatch):
    st = _session_with_blocks(client)
    before = _api_served(client, st["session"])
    target = st["occurrences"][0]["date"]
    _activate_scenario(monkeypatch, target)

    st = _state(client)
    assert all(o["date"] != target for o in st["occurrences"])
    served = _api_served(client, st["session"])
    assert all(day != target for day, _, _ in served)
    assert [row for row in before if row[0] == target], "target day should have had classes"
    assert _editor_served(st) == served


def _course_window(session):
    entry = next(
        s for s in sessions.get_raw_sessions() if s.get("abrege") == session
    )
    return entry["dateDebut"], entry["dateFinCours"]


@pytest.mark.parametrize("semester_week", ["1", "8", "15", "18"])
def test_scenario_overrides_stay_inside_the_course_window(
    client, monkeypatch, semester_week
):
    """Skip dates resolve off today, the course window moves with SEMESTER_WEEK, so a
    late enough week pushes them past dateFinCours where they can never expand."""
    monkeypatch.setenv("SCENARIO", "semaine-relache")
    monkeypatch.setenv("SEMESTER_WEEK", semester_week)
    _clear_editor_state()
    data_store.reload()

    session = data_store.ACTIVE_SESSION
    start, end = _course_window(session)
    seeded = [
        override["date"]
        for course in data_store.get_session_courses(session, base=True)
        for override in course.get("occurrenceOverrides", [])
    ]
    assert all(start <= day <= end for day in seeded), sorted(set(seeded))

    skip_dates, _ = scenarios._resolve_and_cache("semaine-relache")
    if [d for d in skip_dates if start <= d.isoformat() <= end]:
        assert seeded, "relache inside the window should still cancel occurrences"


def test_scenario_cancellations_are_editable(client, monkeypatch):
    st = _session_with_blocks(client)
    target = st["occurrences"][0]["date"]
    block_id = st["occurrences"][0]["blockId"]
    _activate_scenario(monkeypatch, target)

    res = client.post(
        "/editor/api/occurrence/reset",
        json={"session": st["session"], "blockId": block_id, "date": target},
    )
    assert res.status_code == 200, res.text
    restored = [
        o
        for o in res.json()["occurrences"]
        if o["date"] == target and o["blockId"] == block_id
    ]
    assert restored, "a scenario cancellation should be reversible from the editor"
    assert _editor_served(res.json()) == _api_served(client, st["session"])


def test_index_served(client):
    res = client.get("/editor")
    assert res.status_code == 200
    assert "Horaire" in res.text


def _anchor_for(st, block, week_index=1):
    week = st["meta"]["semester"]["weeks"][week_index]
    return week["dates"][block["jour"]]


def _seances(client, session, course_group):
    res = client.get(
        "/api/Etudiant/lireHoraireDesSeances", params={"session": session}
    )
    assert res.status_code == 200, res.text
    return [
        a
        for a in res.json()["ListeDesSeances"]
        if a["coursGroupe"] == course_group
    ]


def test_set_occurrence_moves_only_that_week(client):
    st = _session_with_blocks(client)
    session = st["session"]
    block = st["blocks"][0]
    anchor = _anchor_for(st, block)

    res = client.post(
        "/editor/api/occurrence/set",
        json={
            "session": session,
            "blockId": block["id"],
            "date": anchor,
            "jour": block["jour"],
            "heureDebut": "18:00",
            "heureFin": "20:00",
        },
    )
    assert res.status_code == 200, res.text
    moved = next(b for b in res.json()["blocks"] if b["id"] == block["id"])
    assert moved["heureDebut"] == block["heureDebut"]
    occ = _occurrence(res.json(), block["id"], anchor)
    assert occ["heureDebut"] == "18:00" and occ["heureFin"] == "20:00"
    assert occ["overridden"] is True

    seances = _seances(client, session, block["courseId"])
    on_anchor = [s for s in seances if s["dateDebut"].startswith(anchor)]
    assert on_anchor and on_anchor[0]["dateDebut"] == f"{anchor}T18:00:00"
    others = [s for s in seances if not s["dateDebut"].startswith(anchor)]
    assert others, "other weeks should still exist"


def test_cancel_occurrence_removes_only_that_seance(client):
    st = _session_with_blocks(client)
    session = st["session"]
    block = st["blocks"][0]
    anchor = _anchor_for(st, block)

    before = _seances(client, session, block["courseId"])
    assert any(s["dateDebut"].startswith(anchor) for s in before)

    res = client.post(
        "/editor/api/occurrence/cancel",
        json={"session": session, "blockId": block["id"], "date": anchor},
    )
    assert res.status_code == 200, res.text
    assert _occurrence(res.json(), block["id"], anchor) is None

    after = _seances(client, session, block["courseId"])
    assert not any(s["dateDebut"].startswith(anchor) for s in after)
    assert len(after) == len(before) - 1


def test_reset_occurrence_restores_pattern(client):
    st = _session_with_blocks(client)
    session = st["session"]
    block = st["blocks"][0]
    anchor = _anchor_for(st, block)

    client.post(
        "/editor/api/occurrence/cancel",
        json={"session": session, "blockId": block["id"], "date": anchor},
    )
    res = client.post(
        "/editor/api/occurrence/reset",
        json={"session": session, "blockId": block["id"], "date": anchor},
    )
    assert res.status_code == 200, res.text
    occ = _occurrence(res.json(), block["id"], anchor)
    assert occ is not None and occ["overridden"] is False

    seances = _seances(client, session, block["courseId"])
    assert any(s["dateDebut"].startswith(anchor) for s in seances)


def test_reset_occurrence_without_override_errors(client):
    st = _session_with_blocks(client)
    session = st["session"]
    block = st["blocks"][0]
    anchor = _anchor_for(st, block)
    res = client.post(
        "/editor/api/occurrence/reset",
        json={"session": session, "blockId": block["id"], "date": anchor},
    )
    assert res.status_code == 400


def _replaced_day(client, session):
    res = client.get("/api/Etudiant/lireJoursRemplaces", params={"session": session})
    assert res.status_code == 200, res.text
    entries = res.json()["listeJours"]
    assert len(entries) == 1, entries
    return entries[0]["dateOrigine"], entries[0]["dateRemplacement"]


def _dates_by_block(state):
    by_block = {}
    for occ in state["occurrences"]:
        by_block.setdefault(occ["blockId"], set()).add(occ["date"])
    return by_block


def _blocks_on(state, weekday):
    return [b for b in state["blocks"] if b["jour"] == weekday]


def test_replaced_day_moves_the_origin_timetable(client, monkeypatch):
    """A jour remplace is a swap: the origin day's blocks run on the replacement
    date, and the replacement date gives up its own timetable to host them."""
    monkeypatch.setenv("SCENARIO", "monday-holiday")
    _clear_editor_state()
    data_store.reload()

    st = _state(client)
    origin, replacement = _replaced_day(client, st["session"])
    origin_jour = str(date.fromisoformat(origin).isoweekday())
    replacement_jour = str(date.fromisoformat(replacement).isoweekday())

    moved = _blocks_on(st, origin_jour)
    displaced = _blocks_on(st, replacement_jour)
    assert moved or displaced, "scenario should touch at least one block"

    by_block = _dates_by_block(st)
    for block in moved:
        dates = by_block.get(block["id"], set())
        assert origin not in dates, f"{block['id']} should not run on the holiday"
        assert replacement in dates, f"{block['id']} should run on the replacement"
    for block in displaced:
        dates = by_block.get(block["id"], set())
        assert replacement not in dates, f"{block['id']} yields its day to the swap"

    assert _editor_served(st) == _api_served(client, st["session"])


def test_replaced_day_relocation_is_resettable(client, monkeypatch):
    monkeypatch.setenv("SCENARIO", "monday-holiday")
    _clear_editor_state()
    data_store.reload()

    st = _state(client)
    origin, replacement = _replaced_day(client, st["session"])
    origin_jour = str(date.fromisoformat(origin).isoweekday())
    moved = _blocks_on(st, origin_jour)
    if not moved:
        pytest.skip("no block on the replaced weekday to relocate")

    block_id = moved[0]["id"]
    occ = _occurrence(st, block_id, replacement)
    assert occ is not None and occ["overridden"] is True

    # The grid hands back the date the occurrence is drawn on, not the pattern
    # date its override is keyed by.
    res = client.post(
        "/editor/api/occurrence/reset",
        json={"session": st["session"], "blockId": block_id, "date": replacement},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert _occurrence(body, block_id, origin) is not None
    assert _occurrence(body, block_id, replacement) is None
    assert _editor_served(body) == _api_served(client, st["session"])


def test_moved_occurrence_resets_from_the_date_it_renders_on(client):
    st = _session_with_blocks(client)
    session = st["session"]
    block = st["blocks"][0]
    anchor = _anchor_for(st, block)
    target_day = "6" if block["jour"] != "6" else "1"

    body = client.post(
        "/editor/api/occurrence/set",
        json={
            "session": session,
            "blockId": block["id"],
            "date": anchor,
            "jour": target_day,
            "heureDebut": "18:00",
            "heureFin": "20:00",
        },
    ).json()
    moved = next(
        o
        for o in body["occurrences"]
        if o["blockId"] == block["id"] and o["overridden"]
    )
    assert moved["date"] != anchor

    res = client.post(
        "/editor/api/occurrence/reset",
        json={"session": session, "blockId": block["id"], "date": moved["date"]},
    )
    assert res.status_code == 200, res.text
    restored = _occurrence(res.json(), block["id"], anchor)
    assert restored is not None and restored["overridden"] is False


def test_reload_refreshes_the_editor_grid(client, monkeypatch):
    """/reload rebuilds data_store, and the editor caches its own copy of the
    courses, so the grid has to be invalidated with it."""
    st = _session_with_blocks(client)
    session = st["session"]
    before = {c["courseId"] for c in st["courses"]}

    monkeypatch.setenv("PROFILE", "generated-busy")
    assert client.post("/reload").status_code == 200

    served = set(_api_course_keys(client, session))
    assert served != before, "profile switch should change the served courses"

    st2 = _state(client, session)
    assert {c["courseId"] for c in st2["courses"]} == served
    # Final exams are deliberately block-less; every teachable occurrence is not.
    block_ids = {b["id"] for b in st2["blocks"]}
    orphans = [
        o
        for o in st2["occurrences"]
        if o["kind"] != "exam" and o["blockId"] not in block_ids
    ]
    assert not orphans, f"{len(orphans)} occurrences resolve to no block"
    assert _editor_served(st2) == _api_served(client, session)


def test_reload_keeps_persisted_edits(client, monkeypatch):
    st = _session_with_blocks(client)
    session = st["session"]
    block = st["blocks"][0]
    target_day = "6" if block["jour"] != "6" else "1"
    client.post(
        "/editor/api/block/move",
        json={
            "session": session,
            "blockId": block["id"],
            "jour": target_day,
            "heureDebut": "14:00",
        },
    )

    assert client.post("/reload").status_code == 200

    moved = next(
        b for b in _state(client, session)["blocks"] if b["id"] == block["id"]
    )
    assert moved["jour"] == target_day and moved["heureDebut"] == "14:00"


def _seed_replaced_days() -> dict:
    return json.loads((SEED / "replaced_days.json").read_text(encoding="utf-8"))


def _jour(iso: str) -> str:
    return str(date.fromisoformat(iso).isoweekday())


def test_seed_replaced_days_relocate_like_scenario_ones(client):
    """seed/replaced_days.json declares swaps for sessions other than the active
    one, so lireHoraireDesSeances has to move those seances too, not merely
    announce them through lireJoursRemplaces."""
    live = 0
    for session, entries in _seed_replaced_days().items():
        if session not in data_store.get_sessions_with_courses():
            continue
        st = _state(client, session)
        assert _editor_served(st) == _api_served(client, session)
        start, end = _course_window(session)
        by_block = _dates_by_block(st)
        for entry in entries:
            origin = entry["dateOrigine"]
            replacement = entry["dateRemplacement"]
            if not (start <= origin <= end and start <= replacement <= end):
                continue
            moved = _blocks_on(st, _jour(origin))
            displaced = _blocks_on(st, _jour(replacement))

            if not moved:
                # Nothing to host, so the swap is inert and the replacement
                # date keeps the timetable it would otherwise have yielded.
                for block in displaced:
                    assert replacement in by_block.get(block["id"], set()), (
                        f"{session}/{block['id']} lost its day to an empty swap"
                    )
                continue

            live += 1
            for block in moved:
                dates = by_block.get(block["id"], set())
                assert origin not in dates, f"{block['id']} ran on the holiday"
                assert replacement in dates, f"{session}/{block['id']} did not relocate"
            for block in displaced:
                assert replacement not in by_block.get(block["id"], set())
    assert live, "seed replaced days should relocate in at least one session"


def _activate_swap(monkeypatch, origin, replacement):
    real_reload = scenarios.reload_scenarios

    def reload_with_test_scenario():
        loaded = real_reload()
        loaded["test-swap"] = {
            "replacedDays": [
                {
                    "origin": {"rule": "absolute", "date": origin},
                    "replacement": {"rule": "absolute", "date": replacement},
                }
            ]
        }
        scenarios.VALID_SCENARIOS.add("test-swap")
        return loaded

    monkeypatch.setattr(scenarios, "reload_scenarios", reload_with_test_scenario)
    monkeypatch.setenv("SCENARIO", "test-swap")
    _clear_editor_state()
    data_store.reload()


def test_swap_with_nothing_to_relocate_leaves_the_day_alone(client, monkeypatch):
    """The replacement day only yields its timetable to make room for the
    origin's. With no block on the origin weekday there is nothing to host, so
    the swap is inert rather than a deletion dressed up as a swap."""
    monkeypatch.setenv("PROFILE", "generated-light")
    _clear_editor_state()
    data_store.reload()

    st = _state(client)
    session = st["session"]
    used = {b["jour"] for b in st["blocks"]}
    origin_jour = next(d for d in "12345" if d not in used)
    replacement_jour = next(d for d in "12345" if d in used)

    start, end = _course_window(session)
    week = next(
        w
        for w in st["meta"]["semester"]["weeks"]
        if start <= w["dates"][origin_jour] <= end
        and start <= w["dates"][replacement_jour] <= end
    )
    origin = week["dates"][origin_jour]
    replacement = week["dates"][replacement_jour]
    before = _api_served(client, session)
    assert [row for row in before if row[0] == replacement], (
        "the replacement day should have had classes to lose"
    )

    _activate_swap(monkeypatch, origin, replacement)

    st = _state(client)
    assert _api_served(client, session) == before
    assert _editor_served(st) == before
    assert _replaced_day(client, session) == (origin, replacement), (
        "an inert swap is still announced by lireJoursRemplaces"
    )


def _load_profile(client, monkeypatch, profile):
    monkeypatch.setenv("PROFILE", profile)
    _clear_editor_state()
    data_store.reload()
    return _state(client)


def test_internship_profiles_are_observably_different(client, monkeypatch):
    """internship-courses is an internship *plus* real courses. It used to pin
    LOG410, which no active session ever holds, leaving it identical to
    internship-only."""
    st = _load_profile(client, monkeypatch, "internship-only")
    session = st["session"]
    alone = sorted(_api_course_keys(client, session))
    assert alone == ["STA206-01"]
    assert not st["blocks"], "the internship alone carries no timetable"

    st = _load_profile(client, monkeypatch, "internship-courses")
    with_courses = sorted(_api_course_keys(client, session))
    assert "STA206-01" in with_courses
    assert with_courses != alone, "the two internship profiles must differ"
    assert st["blocks"], "the courses alongside the internship need a timetable"
    assert _api_served(client, session), "those courses should serve seances"
    assert _editor_served(st) == _api_served(client, session)


def _programs(client):
    res = client.get("/api/Etudiant/listeProgrammes")
    assert res.status_code == 200, res.text
    return res.json()["liste"]


def _sta206(client):
    return next(
        c
        for c in client.get("/api/Etudiant/listeCours").json()["liste"]
        if c["sigle"] == "STA206"
    )


def test_internship_adds_a_program_distinct_from_the_seeded_one(client, monkeypatch):
    """The seed already carries a completed co-op microprogram. The internship
    profiles enroll the student in the next one, which is a different program:
    same-code records would collapse for any client keying by code."""
    _load_profile(client, monkeypatch, "normal")
    base = {p["code"] for p in _programs(client)}

    for profile in ("internship-only", "internship-courses"):
        _load_profile(client, monkeypatch, profile)
        codes = [p["code"] for p in _programs(client)]
        assert len(codes) == len(set(codes)), f"{profile} serves a duplicate: {codes}"
        assert base <= set(codes), f"{profile} dropped a seeded program"
        added = set(codes) - base
        assert len(added) == 1, f"{profile} should add exactly one program: {added}"
        assert _sta206(client)["programmeEtudes"] == added.pop(), (
            f"{profile} should enroll STA206 under the program it adds"
        )
