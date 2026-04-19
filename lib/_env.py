import os

_TRUTHY = {"1", "true", "yes", "on"}


def env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY
