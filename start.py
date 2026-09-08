import argparse
import json
import os
import signal
import subprocess
import sys

from lib._paths import SEED

OVERRIDES_FILENAME = "schedule_overrides.json"

DEFAULT_PROFILE = "normal"

TIME_CHOICES = ("morning", "afternoon", "evening")

MANAGED_ENV = (
    "PROFILE",
    "SCENARIO",
    "SEMESTER_WEEK",
    "COURSE_COUNT",
    "SCHEDULE_DAYS",
    "TIME_PREFERENCE",
)

CONFIG_FLAGS = ("profile", "scenario", "semester_week", "courses", "days", "time")

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


def _load_profiles() -> dict:
    return json.loads((SEED / "profiles.json").read_text(encoding="utf-8"))


def _load_scenarios() -> dict:
    return json.loads((SEED / "scenarios.json").read_text(encoding="utf-8"))


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


def _epilog(profiles: dict, scenarios: dict) -> str:
    lines = ["profils:"]
    for name in profiles:
        lines.append(f"  {name:<20}{PROFILE_DESCRIPTIONS.get(name, '')}")
    lines.append("")
    lines.append("scénarios:")
    for name, body in scenarios.items():
        desc = SCENARIO_DESCRIPTIONS.get(name) or body.get("description", "")
        lines.append(f"  {name:<20}{desc}")
    lines.append("")
    lines.append("codes de jour:")
    lines.append("  " + ", ".join(f"{c}={n}" for c, n in DAY_NAMES.items()))
    lines.append("")
    lines.append("exemples:")
    lines.append("  python start.py")
    lines.append("  python start.py --profile semester-off")
    lines.append("  python start.py --courses 2 --days 1,3,5 --time morning")
    lines.append("  python start.py --scenario semaine-relache --semester-week 3")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    profiles = _load_profiles()
    scenarios = _load_scenarios()

    parser = argparse.ArgumentParser(
        prog="python start.py",
        description=(
            "Démarre le serveur mock ETSMobileAPI. Sans argument, un menu "
            "interactif s'affiche; avec des options, le serveur démarre "
            "directement."
        ),
        epilog=_epilog(profiles, scenarios),
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
    return parser


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

    generated = any(
        getattr(args, name) is not None for name in ("courses", "days", "time")
    )
    base = args.profile or DEFAULT_PROFILE
    profile_display = f"{base} (personnalisé)" if generated else base

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

    print("\n=== Sélection du profil (Signets Mock) ===\n")
    for i, name in enumerate(names, 1):
        desc = PROFILE_DESCRIPTIONS.get(name, "")
        label = f"{name}: {desc}" if desc else name
        print(f"  {i}) {label}")
    print("\n  C) Personnalisé (choisir nombre de cours, jours, etc.)")
    print("  0) Quitter")

    while True:
        try:
            raw = input("\nChoix: ").strip()
        except (ValueError, EOFError):
            return None

        if raw.lower() == "c":
            return "__custom__"
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


def _clear_overrides() -> None:
    path = SEED / OVERRIDES_FILENAME
    try:
        if path.exists():
            path.unlink()
            print("Configuration précédente réinitialisée (overrides supprimés).")
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


def _config_from_menu() -> tuple[dict, str, str, int | None] | None:
    profile = _select_profile()
    if profile is None:
        print("Au revoir!")
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
    overrides: dict, profile_display: str, scenario: str, semester_week: int | None
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
        ],
        env=_build_env(overrides),
    )


def main(argv: list[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)

    if any(getattr(args, name) is not None for name in CONFIG_FLAGS):
        config = _config_from_args(args)
    else:
        config = _config_from_menu()

    if config is None:
        return

    _start_server(*config)


if __name__ == "__main__":
    main()
