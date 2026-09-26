import argparse
import json
import os
import signal
import subprocess
import sys

from lib import snapshots
from lib._paths import SEED

OVERRIDES_FILENAME = "schedule_overrides.json"
STUDENT_OVERRIDES_FILENAME = "student_overrides.json"

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

DAY_NAMES = {
    "1": "Lundi",
    "2": "Mardi",
    "3": "Mercredi",
    "4": "Jeudi",
    "5": "Vendredi",
    "6": "Samedi",
}

PROFILE_DESCRIPTIONS = {
    "normal": "4 cours + labos, Lun-Ven jour seulement",
    "semester-off": "Aucun cours (session libre)",
    "internship-only": "Stage coopératif seulement",
    "internship-courses": "Stage coopératif + 2 cours du soir",
    "generated-light": "2 cours + labos, Lun-Ven matins",
    "generated-busy": "5 cours + labos, Lun-Ven",
    "generated-evening": "3 cours + labos, Lun-Ven soirs",
    "new-student": "Nouvel étudiant (aucune session)",
}

SCENARIO_DESCRIPTIONS = {
    "none": "Aucune modification au calendrier",
}

SCOPE_LABELS = {"personal": "personnel", "shared": "partagé"}

DATE_MODE_LABELS = {
    "week": "Même semaine de session",
    "exact": "Dates exactes",
    "setup": "Configuration seulement",
}


def _load_profiles() -> dict:
    return json.loads((SEED / "profiles.json").read_text(encoding="utf-8"))


def _load_scenarios() -> dict:
    return json.loads((SEED / "scenarios.json").read_text(encoding="utf-8"))


def _load_failure_presets() -> dict:
    return json.loads((SEED / "failure_presets.json").read_text(encoding="utf-8"))


def _day_list(raw: str) -> list[str]:
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    invalid = [p for p in parts if p not in DAY_NAMES]
    if not parts or invalid:
        codes = ", ".join(f"{c}={n}" for c, n in DAY_NAMES.items())
        raise argparse.ArgumentTypeError(
            f"invalid day code(s): {', '.join(invalid) or raw!r}. Valid codes: {codes}"
        )
    return parts


def _time_list(raw: str) -> str:
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    invalid = [p for p in parts if p not in TIME_CHOICES]
    if not parts or invalid:
        raise argparse.ArgumentTypeError(
            f"invalid time preference(s): {', '.join(invalid) or raw!r}. "
            f"Valid values: {', '.join(TIME_CHOICES)}"
        )
    return ",".join(parts)


def _latency(raw: str) -> str:
    text = raw.strip()
    parts = text.split("-", 1) if "-" in text else [text, text]
    try:
        lo, hi = int(parts[0]), int(parts[1])
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"expected milliseconds or a min-max range, got {raw!r}"
        ) from None
    if lo < 0 or hi < lo:
        raise argparse.ArgumentTypeError(f"invalid latency range: {raw!r}")
    return text


def _rate(raw: str) -> float:
    try:
        val = float(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"expected a number between 0.0 and 1.0, got {raw!r}"
        ) from None
    if not 0.0 <= val <= 1.0:
        raise argparse.ArgumentTypeError(
            f"expected a number between 0.0 and 1.0, got {val}"
        )
    return val


def _seconds(raw: str) -> float:
    try:
        val = float(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"expected a number of seconds, got {raw!r}"
        ) from None
    if val < 0:
        raise argparse.ArgumentTypeError(f"expected a number of seconds, got {val}")
    return val


def _bounded_int(low: int, high: int):
    def parse(raw: str) -> int:
        try:
            val = int(raw)
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"expected an integer between {low} and {high}, got {raw!r}"
            ) from None
        if val < low or val > high:
            raise argparse.ArgumentTypeError(
                f"expected an integer between {low} and {high}, got {val}"
            )
        return val

    return parse


def _snapshot_label(item: dict) -> str:
    anchor = item["anchor"]
    return (
        f"{item['name']} ({SCOPE_LABELS[item['scope']]}, {anchor['session']} "
        f"semaine {anchor['week']}, enregistré le {anchor['date']})"
    )


def _epilog(profiles: dict, scenarios: dict, presets: dict) -> str:
    lines = ["profils:"]
    for name in profiles:
        lines.append(f"  {name:<20}{PROFILE_DESCRIPTIONS.get(name, '')}")
    lines.append("")
    lines.append("scénarios:")
    for name, body in scenarios.items():
        desc = SCENARIO_DESCRIPTIONS.get(name) or body.get("description", "")
        lines.append(f"  {name:<20}{desc}")
    lines.append("")
    lines.append("pannes:")
    for name, body in presets.items():
        lines.append(f"  {name:<20}{body.get('description', '')}")
    lines.append("")
    lines.append("instantanés (onglet Instantanés de l'éditeur):")
    items = snapshots.list_all()
    for item in items:
        lines.append(f"  {item['scope'] + '/' + item['id']:<28}{_snapshot_label(item)}")
    if not items:
        lines.append("  (aucun)")
    lines.append("")
    lines.append("codes de jour:")
    lines.append("  " + ", ".join(f"{c}={n}" for c, n in DAY_NAMES.items()))
    lines.append("")
    lines.append("exemples:")
    lines.append("  python start.py")
    lines.append("  python start.py --profile semester-off")
    lines.append("  python start.py --courses 2 --days 1,3,5 --time morning")
    lines.append("  python start.py --scenario semaine-relache --semester-week 3")
    lines.append("  python start.py --failures flaky")
    lines.append("  python start.py --latency 200-600 --error-rate 0.1")
    lines.append('  python start.py --snapshot "examen final"')
    lines.append("  python start.py --snapshot shared/demo --snapshot-dates exact")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    profiles = _load_profiles()
    scenarios = _load_scenarios()
    presets = _load_failure_presets()

    parser = argparse.ArgumentParser(
        prog="python start.py",
        description=(
            "Démarre le serveur mock ETSMobileAPI. Sans argument, un menu "
            "interactif s'affiche; avec des options, le serveur démarre "
            "directement."
        ),
        epilog=_epilog(profiles, scenarios, presets),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--profile",
        choices=list(profiles),
        help=f"Profil étudiant à charger (défaut: {DEFAULT_PROFILE}).",
        default=None,
    )
    parser.add_argument(
        "--scenario",
        choices=list(scenarios),
        help="Modification du calendrier de la session active.",
        default=None,
    )
    parser.add_argument(
        "--semester-week",
        type=_bounded_int(1, 15),
        metavar="N",
        help="Décale la session pour qu'aujourd'hui tombe à la semaine N (1-15).",
        default=None,
    )
    parser.add_argument(
        "--courses",
        type=_bounded_int(1, 5),
        metavar="N",
        help="Nombre de cours générés (1-5).",
        default=None,
    )
    parser.add_argument(
        "--days",
        type=_day_list,
        metavar="1,3,5",
        help="Jours de cours, codes séparés par des virgules.",
        default=None,
    )
    parser.add_argument(
        "--time",
        type=_time_list,
        metavar="morning,evening",
        help=f"Plage horaire: {', '.join(TIME_CHOICES)} (séparées par des virgules).",
        default=None,
    )

    failures = parser.add_argument_group(
        "pannes",
        "Injection de pannes au démarrage. Les mêmes options existent à chaud "
        "avec manage_failures.py.",
    )
    failures.add_argument(
        "--failures",
        choices=list(presets),
        metavar="PRESET",
        help="Applique un préréglage de seed/failure_presets.json.",
        default=None,
    )
    failures.add_argument(
        "--latency",
        type=_latency,
        metavar="MS",
        help="Latence en ms, fixe ou intervalle (500 ou 100-800).",
        default=None,
    )
    failures.add_argument(
        "--error-rate",
        type=_rate,
        metavar="R",
        help="Probabilité (0.0-1.0) qu'un appel retourne 500.",
        default=None,
    )
    failures.add_argument(
        "--fail",
        action="append",
        metavar="ENDPOINT",
        help="Endpoint retournant 503 (répétable, '*' pour tous).",
        default=None,
    )
    failures.add_argument(
        "--timeout",
        action="append",
        metavar="ENDPOINT",
        help="Endpoint qui fige la requête (répétable, '*' pour tous).",
        default=None,
    )
    failures.add_argument(
        "--timeout-duration",
        type=_seconds,
        metavar="S",
        help="Secondes avant qu'un endpoint figé retourne 504.",
        default=None,
    )
    failures.add_argument(
        "--malformed",
        action=argparse.BooleanOptionalAction,
        help="Tronque de moitié chaque réponse 2xx.",
        default=None,
    )
    failures.add_argument(
        "--auth",
        action=argparse.BooleanOptionalAction,
        help="Exige un header Authorization.",
        default=None,
    )

    snapshot = parser.add_argument_group(
        "instantanés",
        "Charge un instantané enregistré depuis l'onglet Instantanés de l'éditeur. "
        "Ne se combine pas avec les options ci-dessus.",
    )
    snapshot.add_argument(
        "--snapshot",
        "--preset",
        dest="snapshot",
        metavar="NOM",
        help="Instantané à charger (nom, ou shared/nom et personal/nom).",
        default=None,
    )
    snapshot.add_argument(
        "--snapshot-dates",
        choices=snapshots.DATE_MODES,
        help="week: même semaine de session (défaut); exact: dates exactes; "
        "setup: configuration seulement, l'horaire est régénéré.",
        default=None,
    )
    snapshot.add_argument(
        "--no-snapshot-failures",
        dest="snapshot_failures",
        action="store_false",
        help="N'applique pas les pannes enregistrées dans l'instantané.",
        default=None,
    )
    return parser


def _failure_value(key: str, value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set)):
        return ",".join(str(v) for v in value)
    return str(value)


def _failure_env(config: dict) -> dict:
    return {
        FAILURE_ENV[k]: _failure_value(k, v) for k, v in config.items() if k in FAILURE_ENV
    }


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
        label = f"{label} + ajusté" if label else "personnalisées"

    return _failure_env(config), label


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
    profile_display = f"{base} (personnalisé)" if generated else base
    if failure_label:
        profile_display = f"{profile_display} + pannes « {failure_label} »"

    return overrides, profile_display, args.scenario or "none", args.semester_week


def _failure_summary(config: dict) -> str:
    parts = []
    if config.get("latencyMs"):
        parts.append(f"latence {config['latencyMs']} ms")
    if config.get("errorRate"):
        parts.append(f"erreurs aléatoires {round(config['errorRate'] * 100)} %")
    if config.get("failEndpoints"):
        parts.append(f"en panne: {', '.join(config['failEndpoints'])}")
    if config.get("timeoutEndpoints"):
        parts.append(f"figés: {', '.join(config['timeoutEndpoints'])}")
    if "timeoutDurationS" in config:
        parts.append(f"délai de {config['timeoutDurationS']} s")
    if config.get("malformed"):
        parts.append("réponses tronquées")
    if config.get("authRequired"):
        parts.append("authentification requise")
    return ", ".join(parts)


def _snapshot_config(
    scope: str, snapshot_id: str, mode: str, include_failures: bool
) -> tuple[dict, str, str, int | None, snapshots.Plan]:
    snapshot = snapshots.read(scope, snapshot_id)
    plan = snapshots.plan(snapshot, mode, failures=include_failures)
    overrides = snapshots.setup_to_env(plan.setup)
    if plan.failures:
        overrides.update(_failure_env(plan.failures))
    display = f"{plan.setup['profile']} + instantané « {snapshot['name']} »"
    scenario = plan.setup.get("scenario") or "none"
    return overrides, display, scenario, plan.setup.get("semesterWeek"), plan


def _config_from_snapshot(
    parser: argparse.ArgumentParser, args: argparse.Namespace
) -> tuple[dict, str, str, int | None, snapshots.Plan]:
    used = [
        "--" + name.replace("_", "-")
        for name in CONFIG_FLAGS
        if getattr(args, name) is not None
    ]
    if used:
        parser.error(f"--snapshot ne se combine pas avec {', '.join(used)}")
    matches = snapshots.find(args.snapshot)
    if not matches:
        known = ", ".join(f"{i['scope']}/{i['id']}" for i in snapshots.list_all())
        parser.error(
            f"instantané introuvable: {args.snapshot!r} "
            f"(disponibles: {known or 'aucun'})"
        )
    if len(matches) > 1:
        refs = " ou ".join(f"{scope}/{snapshot_id}" for scope, snapshot_id in matches)
        parser.error(
            f"plusieurs instantanés correspondent à {args.snapshot!r}: précisez {refs}"
        )
    scope, snapshot_id = matches[0]
    mode = args.snapshot_dates or snapshots.DEFAULT_DATE_MODE
    try:
        return _snapshot_config(
            scope, snapshot_id, mode, args.snapshot_failures is not False
        )
    except snapshots.SnapshotError as exc:
        parser.error(f"instantané illisible: {exc}")


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

    print("\n=== Sélection du profil (Signets Mock) ===\n")
    for i, name in enumerate(names, 1):
        desc = PROFILE_DESCRIPTIONS.get(name, "")
        label = f"{name}: {desc}" if desc else name
        print(f"  {i}) {label}")
    print("\n  C) Personnalisé (choisir nombre de cours, jours, etc.)")
    has_snapshots = bool(snapshots.list_all())
    if has_snapshots:
        print("  I) Charger un instantané")
    print("  0) Quitter")

    while True:
        try:
            raw = input("\nChoix: ").strip()
        except (ValueError, EOFError):
            return None

        if raw.lower() == "c":
            return "__custom__"
        if raw.lower() == "i" and has_snapshots:
            return "__snapshot__"
        if raw == "0":
            return None
        idx = _validate_menu_choice(raw, len(names))
        if idx is None:
            print("  Choix invalide, réessayez.")
            continue
        return names[idx - 1]


def _select_scenario() -> str:
    scenarios = _load_scenarios()
    names = [n for n in scenarios.keys() if n != "none"]

    if not names:
        return "none"

    print("\n=== Scénario calendrier (optionnel) ===\n")
    for i, name in enumerate(names, 1):
        desc = SCENARIO_DESCRIPTIONS.get(name) or scenarios[name].get("description", "")
        label = f"{name}: {desc}" if desc else name
        print(f"  {i}) {label}")
    print("\n  0) Aucun (par défaut)")

    while True:
        try:
            raw = input("\nChoix [0]: ").strip()
        except (ValueError, EOFError):
            return "none"

        if not raw or raw == "0":
            return "none"
        idx = _validate_menu_choice(raw, len(names))
        if idx is None:
            print("  Choix invalide, réessayez.")
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
            print(
                f"  Entrée invalide, veuillez entrer un nombre entre {low} et {high}."
            )
            continue
        if val < low or val > high:
            print(
                f"  Entrée invalide, veuillez entrer un nombre entre {low} et {high}."
            )
            continue
        return val


def _prompt_days() -> list[str] | None:
    print("\n  Jours disponibles:")
    for code, name in DAY_NAMES.items():
        print(f"    {code} = {name}")
    print()
    while True:
        try:
            raw = input("  Jours (ex: 1,3,5 pour Lun/Mer/Ven, vide = tous): ").strip()
        except EOFError:
            return None
        if not raw:
            return None
        parts = [p.strip() for p in raw.split(",")]
        valid = [p for p in parts if p in DAY_NAMES]
        if valid:
            return valid
        print("  Entrée invalide, utilisez les codes 1-6 séparés par des virgules.")


def _prompt_semester_week() -> int | None:
    print("\n=== Semaine de la session (optionnel) ===\n")
    print("  À quelle semaine de la session active voulez-vous être?")
    print("  Utile si la session réelle est presque terminée.")
    print("  (Vide = utiliser les dates réelles)")
    while True:
        try:
            raw = input("\n  Semaine (1-15, vide = réelle): ").strip()
        except EOFError:
            return None
        if not raw:
            return None
        try:
            week = int(raw)
        except ValueError:
            print("  Entrée invalide, entrez un nombre entre 1 et 15.")
            continue
        if week < 1 or week > 15:
            print("  Entrée invalide, entrez un nombre entre 1 et 15.")
            continue
        return week


def _prompt_time_preference() -> str | None:
    print("\n  Plage horaire (plusieurs possibles, ex: 1,3):")
    print("    1) Matin (09:00-12:30)")
    print("    2) Après-midi (13:30-17:00)")
    print("    3) Soir (18:00-21:30)")
    print("    4) Aucune préférence")
    mapping = {"1": "morning", "2": "afternoon", "3": "evening"}
    while True:
        try:
            raw = input("  Choix [4]: ").strip()
        except EOFError:
            return None
        if not raw or raw == "4":
            return None
        parts = [p.strip() for p in raw.split(",")]
        prefs = [mapping[p] for p in parts if p in mapping]
        if prefs:
            return ",".join(prefs)
        print("  Entrée invalide, utilisez les choix 1-4 séparés par des virgules.")


def _configure_custom() -> dict | None:
    print("\n=== Configuration personnalisée ===")

    count = _prompt_int("\n  Nombre de cours (1-5) [3]: ", 1, 5, 3)
    allowed_days = _prompt_days()
    time_pref = _prompt_time_preference()

    days_display = (
        ", ".join(DAY_NAMES[d] for d in allowed_days) if allowed_days else "Tous"
    )
    time_labels = {"morning": "Matin", "afternoon": "Après-midi", "evening": "Soir"}
    time_display = (
        ", ".join(time_labels[t] for t in time_pref.split(","))
        if time_pref
        else "Aucune"
    )

    print("\n  Résumé:")
    print(f"    Cours:    {count}")
    print(f"    Jours:    {days_display}")
    print(f"    Plage:    {time_display}")

    try:
        confirm = input("\n  Confirmer? (O/n): ").strip().lower()
    except EOFError:
        confirm = "o"
    if confirm == "n":
        return None

    return {
        "count": count,
        "allowedDays": allowed_days,
        "timePreference": time_pref,
    }


def _select_snapshot() -> dict | None:
    items = snapshots.list_all()
    print("\n=== Instantanés ===\n")
    for i, item in enumerate(items, 1):
        print(f"  {i}) {_snapshot_label(item)}")
    print("\n  0) Annuler")

    while True:
        try:
            raw = input("\nChoix: ").strip()
        except (ValueError, EOFError):
            return None
        if raw == "0":
            return None
        idx = _validate_menu_choice(raw, len(items))
        if idx is None:
            print("  Choix invalide, réessayez.")
            continue
        return items[idx - 1]


def _prompt_snapshot_dates(item: dict) -> str:
    anchor = item["anchor"]
    details = {
        "week": f"la semaine {anchor['week']} de {anchor['session']} devient la "
        "semaine courante",
        "exact": f"dates telles qu'enregistrées le {anchor['date']} (réglez "
        "l'horloge du téléphone)",
        "setup": "profil, scénario, semaine, options et pannes; l'horaire est "
        "régénéré à partir d'aujourd'hui",
    }
    print("\n=== Dates de l'instantané ===\n")
    for i, mode in enumerate(snapshots.DATE_MODES, 1):
        print(f"  {i}) {DATE_MODE_LABELS[mode]}: {details[mode]}")
    while True:
        try:
            raw = input("\nChoix [1]: ").strip()
        except EOFError:
            return snapshots.DEFAULT_DATE_MODE
        if not raw:
            return snapshots.DEFAULT_DATE_MODE
        idx = _validate_menu_choice(raw, len(snapshots.DATE_MODES))
        if idx is None:
            print("  Choix invalide, réessayez.")
            continue
        return snapshots.DATE_MODES[idx - 1]


def _prompt_snapshot_failures(item: dict) -> bool:
    if not item["failures"]:
        return False
    print(f"\n  Pannes enregistrées: {_failure_summary(item['failures'])}")
    try:
        confirm = input("  Appliquer les pannes? (O/n): ").strip().lower()
    except EOFError:
        confirm = "o"
    return confirm != "n"


def _config_from_snapshot_menu() -> (
    tuple[dict, str, str, int | None, snapshots.Plan] | None
):
    item = _select_snapshot()
    if item is None:
        print("Annulé.")
        return None
    mode = _prompt_snapshot_dates(item)
    include_failures = _prompt_snapshot_failures(item)
    return _snapshot_config(item["scope"], item["id"], mode, include_failures)


def _clear_overrides() -> None:
    cleared = False
    for name in (OVERRIDES_FILENAME, STUDENT_OVERRIDES_FILENAME):
        path = SEED / name
        try:
            if path.exists():
                path.unlink()
                cleared = True
        except OSError:
            pass
    if cleared:
        print("Configuration précédente réinitialisée (overrides supprimés).")


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

    print(f"Arrêt de {len(pids)} serveur(s) déjà en cours...")
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


def _config_from_menu() -> (
    tuple[dict, str, str, int | None]
    | tuple[dict, str, str, int | None, snapshots.Plan]
    | None
):
    profile = _select_profile()
    if profile is None:
        print("Au revoir!")
        return None
    if profile == "__snapshot__":
        return _config_from_snapshot_menu()

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
            print("Annulé.")
            return None
        overrides["PROFILE"] = DEFAULT_PROFILE
        overrides["COURSE_COUNT"] = str(config["count"])
        if config["allowedDays"]:
            overrides["SCHEDULE_DAYS"] = ",".join(config["allowedDays"])
        overrides["TIME_PREFERENCE"] = config["timePreference"] or ""
        profile_display = "Personnalisé"
    else:
        overrides["PROFILE"] = profile
        profile_display = profile

    return overrides, profile_display, scenario, semester_week


def _build_env(overrides: dict) -> dict:
    env = os.environ.copy()
    for name in MANAGED_ENV:
        env.pop(name, None)
    env.update(overrides)
    return env


def _start_server(
    overrides: dict,
    profile_display: str,
    scenario: str,
    semester_week: int | None,
    snapshot: snapshots.Plan | None = None,
) -> None:
    scenario_display = f" + scénario « {scenario} »" if scenario != "none" else ""
    week_display = f" + semaine {semester_week}" if semester_week is not None else ""
    print(
        f"\nDémarrage du serveur avec le profil « {profile_display} »"
        f"{scenario_display}{week_display}...\n"
    )
    print("  API   : http://localhost:8080/docs")
    print("  Horaire (éditeur visuel) : http://localhost:8080/editor\n")

    _stop_existing_servers()
    _clear_overrides()
    snapshot_dir = snapshots.snapshots_dir()
    snapshot_dir.mkdir(exist_ok=True)
    if snapshot is not None:
        snapshots.write_overrides(
            snapshot.schedule,
            snapshot.student,
            SEED / OVERRIDES_FILENAME,
            SEED / STUDENT_OVERRIDES_FILENAME,
        )
        for notice in snapshot.notices:
            print(f"  {notice}")

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
            "--reload-exclude",
            STUDENT_OVERRIDES_FILENAME,
            "--reload-exclude",
            str(snapshot_dir),
        ],
        env=_build_env(overrides),
    )


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.snapshot is not None:
        config = _config_from_snapshot(parser, args)
    elif args.snapshot_dates is not None or args.snapshot_failures is not None:
        parser.error("--snapshot-dates et --no-snapshot-failures exigent --snapshot")
    elif any(getattr(args, name) is not None for name in CONFIG_FLAGS):
        config = _config_from_args(args)
    else:
        config = _config_from_menu()

    if config is None:
        return

    _start_server(*config)


if __name__ == "__main__":
    main()
