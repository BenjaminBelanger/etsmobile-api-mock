import pytest
from fastapi import HTTPException

from lib import responses


class Request:
    def __init__(self, accept=None):
        self.headers = {} if accept is None else {"accept": accept}


@pytest.mark.parametrize(
    "accept,expected",
    [
        (None, False),
        ("", False),
        ("application/json", False),
        ("*/*", False),
        ("application/xml", True),
        ("text/xml", True),
        ("application/xml, text/plain", True),
        ("text/html, application/xml;q=0.9", True),
    ],
)
def test_xml_is_served_only_when_asked_for(accept, expected):
    assert responses.wants_xml(Request(accept)) is expected


@pytest.mark.parametrize(
    "params",
    [
        {"session": None},
        {"session": ""},
        {"session": "H2026", "sigle": None},
        {"session": "H2026", "sigle": ""},
    ],
)
def test_a_missing_parameter_is_reported_as_a_400(params):
    with pytest.raises(HTTPException) as exc:
        responses.require(**params)

    assert exc.value.status_code == 400
    assert exc.value.detail == (
        "Un des paramètres obligatoires est absent de la requête."
    )


def test_complete_parameters_pass():
    assert responses.require(session="H2026", sigle="LOG430") is None


def test_no_parameters_at_all_pass():
    assert responses.require() is None


@pytest.mark.parametrize(
    "raw,expected",
    [("1", True), ("true", True), ("YES", True), ("on", True), (" true ", True),
     ("0", False), ("false", False), ("", False), ("maybe", False)],
)
def test_boolean_environment_values(monkeypatch, raw, expected):
    from lib import _env

    monkeypatch.setenv("SOME_FLAG", raw)
    assert _env.env_bool("SOME_FLAG") is expected


def test_a_missing_environment_flag_is_false(monkeypatch):
    from lib import _env

    monkeypatch.delenv("SOME_FLAG", raising=False)
    assert _env.env_bool("SOME_FLAG") is False
