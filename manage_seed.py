"""Interactive CLI for adding/removing seed courses."""

import json
import os
import random
import sys
import urllib.error
import urllib.request
from pathlib import Path

from lib import i18n
from lib._paths import SEED


def _notify_server():
    try:
        req = urllib.request.Request("http://localhost:8080/reload", method="POST")
        urllib.request.urlopen(req, timeout=2)
    except (urllib.error.URLError, OSError):
        print(f"  {i18n.t('cli.seed.server_offline')}")


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, data):
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _load_seed_courses() -> list[dict]:
    return _load_json(SEED / "courses.json")


def _save_seed_courses(courses: list[dict]):
    _save_json(SEED / "courses.json", courses)


def _load_pools() -> dict:
    return _load_json(SEED / "pools.json")


def _load_professors() -> dict:
    return _load_json(SEED / "professors.json")


def _load_sessions() -> list[dict]:
    return _load_json(SEED / "sessions.json")


def _next_group(courses: list[dict], sigle: str, session: str) -> str:
    existing = [
        int(c["groupe"])
        for c in courses
        if c["sigle"] == sigle and c["session"] == session
    ]
    return f"{max(existing, default=0) + 1:02d}"


def _apply_defaults(
    pools: dict,
    professors: dict,
    *,
    professor_id: str | None,
    room: str | None,
    exam_room: str | None,
    evaluations: list[dict] | None,
    grade_seed: int | None,
) -> dict:
    return {
        "professor_id": (
            random.choice(list(professors.keys()))
            if professor_id is None
            else professor_id
        ),
        "room": random.choice(pools["rooms"]) if room is None else room,
        "exam_room": (
            random.choice(pools["examRooms"]) if exam_room is None else exam_room
        ),
        "evaluations": (
            random.choice(pools["evalTemplates"])
            if evaluations is None
            else evaluations
        ),
        "grade_seed": random.randint(1000, 9999) if grade_seed is None else grade_seed,
    }


def add_course_to_seed(
    session: str,
    sigle: str,
    title: str,
    schedule: dict,
    *,
    extra_activities: list[dict] | None = None,
    professor_id: str | None = None,
    room: str | None = None,
    exam_room: str | None = None,
    evaluations: list[dict] | None = None,
    teammates: dict | None = None,
    nb_credits: int = 3,
    programme: str = "7084",
    grade_publish_ratio: float = 0.6,
    grade_seed: int | None = None,
) -> dict:
    pools = _load_pools()
    professors = _load_professors()
    courses = _load_seed_courses()

    groupe = _next_group(courses, sigle, session)
    defaults = _apply_defaults(
        pools,
        professors,
        professor_id=professor_id,
        room=room,
        exam_room=exam_room,
        evaluations=evaluations,
        grade_seed=grade_seed,
    )

    record = {
        "sigle": sigle,
        "groupe": groupe,
        "session": session,
        "titreCours": title,
        "nbCredits": nb_credits,
        "programmeEtudes": programme,
        "cote": "",
        "professorId": defaults["professor_id"],
        "room": defaults["room"],
        "examRoom": defaults["exam_room"],
        "schedule": schedule,
        "extraActivities": extra_activities or [],
        "evaluations": defaults["evaluations"],
        "teammates": teammates or {},
        "gradePublishRatio": grade_publish_ratio,
        "gradeSeed": defaults["grade_seed"],
    }

    courses.append(record)
    _save_seed_courses(courses)
    _notify_server()
    return record


def remove_course_from_seed(session: str, sigle: str, groupe: str) -> bool:
    courses = _load_seed_courses()
    before = len(courses)
    courses = [
        c
        for c in courses
        if not (
            c["sigle"] == sigle and c["groupe"] == groupe and c["session"] == session
        )
    ]
    if len(courses) == before:
        return False
    _save_seed_courses(courses)
    _notify_server()
    return True


def list_seed_courses(session: str | None = None) -> list[dict]:
    courses = _load_seed_courses()
    if session:
        courses = [c for c in courses if c["session"] == session]
    return courses


def _select_session() -> dict | None:
    sessions = _load_sessions()
    print(f"\n{i18n.t('cli.seed.sessions_available')}")
    for i, s in enumerate(sessions, 1):
        print(f"{i}) {s['abrege']} ({s['auLong']})")
    print(i18n.t("cli.seed.cancel_entry"))
    try:
        idx = int(input(i18n.t("cli.seed.session_prompt")).strip())
    except ValueError:
        return None
    if idx == 0:
        return None
    if idx < 1 or idx > len(sessions):
        print(i18n.t("cli.common.invalid_choice"))
        return None
    return sessions[idx - 1]


def _interactive_add(session_code: str) -> str:
    pools = _load_pools()
    slots = pools["scheduleSlots"]

    sigle = input(i18n.t("cli.seed.sigle_prompt")).strip().upper()
    if not sigle:
        return i18n.t("cli.common.cancelled")
    title = input(i18n.t("cli.seed.title_prompt")).strip()
    if not title:
        return i18n.t("cli.common.cancelled")

    day_pairs = list(dict.fromkeys((s["jour"], s["journee"]) for s in slots))
    print(f"\n{i18n.t('cli.seed.weekday_title')}")
    for i, (day_code, _) in enumerate(day_pairs, 1):
        print(f"{i}) {i18n.t(f'cli.days.{day_code}')}")
    try:
        day_idx = int(input(i18n.t("cli.seed.weekday_prompt")).strip()) - 1
        chosen_day_code, _ = day_pairs[day_idx]
    except (ValueError, IndexError):
        return i18n.t("cli.seed.invalid_cancelled")
    chosen_day_name = i18n.t(f"cli.days.{chosen_day_code}")

    day_slots = [s for s in slots if s["jour"] == chosen_day_code]
    print(f"\n{i18n.t('cli.seed.slots_title', day=chosen_day_name)}")
    for i, s in enumerate(day_slots, 1):
        print(f"{i}) {s['heureDebut']}-{s['heureFin']}")
    try:
        slot_idx = int(input(i18n.t("cli.seed.slot_prompt")).strip()) - 1
        slot = day_slots[slot_idx]
    except (ValueError, IndexError):
        return i18n.t("cli.seed.invalid_cancelled")

    schedule = {
        "jour": slot["jour"],
        "journee": slot["journee"],
        "heureDebut": slot["heureDebut"],
        "heureFin": slot["heureFin"],
        "codeActivite": "C",
        "nomActivite": "Activité de cours",
    }

    record = add_course_to_seed(session_code, sigle, title, schedule)
    return "\n".join(
        [
            i18n.t(
                "cli.seed.added",
                sigle=record["sigle"],
                groupe=record["groupe"],
                titre=title,
            ),
            i18n.t(
                "cli.seed.added_details",
                session=session_code,
                day=chosen_day_name,
                start=slot["heureDebut"],
                end=slot["heureFin"],
            ),
        ]
    )


def _interactive_remove(session_code: str) -> str:
    courses = list_seed_courses(session_code)
    if not courses:
        return i18n.t("cli.seed.empty_session")

    print(f"\n{i18n.t('cli.seed.courses_in', session=session_code)}")
    for i, c in enumerate(courses, 1):
        print(f"{i}) {c['sigle']}-{c['groupe']} - {c['titreCours']}")
    print(i18n.t("cli.seed.cancel_entry"))

    try:
        idx = int(input(i18n.t("cli.seed.remove_prompt")).strip())
    except ValueError:
        return i18n.t("cli.common.cancelled")
    if idx == 0:
        return ""
    if idx < 1 or idx > len(courses):
        return i18n.t("cli.common.invalid_choice")

    target = courses[idx - 1]
    removed = remove_course_from_seed(session_code, target["sigle"], target["groupe"])
    if removed:
        return i18n.t(
            "cli.seed.removed",
            sigle=target["sigle"],
            groupe=target["groupe"],
            titre=target["titreCours"],
        )
    return i18n.t("cli.seed.not_found")


def _interactive_list(session_code: str) -> str:
    courses = list_seed_courses(session_code)
    if not courses:
        return i18n.t("cli.seed.empty_session")

    lines = [i18n.t("cli.seed.courses_in", session=session_code)]
    for c in courses:
        lines.append(f"{c['sigle']}-{c['groupe']} - {c['titreCours']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None):
    argv = list(sys.argv[1:] if argv is None else argv)
    _, lang = i18n.split_lang_arg(argv)
    i18n.set_locale(lang)

    last_message = ""
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        if last_message:
            print(last_message)
        print(f"\n{i18n.t('cli.seed.menu_title')}")
        print(i18n.t("cli.seed.menu_add"))
        print(i18n.t("cli.seed.menu_remove"))
        print(i18n.t("cli.seed.menu_list"))
        print(i18n.t("cli.seed.menu_quit"))
        choice = input(i18n.t("cli.common.choice_prompt")).strip()

        if choice == "4":
            print(i18n.t("cli.common.goodbye"))
            break

        if choice in ("1", "2", "3"):
            session = _select_session()
            if session is None:
                last_message = ""
                continue
            if choice == "1":
                last_message = _interactive_add(session["abrege"])
            elif choice == "2":
                last_message = _interactive_remove(session["abrege"])
            else:
                last_message = _interactive_list(session["abrege"])
        else:
            last_message = i18n.t("cli.common.invalid_choice")


if __name__ == "__main__":
    main()
