import ctypes
import json
import os
import sys
from contextvars import ContextVar
from functools import cache

from ._paths import ROOT

LOCALES = ROOT / "locales"
DEFAULT_LOCALE = "fr"
LANG_ENV = "MOCK_LANG"
LANG_FLAG = "--lang"

_SYSTEM_ENV = ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE")
_LOCALE_NAME_MAX_LENGTH = 85

_catalogs: dict[str, dict] = {}
_current: ContextVar[str] = ContextVar("locale", default=DEFAULT_LOCALE)


@cache
def available_locales() -> tuple[str, ...]:
    found = sorted(path.stem for path in LOCALES.glob("*.json"))
    return (DEFAULT_LOCALE, *(code for code in found if code != DEFAULT_LOCALE))


def normalize(raw: str | None) -> str | None:
    if not raw:
        return None
    tag = str(raw).strip().split(".")[0].replace("_", "-").split("-")[0].lower()
    return tag if tag in available_locales() else None


def os_locale() -> str | None:
    """Locale reported by the OS. Windows sets none of the _SYSTEM_ENV vars."""
    if sys.platform != "win32":
        return None
    buffer = ctypes.create_unicode_buffer(_LOCALE_NAME_MAX_LENGTH)
    if not ctypes.windll.kernel32.GetUserDefaultLocaleName(
        buffer, _LOCALE_NAME_MAX_LENGTH
    ):
        return None
    return buffer.value or None


def system_locale() -> str | None:
    for name in _SYSTEM_ENV:
        for part in os.environ.get(name, "").split(":"):
            code = normalize(part)
            if code:
                return code
    return normalize(os_locale())


def resolve(explicit: str | None = None) -> str:
    return (
        normalize(explicit)
        or normalize(os.environ.get(LANG_ENV))
        or system_locale()
        or DEFAULT_LOCALE
    )


def get_locale() -> str:
    return _current.get()


def set_locale(explicit: str | None = None) -> str:
    code = resolve(explicit)
    _current.set(code)
    return code


def split_lang_arg(argv: list[str]) -> tuple[list[str], str | None]:
    rest: list[str] = []
    lang: str | None = None
    index = 0
    while index < len(argv):
        item = argv[index]
        if item == LANG_FLAG and index + 1 < len(argv):
            lang = argv[index + 1]
            index += 2
            continue
        if item.startswith(f"{LANG_FLAG}="):
            lang = item.split("=", 1)[1]
            index += 1
            continue
        rest.append(item)
        index += 1
    return rest, lang


def catalog(locale: str | None = None) -> dict:
    code = locale or get_locale()
    if code not in _catalogs:
        path = LOCALES / f"{code}.json"
        _catalogs[code] = (
            json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        )
    return _catalogs[code]


def _lookup(data: dict, key: str):
    node = data
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def lookup(key: str, locale: str | None = None):
    value = _lookup(catalog(locale), key)
    if value is None and (locale or get_locale()) != DEFAULT_LOCALE:
        value = _lookup(catalog(DEFAULT_LOCALE), key)
    return value


def t(key: str, **params) -> str:
    value = lookup(key)
    if not isinstance(value, str):
        return key
    return value.format(**params) if params else value


def values(key: str) -> list:
    value = lookup(key)
    return value if isinstance(value, list) else []


def describe(namespace: str, name: str, fallback: str = "") -> str:
    value = lookup(f"{namespace}.{name}")
    return value if isinstance(value, str) else fallback
