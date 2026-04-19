def build_course_key(sigle: str, groupe: str) -> str:
    return f"{sigle}-{groupe}"


def empty_schedule_activities() -> dict:
    return {
        "listeActivites": [],
        "listeEnseignants": [],
        "enseignantsParCours": {},
    }


def flatten_teachers_by_course(teachers_by_course: dict[str, list[dict]]) -> list[dict]:
    unique_teachers = []
    seen = set()
    for teachers in teachers_by_course.values():
        for teacher in teachers:
            teacher_key = (
                teacher.get("nom", ""),
                teacher.get("prenom", ""),
                teacher.get("courriel", ""),
            )
            if teacher_key in seen:
                continue
            seen.add(teacher_key)
            unique_teachers.append(teacher)
    return unique_teachers


def register_course_teachers(
    session_data: dict,
    sigle: str,
    groupe: str,
    teachers: list[dict],
) -> None:
    teachers_by_course = session_data.setdefault("enseignantsParCours", {})
    teachers_by_course[build_course_key(sigle, groupe)] = list(teachers)
    session_data["listeEnseignants"] = flatten_teachers_by_course(teachers_by_course)
