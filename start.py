import argparse
import json
import os
import signal
import subprocess
import sys

from lib import i18n
from lib._paths import SEED

OVERRIDES_FILENAME = "schedule_overrides.json"

DEFAULT_PROFILE = "normal"

TIME_CHOICES = ("morning", "afternoon", "evening")

FAILURE_ENV = {
    "latencyMs": "LATENCY_MS",
    "errorRate": "ERROR_RATE",
    "failEndpoints": "FAIL_ENDPOINTS",
    "timeoutEndpoints": "TIMEOUT_ENDPOINTS",
    "timeoutDurationS": "TIMEOUT_DURATION_S",
    "malformed": "MALFORMED",
    "authRequired": "AUTH_REQUIRED",
}

MANAGED_ENV = (
    "PROFILE",
    "SCENARIO",
    "SEMESTER_WEEK",
    "COURSE_COUNT",
    "SCHEDULE_DAYS",
    "TIME_PREFERENCE",
    *FAILURE_ENV.values(),
)

CONFIG_FLAGS = (
    "profile",
    "scenario",
    "semester_week",
    "courses",
    "days",
    "time",
    "failures",
    "latency",
    "error_rate",
    "fail",
    "timeout",
    "timeout_duration",
    "malformed",
    "auth",
)

DAY_CODES = ("1", "2", "3", "4", "5", "6")


def _day_name(code: str) -> str:
    return i18n.t(f"cli.days.{code}")


def _day_names() -> dict[str, str]:
    return {code: _day_name(code) for code in DAY_CODES}


def _load_profiles() -> dict:
    return json.loads((SEED / "profiles.json").read_text(encoding="utf-8"))


def _load_scenarios() -> dict:
    return json.loads((SEED / "scenarios.json").read_text(encoding="utf-8"))


def _load_failure_presets() -> dict:
    return json.loads((SEED / "failure_presets.json").read_text(encoding="utf-8"))


def _day_list(raw: str) -> list[str]:
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    invalid = [p for p in parts if p not in DAY_CODES]
    if not parts or invalid:
        codes = ", ".join(f"{c}={n}" for c, n in _day_names().items())
        raise argparse.ArgumentTypeError(
            i18n.t(
                "cli.start.errors.invalid_days",
                value=", ".join(invalid) or repr(raw),
                codes=codes,
            )
        )
    return parts


def _time_list(raw: str) -> str:
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    invalid = [p for p in parts if p not in TIME_CHOICES]
    if not parts or invalid:
        raise argparse.ArgumentTypeError(
            i18n.t(
                "cli.start.errors.invalid_times",
                value=", ".join(invalid) or repr(raw),
                choices=", ".join(TIME_CHOICES),
            )
        )
    return ",".join(parts)


def _latency(raw: str) -> str:
    text = raw.strip()
    parts = text.split("-", 1) if "-" in text else [text, text]
    try:
        lo, hi = int(parts[0]), int(parts[1])
    except ValueError:
        raise argparse.ArgumentTypeError(
            i18n.t("cli.start.errors.latency_format", value=repr(raw))
        ) from None
    if lo < 0 or hi < lo:
        raise argparse.ArgumentTypeError(
            i18n.t("cli.start.errors.latency_range", value=repr(raw))
        )
    return text


def _rate(raw: str) -> float:
    try:
        val = float(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(
            i18n.t("cli.start.errors.rate", value=repr(raw))
        ) from None
    if not 0.0 <= val <= 1.0:
        raise argparse.ArgumentTypeError(i18n.t("cli.start.errors.rate", value=val))
    return val


def _seconds(raw: str) -> float:
    try:
        val = float(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(
            i18n.t("cli.start.errors.seconds", value=repr(raw))
        ) from None
    if val < 0:
        raise argparse.ArgumentTypeError(i18n.t("cli.start.errors.seconds", value=val))
    return val


def _bounded_int(low: int, high: int):
    def parse(raw: str) -> int:
        try:
            val = int(raw)
        except ValueError:
            raise argparse.ArgumentTypeError(
                i18n.t(
                    "cli.start.errors.bounded_int",
                    low=low,
                    high=high,
                    value=repr(raw),
                )
            ) from None
        if val < low or val > high:
            raise argparse.ArgumentTypeError(
                i18n.t("cli.start.errors.bounded_int", low=low, high=high, value=val)
            )
        return val

    return parse


def _epilog(profiles: dict, scenarios: dict, presets: dict) -> str:
    lines = [i18n.t("cli.start.epilog.profiles")]
    for name in profiles:
        lines.append(f"  {name:<20}{i18n.describe('cli.profiles', name)}")
    lines.append("")
    lines.append(i18n.t("cli.start.epilog.scenarios"))
    for name, body in scenarios.items():
        desc = i18n.describe("cli.scenarios", name, body.get("description", ""))
        lines.append(f"  {name:<20}{desc}")
    lines.append("")
    lines.append(i18n.t("cli.start.epilog.failures"))
    for name, body in presets.items():
        desc = i18n.describe("cli.presets", name, body.get("description", ""))
        lines.append(f"  {name:<20}{desc}")
    lines.append("")
    lines.append(i18n.t("cli.start.epilog.day_codes"))
    lines.append("  " + ", ".join(f"{c}={n}" for c, n in _day_names().items()))
    lines.append("")
    lines.append(i18n.t("cli.start.epilog.examples"))
    lines.append("  python start.py")
    lines.append("  python start.py --profile semester-off")
    lines.append("  python start.py --courses 2 --days 1,3,5 --time morning")
    lines.append("  python start.py --scenario semaine-relache --semester-week 3")
    lines.append("  python start.py --failures flaky")
    lines.append("  python start.py --latency 200-600 --error-rate 0.1")
    lines.append("  python start.py --lang en")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    profiles = _load_profiles()
    scenarios = _load_scenarios()
    presets = _load_failure_presets()

    parser = argparse.ArgumentParser(
        prog="python start.py",
        description=i18n.t("cli.start.description"),
        epilog=_epilog(profiles, scenarios, presets),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--lang",
        choices=i18n.available_locales(),
        help=i18n.t(
            "cli.common.lang_help", choices=", ".join(i18n.available_locales())
        ),
        default=None,
    )
    parser.add_argument(
        "--profile",
        choices=list(profiles),
        help=i18n.t("cli.start.flags.profile", default=DEFAULT_PROFILE),
        default=None,
    )
    parser.add_argument(
        "--scenario",
        choices=list(scenarios),
        help=i18n.t("cli.start.flags.scenario"),
        default=None,
    )
    parser.add_argument(
        "--semester-week",
        type=_bounded_int(1, 15),
        metavar="N",
        help=i18n.t("cli.start.flags.semester_week"),
        default=None,
    )
    parser.add_argument(
        "--courses",
        type=_bounded_int(1, 5),
        metavar="N",
        help=i18n.t("cli.start.flags.courses"),
        default=None,
    )
    parser.add_argument(
        "--days",
        type=_day_list,
        metavar="1,3,5",
        help=i18n.t("cli.start.flags.days"),
        default=None,
    )
    parser.add_argument(
        "--time",
        type=_time_list,
        metavar="morning,evening",
        help=i18n.t("cli.start.flags.time", choices=", ".join(TIME_CHOICES)),
        default=None,
    )

    failures = parser.add_argument_group(
        i18n.t("cli.start.flags.group_title"),
        i18n.t("cli.start.flags.group_description"),
    )
    failures.add_argument(
        "--failures",
        choices=list(presets),
        metavar="PRESET",
        help=i18n.t("cli.start.flags.failures"),
        default=None,
    )
    failures.add_argument(
        "--latency",
        type=_latency,
        metavar="MS",
        help=i18n.t("cli.start.flags.latency"),
        default=None,
    )
    failures.add_argument(
        "--error-rate",
        type=_rate,
        metavar="R",
        help=i18n.t("cli.start.flags.error_rate"),
        default=None,
    )
    failures.add_argument(
        "--fail",
        action="append",
        metavar="ENDPOINT",
        help=i18n.t("cli.start.flags.fail"),
        default=None,
    )
    failures.add_argument(
        "--timeout",
        action="append",
        metavar="ENDPOINT",
        help=i18n.t("cli.start.flags.timeout"),
        default=None,
    )
    failures.add_argument(
        "--timeout-duration",
        type=_seconds,
        metavar="S",
        help=i18n.t("cli.start.flags.timeout_duration"),
        default=None,
    )
    failures.add_argument(
        "--malformed",
        action=argparse.BooleanOptionalAction,
        help=i18n.t("cli.start.flags.malformed"),
        default=None,
    )
    failures.add_argument(
        "--auth",
        action=argparse.BooleanOptionalAction,
        help=i18n.t("cli.start.flags.auth"),
        default=None,
    )
    return parser


def _failure_value(key: str, value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set)):
        return ",".join(str(v) for v in value)
    return str(value)


def _failure_overrides(args: argparse.Namespace) -> tuple[dict, str]:
    config: dict = {}
    label = ""

    if args.failures is not None:
        preset = _load_failure_presets()[args.failures]
        config.update(preset.get("config", {}))
        label = args.failures

    explicit = {
        "latencyMs": args.latency,
        "errorRate": args.error_rate,
        "failEndpoints": args.fail,
        "timeoutEndpoints": args.timeout,
        "timeoutDurationS": args.timeout_duration,
        "malformed": args.malformed,
        "authRequired": args.auth,
    }
    overrides = {k: v for k, v in explicit.items() if v is not None}
    if overrides:
        config.update(overrides)
        label = (
            i18n.t("cli.start.run.failure_adjusted", preset=label)
            if label
            else i18n.t("cli.start.run.failure_custom")
        )

    return (
        {FAILURE_ENV[k]: _failure_value(k, v) for k, v in config.items()},
        label,
    )


def _config_from_args(args: argparse.Namespace) -> tuple[dict, str, str, int | None]:
    overrides: dict[str, str] = {}
    if args.profile is not None:
        overrides["PROFILE"] = args.profile
    if args.scenario is not None and args.scenario != "none":
        overrides["SCENARIO"] = args.scenario
    if args.semester_week is not None:
        overrides["SEMESTER_WEEK"] = str(args.semester_week)
    if args.courses is not None:
        overrides["COURSE_COUNT"] = str(args.courses)
    if args.days is not None:
        overrides["SCHEDULE_DAYS"] = ",".join(args.days)
    if args.time is not None:
        overrides["TIME_PREFERENCE"] = args.time

    failure_env, failure_label = _failure_overrides(args)
    overrides.update(failure_env)

    generated = any(
        getattr(args, name) is not None for name in ("courses", "days", "time")
    )
    base = args.profile or DEFAULT_PROFILE
    profile_display = (
        i18n.t("cli.start.run.custom_profile", profile=base) if generated else base
    )
    if failure_label:
        profile_display = i18n.t(
            "cli.start.run.profile_with_failures",
            profile=profile_display,
            label=failure_label,
        )

    return overrides, profile_display, args.scenario or "none", args.semester_week


def _validate_menu_choice(raw: str, max_choices: int) -> int | None:
    try:
        idx = int(raw)
    except ValueError:
        return None
    if idx < 1 or idx > max_choices:
        return None
    return idx


def _select_profile() -> str | None:
    profiles = _load_profiles()
    names = list(profiles.keys())

    print(f"\n{i18n.t('cli.start.menu.profile_title')}\n")
    for i, name in enumerate(names, 1):
        desc = i18n.describe("cli.profiles", name)
        label = f"{name}: {desc}" if desc else name
        print(f"  {i}) {label}")
    print(f"\n  {i18n.t('cli.start.menu.custom_entry')}")
    print(f"  {i18n.t('cli.start.menu.quit_entry')}")

    while True:
        try:
            raw = input(f"\n{i18n.t('cli.common.choice_prompt')}").strip()
        except (ValueError, EOFError):
            return None

        if raw.lower() == "c":
            return "__custom__"
        if raw == "0":
            return None
        idx = _validate_menu_choice(raw, len(names))
        if idx is None:
            print(f"  {i18n.t('cli.common.invalid_choice_retry')}")
            continue
        return names[idx - 1]


def _select_scenario() -> str:
    scenarios = _load_scenarios()
    names = [n for n in scenarios.keys() if n != "none"]

    if not names:
        return "none"

    print(f"\n{i18n.t('cli.start.menu.scenario_title')}\n")
    for i, name in enumerate(names, 1):
        desc = i18n.describe(
            "cli.scenarios", name, scenarios[name].get("description", "")
        )
        label = f"{name}: {desc}" if desc else name
        print(f"  {i}) {label}")
    print(f"\n  {i18n.t('cli.start.menu.scenario_none')}")

    while True:
        try:
            raw = input(f"\n{i18n.t('cli.start.menu.scenario_prompt')}").strip()
        except (ValueError, EOFError):
            return "none"

        if not raw or raw == "0":
            return "none"
        idx = _validate_menu_choice(raw, len(names))
        if idx is None:
            print(f"  {i18n.t('cli.common.invalid_choice_retry')}")
            continue
        return names[idx - 1]


def _prompt_int(prompt: str, low: int, high: int, default: int) -> int:
    while True:
        try:
            raw = input(prompt).strip()
        except EOFError:
            return default
        if not raw:
            return default
        try:
            val = int(raw)
        except ValueError:
            print(f"  {i18n.t('cli.start.custom.number_invalid', low=low, high=high)}")
            continue
        if val < low or val > high:
            print(f"  {i18n.t('cli.start.custom.number_invalid', low=low, high=high)}")
            continue
        return val


def _prompt_days() -> list[str] | None:
    print(f"\n  {i18n.t('cli.start.custom.days_available')}")
    for code, name in _day_names().items():
        print(f"    {code} = {name}")
    print()
    while True:
        try:
            raw = input(f"  {i18n.t('cli.start.custom.days_prompt')}").strip()
        except EOFError:
            return None
        if not raw:
            return None
        parts = [p.strip() for p in raw.split(",")]
        valid = [p for p in parts if p in DAY_CODES]
        if valid:
            return valid
        print(f"  {i18n.t('cli.start.custom.days_invalid')}")


def _prompt_semester_week() -> int | None:
    print(f"\n{i18n.t('cli.start.week.title')}\n")
    print(f"  {i18n.t('cli.start.week.question')}")
    print(f"  {i18n.t('cli.start.week.hint')}")
    print(f"  {i18n.t('cli.start.week.default_hint')}")
    while True:
        try:
            raw = input(f"\n  {i18n.t('cli.start.week.prompt')}").strip()
        except EOFError:
            return None
        if not raw:
            return None
        try:
            week = int(raw)
        except ValueError:
            print(f"  {i18n.t('cli.start.week.invalid')}")
            continue
        if week < 1 or week > 15:
            print(f"  {i18n.t('cli.start.week.invalid')}")
            continue
        return week


def _prompt_time_preference() -> str | None:
    print(f"\n  {i18n.t('cli.start.time_preference.title')}")
    print(f"    1) {i18n.t('cli.start.time_preference.morning')}")
    print(f"    2) {i18n.t('cli.start.time_preference.afternoon')}")
    print(f"    3) {i18n.t('cli.start.time_preference.evening')}")
    print(f"    4) {i18n.t('cli.start.time_preference.none')}")
    mapping = {"1": "morning", "2": "afternoon", "3": "evening"}
    while True:
        try:
            raw = input(f"  {i18n.t('cli.start.time_preference.prompt')}").strip()
        except EOFError:
            return None
        if not raw or raw == "4":
            return None
        parts = [p.strip() for p in raw.split(",")]
        prefs = [mapping[p] for p in parts if p in mapping]
        if prefs:
            return ",".join(prefs)
        print(f"  {i18n.t('cli.start.time_preference.invalid')}")


def _configure_custom() -> dict | None:
    print(f"\n{i18n.t('cli.start.custom.title')}")

    count = _prompt_int(f"\n  {i18n.t('cli.start.custom.count_prompt')}", 1, 5, 3)
    allowed_days = _prompt_days()
    time_pref = _prompt_time_preference()

    days_display = (
        ", ".join(_day_name(d) for d in allowed_days)
        if allowed_days
        else i18n.t("cli.start.custom.all_days")
    )
    time_labels = {
        "morning": i18n.t("cli.start.time_preference.label_morning"),
        "afternoon": i18n.t("cli.start.time_preference.label_afternoon"),
        "evening": i18n.t("cli.start.time_preference.label_evening"),
    }
    time_display = (
        ", ".join(time_labels[t] for t in time_pref.split(","))
        if time_pref
        else i18n.t("cli.start.custom.no_time")
    )

    print(f"\n  {i18n.t('cli.start.custom.summary')}")
    print(f"    {i18n.t('cli.start.custom.summary_courses'):<10}{count}")
    print(f"    {i18n.t('cli.start.custom.summary_days'):<10}{days_display}")
    print(f"    {i18n.t('cli.start.custom.summary_time'):<10}{time_display}")

    try:
        confirm = input(f"\n  {i18n.t('cli.start.custom.confirm')}").strip().lower()
    except EOFError:
        confirm = ""
    if confirm == i18n.t("cli.start.custom.confirm_no"):
        return None

    return {
        "count": count,
        "allowedDays": allowed_days,
        "timePreference": time_pref,
    }


def _clear_overrides() -> None:
    path = SEED / OVERRIDES_FILENAME
    try:
        if path.exists():
            path.unlink()
            print(i18n.t("cli.start.run.overrides_cleared"))
    except OSError:
        pass


def _stop_existing_servers() -> None:
    self_pid = os.getpid()

    def _pids_matching() -> list[int]:
        pids: list[int] = []
        try:
            if os.name == "nt":
                out = subprocess.run(
                    [
                        "powershell",
                        "-NoProfile",
                        "-Command",
                        "Get-CimInstance Win32_Process "
                        "| Where-Object { $_.ProcessId -ne $PID "
                        "-and $_.CommandLine -match 'uvicorn' "
                        "-and $_.CommandLine -match 'main:app' } "
                        "| Select-Object -ExpandProperty ProcessId",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                lines = out.stdout.split()
            else:
                out = subprocess.run(
                    ["pgrep", "-f", "uvicorn.*main:app"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                lines = out.stdout.split()
        except (OSError, subprocess.SubprocessError):
            return []
        for line in lines:
            try:
                pid = int(line.strip())
            except ValueError:
                continue
            if pid != self_pid:
                pids.append(pid)
        return pids

    pids = _pids_matching()
    if not pids:
        return

    print(i18n.t("cli.start.run.stopping_servers", count=len(pids)))
    for pid in pids:
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                    timeout=15,
                )
            else:
                os.kill(pid, signal.SIGTERM)
        except (OSError, subprocess.SubprocessError):
            pass


def _config_from_menu() -> tuple[dict, str, str, int | None] | None:
    profile = _select_profile()
    if profile is None:
        print(i18n.t("cli.common.goodbye"))
        return None

    scenario = _select_scenario()
    semester_week = _prompt_semester_week()

    overrides: dict[str, str] = {}
    if scenario != "none":
        overrides["SCENARIO"] = scenario
    if semester_week is not None:
        overrides["SEMESTER_WEEK"] = str(semester_week)

    if profile == "__custom__":
        config = _configure_custom()
        if config is None:
            print(i18n.t("cli.common.cancelled"))
            return None
        overrides["PROFILE"] = DEFAULT_PROFILE
        overrides["COURSE_COUNT"] = str(config["count"])
        if config["allowedDays"]:
            overrides["SCHEDULE_DAYS"] = ",".join(config["allowedDays"])
        overrides["TIME_PREFERENCE"] = config["timePreference"] or ""
        profile_display = i18n.t("cli.start.run.custom_profile_menu")
    else:
        overrides["PROFILE"] = profile
        profile_display = profile

    return overrides, profile_display, scenario, semester_week


def _build_env(overrides: dict) -> dict:
    env = os.environ.copy()
    for name in MANAGED_ENV:
        env.pop(name, None)
    env[i18n.LANG_ENV] = i18n.get_locale()
    env.update(overrides)
    return env


def _start_server(
    overrides: dict, profile_display: str, scenario: str, semester_week: int | None
) -> None:
    scenario_display = (
        i18n.t("cli.start.run.with_scenario", scenario=scenario)
        if scenario != "none"
        else ""
    )
    week_display = (
        i18n.t("cli.start.run.with_week", week=semester_week)
        if semester_week is not None
        else ""
    )
    print(
        "\n"
        + i18n.t(
            "cli.start.run.starting",
            profile=profile_display,
            scenario=scenario_display,
            week=week_display,
        )
        + "\n"
    )
    api_url = i18n.t("cli.start.run.api_url", url="http://localhost:8080/docs")
    editor_url = i18n.t("cli.start.run.editor_url", url="http://localhost:8080/editor")
    print(f"  {api_url}")
    print(f"  {editor_url}\n")

    _stop_existing_servers()
    _clear_overrides()

    subprocess.run(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8080",
            "--reload",
            "--reload-include",
            "*.json",
            "--reload-exclude",
            OVERRIDES_FILENAME,
        ],
        env=_build_env(overrides),
    )


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    _, lang = i18n.split_lang_arg(argv)
    i18n.set_locale(lang)

    args = _build_parser().parse_args(argv)
    i18n.set_locale(args.lang)

    if any(getattr(args, name) is not None for name in CONFIG_FLAGS):
        config = _config_from_args(args)
    else:
        config = _config_from_menu()

    if config is None:
        return

    _start_server(*config)


if __name__ == "__main__":
    main()
