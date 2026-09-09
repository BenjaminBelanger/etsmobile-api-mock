import json
import re

import pytest

from lib import i18n, schedule_editor
from lib._paths import ROOT

import start


def flat_keys(node, prefix=""):
    if isinstance(node, dict):
        keys = set()
        for name, value in node.items():
            keys |= flat_keys(value, f"{prefix}.{name}" if prefix else name)
        return keys
    return {prefix}


def catalog_of(code):
    path = i18n.LOCALES / f"{code}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_french_is_the_default_locale():
    assert i18n.DEFAULT_LOCALE == "fr"
    assert i18n.available_locales()[0] == "fr"
    assert set(i18n.available_locales()) == {"fr", "en"}


def test_every_locale_defines_the_same_keys():
    reference = flat_keys(catalog_of(i18n.DEFAULT_LOCALE))
    for code in i18n.available_locales():
        assert flat_keys(catalog_of(code)) == reference, f"{code} drifted"


def test_no_translation_is_left_empty():
    for code in i18n.available_locales():
        for key in flat_keys(catalog_of(code)):
            value = i18n.lookup(key, code)
            assert value not in ("", None), f"{code}:{key} is empty"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("en", "en"),
        ("EN", "en"),
        ("en_US.UTF-8", "en"),
        ("fr-CA", "fr"),
        ("de", None),
        ("", None),
        (None, None),
    ],
)
def test_locale_tags_are_normalized(raw, expected):
    assert i18n.normalize(raw) == expected


def test_an_explicit_locale_wins_over_the_environment(monkeypatch):
    monkeypatch.setenv(i18n.LANG_ENV, "fr")
    monkeypatch.setenv("LANG", "fr_CA.UTF-8")
    assert i18n.resolve("en") == "en"


def test_the_configured_locale_wins_over_the_system_locale(monkeypatch):
    monkeypatch.setenv(i18n.LANG_ENV, "en")
    monkeypatch.setenv("LANG", "fr_CA.UTF-8")
    assert i18n.resolve() == "en"


def test_the_system_locale_is_used_when_nothing_is_configured(monkeypatch):
    monkeypatch.delenv(i18n.LANG_ENV, raising=False)
    monkeypatch.setenv("LANG", "en_CA.UTF-8")
    assert i18n.resolve() == "en"


def test_french_is_the_last_resort(monkeypatch):
    for name in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE", i18n.LANG_ENV):
        monkeypatch.delenv(name, raising=False)
    assert i18n.resolve() == "fr"
    assert i18n.resolve("klingon") == "fr"


def test_the_os_locale_is_used_when_no_variable_is_set(monkeypatch):
    monkeypatch.setattr(i18n, "os_locale", lambda: "en-US")
    assert i18n.resolve() == "en"


def test_a_configured_variable_wins_over_the_os_locale(monkeypatch):
    monkeypatch.setattr(i18n, "os_locale", lambda: "en-US")
    monkeypatch.setenv("LANG", "fr_CA.UTF-8")
    assert i18n.resolve() == "fr"


def test_an_unsupported_os_locale_falls_back_to_french(monkeypatch):
    monkeypatch.setattr(i18n, "os_locale", lambda: "de-DE")
    assert i18n.resolve() == "fr"


def test_unsupported_locales_fall_back_to_the_system_locale(monkeypatch):
    monkeypatch.delenv(i18n.LANG_ENV, raising=False)
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    assert i18n.resolve("de") == "en"


def test_translations_interpolate_their_parameters():
    i18n.set_locale("en")
    assert i18n.t("editor.week_label", index=3) == "Week 3"
    i18n.set_locale("fr")
    assert i18n.t("editor.week_label", index=3) == "Semaine 3"


def test_an_unknown_key_returns_itself():
    assert i18n.t("cli.start.nope") == "cli.start.nope"


def test_describe_falls_back_to_the_provided_description():
    assert i18n.describe("cli.presets", "made-up", "seeded text") == "seeded text"
    assert i18n.describe("cli.presets", "flaky", "seeded text") != "seeded text"


@pytest.mark.parametrize("code", ["fr", "en"])
def test_every_locale_names_the_twelve_months(code):
    i18n.set_locale(code)
    assert len(i18n.values("editor.months")) == 12


@pytest.mark.parametrize(
    "argv,rest,lang",
    [
        (["list", "--lang", "en"], ["list"], "en"),
        (["--lang=fr", "custom"], ["custom"], "fr"),
        (["status"], ["status"], None),
        (["--lang"], ["--lang"], None),
    ],
)
def test_the_lang_flag_is_split_out_of_the_arguments(argv, rest, lang):
    assert i18n.split_lang_arg(argv) == (rest, lang)


def test_the_editor_state_is_localized(session):
    i18n.set_locale("en")
    days = schedule_editor.get_state(session)["meta"]["days"]
    assert [d["name"] for d in days][:2] == ["Monday", "Tuesday"]

    i18n.set_locale("fr")
    days = schedule_editor.get_state(session)["meta"]["days"]
    assert [d["name"] for d in days][:2] == ["Lundi", "Mardi"]


def test_editor_errors_are_localized(session):
    i18n.set_locale("en")
    with pytest.raises(schedule_editor.EditorError, match="Nothing to undo"):
        schedule_editor.undo(session)

    i18n.set_locale("fr")
    with pytest.raises(schedule_editor.EditorError, match="Rien à annuler"):
        schedule_editor.undo(session)


def test_the_mock_api_payload_stays_french_in_every_locale(session):
    i18n.set_locale("en")
    state = schedule_editor.get_state(session)
    blocks = [b for c in state["courses"] for b in c["blocks"]]
    assert blocks
    assert all(b["journee"] in schedule_editor.DAY_NAMES.values() for b in blocks)


def test_the_cli_help_is_translated():
    i18n.set_locale("en")
    assert "day codes:" in start._epilog(
        start._load_profiles(), start._load_scenarios(), start._load_failure_presets()
    )
    i18n.set_locale("fr")
    assert "codes de jour:" in start._epilog(
        start._load_profiles(), start._load_scenarios(), start._load_failure_presets()
    )


KEY_CALL = re.compile(r'i18n\.(?:t|values|lookup)\(\s*"([\w.]+)"')


def translated_sources():
    return [
        ROOT / "start.py",
        ROOT / "manage_seed.py",
        ROOT / "manage_failures.py",
        *sorted((ROOT / "lib").glob("*.py")),
    ]


def test_every_key_used_by_the_code_exists_in_every_locale():
    for path in translated_sources():
        for key in KEY_CALL.findall(path.read_text(encoding="utf-8")):
            for code in i18n.available_locales():
                assert i18n.lookup(key, code) is not None, f"{code}:{key} ({path.name})"
