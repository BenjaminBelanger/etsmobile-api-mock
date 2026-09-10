import json
import urllib.error

import pytest

import manage_failures
from lib import failures


@pytest.fixture
def http(monkeypatch):
    calls = []
    replies = {}

    def fake_http(method, path, payload=None):
        calls.append((method, path, payload))
        return replies.get((method, path), (200, {"ok": True}))

    monkeypatch.setattr(manage_failures, "_http", fake_http)
    fake_http.calls = calls
    fake_http.replies = replies
    return fake_http


def test_the_server_url_defaults_to_localhost(monkeypatch):
    monkeypatch.delenv("MOCK_URL", raising=False)
    assert manage_failures._server_url() == "http://localhost:8080"


def test_the_server_url_can_be_overridden(monkeypatch):
    monkeypatch.setenv("MOCK_URL", "http://elsewhere:9000/")
    assert manage_failures._server_url() == "http://elsewhere:9000"


def test_the_presets_are_loaded_from_the_seed_file():
    presets = manage_failures._load_presets()
    assert "flaky" in presets
    assert presets["flaky"]["config"] == {"latencyMs": "100-800", "errorRate": 0.3}


def test_listing_presets_prints_every_name(capsys):
    assert manage_failures.cmd_list() == 0

    printed = capsys.readouterr().out
    for name in manage_failures._load_presets():
        assert name in printed


def test_listing_survives_an_empty_preset_file(monkeypatch, capsys):
    monkeypatch.setattr(manage_failures, "_load_presets", lambda: {})
    assert manage_failures.cmd_list() == 0
    assert "aucun préréglage défini" in capsys.readouterr().out


def test_status_asks_the_server(http, capsys):
    http.replies[("GET", "/admin/failures")] = (200, {"errorRate": 0.3})

    assert manage_failures.cmd_status() == 0

    assert http.calls == [("GET", "/admin/failures", None)]
    assert json.loads(capsys.readouterr().out) == {"errorRate": 0.3}


def test_reset_clears_the_config(http, capsys):
    assert manage_failures.cmd_reset() == 0

    assert http.calls == [("DELETE", "/admin/failures", None)]
    assert "(réinitialisé)" in capsys.readouterr().err


def test_a_preset_is_applied_on_a_clean_slate(http):
    assert manage_failures.cmd_apply_preset("flaky") == 0

    assert http.calls == [
        ("DELETE", "/admin/failures", None),
        ("PATCH", "/admin/failures", {"latencyMs": "100-800", "errorRate": 0.3}),
    ]


def test_an_unknown_preset_is_refused(http, capsys):
    assert manage_failures.cmd_apply_preset("inconnu") == 1

    assert http.calls == []
    assert "préréglage inconnu" in capsys.readouterr().err


def test_a_custom_config_is_built_from_the_flags(http):
    code = manage_failures.cmd_custom(
        [
            "--latency",
            "100-500",
            "--error-rate",
            "0.5",
            "--fail",
            "listeCoequipiers",
            "--fail",
            "listeCours",
            "--timeout",
            "echo",
            "--timeout-duration",
            "10",
            "--malformed",
            "--auth",
        ]
    )

    assert code == 0
    assert http.calls[-1] == (
        "PATCH",
        "/admin/failures",
        {
            "latencyMs": "100-500",
            "errorRate": 0.5,
            "failEndpoints": ["listeCoequipiers", "listeCours"],
            "timeoutEndpoints": ["echo"],
            "timeoutDurationS": 10.0,
            "malformed": True,
            "authRequired": True,
        },
    )


def test_the_negative_form_of_a_boolean_flag_is_sent(http):
    manage_failures.cmd_custom(["--no-malformed", "--no-auth"])
    assert http.calls[-1][2] == {"malformed": False, "authRequired": False}


def test_a_custom_config_resets_before_patching(http):
    manage_failures.cmd_custom(["--latency", "200"])
    assert [call[0] for call in http.calls] == ["DELETE", "PATCH"]


def test_a_custom_config_needs_at_least_one_flag(http):
    with pytest.raises(SystemExit) as exc:
        manage_failures.cmd_custom([])
    assert exc.value.code == 2
    assert http.calls == []


def test_flags_that_were_not_given_are_left_out():
    parser = manage_failures._build_custom_parser()
    args = parser.parse_args(["--latency", "200"])
    assert manage_failures._custom_args_to_config(args) == {"latencyMs": "200"}


def test_an_error_from_the_server_is_reported(http, capsys):
    http.replies[("GET", "/admin/failures")] = (500, "boom")

    assert manage_failures.cmd_status() == 1
    assert "Erreur 500" in capsys.readouterr().err


def test_a_plain_text_body_is_printed_as_is(capsys):
    assert manage_failures._print_response(200, "plain") == 0
    assert capsys.readouterr().out.strip() == "plain"


@pytest.mark.parametrize("argv", [[], ["-h"], ["--help"], ["help"]])
def test_the_usage_is_printed_without_a_command(argv, capsys):
    assert manage_failures.main(argv) == 0
    assert "Usage: python manage_failures.py" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv,expected",
    [
        (["list"], []),
        (["status"], [("GET", "/admin/failures", None)]),
        (["reset"], [("DELETE", "/admin/failures", None)]),
        (["off"], [("DELETE", "/admin/failures", None)]),
    ],
)
def test_commands_are_dispatched(http, argv, expected):
    assert manage_failures.main(argv) == 0
    assert http.calls == expected


def test_a_bare_name_is_treated_as_a_preset(http):
    assert manage_failures.main(["outage"]) == 0
    assert http.calls[-1] == (
        "PATCH",
        "/admin/failures",
        {"failEndpoints": ["*"]},
    )


def test_an_unreachable_server_is_reported(monkeypatch, capsys):
    def boom(*_args, **_kwargs):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(manage_failures, "_http", boom)

    assert manage_failures.main(["status"]) == 2
    assert "serveur mock injoignable" in capsys.readouterr().err


def test_every_preset_is_a_valid_runtime_patch():
    for name, body in manage_failures._load_presets().items():
        failures.reset_config()
        config = failures.update_config(
            failures.FailureConfigUpdate(**body["config"])
        )
        assert not config.is_default(), f"preset {name} changes nothing"
    failures.reset_config()


def test_the_http_helper_talks_json(monkeypatch):
    sent = {}

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b'{"ok": true}'

    def fake_urlopen(request, timeout=None):
        sent["url"] = request.full_url
        sent["method"] = request.get_method()
        sent["body"] = request.data
        sent["type"] = request.get_header("Content-type")
        return Response()

    monkeypatch.setattr(manage_failures.urllib.request, "urlopen", fake_urlopen)

    status, body = manage_failures._http("PATCH", "/admin/failures", {"errorRate": 0.5})

    assert (status, body) == (200, {"ok": True})
    assert sent["method"] == "PATCH"
    assert sent["url"].endswith("/admin/failures")
    assert json.loads(sent["body"]) == {"errorRate": 0.5}
    assert sent["type"] == "application/json"


def test_an_http_error_body_is_read_back(monkeypatch):
    import io

    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url, 400, "Bad Request", {}, io.BytesIO(b'{"error": "nope"}')
        )

    monkeypatch.setattr(manage_failures.urllib.request, "urlopen", fake_urlopen)

    assert manage_failures._http("GET", "/admin/failures") == (400, {"error": "nope"})
