import os
import re
import subprocess
from pathlib import Path

from ._api import API_PREFIX, SERVER_PORT
from ._paths import ROOT

APP_PATH_FILE = ROOT / ".flutter_app_path"

DEFAULT_PLATFORM = "android"

PLATFORM_HOSTS = {
    "android": "10.0.2.2",
    "ios": "localhost",
}

URLS = "lib/domain/constants/urls.dart"
REQUEST_BUILDER = "lib/data/services/signets-api/request_builder_service.dart"
LOCATOR = "lib/locator.dart"

_SIGNETS_HOST = re.compile(r"(signetsAPI\s*=\s*)(['\"])[^'\"]*\2")
_HTTPS_CALL = re.compile(r"Uri\.https\(")
_SIGNETS_CLIENT = re.compile(
    r"SignetsClient\(\s*dio\s*(?:,\s*baseUrl:\s*(['\"])[^'\"]*\1\s*)?\)"
)


class AppError(Exception):
    pass


def resolve_host(platform: str | None, host: str | None) -> str:
    if host:
        return host if ":" in host else f"{host}:{SERVER_PORT}"
    return f"{PLATFORM_HOSTS[platform or DEFAULT_PLATFORM]}:{SERVER_PORT}"


def base_url(host: str) -> str:
    return f"http://{host}{API_PREFIX}/"


def _patch_host(text: str, host: str) -> str:
    patched, count = _SIGNETS_HOST.subn(lambda m: f'{m.group(1)}"{host}"', text)
    if not count:
        raise AppError(f"{URLS}: aucune constante signetsAPI trouvée.")
    return patched


def _patch_scheme(text: str, _host: str) -> str:
    patched, count = _HTTPS_CALL.subn("Uri.http(", text)
    if not count and "Uri.http(" not in text:
        raise AppError(f"{REQUEST_BUILDER}: aucun appel Uri.https trouvé.")
    return patched


def _patch_client(text: str, host: str) -> str:
    patched, count = _SIGNETS_CLIENT.subn(
        lambda _: f"SignetsClient(dio, baseUrl: '{base_url(host)}')", text
    )
    if not count:
        raise AppError(f"{LOCATOR}: aucun appel SignetsClient(dio) trouvé.")
    return patched


PATCHES = (
    (URLS, _patch_host),
    (REQUEST_BUILDER, _patch_scheme),
    (LOCATOR, _patch_client),
)

TARGETS = tuple(name for name, _ in PATCHES)


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
    )


def _repo(path: Path) -> tuple[Path, list[str]]:
    top = _git(path, "rev-parse", "--show-toplevel")
    if top.returncode != 0:
        raise AppError(
            f"{path} n'est pas un dépôt git; le retour en arrière a besoin de "
            "« git checkout -- »."
        )
    root = Path(top.stdout.strip())
    prefix = os.path.relpath(path, root).replace(os.sep, "/")
    names = [name if prefix == "." else f"{prefix}/{name}" for name in TARGETS]
    tracked = _git(root, "ls-files", "--error-unmatch", "--", *names)
    if tracked.returncode != 0:
        raise AppError(
            f"fichiers non suivis par git dans {path}: {tracked.stderr.strip()}"
        )
    return root, names


def _modified(root: Path, names: list[str]) -> list[str]:
    diff = _git(root, "diff", "--name-only", "-z", "HEAD", "--", *names)
    if diff.returncode != 0:
        raise AppError(f"git diff a échoué: {diff.stderr.strip()}")
    return [name for name in diff.stdout.split("\0") if name]


def _normalized(text: str, patch, host: str) -> str:
    return patch(text, host).replace("\r\n", "\n")


def resolve_path(raw) -> Path:
    path = Path(raw).expanduser()
    try:
        path = path.resolve(strict=True)
    except OSError:
        raise AppError(f"Dossier introuvable: {raw}") from None
    if not path.is_dir():
        raise AppError(f"{path} n'est pas un dossier.")
    missing = [name for name in TARGETS if not (path / name).is_file()]
    if missing:
        raise AppError(
            f"{path} ne ressemble pas à l'app ÉTSMobile; "
            f"fichiers absents: {', '.join(missing)}"
        )
    return path


def configure(path: Path, host: str) -> list[str]:
    root, names = _repo(path)
    modified = set(_modified(root, names))

    conflicts = []
    for name, (target, patch) in zip(names, PATCHES):
        if name not in modified:
            continue
        head = _git(root, "show", f"HEAD:{name}")
        if head.returncode != 0:
            conflicts.append(target)
            continue
        working = (path / target).read_text(encoding="utf-8")
        if _normalized(head.stdout, patch, host) != _normalized(working, patch, host):
            conflicts.append(target)
    if conflicts:
        raise AppError(
            "modifications locales non liées au mock dans:\n"
            + "\n".join(f"    {name}" for name in conflicts)
            + "\n  Commitez-les ou remisez-les: le retour en arrière fait "
            "« git checkout -- »."
        )

    patched = []
    for target, patch in PATCHES:
        file = path / target
        text = file.read_text(encoding="utf-8")
        updated = patch(text, host)
        if updated != text:
            file.write_text(updated, encoding="utf-8")
            patched.append(target)
    return patched


def revert(path: Path) -> list[str]:
    root, names = _repo(path)
    modified = set(_modified(root, names))
    if not modified:
        return []
    checkout = _git(root, "checkout", "--", *sorted(modified))
    if checkout.returncode != 0:
        raise AppError(f"git checkout a échoué: {checkout.stderr.strip()}")
    return [target for target, name in zip(TARGETS, names) if name in modified]


def saved_path() -> str | None:
    try:
        raw = APP_PATH_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return raw or None


def save_path(path: Path) -> None:
    try:
        APP_PATH_FILE.write_text(f"{path}\n", encoding="utf-8")
    except OSError:
        pass
