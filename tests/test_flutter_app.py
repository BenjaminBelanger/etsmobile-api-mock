import subprocess

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


def commit(path, sources=SOURCES):
    write_sources(path, sources)
    git(path.parent, "init", str(path))
    git(path, "config", "user.email", "mock@example.com")
    git(path, "config", "user.name", "Mock")
    git(path, "config", "core.autocrlf", "false")
    git(path, "add", ".")
    git(path, "commit", "-m", "app")
    return path


def assert_untouched(app):
    for name, source in SOURCES.items():
        assert read(app, name) == source


def record_urls(monkeypatch, app):
    seen = []
    monkeypatch.setattr(
        start, "_start_server", lambda *a: seen.append(read(app, flutter_app.URLS))
    )
    return seen


@pytest.fixture
def app(tmp_path):
    return commit(tmp_path / "Notre-Dame")


@pytest.fixture
def saved_app(app):
    flutter_app.save_config({"app": str(app)})
    return app


def test_platform_decides_the_host():
    assert flutter_app.resolve_host(None, None) == "10.0.2.2:8080"
    assert flutter_app.resolve_host("android", None) == "10.0.2.2:8080"
    assert flutter_app.resolve_host("ios", None) == "localhost:8080"


def test_explicit_host_wins_and_gets_the_server_port():
    assert flutter_app.resolve_host("ios", "192.168.1.10") == "192.168.1.10:8080"
    assert flutter_app.resolve_host(None, "192.168.1.10:9000") == "192.168.1.10:9000"


def test_base_url_follows_the_api_router_prefix():
    from lib.routes import router

    assert flutter_app.base_url("host:1") == f"http://host:1{router.prefix}/"


def test_configure_rewrites_the_three_files(app):
    patched = flutter_app.configure(app, "10.0.2.2:8080")

    assert patched == list(flutter_app.TARGETS)
    assert 'signetsAPI = "10.0.2.2:8080"' in read(app, flutter_app.URLS)
    assert "Uri.http(" in read(app, flutter_app.REQUEST_BUILDER)
    assert "Uri.https(" not in read(app, flutter_app.REQUEST_BUILDER)
    assert (
        "SignetsClient(dio, baseUrl: 'http://10.0.2.2:8080/api/Etudiant/')"
        in read(app, flutter_app.LOCATOR)
    )


def test_revert_restores_every_patched_file(app):
    flutter_app.configure(app, "localhost:8080")

    assert flutter_app.revert(app) == (list(flutter_app.TARGETS), [])
    assert_untouched(app)
    assert flutter_app.revert(app) == ([], [])


def test_configure_reruns_over_a_previous_run(app):
    flutter_app.configure(app, "10.0.2.2:8080")
    flutter_app.configure(app, "localhost:8080")

    assert 'signetsAPI = "localhost:8080"' in read(app, flutter_app.URLS)
    assert (
        "SignetsClient(dio, baseUrl: 'http://localhost:8080/api/Etudiant/')"
        in read(app, flutter_app.LOCATOR)
    )

    flutter_app.revert(app)
    assert_untouched(app)


def test_local_edits_made_before_the_run_are_kept(app):
    edited = LOCATOR_SOURCE + "// travail en cours\n"
    (app / flutter_app.LOCATOR).write_text(edited, encoding="utf-8")

    flutter_app.configure(app, "10.0.2.2:8080")
    assert "baseUrl" in read(app, flutter_app.LOCATOR)

    flutter_app.revert(app)
    assert read(app, flutter_app.LOCATOR) == edited


def test_edits_made_while_the_server_runs_survive_the_revert(app):
    flutter_app.configure(app, "10.0.2.2:8080")
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
    git(app, "commit", "--allow-empty", "-am", "eol")

    flutter_app.configure(app, "10.0.2.2:8080")
    assert urls.read_bytes() == encoded(
        URLS_SOURCE.replace("etsmobileapi.etsmtl.ca", "10.0.2.2:8080")
    )

    flutter_app.revert(app)
    assert urls.read_bytes() == encoded(URLS_SOURCE)


def test_configure_refuses_lines_it_could_not_put_back(app):
    doubled = LOCATOR_SOURCE + "final other = SignetsClient(dio);\n"
    (app / flutter_app.LOCATOR).write_text(doubled, encoding="utf-8")

    with pytest.raises(flutter_app.AppError) as exc:
        flutter_app.configure(app, "10.0.2.2:8080")

    assert flutter_app.LOCATOR in str(exc.value)
    assert read(app, flutter_app.URLS) == URLS_SOURCE
    assert read(app, flutter_app.LOCATOR) == doubled


def test_revert_reports_a_file_it_could_not_put_back(app):
    flutter_app.configure(app, "10.0.2.2:8080")
    locator = app / flutter_app.LOCATOR
    doubled = locator.read_text(encoding="utf-8") + "final other = SignetsClient(dio);\n"
    locator.write_text(doubled, encoding="utf-8")

    restored, stuck = flutter_app.revert(app)

    assert restored == [flutter_app.URLS, flutter_app.REQUEST_BUILDER]
    assert stuck == [flutter_app.LOCATOR]
    assert read(app, flutter_app.LOCATOR) == doubled


def test_a_failed_patch_writes_nothing(tmp_path):
    app = commit(tmp_path / "Notre-Dame", {**SOURCES, flutter_app.LOCATOR: "void f() {}\n"})

    with pytest.raises(flutter_app.AppError):
        flutter_app.configure(app, "10.0.2.2:8080")

    assert read(app, flutter_app.URLS) == URLS_SOURCE
    assert read(app, flutter_app.REQUEST_BUILDER) == REQUEST_BUILDER_SOURCE


def test_a_missing_or_foreign_directory_is_rejected(tmp_path):
    with pytest.raises(flutter_app.AppError):
        flutter_app.resolve_path(tmp_path / "nope")

    with pytest.raises(flutter_app.AppError):
        flutter_app.resolve_path(tmp_path)


def test_a_directory_outside_git_is_rejected(tmp_path):
    app = tmp_path / "Notre-Dame"
    write_sources(app)

    with pytest.raises(flutter_app.AppError):
        flutter_app.configure(app, "10.0.2.2:8080")
    assert_untouched(app)


def test_the_app_is_patched_while_the_server_runs_and_reverted_after(app, monkeypatch):
    seen = record_urls(monkeypatch, app)

    start.main(["--profile", "semester-off", "--app", str(app), "--platform", "ios"])

    assert 'signetsAPI = "localhost:8080"' in seen[0]
    assert_untouched(app)


def test_the_server_does_not_start_when_the_app_cannot_be_patched(app, monkeypatch):
    (app / flutter_app.URLS).write_text("class Urls {}\n", encoding="utf-8")
    git(app, "commit", "-am", "drop the constant")
    monkeypatch.setattr(
        start, "_start_server", lambda *a: pytest.fail("server should not start")
    )

    start.main(["--profile", "normal", "--app", str(app)])


def test_revert_app_flag_reverts_without_starting_the_server(app, monkeypatch):
    monkeypatch.setattr(
        start, "_start_server", lambda *a: pytest.fail("server should not start")
    )
    flutter_app.configure(app, "10.0.2.2:8080")

    start.main(["--revert-app", "--app", str(app)])

    assert_untouched(app)


def test_revert_app_flag_uses_the_saved_app(saved_app, monkeypatch):
    flutter_app.configure(saved_app, "10.0.2.2:8080")

    start.main(["--revert-app"])

    assert_untouched(saved_app)


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


def test_app_and_no_app_cannot_be_combined(app):
    with pytest.raises(SystemExit):
        start._build_parser().parse_args(["--app", str(app), "--no-app"])


def test_platform_without_any_app_does_not_start_the_server(monkeypatch):
    monkeypatch.setattr(
        start, "_start_server", lambda *a: pytest.fail("server should not start")
    )

    start.main(["--profile", "normal", "--platform", "ios"])


def test_flags_without_any_app_start_the_server_only(monkeypatch):
    started = []
    monkeypatch.setattr(start, "_start_server", lambda *a: started.append(a))

    start.main(["--profile", "normal"])

    assert len(started) == 1
    assert flutter_app.load_config() == {}


def test_a_broken_config_file_does_not_start_the_server(monkeypatch):
    flutter_app.CONFIG_FILE.write_text("{ pas du json", encoding="utf-8")
    monkeypatch.setattr(
        start, "_start_server", lambda *a: pytest.fail("server should not start")
    )

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


