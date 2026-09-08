import pytest

import start


def config(*argv):
    args = start._build_parser().parse_args(list(argv))
    return start._config_from_args(args)


def env_for(*argv):
    overrides, _, _, _ = config(*argv)
    return start._build_env(overrides)


def test_profile_flag_sets_the_profile_env_var():
    overrides, display, scenario, week = config("--profile", "semester-off")
    assert overrides == {"PROFILE": "semester-off"}
    assert display == "semester-off"
    assert scenario == "none"
    assert week is None


def test_generation_flags_map_to_the_generation_env_vars():
    overrides, display, _, _ = config(
        "--courses", "2", "--days", "1,3,5", "--time", "morning,evening"
    )
    assert overrides == {
        "COURSE_COUNT": "2",
        "SCHEDULE_DAYS": "1,3,5",
        "TIME_PREFERENCE": "morning,evening",
    }
    assert display == "normal (personnalisé)"


def test_generation_flags_combine_with_an_explicit_profile():
    overrides, display, _, _ = config("--profile", "generated-busy", "--courses", "2")
    assert overrides == {"PROFILE": "generated-busy", "COURSE_COUNT": "2"}
    assert display == "generated-busy (personnalisé)"


def test_scenario_none_is_left_unset():
    overrides, _, scenario, _ = config("--scenario", "none")
    assert "SCENARIO" not in overrides
    assert scenario == "none"


def test_semester_week_is_passed_through():
    overrides, _, _, week = config("--semester-week", "3")
    assert overrides == {"SEMESTER_WEEK": "3"}
    assert week == 3


@pytest.mark.parametrize(
    "argv",
    [
        ("--days", "9"),
        ("--days", "1,9"),
        ("--days", ""),
        ("--courses", "0"),
        ("--courses", "6"),
        ("--courses", "abc"),
        ("--time", "lunch"),
        ("--semester-week", "0"),
        ("--semester-week", "16"),
        ("--profile", "nope"),
        ("--scenario", "nope"),
    ],
)
def test_invalid_values_are_rejected_before_the_server_starts(argv):
    with pytest.raises(SystemExit) as exc:
        start._build_parser().parse_args(list(argv))
    assert exc.value.code == 2


def test_stale_managed_env_vars_do_not_leak_into_a_run(monkeypatch):
    for name in start.MANAGED_ENV:
        monkeypatch.setenv(name, "stale")

    env = env_for("--profile", "semester-off")

    assert env["PROFILE"] == "semester-off"
    for name in start.MANAGED_ENV:
        if name != "PROFILE":
            assert name not in env, f"{name} leaked from the shell environment"


def test_unmanaged_env_vars_are_passed_through(monkeypatch):
    monkeypatch.setenv("LATENCY_MS", "200-600")
    assert env_for("--profile", "normal")["LATENCY_MS"] == "200-600"


def test_no_flags_falls_back_to_the_interactive_menu(monkeypatch):
    calls = []
    monkeypatch.setattr(start, "_config_from_menu", lambda: calls.append("menu") or None)
    monkeypatch.setattr(start, "_start_server", lambda *a: calls.append("start"))

    start.main([])

    assert calls == ["menu"]


def test_flags_skip_the_interactive_menu(monkeypatch):
    started = []
    monkeypatch.setattr(
        start, "_config_from_menu", lambda: pytest.fail("menu should be skipped")
    )
    monkeypatch.setattr(start, "_start_server", lambda *a: started.append(a))

    start.main(["--profile", "semester-off"])

    assert started == [({"PROFILE": "semester-off"}, "semester-off", "none", None)]


def answer(monkeypatch, *responses):
    queue = list(responses)
    monkeypatch.setattr("builtins.input", lambda *_: queue.pop(0))
    return queue


def test_menu_path_builds_the_same_overrides_as_the_flags(monkeypatch):
    left = answer(monkeypatch, "2", "", "")

    overrides, display, scenario, week = start._config_from_menu()

    assert left == []
    assert overrides == {"PROFILE": "semester-off"}
    assert (display, scenario, week) == ("semester-off", "none", None)


def test_menu_custom_path_sets_the_generation_vars(monkeypatch):
    left = answer(monkeypatch, "c", "", "", "2", "1,3", "1", "")

    overrides, display, _, _ = start._config_from_menu()

    assert left == []
    assert overrides == {
        "PROFILE": "normal",
        "COURSE_COUNT": "2",
        "SCHEDULE_DAYS": "1,3",
        "TIME_PREFERENCE": "morning",
    }
    assert display == "Personnalisé"


def test_menu_quit_starts_nothing(monkeypatch):
    answer(monkeypatch, "0")
    assert start._config_from_menu() is None
