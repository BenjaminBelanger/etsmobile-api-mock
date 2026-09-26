import ctypes
import os
import signal
import subprocess
from pathlib import Path

import pytest

import start
from lib import flutter_app

URLS_SOURCE = """class Urls {
  static const String signetsAPI = "etsmobileapi.etsmtl.ca";
}
"""

REQUEST_BUILDER_SOURCE = """class RequestBuilderService {
  Uri build(String endpoint) {
    final uri = Uri.https(Urls.signetsAPI, endpoint, queryParameters);
    return uri;
  }
}
"""

LOCATOR_SOURCE = """void setupLocator() {
  locator.registerLazySingleton(() => SignetsClient(dio));
}
"""

SOURCES = {
    flutter_app.URLS: URLS_SOURCE,
    flutter_app.REQUEST_BUILDER: REQUEST_BUILDER_SOURCE,
    flutter_app.LOCATOR: LOCATOR_SOURCE,
}

CLOSE_SIGNALS = [name for name in start.CLOSE_SIGNALS if hasattr(signal, name)]


def git(path, *args):
    return subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        text=True,
        check=True,
    )


def read(app, name):
    return (app / name).read_text(encoding="utf-8")


def write_sources(path, sources=SOURCES):
    for name, source in sources.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.encode("utf-8"))
    return path


def commit(path):
    git(path.parent, "init", str(path))
    git(path, "config", "user.email", "mock@example.com")
    git(path, "config", "user.name", "Mock")
    git(path, "config", "core.autocrlf", "false")
    git(path, "add", ".")
    git(path, "commit", "-m", "app")


def assert_untouched(app):
    for name, source in SOURCES.items():
        assert read(app, name) == source


def record_urls(monkeypatch, app):
    seen = []
    monkeypatch.setattr(
        start, "_start_server", lambda *a: seen.append(read(app, flutter_app.URLS))
    )
    return seen


def refuse_to_start(monkeypatch):
    monkeypatch.setattr(
        start, "_start_server", lambda *a: pytest.fail("server should not start")
    )


@pytest.fixture
def app(tmp_path):
    return write_sources(tmp_path / "Notre-Dame")


@pytest.fixture
def saved_app(app):
    flutter_app.save_config({"app": str(app)})
    return app


def test_platform_decides_the_host():
    assert flutter_app.resolve_host(None, None) == "10.0.2.2:8080"
    assert flutter_app.resolve_host("android", None) == "10.0.2.2:8080"
    assert flutter_app.resolve_host("ios", None) == "localhost:8080"


@pytest.mark.parametrize(
    "host, expected",
    [
        ("192.168.1.10", "192.168.1.10:8080"),
        ("192.168.1.10:9000", "192.168.1.10:9000"),
        ("my-laptop.local", "my-laptop.local:8080"),
        ("[fe80::1]", "[fe80::1]:8080"),
        ("[::1]:9000", "[::1]:9000"),
    ],
)
def test_explicit_host_wins_and_gets_the_server_port(host, expected):
    assert flutter_app.resolve_host("ios", host) == expected


@pytest.mark.parametrize(
    "host",
    [
        "http://192.168.1.10",
        '192.168.1.10:8080"',
        "my'laptop",
        "192.168.1.10/api",
        "fe80::1",
        "",
        "192.168.1.10:0",
        "192.168.1.10:65536",
    ],
)
def test_a_host_that_would_break_the_dart_files_is_rejected(host):
    with pytest.raises(flutter_app.AppError):
        flutter_app.resolve_host(None, host)


def test_an_invalid_host_flag_is_rejected_before_the_menus(capsys):
    with pytest.raises(SystemExit):
        start._build_parser().parse_args(["--host", "http://192.168.1.10"])

    assert "sans http://" in capsys.readouterr().err


def test_an_invalid_saved_host_does_not_start_the_server(saved_app, monkeypatch):
    flutter_app.save_config({"app": str(saved_app), "host": "http://192.168.1.10"})
    refuse_to_start(monkeypatch)

    start.main(["--profile", "normal"])

    assert_untouched(saved_app)


def test_base_url_follows_the_api_router_prefix():
    from lib.routes import router

    assert flutter_app.base_url("host:1") == f"http://host:1{router.prefix}/"


def test_configure_rewrites_the_three_files(app):
    patched = flutter_app.configure(app, "10.0.2.2:8080", "run")

    assert patched == list(flutter_app.TARGETS)
    assert 'signetsAPI = "10.0.2.2:8080"' in read(app, flutter_app.URLS)
    assert "Uri.http(" in read(app, flutter_app.REQUEST_BUILDER)
    assert "Uri.https(" not in read(app, flutter_app.REQUEST_BUILDER)
    assert (
        "SignetsClient(dio, baseUrl: 'http://10.0.2.2:8080/api/Etudiant/')"
        in read(app, flutter_app.LOCATOR)
    )


def test_revert_restores_every_patched_file(app):
    flutter_app.configure(app, "localhost:8080", "run")

    assert flutter_app.revert(app) == (list(flutter_app.TARGETS), [])
    assert_untouched(app)
    assert "patched" not in flutter_app.load_config()
    with pytest.raises(flutter_app.AppError):
        flutter_app.revert(app)


def test_configure_reruns_over_a_run_that_did_not_revert(app):
    flutter_app.configure(app, "10.0.2.2:8080", "crashed")
    flutter_app.configure(app, "localhost:8080", "next")

    assert 'signetsAPI = "localhost:8080"' in read(app, flutter_app.URLS)
    assert (
        "SignetsClient(dio, baseUrl: 'http://localhost:8080/api/Etudiant/')"
        in read(app, flutter_app.LOCATOR)
    )

    flutter_app.revert(app)
    assert_untouched(app)


@pytest.mark.parametrize(
    "name, production, local",
    [
        (flutter_app.URLS, "etsmobileapi.etsmtl.ca", "192.168.1.10:8080"),
        (flutter_app.REQUEST_BUILDER, "Uri.https(", "Uri.http("),
        (
            flutter_app.LOCATOR,
            "SignetsClient(dio)",
            "SignetsClient(dio, baseUrl: 'http://10.0.2.2:8080/api/Etudiant/')",
        ),
    ],
)
def test_an_app_pointed_at_a_local_server_by_hand_is_refused(
    app, name, production, local
):
    source = SOURCES[name].replace(production, local)
    (app / name).write_text(source, encoding="utf-8")

    with pytest.raises(flutter_app.AppError) as exc:
        flutter_app.configure(app, "10.0.2.2:8080", "run")

    assert name in str(exc.value)
    assert read(app, name) == source
    assert flutter_app.load_config() == {}


def test_a_patched_app_whose_record_was_deleted_is_refused(app):
    flutter_app.configure(app, "10.0.2.2:8080", "crashed")
    flutter_app.CONFIG_FILE.unlink()

    with pytest.raises(flutter_app.AppError):
        flutter_app.configure(app, "localhost:8080", "next")


def test_only_the_run_that_configured_the_app_reverts_it(app):
    flutter_app.configure(app, "10.0.2.2:8080", "first")
    flutter_app.configure(app, "localhost:8080", "second")

    with pytest.raises(flutter_app.AppError):
        flutter_app.revert(app, "first")
    assert 'signetsAPI = "localhost:8080"' in read(app, flutter_app.URLS)

    flutter_app.revert(app, "second")
    assert_untouched(app)


def test_each_app_keeps_its_own_record(tmp_path):
    first = write_sources(tmp_path / "first")
    second = write_sources(tmp_path / "second")
    flutter_app.configure(first, "10.0.2.2:8080", "a")
    flutter_app.configure(second, "localhost:8080", "b")

    flutter_app.revert(first, "a")
    flutter_app.revert(second, "b")

    assert_untouched(first)
    assert_untouched(second)


def test_local_edits_made_before_the_run_are_kept(app):
    edited = LOCATOR_SOURCE + "// travail en cours\n"
    (app / flutter_app.LOCATOR).write_text(edited, encoding="utf-8")

    flutter_app.configure(app, "10.0.2.2:8080", "run")
    assert "baseUrl" in read(app, flutter_app.LOCATOR)

    flutter_app.revert(app)
    assert read(app, flutter_app.LOCATOR) == edited


def test_uncommitted_edits_on_the_patched_lines_are_put_back(app):
    commit(app)
    staging = URLS_SOURCE.replace("etsmobileapi.etsmtl.ca", "staging.etsmtl.ca")
    (app / flutter_app.URLS).write_text(staging, encoding="utf-8")

    flutter_app.configure(app, "10.0.2.2:8080", "run")
    flutter_app.revert(app)

    assert read(app, flutter_app.URLS) == staging


def test_patched_lines_committed_by_mistake_are_still_put_back(app):
    commit(app)
    flutter_app.configure(app, "10.0.2.2:8080", "run")
    git(app, "commit", "-am", "oops")

    flutter_app.revert(app)

    assert_untouched(app)


def test_edits_made_while_the_server_runs_survive_the_revert(app):
    flutter_app.configure(app, "10.0.2.2:8080", "run")
    locator = app / flutter_app.LOCATOR
    edited = locator.read_text(encoding="utf-8") + "void nouveauService() {}\n"
    locator.write_text(edited, encoding="utf-8")

    assert flutter_app.revert(app) == (list(flutter_app.TARGETS), [])
    assert read(app, flutter_app.LOCATOR) == LOCATOR_SOURCE + "void nouveauService() {}\n"


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_line_endings_are_preserved(app, newline):
    def encoded(text):
        return text.replace("\n", newline).encode("utf-8")

    urls = app / flutter_app.URLS
    urls.write_bytes(encoded(URLS_SOURCE))

    flutter_app.configure(app, "10.0.2.2:8080", "run")
    assert urls.read_bytes() == encoded(
        URLS_SOURCE.replace("etsmobileapi.etsmtl.ca", "10.0.2.2:8080")
    )

    flutter_app.revert(app)
    assert urls.read_bytes() == encoded(URLS_SOURCE)


def test_every_matching_line_is_patched_and_put_back(app):
    doubled = LOCATOR_SOURCE + "final other = SignetsClient(dio);\n"
    (app / flutter_app.LOCATOR).write_text(doubled, encoding="utf-8")

    flutter_app.configure(app, "10.0.2.2:8080", "run")
    assert read(app, flutter_app.LOCATOR).count("baseUrl") == 2

    flutter_app.revert(app)
    assert read(app, flutter_app.LOCATOR) == doubled


def test_a_file_that_could_not_be_put_back_can_be_retried(app):
    flutter_app.configure(app, "10.0.2.2:8080", "run")
    locator = app / flutter_app.LOCATOR
    patched = locator.read_text(encoding="utf-8")
    doubled = patched + "final other = SignetsClient(dio);\n"
    locator.write_text(doubled, encoding="utf-8")

    restored, stuck = flutter_app.revert(app)

    assert restored == [flutter_app.URLS, flutter_app.REQUEST_BUILDER]
    assert stuck == [flutter_app.LOCATOR]
    assert read(app, flutter_app.LOCATOR) == doubled

    locator.write_text(patched, encoding="utf-8")
    assert flutter_app.revert(app) == ([flutter_app.LOCATOR], [])
    assert_untouched(app)


def test_a_missing_file_does_not_keep_the_others_from_being_put_back(app):
    flutter_app.configure(app, "10.0.2.2:8080", "run")
    (app / flutter_app.REQUEST_BUILDER).unlink()

    restored, stuck = flutter_app.revert(app)

    assert restored == [flutter_app.URLS, flutter_app.LOCATOR]
    assert stuck == [flutter_app.REQUEST_BUILDER]
    assert read(app, flutter_app.URLS) == URLS_SOURCE


def test_a_failed_patch_writes_nothing(tmp_path):
    app = write_sources(
        tmp_path / "Notre-Dame", {**SOURCES, flutter_app.LOCATOR: "void f() {}\n"}
    )

    with pytest.raises(flutter_app.AppError):
        flutter_app.configure(app, "10.0.2.2:8080", "run")

    assert read(app, flutter_app.URLS) == URLS_SOURCE
    assert read(app, flutter_app.REQUEST_BUILDER) == REQUEST_BUILDER_SOURCE
    assert flutter_app.load_config() == {}


def test_a_file_that_is_not_utf8_is_reported_before_anything_is_written(app):
    locator = app / flutter_app.LOCATOR
    locator.write_bytes("// café\n".encode("latin-1") + LOCATOR_SOURCE.encode())

    with pytest.raises(flutter_app.AppError) as exc:
        flutter_app.configure(app, "10.0.2.2:8080", "run")

    assert "locator.dart" in str(exc.value)
    assert read(app, flutter_app.URLS) == URLS_SOURCE


def test_a_file_that_cannot_be_written_puts_the_others_back(app, monkeypatch):
    write_bytes = Path.write_bytes

    def locked(self, data):
        if self.name == "locator.dart":
            raise PermissionError(13, "Permission denied", str(self))
        return write_bytes(self, data)

    monkeypatch.setattr(Path, "write_bytes", locked)
    refuse_to_start(monkeypatch)

    start.main(["--profile", "normal", "--app", str(app)])

    assert_untouched(app)
    assert flutter_app.load_config() == {}


def test_a_missing_or_foreign_directory_is_rejected(tmp_path):
    with pytest.raises(flutter_app.AppError):
        flutter_app.resolve_path(tmp_path / "nope")

    with pytest.raises(flutter_app.AppError):
        flutter_app.resolve_path(tmp_path)


def test_the_app_is_patched_while_the_server_runs_and_reverted_after(app, monkeypatch):
    seen = record_urls(monkeypatch, app)

    start.main(["--profile", "semester-off", "--app", str(app), "--platform", "ios"])

    assert 'signetsAPI = "localhost:8080"' in seen[0]
    assert_untouched(app)


def test_a_run_taken_over_by_a_new_one_leaves_the_app_to_it(app, monkeypatch, capsys):
    monkeypatch.setattr(
        start,
        "_start_server",
        lambda *a: flutter_app.configure(app, "localhost:8080", "new run"),
    )

    start.main(["--profile", "normal", "--app", str(app)])

    assert 'signetsAPI = "localhost:8080"' in read(app, flutter_app.URLS)
    assert "un autre lancement" in capsys.readouterr().out

    flutter_app.revert(app, "new run")
    assert_untouched(app)


@pytest.mark.parametrize("name", CLOSE_SIGNALS)
def test_a_close_signal_still_reverts_the_app(app, monkeypatch, name):
    sig = getattr(signal, name)
    before = signal.getsignal(sig)
    monkeypatch.setattr(start, "_start_server", lambda *a: signal.raise_signal(sig))

    with pytest.raises(SystemExit):
        start.main(["--profile", "normal", "--app", str(app)])

    assert_untouched(app)
    assert signal.getsignal(sig) == before


@pytest.mark.skipif(os.name != "nt", reason="console events only exist on Windows")
def test_closing_the_console_window_reverts_the_app(app, monkeypatch):
    registrations = []
    monkeypatch.setattr(
        ctypes.windll.kernel32,
        "SetConsoleCtrlHandler",
        lambda handler, add: registrations.append((handler, add)),
    )
    seen = []

    def close_the_window(*_):
        handler = registrations[0][0]
        seen.append(handler(signal.CTRL_C_EVENT))
        seen.append(read(app, flutter_app.URLS) != URLS_SOURCE)
        seen.append(handler(start.CTRL_CLOSE_EVENT))
        seen.append(read(app, flutter_app.URLS) == URLS_SOURCE)

    monkeypatch.setattr(start, "_start_server", close_the_window)

    start.main(["--profile", "normal", "--app", str(app)])

    assert seen == [0, True, 1, True]
    assert_untouched(app)
    assert [add for _, add in registrations] == [True, False]


def test_a_second_ctrl_c_cannot_interrupt_the_revert(app, monkeypatch):
    revert = flutter_app.revert
    handlers = []

    def impatient_revert(*args):
        handlers.append(signal.getsignal(signal.SIGINT))
        signal.raise_signal(signal.SIGINT)
        return revert(*args)

    monkeypatch.setattr(flutter_app, "revert", impatient_revert)
    monkeypatch.setattr(
        start, "_start_server", lambda *a: signal.raise_signal(signal.SIGINT)
    )

    start.main(["--profile", "normal", "--app", str(app)])

    assert handlers == [signal.SIG_IGN]
    assert_untouched(app)
    assert signal.getsignal(signal.SIGINT) is signal.default_int_handler


def test_the_server_does_not_start_when_the_app_cannot_be_patched(app, monkeypatch):
    (app / flutter_app.URLS).write_text("class Urls {}\n", encoding="utf-8")
    refuse_to_start(monkeypatch)

    start.main(["--profile", "normal", "--app", str(app)])


def test_revert_app_flag_reverts_without_starting_the_server(app, monkeypatch):
    refuse_to_start(monkeypatch)
    flutter_app.configure(app, "10.0.2.2:8080", "crashed")

    start.main(["--revert-app", "--app", str(app)])

    assert_untouched(app)


def test_revert_app_flag_uses_the_saved_app(saved_app, monkeypatch):
    flutter_app.configure(saved_app, "10.0.2.2:8080", "crashed")

    start.main(["--revert-app"])

    assert_untouched(saved_app)


def test_revert_app_flag_says_when_nothing_was_recorded(saved_app, capsys):
    start.main(["--revert-app"])

    assert "aucune modification" in capsys.readouterr().out


def test_forget_app_leaves_later_runs_alone(saved_app, monkeypatch, capsys):
    seen = record_urls(monkeypatch, saved_app)
    start.main(["--profile", "normal", "--platform", "ios"])

    start.main(["--forget-app"])
    start.main(["--profile", "normal"])

    assert 'signetsAPI = "localhost:8080"' in seen[0]
    assert seen[1] == URLS_SOURCE
    assert flutter_app.load_config() == {}
    assert "oubliée" in capsys.readouterr().out


def test_forget_app_reverts_a_run_that_did_not(saved_app):
    flutter_app.configure(saved_app, "10.0.2.2:8080", "crashed")

    start.main(["--forget-app"])

    assert_untouched(saved_app)
    assert flutter_app.load_config() == {}


def test_forget_app_keeps_an_app_it_could_not_put_back(saved_app, capsys):
    flutter_app.configure(saved_app, "10.0.2.2:8080", "crashed")
    locator = saved_app / flutter_app.LOCATOR
    doubled = locator.read_text(encoding="utf-8") + "final other = SignetsClient(dio);\n"
    locator.write_text(doubled, encoding="utf-8")

    start.main(["--forget-app"])

    assert flutter_app.load_config()["app"] == str(saved_app)
    assert "python start.py --forget-app" in capsys.readouterr().out


def test_forget_app_without_a_saved_app_says_so(capsys):
    start.main(["--forget-app"])

    assert "Aucune app" in capsys.readouterr().out


def test_the_app_is_saved_for_the_next_run(app, monkeypatch):
    record_urls(monkeypatch, app)

    start.main(["--profile", "normal", "--app", str(app), "--platform", "ios"])

    assert flutter_app.load_config() == {"app": str(app), "platform": "ios"}


def test_flags_reuse_the_saved_app_and_platform(app, monkeypatch):
    seen = record_urls(monkeypatch, app)
    start.main(["--profile", "normal", "--app", str(app), "--platform", "ios"])

    start.main(["--profile", "normal"])

    assert len(seen) == 2
    assert 'signetsAPI = "localhost:8080"' in seen[1]
    assert_untouched(app)


def test_a_new_platform_replaces_the_saved_host(saved_app, monkeypatch):
    flutter_app.save_config({"app": str(saved_app), "host": "192.168.1.10:8080"})
    seen = record_urls(monkeypatch, saved_app)

    start.main(["--profile", "normal", "--platform", "android"])

    assert 'signetsAPI = "10.0.2.2:8080"' in seen[0]
    assert flutter_app.load_config() == {"app": str(saved_app), "platform": "android"}


def test_no_app_leaves_the_saved_app_alone(saved_app, monkeypatch):
    seen = record_urls(monkeypatch, saved_app)

    start.main(["--profile", "normal", "--no-app"])

    assert seen == [URLS_SOURCE]
    assert flutter_app.load_config() == {"app": str(saved_app)}


@pytest.mark.parametrize("flag", ["--no-app", "--forget-app"])
def test_app_cannot_be_combined_with_no_app_or_forget_app(app, flag):
    with pytest.raises(SystemExit):
        start._build_parser().parse_args(["--app", str(app), flag])


def test_platform_without_any_app_does_not_start_the_server(monkeypatch):
    refuse_to_start(monkeypatch)

    start.main(["--profile", "normal", "--platform", "ios"])


def test_flags_without_any_app_start_the_server_only(monkeypatch):
    started = []
    monkeypatch.setattr(start, "_start_server", lambda *a: started.append(a))

    start.main(["--profile", "normal"])

    assert len(started) == 1
    assert flutter_app.load_config() == {}


@pytest.mark.parametrize(
    "content", ["{ pas du json", '{"patched": {"C:/app": {"owner": 1}}}']
)
def test_a_broken_config_file_does_not_start_the_server(monkeypatch, content):
    flutter_app.CONFIG_FILE.write_text(content, encoding="utf-8")
    refuse_to_start(monkeypatch)

    start.main(["--profile", "normal"])


def test_the_menu_defaults_to_the_saved_app(saved_app, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_: "")

    assert start._prompt_app_path(str(saved_app)) == str(saved_app)


def test_the_menu_defaults_to_the_server_only_without_a_saved_app(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_: "")

    assert start._prompt_app_path(None) is None


def test_the_menu_asks_for_another_path(saved_app, monkeypatch):
    answers = iter(["2", "/ailleurs/Notre-Dame"])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))

    assert start._prompt_app_path(str(saved_app)) == "/ailleurs/Notre-Dame"


def test_the_menu_asks_for_a_path_when_none_is_saved(app, monkeypatch):
    answers = iter(["1", str(app)])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))

    assert start._prompt_app_path(None) == str(app)


def test_the_menu_can_start_the_server_without_touching_the_app(saved_app, monkeypatch):
    started = []
    monkeypatch.setattr(
        start, "_config_from_menu", lambda: ({}, "normal", "none", None)
    )
    monkeypatch.setattr("builtins.input", lambda *_: "0")
    monkeypatch.setattr(start, "_start_server", lambda *a: started.append(a))

    start.main([])

    assert started == [({}, "normal", "none", None)]
    assert_untouched(saved_app)
