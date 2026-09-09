import shutil
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


@pytest.fixture
def app(tmp_path, monkeypatch):
    path = tmp_path / "Notre-Dame"
    for name, source in SOURCES.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source, encoding="utf-8")

    git(path.parent, "init", str(path))
    git(path, "config", "user.email", "mock@example.com")
    git(path, "config", "user.name", "Mock")
    git(path, "add", ".")
    git(path, "commit", "-m", "app")

    monkeypatch.setattr(flutter_app, "APP_PATH_FILE", tmp_path / ".flutter_app_path")
    return path


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

    assert flutter_app.revert(app) == list(flutter_app.TARGETS)
    for name, source in SOURCES.items():
        assert read(app, name) == source
    assert flutter_app.revert(app) == []


def test_configure_reruns_over_a_previous_run(app):
    flutter_app.configure(app, "10.0.2.2:8080")
    flutter_app.configure(app, "localhost:8080")

    assert 'signetsAPI = "localhost:8080"' in read(app, flutter_app.URLS)
    assert (
        "SignetsClient(dio, baseUrl: 'http://localhost:8080/api/Etudiant/')"
        in read(app, flutter_app.LOCATOR)
    )

    flutter_app.revert(app)
    for name, source in SOURCES.items():
        assert read(app, name) == source


def test_configure_refuses_to_clobber_unrelated_edits(app):
    locator = app / flutter_app.LOCATOR
    locator.write_text(LOCATOR_SOURCE + "// travail en cours\n", encoding="utf-8")

    with pytest.raises(flutter_app.AppError) as exc:
        flutter_app.configure(app, "10.0.2.2:8080")

    assert flutter_app.LOCATOR in str(exc.value)
    assert read(app, flutter_app.URLS) == URLS_SOURCE


def test_a_missing_or_foreign_directory_is_rejected(tmp_path):
    with pytest.raises(flutter_app.AppError):
        flutter_app.resolve_path(tmp_path / "nope")

    with pytest.raises(flutter_app.AppError):
        flutter_app.resolve_path(tmp_path)


def test_a_directory_outside_git_is_rejected(app):
    shutil.rmtree(app / ".git")

    with pytest.raises(flutter_app.AppError):
        flutter_app.configure(app, "10.0.2.2:8080")


def test_the_app_is_patched_while_the_server_runs_and_reverted_after(app, monkeypatch):
    seen = {}

    def fake_server(*_args):
        seen["urls"] = read(app, flutter_app.URLS)

    monkeypatch.setattr(start, "_start_server", fake_server)

    start.main(["--profile", "semester-off", "--app", str(app), "--platform", "ios"])

    assert 'signetsAPI = "localhost:8080"' in seen["urls"]
    for name, source in SOURCES.items():
        assert read(app, name) == source


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

    for name, source in SOURCES.items():
        assert read(app, name) == source


def test_the_menu_leaves_the_app_alone_by_default(app, monkeypatch):
    flutter_app.save_path(app)
    monkeypatch.setattr("builtins.input", lambda *_: "")

    assert start._prompt_app_path() is None


def test_the_menu_reuses_the_saved_path(app, monkeypatch):
    flutter_app.save_path(app)
    monkeypatch.setattr("builtins.input", lambda *_: "1")

    assert flutter_app.saved_path() == str(app)
    assert start._prompt_app_path() == str(app)


def test_the_menu_asks_for_a_path(app, monkeypatch):
    answers = iter(["2", "/ailleurs/Notre-Dame"])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))
    flutter_app.save_path(app)

    assert start._prompt_app_path() == "/ailleurs/Notre-Dame"


def test_the_menu_asks_for_a_path_when_none_is_saved(app, monkeypatch):
    answers = iter(["1", str(app)])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))

    assert flutter_app.saved_path() is None
    assert start._prompt_app_path() == str(app)


def test_the_menu_can_start_the_server_without_touching_the_app(app, monkeypatch):
    started = []
    flutter_app.save_path(app)
    monkeypatch.setattr(
        start, "_config_from_menu", lambda: ({}, "normal", "none", None)
    )
    monkeypatch.setattr("builtins.input", lambda *_: "")
    monkeypatch.setattr(start, "_start_server", lambda *a: started.append(a))

    start.main([])

    assert started == [({}, "normal", "none", None)]
    for name, source in SOURCES.items():
        assert read(app, name) == source


def test_flags_without_app_leave_the_saved_path_alone(app, monkeypatch):
    flutter_app.save_path(app)
    args = start._build_parser().parse_args(["--profile", "normal"])

    assert start._setup_app(args, interactive=False) is None
    for name, source in SOURCES.items():
        assert read(app, name) == source
