"""CLI to configure failure injection on a running mock server."""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from lib import i18n
from lib._paths import SEED

DEFAULT_URL = "http://localhost:8080"
PRESETS_FILE = SEED / "failure_presets.json"


def _server_url() -> str:
    return os.environ.get("MOCK_URL", DEFAULT_URL).rstrip("/")


def _load_presets() -> dict:
    return json.loads(PRESETS_FILE.read_text(encoding="utf-8"))


def _http(method: str, path: str, payload: dict | None = None) -> tuple[int, object]:
    url = f"{_server_url()}{path}"
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body_text = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(body_text)
            except json.JSONDecodeError:
                return resp.status, body_text
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8") if exc.fp else ""
        try:
            return exc.code, json.loads(body_text)
        except json.JSONDecodeError:
            return exc.code, body_text


def _print_response(status: int, body: object) -> int:
    if status >= 400:
        print(
            i18n.t("cli.failures.error_status", status=status, body=body),
            file=sys.stderr,
        )
        return 1
    if isinstance(body, (dict, list)):
        print(json.dumps(body, indent=2, ensure_ascii=False))
    else:
        print(body)
    return 0


def cmd_list() -> int:
    presets = _load_presets()
    if not presets:
        print(i18n.t("cli.failures.no_presets"))
        return 0
    print(f"{i18n.t('cli.failures.available_presets')}\n")
    name_width = max(len(n) for n in presets)
    for name, spec in presets.items():
        desc = i18n.describe("cli.presets", name, spec.get("description", ""))
        print(f"  {name:<{name_width}}  {desc}")
    print(f"\n{i18n.t('cli.failures.apply_hint')}")
    return 0


def cmd_status() -> int:
    status, body = _http("GET", "/admin/failures")
    return _print_response(status, body)


def cmd_reset() -> int:
    status, body = _http("DELETE", "/admin/failures")
    code = _print_response(status, body)
    if code == 0:
        print(i18n.t("cli.failures.reset_done"), file=sys.stderr)
    return code


def cmd_apply_preset(name: str) -> int:
    presets = _load_presets()
    if name not in presets:
        print(i18n.t("cli.failures.unknown_preset", name=name), file=sys.stderr)
        print(i18n.t("cli.failures.unknown_preset_hint"), file=sys.stderr)
        return 1
    config = presets[name].get("config", {})
    _http("DELETE", "/admin/failures")
    status, body = _http("PATCH", "/admin/failures", payload=config)
    code = _print_response(status, body)
    if code == 0:
        print(i18n.t("cli.failures.preset_applied", name=name), file=sys.stderr)
    return code


def _build_custom_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="manage_failures.py custom",
        description=i18n.t("cli.failures.custom_description"),
    )
    parser.add_argument("--latency", help=i18n.t("cli.failures.custom_latency"))
    parser.add_argument(
        "--error-rate", type=float, help=i18n.t("cli.failures.custom_error_rate")
    )
    parser.add_argument(
        "--fail", action="append", help=i18n.t("cli.failures.custom_fail")
    )
    parser.add_argument(
        "--timeout", action="append", help=i18n.t("cli.failures.custom_timeout")
    )
    parser.add_argument(
        "--timeout-duration",
        type=float,
        help=i18n.t("cli.failures.custom_timeout_duration"),
    )
    parser.add_argument(
        "--malformed",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=i18n.t("cli.failures.custom_malformed"),
    )
    parser.add_argument(
        "--auth",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=i18n.t("cli.failures.custom_auth"),
    )
    return parser


def _custom_args_to_config(args: argparse.Namespace) -> dict:
    config: dict = {}
    if args.latency is not None:
        config["latencyMs"] = args.latency
    if args.error_rate is not None:
        config["errorRate"] = args.error_rate
    if args.fail is not None:
        config["failEndpoints"] = args.fail
    if args.timeout is not None:
        config["timeoutEndpoints"] = args.timeout
    if args.timeout_duration is not None:
        config["timeoutDurationS"] = args.timeout_duration
    if args.malformed is not None:
        config["malformed"] = args.malformed
    if args.auth is not None:
        config["authRequired"] = args.auth
    return config


def cmd_custom(argv: list[str]) -> int:
    parser = _build_custom_parser()
    args = parser.parse_args(argv)
    config = _custom_args_to_config(args)
    if not config:
        parser.error(i18n.t("cli.failures.custom_needs_option"))
    _http("DELETE", "/admin/failures")
    status, body = _http("PATCH", "/admin/failures", payload=config)
    return _print_response(status, body)


def _print_usage() -> None:
    locales = i18n.available_locales()
    lang_flag = f"--lang {{{','.join(locales)}}}"
    lang_help = i18n.t("cli.common.lang_help", choices=", ".join(locales))
    lines = [
        i18n.t("cli.failures.usage"),
        "",
        i18n.t("cli.failures.usage_commands"),
        f"  {i18n.t('cli.failures.usage_list')}",
        f"  {i18n.t('cli.failures.usage_status')}",
        f"  {i18n.t('cli.failures.usage_reset')}",
        f"  {i18n.t('cli.failures.usage_custom')}",
        f"  {i18n.t('cli.failures.usage_preset')}",
        f"  {lang_flag:<22}{lang_help}",
        "",
        i18n.t("cli.failures.usage_server", url=_server_url()),
    ]
    print("\n".join(lines), file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    argv, lang = i18n.split_lang_arg(argv)
    i18n.set_locale(lang)
    if not argv or argv[0] in {"-h", "--help", "help"}:
        _print_usage()
        return 0
    cmd = argv[0]
    try:
        if cmd == "list":
            return cmd_list()
        if cmd == "status":
            return cmd_status()
        if cmd in {"reset", "off"}:
            return cmd_reset()
        if cmd == "custom":
            return cmd_custom(argv[1:])
        return cmd_apply_preset(cmd)
    except urllib.error.URLError as exc:
        print(
            i18n.t("cli.failures.unreachable", url=_server_url(), reason=exc.reason),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
