import os

_TRUTHY = {"1", "true", "yes", "on"}


def env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def env_number(name: str, parse, valid, default):
    try:
        value = parse(os.environ[name])
    except (KeyError, ValueError):
        return default
    return value if valid(value) else default
