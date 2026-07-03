"""Tests for failure injection (middleware) and the /admin/failures endpoints."""

from conftest import api

ADMIN = "/admin/failures"


def _patch(client, **fields):
    res = client.patch(ADMIN, json=fields)
    assert res.status_code == 200, res.text
    return res.json()


# --- Admin endpoint -----------------------------------------------------------


def test_admin_default_config(client):
    res = client.get(ADMIN)
    assert res.status_code == 200
    cfg = res.json()
    assert cfg["errorRate"] == 0.0
    assert cfg["failEndpoints"] == []
    assert cfg["authRequired"] is False


def test_admin_patch_and_reset(client):
    cfg = _patch(client, errorRate=0.5, failEndpoints=["listeCoequipiers"])
    assert cfg["errorRate"] == 0.5
    assert cfg["failEndpoints"] == ["listeCoequipiers"]

    reset = client.delete(ADMIN).json()
    assert reset["errorRate"] == 0.0
    assert reset["failEndpoints"] == []


def test_admin_patch_rejects_unknown_field(client):
    res = client.patch(ADMIN, json={"bogus": 1})
    assert res.status_code == 422


def test_admin_patch_rejects_bad_error_rate(client):
    res = client.patch(ADMIN, json={"errorRate": 5})
    assert res.status_code == 422


def test_latency_range_string_roundtrips(client):
    cfg = _patch(client, latencyMs="100-500")
    assert cfg["latencyMs"] == "100-500"


# --- Middleware behaviour -----------------------------------------------------


def test_fail_endpoints_return_503(client):
    _patch(client, failEndpoints=["helloWorld"])
    assert api(client, "helloWorld").status_code == 503
    # A different endpoint is unaffected
    assert api(client, "listeCours").status_code == 200


def test_wildcard_fails_all_api(client):
    _patch(client, failEndpoints=["*"])
    assert api(client, "helloWorld").status_code == 503
    assert api(client, "listeCours").status_code == 503


def test_error_rate_one_always_500(client):
    _patch(client, errorRate=1.0)
    assert api(client, "helloWorld").status_code == 500


def test_timeout_endpoint_returns_504(client):
    _patch(client, timeoutEndpoints=["helloWorld"], timeoutDurationS=0.01)
    res = api(client, "helloWorld")
    assert res.status_code == 504


def test_auth_required_blocks_without_header(client):
    _patch(client, authRequired=True)
    assert api(client, "helloWorld").status_code == 401
    res = client.get(
        "/api/Etudiant/helloWorld", headers={"Authorization": "Bearer x"}
    )
    assert res.status_code == 200


def test_malformed_truncates_body(client):
    full = api(client, "listeCours").content
    _patch(client, malformed=True)
    truncated = api(client, "listeCours").content
    assert len(truncated) < len(full)


def test_latency_does_not_break_response(client):
    _patch(client, latencyMs=10)
    assert api(client, "helloWorld").status_code == 200


def test_failures_do_not_affect_non_api_routes(client):
    _patch(client, failEndpoints=["*"], authRequired=True)
    # The editor and admin routes live outside /api and stay reachable
    assert client.get("/editor/api/state", params={"session": ""}).status_code == 200
    assert client.get(ADMIN).status_code == 200
