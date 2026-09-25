import asyncio
import types
from collections import deque
from datetime import datetime

import pytest

from lib import call_log, failures

ENDPOINT = "/api/Etudiant/listeCours"
GRADES = "/api/Etudiant/listeElementsEvaluation?session=H2026&sigle=LOG430&groupe=02"


@pytest.fixture
def no_sleep(monkeypatch):
    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(failures, "asyncio", types.SimpleNamespace(sleep=fake_sleep))
    return slept


@pytest.fixture
def fixed_random(monkeypatch):
    def apply(value=0.0, randint=0):
        monkeypatch.setattr(
            failures,
            "random",
            types.SimpleNamespace(
                random=lambda: value, randint=lambda lo, hi: randint or lo
            ),
        )

    return apply


def entries(client, after=None):
    query = "" if after is None else f"?after={after}"
    return client.get(f"/admin/calls{query}").json()["entries"]


def only_call(client):
    logged = entries(client)
    assert len(logged) == 1
    return logged[0]


def test_an_api_call_is_logged_with_what_it_sent_back(client):
    response = client.get(GRADES)

    entry = only_call(client)
    assert entry["kind"] == "call"
    assert entry["endpoint"] == "listeElementsEvaluation"
    assert entry["path"] == "/api/Etudiant/listeElementsEvaluation"
    assert entry["params"] == {"session": "H2026", "sigle": "LOG430", "groupe": "02"}
    assert entry["status"] == 200
    assert entry["bytes"] == len(response.content)
    assert entry["durationMs"] >= 0
    assert entry["failures"] == []


def test_a_logged_call_is_stamped_with_a_utc_time_to_the_millisecond(client):
    client.get(ENDPOINT)

    stamp = datetime.fromisoformat(only_call(client)["time"])
    assert stamp.utcoffset().total_seconds() == 0
    assert stamp.microsecond % 1000 == 0


def test_the_duration_is_measured_around_the_whole_call(client, monkeypatch):
    ticks = iter([10.0, 10.25])
    monkeypatch.setattr(
        call_log, "time", types.SimpleNamespace(perf_counter=lambda: next(ticks))
    )

    client.get(ENDPOINT)

    assert only_call(client)["durationMs"] == 250.0


def test_the_size_counts_the_xml_body_when_xml_is_asked_for(client):
    response = client.get(ENDPOINT, headers={"Accept": "application/xml"})

    assert only_call(client)["bytes"] == len(response.content)


def test_a_refused_call_is_logged_with_its_status(client):
    client.get("/api/Etudiant/echo")

    entry = only_call(client)
    assert entry["endpoint"] == "echo"
    assert entry["status"] == 400


def test_a_call_to_an_unknown_endpoint_is_logged(client):
    client.get("/api/Etudiant/nexistePas")

    assert only_call(client)["status"] == 404


def test_calls_outside_the_api_are_not_logged(client, session):
    client.get("/editor")
    client.get(f"/editor/api/state?session={session}")
    client.get("/admin/failures")
    client.get("/docs")

    assert entries(client) == []


def test_a_failing_endpoint_is_logged_with_its_injection(client):
    client.patch("/admin/failures", json={"failEndpoints": ["listeCours"]})

    client.get(ENDPOINT)

    entry = only_call(client)
    assert entry["status"] == 503
    assert entry["failures"] == [{"kind": "fail"}]


def test_a_missing_header_is_logged_as_an_auth_injection(client):
    client.patch("/admin/failures", json={"authRequired": True})

    client.get(ENDPOINT)
    client.get(ENDPOINT, headers={"Authorization": "Bearer token"})

    refused, allowed = entries(client)
    assert (refused["status"], refused["failures"]) == (401, [{"kind": "auth"}])
    assert (allowed["status"], allowed["failures"]) == (200, [])


def test_a_timeout_is_logged_with_how_long_it_held_the_call(client, no_sleep):
    client.patch(
        "/admin/failures",
        json={"timeoutEndpoints": ["listeCours"], "timeoutDurationS": 30},
    )

    client.get(ENDPOINT)

    entry = only_call(client)
    assert entry["status"] == 504
    assert entry["failures"] == [{"kind": "timeout", "seconds": 30.0}]


def test_a_random_error_is_logged_only_on_the_call_it_hit(client, fixed_random):
    client.patch("/admin/failures", json={"errorRate": 0.5})

    fixed_random(value=0.49)
    client.get(ENDPOINT)
    fixed_random(value=0.51)
    client.get(ENDPOINT)

    hit, missed = entries(client)
    assert (hit["status"], hit["failures"]) == (500, [{"kind": "errorRate"}])
    assert (missed["status"], missed["failures"]) == (200, [])


def test_the_latency_drawn_for_a_call_is_logged(client, no_sleep, fixed_random):
    fixed_random(randint=300)
    client.patch("/admin/failures", json={"latencyMs": "100-800"})

    client.get(ENDPOINT)

    assert only_call(client)["failures"] == [{"kind": "latency", "ms": 300}]


def test_a_zero_latency_draw_is_not_an_injection(client, no_sleep, fixed_random):
    fixed_random(randint=0)
    client.patch("/admin/failures", json={"latencyMs": "0-800"})

    client.get(ENDPOINT)

    assert only_call(client)["failures"] == []
    assert no_sleep == []


def test_a_truncated_body_is_logged_with_the_size_actually_sent(client):
    client.patch("/admin/failures", json={"malformed": True})

    response = client.get(ENDPOINT)

    entry = only_call(client)
    assert entry["failures"] == [{"kind": "malformed"}]
    assert entry["bytes"] == len(response.content)


def test_every_injection_a_call_received_is_logged(client, no_sleep):
    client.patch("/admin/failures", json={"latencyMs": 250, "malformed": True})

    client.get(ENDPOINT)

    assert only_call(client)["failures"] == [
        {"kind": "latency", "ms": 250},
        {"kind": "malformed"},
    ]


def test_calls_are_listed_in_the_order_they_came_in(client):
    client.get(ENDPOINT)
    client.get("/api/Etudiant/helloWorld")

    logged = entries(client)
    assert [entry["endpoint"] for entry in logged] == ["listeCours", "helloWorld"]
    assert logged[0]["id"] < logged[1]["id"]


def test_a_marker_is_listed_between_the_calls_around_it(client):
    client.get(ENDPOINT)
    marker = client.post("/admin/calls/marker", json={"label": " notes ouvertes "})
    client.get(GRADES)

    assert marker.status_code == 200
    before, listed, after = entries(client)
    assert listed == marker.json()
    assert listed["kind"] == "marker"
    assert listed["label"] == "notes ouvertes"
    assert before["id"] < listed["id"] < after["id"]


@pytest.mark.parametrize("payload", [{}, {"label": ""}, {"label": "   "}, {"label": "x" * 121}])
def test_a_marker_needs_a_label(client, payload):
    response = client.post("/admin/calls/marker", json=payload)

    assert response.status_code == 422
    assert entries(client) == []


def test_only_newer_entries_are_sent_when_asked(client):
    client.get(ENDPOINT)
    first = only_call(client)
    client.get("/api/Etudiant/helloWorld")

    newer = entries(client, after=first["id"])

    assert [entry["endpoint"] for entry in newer] == ["helloWorld"]


def test_clearing_empties_the_log_without_reusing_ids(client):
    client.get(ENDPOINT)
    old = only_call(client)

    cleared = client.delete("/admin/calls").json()
    client.get(ENDPOINT)

    assert cleared["entries"] == []
    assert cleared["firstId"] > old["id"]
    assert only_call(client)["id"] == cleared["firstId"]


def test_the_log_reports_its_oldest_entry(client):
    client.get(ENDPOINT)
    client.get(ENDPOINT)

    body = client.get("/admin/calls?after=1000000").json()

    assert body["entries"] == []
    assert body["firstId"] == entries(client)[0]["id"]


def test_the_oldest_entries_make_way_once_the_log_is_full(client, monkeypatch):
    monkeypatch.setattr(call_log, "_entries", deque(maxlen=2))

    for path in (ENDPOINT, "/api/Etudiant/helloWorld", "/api/Etudiant/listeSessions"):
        client.get(path)

    body = client.get("/admin/calls").json()
    assert [entry["endpoint"] for entry in body["entries"]] == [
        "helloWorld",
        "listeSessions",
    ]
    assert body["firstId"] == body["entries"][0]["id"]


def run_through_log(app, path=ENDPOINT, query=b""):
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "path": path, "query_string": query, "headers": []}
    asyncio.run(call_log.CallLogMiddleware(app)(scope, receive, send))
    return sent


def test_a_call_is_listed_while_it_is_still_running():
    seen = []

    async def app(scope, receive, send):
        seen.append(dict(call_log.snapshot()["entries"][-1]))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    run_through_log(app, query=b"session=H2026")

    running = seen[0]
    assert running["params"] == {"session": "H2026"}
    assert running["status"] is None
    assert running["durationMs"] is None
    assert running["bytes"] is None
    done = call_log.snapshot()["entries"][-1]
    assert (done["status"], done["bytes"]) == (200, 2)


def test_a_body_sent_in_pieces_is_counted_whole():
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"abc", "more_body": True})
        await send({"type": "http.response.body", "body": b"de"})

    run_through_log(app)

    assert call_log.snapshot()["entries"][-1]["bytes"] == 5


def test_a_call_that_crashes_is_logged_as_a_server_error():
    async def app(scope, receive, send):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        run_through_log(app)

    entry = call_log.snapshot()["entries"][-1]
    assert (entry["status"], entry["bytes"]) == (500, 0)
