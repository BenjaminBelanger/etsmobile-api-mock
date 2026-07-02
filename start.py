"""Interactive launcher for the mock server (profile/scenario/schedule selection)."""

import json
import os
import subprocess
import sys

from lib._paths import SEED

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
    "internship-courses": "Stage coopératif + LOG410",
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


def main():
    profile = _select_profile()
    if profile is None:
        print("Au revoir!")
        return

    scenario = _select_scenario()
    semester_week = _prompt_semester_week()

    env = os.environ.copy()

    if scenario != "none":
        env["SCENARIO"] = scenario

    if semester_week is not None:
        env["SEMESTER_WEEK"] = str(semester_week)

    if profile == "__custom__":
        config = _configure_custom()
        if config is None:
            print("Annulé.")
            return
        env["PROFILE"] = "normal"
        env["COURSE_COUNT"] = str(config["count"])
        if config["allowedDays"]:
            env["SCHEDULE_DAYS"] = ",".join(config["allowedDays"])
        env["TIME_PREFERENCE"] = config["timePreference"] or ""
        profile_display = "Personnalisé"
    else:
        env["PROFILE"] = profile
        profile_display = profile

    scenario_display = f" + scénario « {scenario} »" if scenario != "none" else ""
    week_display = f" + semaine {semester_week}" if semester_week is not None else ""
    print(
        f"\nDémarrage du serveur avec le profil « {profile_display} »"
        f"{scenario_display}{week_display}...\n"
    )
    print("  API   : http://localhost:8080/docs")
    print("  Horaire (éditeur visuel) : http://localhost:8080/editor\n")

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
        ],
        env=env,
    )


if __name__ == "__main__":
    main()
