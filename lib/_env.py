import os
from collections.abc import Mapping

_TRUTHY = {"1", "true", "yes", "on"}


def env_bool(name: str, env: Mapping[str, str] = os.environ) -> bool:
    return env.get(name, "").strip().lower() in _TRUTHY


def env_number(name: str, parse, valid, default):
    try:
        value = parse(os.environ[name])
    except (KeyError, ValueError):
        return default
    return value if valid(value) else default
