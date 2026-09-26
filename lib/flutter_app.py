import json
import re
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

_HOST = re.compile(r"(?:[A-Za-z0-9._-]+|\[[0-9A-Fa-f:.]+\])(?::(?P<port>\d{1,5}))?")
_SIGNETS_HOST = re.compile(r"(signetsAPI\s*=\s*)(['\"])[^'\"]*\2")
_URI_CALL = re.compile(r"Uri\.https?\(")
_SIGNETS_CLIENT = re.compile(
    r"SignetsClient\(\s*dio\s*(?:,\s*baseUrl:\s*(['\"])[^'\"]*\1\s*)?\)"
)


class AppError(Exception):
    pass


def check_host(host: str) -> str:
    match = _HOST.fullmatch(host)
    if match is None or not 0 < int(match["port"] or SERVER_PORT) < 65536:
        raise AppError(
            f"hôte invalide « {host} »: un nom ou une adresse, avec ou sans "
            "port et sans http:// (ex: 192.168.1.10 ou 192.168.1.10:8080)."
        )
    return host if match["port"] else f"{host}:{SERVER_PORT}"


def resolve_host(platform: str | None, host: str | None) -> str:
    if host is not None:
        return check_host(host)
    return f"{PLATFORM_HOSTS[platform or DEFAULT_PLATFORM]}:{SERVER_PORT}"


def base_url(host: str) -> str:
    return f"http://{host}{API_PREFIX}/"


PATCHES = (
    (
        URLS,
        _SIGNETS_HOST,
        lambda match, host: f'{match.group(1)}"{host}"',
        "aucune constante signetsAPI trouvée.",
    ),
    (
        REQUEST_BUILDER,
        _URI_CALL,
        lambda match, host: "Uri.http(",
        "aucun appel Uri.https trouvé.",
    ),
    (
        LOCATOR,
        _SIGNETS_CLIENT,
        lambda match, host: f"SignetsClient(dio, baseUrl: '{base_url(host)}')",
        "aucun appel SignetsClient(dio) trouvé.",
    ),
)

TARGETS = tuple(target for target, *_ in PATCHES)

_PATTERNS = {target: pattern for target, pattern, *_ in PATCHES}


def _read(file: Path) -> str:
    try:
        return file.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise AppError(f"lecture impossible de {file}: {exc}") from None


def _write(file: Path, text: str) -> None:
    try:
        file.write_bytes(text.encode("utf-8"))
    except OSError as exc:
        raise AppError(f"écriture impossible de {file}: {exc}") from None


def _lines(text: str, pattern: re.Pattern) -> list[str]:
    return [match.group(0) for match in pattern.finditer(text)]


def _originals(current: list[str], recorded: list | None) -> list[str]:
    if recorded and [patched for _, patched in recorded] == current:
        return [original for original, _ in recorded]
    return current


def _points_at_a_local_server(line: str) -> bool:
    return any(mark in line for mark in ("Uri.http(", "http://", f":{SERVER_PORT}"))


def _put_back(file: Path, pattern: re.Pattern, recorded: list) -> bool:
    text = _read(file)
    if len(_lines(text, pattern)) != len(recorded):
        raise AppError(f"{file}: les lignes du mock ont changé.")
    originals = iter(original for original, _ in recorded)
    original = pattern.sub(lambda _: next(originals), text)
    if original == text:
        return False
    _write(file, original)
    return True


def _key(path) -> str:
    return str(Path(path).expanduser().resolve())


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


def configure(
    path: Path, host: str, owner: str, settings: dict | None = None
) -> list[str]:
    config = load_config()
    previous = config.get("patched", {}).get(_key(path), {}).get("lines", {})

    lines, updates, local = {}, {}, []
    for target, pattern, replace, missing in PATCHES:
        text = _read(path / target)
        current = _lines(text, pattern)
        if not current:
            raise AppError(f"{target}: {missing}")
        updated = pattern.sub(lambda match: replace(match, host), text)
        originals = _originals(current, previous.get(target))
        if any(map(_points_at_a_local_server, originals)):
            local.append(target)
        lines[target] = [
            list(pair) for pair in zip(originals, _lines(updated, pattern))
        ]
        if updated != text:
            updates[target] = (text, updated)
    if local:
        raise AppError(
            "ces fichiers pointent déjà vers un serveur local, sans modification "
            "enregistrée par start.py pour les remettre:\n"
            + "\n".join(f"    {name}" for name in local)
            + "\n  Remettez-y les valeurs de production (etsmobileapi.etsmtl.ca, "
            "Uri.https, SignetsClient(dio)) puis relancez."
        )

    save_config(
        {
            **config,
            **(settings or {}),
            "patched": {
                **config.get("patched", {}),
                _key(path): {"owner": owner, "lines": lines},
            },
        }
    )

    written = []
    try:
        for target, (_, updated) in updates.items():
            _write(path / target, updated)
            written.append(target)
    except AppError:
        for target in written:
            _write(path / target, updates[target][0])
        save_config(config)
        raise
    return list(updates)


def revert(path, owner: str | None = None) -> tuple[list[str], list[str]]:
    key = _key(path)
    config = load_config()
    records = config.get("patched", {})
    record = records.get(key)
    if record is None:
        raise AppError(f"aucune modification du mock enregistrée pour {key}.")
    if owner is not None and record["owner"] != owner:
        raise AppError(
            "un autre lancement de start.py l'a reprise; il la remettra à son "
            "état d'origine à son arrêt."
        )

    restored, stuck = [], []
    for target, recorded in record["lines"].items():
        try:
            changed = _put_back(Path(key) / target, _PATTERNS[target], recorded)
        except AppError:
            stuck.append(target)
            continue
        if changed:
            restored.append(target)

    if stuck:
        record["lines"] = {target: record["lines"][target] for target in stuck}
    else:
        del records[key]
    if not records:
        config.pop("patched", None)
    save_config(config)
    return restored, stuck


def _is_record(record) -> bool:
    return (
        isinstance(record, dict)
        and isinstance(record.get("owner"), str)
        and isinstance(record.get("lines"), dict)
        and all(
            target in _PATTERNS
            and isinstance(pairs, list)
            and all(
                isinstance(pair, list)
                and len(pair) == 2
                and all(isinstance(line, str) for line in pair)
                for pair in pairs
            )
            for target, pairs in record["lines"].items()
        )
    )


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
    patched = config.get("patched", {})
    if not isinstance(patched, dict) or not all(map(_is_record, patched.values())):
        raise AppError(f"{CONFIG_FILE.name}: « patched » invalide.")
    return config


def save_config(config: dict) -> None:
    kept = {key: value for key, value in config.items() if value is not None}
    try:
        CONFIG_FILE.write_text(
            json.dumps(kept, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        raise AppError(f"écriture impossible de {CONFIG_FILE.name}: {exc}") from None
