import types

import pytest

from lib import failures
from lib.failures import FailureConfig, FailureConfigUpdate

ENDPOINT = "/api/Etudiant/listeCours"


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


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, (0, 0)),
        ("", (0, 0)),
        ("   ", (0, 0)),
        (0, (0, 0)),
        (500, (500, 500)),
        ("500", (500, 500)),
        (" 500 ", (500, 500)),
        ("100-800", (100, 800)),
        ("0-0", (0, 0)),
    ],
)
def test_latency_is_parsed_into_a_range(raw, expected):
    assert failures.parse_latency(raw) == expected


@pytest.mark.parametrize("raw", [-1, "-5", "800-100", "abc", "100-abc"])
def test_an_impossible_latency_is_rejected(raw):
    with pytest.raises(ValueError):
        failures.parse_latency(raw)


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, set()),
        ("", set()),
        ("a,b", {"a", "b"}),
        (" a , b ", {"a", "b"}),
        ("a,,b,", {"a", "b"}),
        (["a", "b"], {"a", "b"}),
        (("a", " "), {"a"}),
        ({"a"}, {"a"}),
        ("*", {"*"}),
    ],
)
def test_endpoint_sets_are_parsed_from_strings_and_lists(raw, expected):
    assert failures.parse_endpoint_set(raw) == expected


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/api/Etudiant/listeCours", "listeCours"),
        ("/api/Etudiant/listeCours/extra", "listeCours"),
        ("/api/Etudiant/", ""),
        ("/admin/failures", "admin"),
        ("/editor", "editor"),
    ],
)
def test_the_endpoint_name_comes_from_the_path(path, expected):
    assert failures.endpoint_name(path) == expected


def test_a_fresh_config_is_the_default_one():
    assert FailureConfig().is_default()
    assert not FailureConfig(error_rate=0.1).is_default()
    assert not FailureConfig(malformed=True).is_default()
    assert not FailureConfig(timeout_duration_s=5.0).is_default()
    assert not FailureConfig(fail_endpoints={"listeCours"}).is_default()


def test_a_config_renders_a_fixed_latency_as_a_number_and_a_range_as_text():
    assert FailureConfig(latency_ms=(500, 500)).to_dict()["latencyMs"] == 500
    assert FailureConfig(latency_ms=(100, 800)).to_dict()["latencyMs"] == "100-800"


def test_a_config_renders_endpoint_sets_sorted():
    config = FailureConfig(fail_endpoints={"b", "a"}, timeout_endpoints={"d", "c"})
    rendered = config.to_dict()
    assert rendered["failEndpoints"] == ["a", "b"]
    assert rendered["timeoutEndpoints"] == ["c", "d"]


def test_the_boot_config_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("LATENCY_MS", "100-800")
    monkeypatch.setenv("ERROR_RATE", "0.25")
    monkeypatch.setenv("FAIL_ENDPOINTS", "listeCours,echo")
    monkeypatch.setenv("TIMEOUT_ENDPOINTS", "*")
    monkeypatch.setenv("TIMEOUT_DURATION_S", "12.5")
    monkeypatch.setenv("MALFORMED", "true")
    monkeypatch.setenv("AUTH_REQUIRED", "yes")

    config = failures.load_from_env()

    assert config.latency_ms == (100, 800)
    assert config.error_rate == 0.25
    assert config.fail_endpoints == {"listeCours", "echo"}
    assert config.timeout_endpoints == {"*"}
    assert config.timeout_duration_s == 12.5
    assert config.malformed is True
    assert config.auth_required is True


def test_an_empty_environment_boots_the_default_config(monkeypatch):
    for name in (
        "LATENCY_MS",
        "ERROR_RATE",
        "FAIL_ENDPOINTS",
        "TIMEOUT_ENDPOINTS",
        "TIMEOUT_DURATION_S",
        "MALFORMED",
        "AUTH_REQUIRED",
    ):
        monkeypatch.delenv(name, raising=False)

    assert failures.load_from_env().is_default()


@pytest.mark.parametrize(
    "name,value",
    [
        ("LATENCY_MS", "abc"),
        ("ERROR_RATE", "abc"),
        ("ERROR_RATE", "1.5"),
        ("ERROR_RATE", "-0.5"),
        ("TIMEOUT_DURATION_S", "abc"),
        ("TIMEOUT_DURATION_S", "-1"),
    ],
)
def test_a_broken_environment_value_falls_back_to_the_default(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    config = failures.load_from_env()
    assert config.is_default()


@pytest.mark.parametrize(
    "raw,expected", [("1", True), ("on", True), ("YES", True), ("0", False), ("", False)]
)
def test_boolean_environment_values_are_read_loosely(monkeypatch, raw, expected):
    monkeypatch.setenv("MALFORMED", raw)
    assert failures.load_from_env().malformed is expected


def test_a_patch_only_touches_the_fields_it_carries():
    failures.update_config(FailureConfigUpdate(latencyMs=250))
    failures.update_config(FailureConfigUpdate(malformed=True))

    config = failures.get_config()
    assert config.latency_ms == (250, 250)
    assert config.malformed is True
    assert config.error_rate == 0.0


def test_a_patch_can_clear_an_endpoint_list():
    failures.update_config(FailureConfigUpdate(failEndpoints=["listeCours"]))
    failures.update_config(FailureConfigUpdate(failEndpoints=[]))
    assert failures.get_config().fail_endpoints == set()


def test_a_broken_latency_patch_is_rejected():
    with pytest.raises(ValueError):
        failures.update_config(FailureConfigUpdate(latencyMs="800-100"))


@pytest.mark.parametrize(
    "payload",
    [
        {"errorRate": 1.5},
        {"errorRate": -0.1},
        {"timeoutDurationS": -1},
        {"inconnu": True},
    ],
)
def test_an_out_of_range_patch_is_refused_by_the_model(payload):
    with pytest.raises(Exception):
        FailureConfigUpdate(**payload)


def test_the_admin_endpoint_reports_the_current_config(client):
    body = client.get("/admin/failures").json()
    assert body == FailureConfig().to_dict()


def test_the_admin_endpoint_patches_and_resets(client):
    patched = client.patch(
        "/admin/failures", json={"latencyMs": "100-500", "errorRate": 0.2}
    ).json()
    assert patched["latencyMs"] == "100-500"
    assert patched["errorRate"] == 0.2

    assert client.get("/admin/failures").json() == patched

    assert client.delete("/admin/failures").json() == FailureConfig().to_dict()
    assert failures.get_config().is_default()


def test_the_admin_endpoint_rejects_a_broken_latency(client):
    response = client.patch("/admin/failures", json={"latencyMs": "800-100"})
    assert response.status_code == 400
    assert "invalid latency range" in response.json()["error"]


def test_the_admin_endpoint_rejects_unknown_fields(client):
    assert client.patch("/admin/failures", json={"inconnu": 1}).status_code == 422


def test_a_required_header_turns_api_calls_into_401s(client):
    client.patch("/admin/failures", json={"authRequired": True})

    response = client.get(ENDPOINT)
    assert response.status_code == 401
    assert response.json() == {"error": "Authentification requise."}

    ok = client.get(ENDPOINT, headers={"Authorization": "Bearer token"})
    assert ok.status_code == 200


def test_a_blank_authorization_header_does_not_count(client):
    client.patch("/admin/failures", json={"authRequired": True})
    assert client.get(ENDPOINT, headers={"Authorization": "   "}).status_code == 401


def test_a_failing_endpoint_returns_503(client):
    client.patch("/admin/failures", json={"failEndpoints": ["listeCours"]})

    response = client.get(ENDPOINT)
    assert response.status_code == 503
    assert "listeCours" in response.json()["error"]
    assert client.get("/api/Etudiant/helloWorld").status_code == 200


def test_the_wildcard_fails_every_api_endpoint(client):
    client.patch("/admin/failures", json={"failEndpoints": ["*"]})
    assert client.get(ENDPOINT).status_code == 503
    assert client.get("/api/Etudiant/helloWorld").status_code == 503


def test_failure_injection_leaves_the_editor_and_admin_alone(client, session):
    client.patch("/admin/failures", json={"failEndpoints": ["*"], "authRequired": True})

    assert client.get("/admin/failures").status_code == 200
    assert client.get(f"/editor/api/state?session={session}").status_code == 200
    assert client.get("/editor").status_code == 200


def test_a_timeout_endpoint_sleeps_then_returns_504(client, no_sleep):
    client.patch(
        "/admin/failures",
        json={"timeoutEndpoints": ["listeCours"], "timeoutDurationS": 30},
    )

    response = client.get(ENDPOINT)

    assert response.status_code == 504
    assert "listeCours" in response.json()["error"]
    assert no_sleep == [30.0]


def test_the_error_rate_decides_whether_a_call_blows_up(client, fixed_random):
    client.patch("/admin/failures", json={"errorRate": 0.5})

    fixed_random(value=0.49)
    assert client.get(ENDPOINT).status_code == 500

    fixed_random(value=0.51)
    assert client.get(ENDPOINT).status_code == 200


def test_a_zero_error_rate_never_fires(client, fixed_random):
    fixed_random(value=0.0)
    assert client.get(ENDPOINT).status_code == 200


def test_latency_is_slept_before_the_response(client, no_sleep, fixed_random):
    fixed_random(randint=300)
    client.patch("/admin/failures", json={"latencyMs": "100-800"})

    assert client.get(ENDPOINT).status_code == 200
    assert no_sleep == [0.3]


def test_a_fixed_latency_needs_no_draw(client, no_sleep):
    client.patch("/admin/failures", json={"latencyMs": 250})
    client.get(ENDPOINT)
    assert no_sleep == [0.25]


def test_no_latency_means_no_sleep(client, no_sleep):
    client.get(ENDPOINT)
    assert no_sleep == []


def test_malformed_truncates_a_successful_body_in_half(client):
    whole = client.get(ENDPOINT).content

    client.patch("/admin/failures", json={"malformed": True})
    truncated = client.get(ENDPOINT).content

    assert truncated == whole[: len(whole) // 2]
    assert len(truncated) < len(whole)


def test_malformed_leaves_error_bodies_alone(client):
    client.patch("/admin/failures", json={"malformed": True})

    response = client.get("/api/Etudiant/echo")

    assert response.status_code == 400
    assert response.json() == {
        "error": "Un des paramètres obligatoires est absent de la requête."
    }


def test_malformed_announces_the_length_it_actually_sends(client):
    client.patch("/admin/failures", json={"malformed": True})
    response = client.get(ENDPOINT)
    assert int(response.headers["content-length"]) == len(response.content)


def test_the_startup_config_reaches_the_middleware(client, monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    failures.load_from_env()

    assert client.get(ENDPOINT).status_code == 401
