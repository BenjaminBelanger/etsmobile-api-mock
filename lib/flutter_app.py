import json
import os
import re
import subprocess
from pathlib import Path

from ._api import API_PREFIX, SERVER_PORT
from ._paths import ROOT

CONFIG_FILE = ROOT / "mock.config.json"

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
_URI_CALL = re.compile(r"Uri\.https?\(")
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
    (URLS, _SIGNETS_HOST, _patch_host),
    (REQUEST_BUILDER, _URI_CALL, _patch_scheme),
    (LOCATOR, _SIGNETS_CLIENT, _patch_client),
)

TARGETS = tuple(name for name, _, _ in PATCHES)


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _head(root: Path, name: str) -> str | None:
    shown = subprocess.run(
        ["git", "-C", str(root), "cat-file", "--filters", f"HEAD:{name}"],
        capture_output=True,
    )
    return shown.stdout.decode("utf-8") if shown.returncode == 0 else None


def _read(file: Path) -> str:
    return file.read_bytes().decode("utf-8")


def _write(file: Path, text: str) -> None:
    file.write_bytes(text.encode("utf-8"))


def _restore(text: str, original: str, pattern: re.Pattern) -> str | None:
    originals = [match.group(0) for match in pattern.finditer(original)]
    if len(originals) != sum(1 for _ in pattern.finditer(text)):
        return None
    pieces = iter(originals)
    return pattern.sub(lambda _: next(pieces), text)


def _repo(path: Path) -> tuple[Path, list[str]]:
    top = _git(path, "rev-parse", "--show-toplevel")
    if top.returncode != 0:
        raise AppError(
            f"{path} n'est pas un dépôt git; le retour en arrière a besoin de "
            "la version commitée des fichiers."
        )
    root = Path(top.stdout.strip())
    prefix = os.path.relpath(path, root).replace(os.sep, "/")
    names = [name if prefix == "." else f"{prefix}/{name}" for name in TARGETS]
    return root, names


def _originals(path: Path) -> list[tuple[Path, re.Pattern, str | None]]:
    root, names = _repo(path)
    return [
        (path / target, pattern, _head(root, name))
        for name, (target, pattern, _) in zip(names, PATCHES)
    ]


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
    stuck = [
        target
        for target, (file, pattern, head) in zip(TARGETS, _originals(path))
        if head is None or _restore(_read(file), head, pattern) is None
    ]
    if stuck:
        raise AppError(
            "impossible de retrouver la version commitée des lignes à modifier "
            "dans:\n"
            + "\n".join(f"    {name}" for name in stuck)
            + "\n  Commitez-les ou remisez-les: le retour en arrière en a besoin."
        )

    updates = {}
    for target, _, patch in PATCHES:
        text = _read(path / target)
        updated = patch(text, host)
        if updated != text:
            updates[target] = updated
    for target, updated in updates.items():
        _write(path / target, updated)
    return list(updates)


def revert(path: Path) -> tuple[list[str], list[str]]:
    restored, stuck = [], []
    for target, (file, pattern, head) in zip(TARGETS, _originals(path)):
        text = _read(file)
        original = None if head is None else _restore(text, head, pattern)
        if original is None:
            stuck.append(target)
        elif original != text:
            _write(file, original)
            restored.append(target)
    return restored, stuck


def load_config() -> dict:
    try:
        raw = CONFIG_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise AppError(f"{CONFIG_FILE.name} illisible: {exc}") from None
    try:
        config = json.loads(raw)
    except ValueError as exc:
        raise AppError(f"{CONFIG_FILE.name} invalide: {exc}") from None
    if not isinstance(config, dict):
        raise AppError(f"{CONFIG_FILE.name} invalide: un objet JSON est attendu.")
    for key in ("app", "platform", "host"):
        if key in config and not isinstance(config[key], str):
            raise AppError(f"{CONFIG_FILE.name}: « {key} » doit être un texte.")
    if config.get("platform", DEFAULT_PLATFORM) not in PLATFORM_HOSTS:
        raise AppError(
            f"{CONFIG_FILE.name}: plateforme inconnue « {config['platform']} » "
            f"({', '.join(sorted(PLATFORM_HOSTS))})."
        )
    return config


def save_config(config: dict) -> None:
    kept = {key: value for key, value in config.items() if value is not None}
    try:
        CONFIG_FILE.write_text(
            json.dumps(kept, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    except OSError:
        pass
