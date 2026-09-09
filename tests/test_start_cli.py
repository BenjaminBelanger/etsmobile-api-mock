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
    monkeypatch.setenv("MOCK_URL", "http://localhost:9999")
    assert env_for("--profile", "normal")["MOCK_URL"] == "http://localhost:9999"


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


def failure_env(*argv):
    overrides, _, _, _ = config(*argv)
    return {k: v for k, v in overrides.items() if k in start.FAILURE_ENV.values()}


def test_failure_preset_maps_to_the_failure_env_vars():
    assert failure_env("--failures", "flaky") == {
        "LATENCY_MS": "100-800",
        "ERROR_RATE": "0.3",
    }


def test_individual_failure_flags_map_to_env_vars():
    assert failure_env("--latency", "200-600", "--error-rate", "0.1") == {
        "LATENCY_MS": "200-600",
        "ERROR_RATE": "0.1",
    }


def test_repeatable_endpoint_flags_are_comma_joined():
    env = failure_env("--fail", "listeCoequipiers", "--fail", "lireEvaluationCours")
    assert env == {"FAIL_ENDPOINTS": "listeCoequipiers,lireEvaluationCours"}


def test_boolean_failure_flags_render_as_env_booleans():
    assert failure_env("--malformed") == {"MALFORMED": "true"}
    assert failure_env("--no-malformed") == {"MALFORMED": "false"}
    assert failure_env("--auth") == {"AUTH_REQUIRED": "true"}


def test_explicit_flags_override_the_preset():
    env = failure_env("--failures", "flaky", "--error-rate", "0.9")
    assert env == {"LATENCY_MS": "100-800", "ERROR_RATE": "0.9"}


def test_failure_label_appears_in_the_startup_summary():
    _, display, _, _ = config("--failures", "chaos")
    assert display == "normal + pannes « chaos »"

    _, display, _, _ = config("--latency", "500")
    assert display == "normal + pannes « personnalisées »"

    _, display, _, _ = config("--failures", "flaky", "--latency", "500")
    assert display == "normal + pannes « flaky + ajusté »"


@pytest.mark.parametrize(
    "argv",
    [
        ("--latency", "abc"),
        ("--latency", "-5"),
        ("--latency", "800-100"),
        ("--error-rate", "1.5"),
        ("--error-rate", "abc"),
        ("--timeout-duration", "-1"),
        ("--failures", "nope"),
    ],
)
def test_invalid_failure_values_are_rejected(argv):
    with pytest.raises(SystemExit) as exc:
        start._build_parser().parse_args(list(argv))
    assert exc.value.code == 2


def test_stale_failure_env_vars_do_not_leak_into_a_run(monkeypatch):
    monkeypatch.setenv("LATENCY_MS", "9999")
    monkeypatch.setenv("AUTH_REQUIRED", "true")

    env = start._build_env(config("--profile", "normal")[0])

    assert "LATENCY_MS" not in env
    assert "AUTH_REQUIRED" not in env


def test_every_failure_env_name_is_read_by_lib_failures():
    import pathlib

    source = pathlib.Path("lib/failures.py").read_text(encoding="utf-8")
    for name in start.FAILURE_ENV.values():
        assert name in source, f"{name} is not read by lib/failures.py"


def test_boot_presets_produce_the_same_config_as_the_runtime_presets(monkeypatch):
    from lib import failures

    for name, body in start._load_failure_presets().items():
        for var in start.FAILURE_ENV.values():
            monkeypatch.delenv(var, raising=False)
        for var, value in failure_env("--failures", name).items():
            monkeypatch.setenv(var, value)

        failures.reset_config()
        booted = failures.load_from_env().to_dict()

        failures.reset_config()
        runtime = failures.update_config(
            failures.FailureConfigUpdate(**body["config"])
        ).to_dict()

        assert booted == runtime, f"preset {name} differs at boot"

    failures.reset_config()


def test_the_help_epilog_documents_the_choices(capsys):
    parser = start._build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--help"])

    printed = capsys.readouterr().out
    for name in start._load_profiles():
        assert name in printed
    for name in start._load_scenarios():
        assert name in printed
    for name in start._load_failure_presets():
        assert name in printed
    for code, day in start.DAY_NAMES.items():
        assert f"{code}={day}" in printed


@pytest.mark.parametrize(
    "raw,expected",
    [("1", 1), ("3", 3), ("0", None), ("4", None), ("abc", None), ("", None)],
)
def test_menu_choices_are_validated(raw, expected):
    assert start._validate_menu_choice(raw, 3) == expected


@pytest.mark.parametrize("raw,expected", [("", 3), ("1", 1), ("5", 5)])
def test_a_prompted_number_falls_back_to_the_default(monkeypatch, raw, expected):
    answer(monkeypatch, raw)
    assert start._prompt_int("? ", 1, 5, 3) == expected


def test_a_prompted_number_is_asked_again_when_out_of_range(monkeypatch, capsys):
    left = answer(monkeypatch, "9", "abc", "2")

    assert start._prompt_int("? ", 1, 5, 3) == 2

    assert left == []
    assert capsys.readouterr().out.count("Entrée invalide") == 2


def test_a_prompted_number_falls_back_at_end_of_input(monkeypatch):
    def raise_eof(*_):
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)
    assert start._prompt_int("? ", 1, 5, 3) == 3


def test_prompted_days_keep_only_valid_codes(monkeypatch):
    answer(monkeypatch, "1,3,5")
    assert start._prompt_days() == ["1", "3", "5"]


def test_an_empty_day_answer_means_every_day(monkeypatch):
    answer(monkeypatch, "")
    assert start._prompt_days() is None


def test_prompted_days_are_asked_again_when_all_invalid(monkeypatch):
    left = answer(monkeypatch, "9,x", "2")
    assert start._prompt_days() == ["2"]
    assert left == []


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1", "morning"),
        ("2", "afternoon"),
        ("3", "evening"),
        ("1,3", "morning,evening"),
        ("", None),
        ("4", None),
    ],
)
def test_the_prompted_time_range_maps_to_the_generation_value(monkeypatch, raw, expected):
    answer(monkeypatch, raw)
    assert start._prompt_time_preference() == expected


def test_an_invalid_time_range_is_asked_again(monkeypatch):
    left = answer(monkeypatch, "9", "2")
    assert start._prompt_time_preference() == "afternoon"
    assert left == []


@pytest.mark.parametrize("raw,expected", [("", None), ("3", 3), ("15", 15)])
def test_the_prompted_semester_week_is_optional(monkeypatch, raw, expected):
    answer(monkeypatch, raw)
    assert start._prompt_semester_week() == expected


@pytest.mark.parametrize("raw", ["0", "16", "abc"])
def test_an_impossible_semester_week_is_asked_again(monkeypatch, raw):
    left = answer(monkeypatch, raw, "2")
    assert start._prompt_semester_week() == 2
    assert left == []


def test_the_custom_menu_summarizes_the_answers(monkeypatch, capsys):
    answer(monkeypatch, "2", "1,3", "1", "o")

    config = start._configure_custom()

    printed = capsys.readouterr().out
    assert config == {"count": 2, "allowedDays": ["1", "3"], "timePreference": "morning"}
    assert "Lundi, Mercredi" in printed
    assert "Matin" in printed


def test_the_custom_menu_can_be_refused(monkeypatch):
    answer(monkeypatch, "2", "", "4", "n")
    assert start._configure_custom() is None


def test_a_refused_custom_menu_starts_nothing(monkeypatch):
    answer(monkeypatch, "c", "", "", "3", "", "4", "n")
    assert start._config_from_menu() is None


def test_the_scenario_menu_defaults_to_none(monkeypatch):
    answer(monkeypatch, "")
    assert start._select_scenario() == "none"


def test_a_scenario_can_be_picked_from_the_menu(monkeypatch):
    answer(monkeypatch, "1")
    expected = [n for n in start._load_scenarios() if n != "none"][0]
    assert start._select_scenario() == expected


def test_an_invalid_scenario_choice_is_asked_again(monkeypatch):
    left = answer(monkeypatch, "99", "0")
    assert start._select_scenario() == "none"
    assert left == []


def test_the_menu_carries_a_scenario_and_a_week(monkeypatch):
    answer(monkeypatch, "1", "1", "4")

    overrides, display, scenario, week = start._config_from_menu()

    assert overrides["SCENARIO"] == scenario
    assert overrides["SEMESTER_WEEK"] == "4"
    assert display == list(start._load_profiles())[0]
    assert week == 4


def test_an_invalid_profile_choice_is_asked_again(monkeypatch):
    left = answer(monkeypatch, "99", "2", "", "")
    overrides, _, _, _ = start._config_from_menu()
    assert overrides == {"PROFILE": "semester-off"}
    assert left == []


def test_the_overrides_file_is_cleared_before_starting(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(start, "SEED", tmp_path)
    stale = tmp_path / start.OVERRIDES_FILENAME
    stale.write_text("{}", encoding="utf-8")

    start._clear_overrides()

    assert not stale.exists()
    assert "réinitialisée" in capsys.readouterr().out


def test_clearing_a_missing_overrides_file_is_quiet(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(start, "SEED", tmp_path)
    start._clear_overrides()
    assert capsys.readouterr().out == ""


def test_the_server_is_started_with_the_configured_environment(monkeypatch, tmp_path):
    monkeypatch.setattr(start, "SEED", tmp_path)
    monkeypatch.setattr(start, "_stop_existing_servers", lambda: None)
    runs = []
    monkeypatch.setattr(
        start.subprocess, "run", lambda cmd, env=None: runs.append((cmd, env))
    )

    start._start_server({"PROFILE": "semester-off"}, "semester-off", "none", None)

    command, env = runs[0]
    assert command[1:3] == ["-m", "uvicorn"]
    assert "main:app" in command
    assert "--port" in command and "8080" in command
    assert "--reload" in command
    assert command[command.index("--reload-exclude") + 1] == start.OVERRIDES_FILENAME
    assert env["PROFILE"] == "semester-off"


def test_starting_the_server_announces_the_configuration(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(start, "SEED", tmp_path)
    monkeypatch.setattr(start, "_stop_existing_servers", lambda: None)
    monkeypatch.setattr(start.subprocess, "run", lambda *a, **k: None)

    start._start_server({}, "normal", "friday-off", 3)

    printed = capsys.readouterr().out
    assert "normal" in printed
    assert "friday-off" in printed
    assert "semaine 3" in printed
    assert "http://localhost:8080/editor" in printed


def test_running_servers_are_stopped_first(monkeypatch):
    killed = []

    class Result:
        stdout = "123 456"

    monkeypatch.setattr(start.os, "name", "posix")
    monkeypatch.setattr(start.subprocess, "run", lambda *a, **k: Result())
    monkeypatch.setattr(start.os, "kill", lambda pid, sig: killed.append((pid, sig)))
    monkeypatch.setattr(start.os, "getpid", lambda: 456)

    start._stop_existing_servers()

    assert killed == [(123, start.signal.SIGTERM)]


def test_no_running_server_means_nothing_to_stop(monkeypatch):
    class Result:
        stdout = ""

    monkeypatch.setattr(start.subprocess, "run", lambda *a, **k: Result())
    monkeypatch.setattr(
        start.os, "kill", lambda *a: pytest.fail("nothing should be killed")
    )

    start._stop_existing_servers()


def test_a_failing_process_lookup_is_survivable(monkeypatch):
    def boom(*_args, **_kwargs):
        raise OSError("pgrep missing")

    monkeypatch.setattr(start.subprocess, "run", boom)
    monkeypatch.setattr(
        start.os, "kill", lambda *a: pytest.fail("nothing should be killed")
    )

    start._stop_existing_servers()


def test_a_process_that_refuses_to_die_is_survivable(monkeypatch):
    class Result:
        stdout = "123"

    def boom(*_args, **_kwargs):
        raise OSError("no such process")

    monkeypatch.setattr(start.os, "name", "posix")
    monkeypatch.setattr(start.subprocess, "run", lambda *a, **k: Result())
    monkeypatch.setattr(start.os, "kill", boom)
    monkeypatch.setattr(start.os, "getpid", lambda: 999)

    start._stop_existing_servers()
