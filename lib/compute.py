import random
from datetime import date, datetime, timedelta

from .resource_specs import (
    COURSE_ACTIVITIES,
    COURSE_REVIEWS,
    COURSE_SCHEDULE,
    COURSES,
    EVALUATIONS,
    FINAL_EXAMS,
    SCHEDULE_ACTIVITIES,
    TEAMMATES,
)
from .schedule_activities import (
    build_course_key,
    empty_schedule_activities,
    register_course_teachers,
)

_STUDENT_SCORE_RANGE = (0.65, 0.95)
_STD_DEV_RANGE = (0.05, 0.15)
_PERCENTILE_RANGE = (65, 95)

_EXAM_SLOTS = {
    "evening": ("18:00", "21:00"),
    "morning": ("09:00", "12:00"),
    "afternoon": ("13:30", "16:30"),
}

_EVAL_SPREAD_START = 0.25
_EVAL_SPREAD_RANGE = 0.65
_DEFAULT_PUBLISH_RATIO = 0.6


def _format_french(value: float, decimals: int = 1) -> str:
    return f"{value:.{decimals}f}".replace(".", ",")


def _parse_french(s: str) -> float:
    return float(s.replace(",", "."))


def _parse_date(s: str) -> date:
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


def _nearest_weekday(current_date: date) -> date:
    if current_date.isoweekday() == 6:
        return current_date + timedelta(days=2)
    if current_date.isoweekday() == 7:
        return current_date + timedelta(days=1)
    return current_date


def _weekly_dates(start: date, end: date, isoweekday: int) -> list[date]:
    current_date = start
    while current_date.isoweekday() != isoweekday:
        current_date += timedelta(days=1)
    dates = []
    while current_date <= end:
        dates.append(current_date)
        current_date += timedelta(weeks=1)
    return dates


def _exam_date(start: date, end: date, rng: random.Random) -> date:
    candidates = []
    for i in range((end - start).days + 1):
        day = start + timedelta(days=i)
        if day.isoweekday() <= 5:
            candidates.append(day)
    return rng.choice(candidates) if candidates else start


def _stored_value(evaluation: dict, key: str):
    """The value set on the evaluation, else the one frozen when first generated."""
    if key in evaluation:
        return evaluation[key]
    generated = evaluation.get("generated")
    return generated.get(key) if isinstance(generated, dict) else None


def _stored_number(evaluation: dict, key: str) -> str:
    value = _stored_value(evaluation, key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return ""
    return _format_french(float(value))


def _stored_percentile(evaluation: dict) -> str:
    value = _stored_value(evaluation, "rangCentile")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return ""
    return str(int(value))


def _fill_grades(item: dict, max_score: int, rng: random.Random) -> None:
    student_pct = rng.uniform(*_STUDENT_SCORE_RANGE)
    score = round(student_pct * max_score, 1)
    avg_pct = student_pct * rng.uniform(0.75, 0.95)
    average = round(avg_pct * max_score, 1)
    std_dev = round(rng.uniform(*_STD_DEV_RANGE) * max_score, 1)
    median = max(0, min(max_score, round(average + rng.uniform(-2, 2), 1)))
    generated = {
        "note": _format_french(score),
        "moyenne": _format_french(average),
        "ecartType": _format_french(std_dev),
        "mediane": _format_french(median),
        "rangCentile": str(rng.randint(*_PERCENTILE_RANGE)),
    }
    for key, value in generated.items():
        if not item[key]:
            item[key] = value


def _weighted_scores(evals: list) -> tuple[float, float]:
    total_weighting = sum(int(ev["ponderation"]) for ev in evals)
    if total_weighting == 0:
        return 0.0, 0.0
    pct = (
        sum(
            _parse_french(ev["note"])
            / float(ev["corrigeSur"])
            * 100
            * int(ev["ponderation"])
            for ev in evals
        )
        / total_weighting
    )
    raw = sum(
        _parse_french(ev["note"]) / float(ev["corrigeSur"]) * int(ev["ponderation"])
        for ev in evals
    )
    return pct, raw


def _build_grade_summary(evals: list, rng: random.Random) -> dict:
    published = [ev for ev in evals if ev["publie"] == "Oui"]
    total_published_weighting = sum(int(ev["ponderation"]) for ev in published)

    if not published or total_published_weighting == 0:
        return {
            "noteACeJour": "",
            "scoreFinalSur100": "",
            "moyenneClasse": "",
            "ecartTypeClasse": "",
            "medianeClasse": "",
            "rangCentileClasse": "",
            "noteACeJourElementsIndividuels": "",
            "noteSur100PourElementsIndividuels": "",
            "tauxPublication": "0,0",
        }

    current_score, score_final = _weighted_scores(published)
    class_score = sum(
        _parse_french(ev["moyenne"]) / float(ev["corrigeSur"]) * int(ev["ponderation"])
        for ev in published
    )
    median_score = sum(
        _parse_french(ev["mediane"]) / float(ev["corrigeSur"]) * int(ev["ponderation"])
        for ev in published
    )
    individual_evals = [ev for ev in published if ev["equipe"] == ""]
    if individual_evals and sum(int(ev["ponderation"]) for ev in individual_evals) > 0:
        individual_score, individual_raw = _weighted_scores(individual_evals)
    else:
        individual_score, individual_raw = current_score, score_final

    return {
        "noteACeJour": _format_french(current_score),
        "scoreFinalSur100": _format_french(score_final),
        "moyenneClasse": _format_french(class_score),
        "ecartTypeClasse": _format_french(
            round(rng.uniform(*_STD_DEV_RANGE) * total_published_weighting, 1)
        ),
        "medianeClasse": _format_french(median_score),
        "rangCentileClasse": str(rng.randint(*_PERCENTILE_RANGE)),
        "noteACeJourElementsIndividuels": _format_french(individual_score),
        "noteSur100PourElementsIndividuels": _format_french(individual_raw),
        "tauxPublication": _format_french(float(total_published_weighting)),
    }


def _build_evaluations(
    course: dict, session_meta: dict, exam_date_str: str, rng: random.Random
) -> dict:
    course_group = build_course_key(course["sigle"], course["groupe"])
    evals = course["evaluations"]
    team_num = rng.randint(1, 5)

    start = _parse_date(session_meta["dateDebut"])
    course_end = _parse_date(session_meta["dateFinCours"])
    duration = (course_end - start).days

    eval_count = len(evals)
    fractions = [
        _EVAL_SPREAD_START + _EVAL_SPREAD_RANGE * i / max(eval_count - 1, 1)
        for i in range(eval_count)
    ]
    target_dates = [
        _nearest_weekday(start + timedelta(days=int(f * duration))) for f in fractions
    ]
    if target_dates and not _stored_value(evals[-1], "dateCible"):
        target_dates[-1] = _parse_date(exam_date_str)

    num_published = max(
        1, int(eval_count * course.get("gradePublishRatio", _DEFAULT_PUBLISH_RATIO))
    )

    items = []
    for idx, ev in enumerate(evals):
        stored_publie = _stored_value(ev, "publie")
        published = (
            stored_publie if isinstance(stored_publie, bool) else idx < num_published
        )
        item = {
            "coursGroupe": course_group,
            "nom": ev["nom"],
            "equipe": f"\u00c9quipe {team_num}" if ev["isTeam"] else "",
            "dateCible": _stored_value(ev, "dateCible")
            or target_dates[idx].isoformat(),
            "note": _stored_number(ev, "note"),
            "corrigeSur": str(ev["corrigeSur"]),
            "ponderation": str(ev["ponderation"]),
            "moyenne": _stored_number(ev, "moyenne"),
            "ecartType": _stored_number(ev, "ecartType"),
            "mediane": _stored_number(ev, "mediane"),
            "rangCentile": _stored_percentile(ev),
            "publie": "Oui" if published else "Non",
            "messageDuProf": "",
            "ignoreDuCalcul": "Non",
        }
        if published:
            _fill_grades(item, ev["corrigeSur"], rng)
        items.append(item)

    return {**_build_grade_summary(items, rng), "liste": items}


def _build_course_entry(course: dict, session_code: str) -> dict:
    return {
        "sigle": course["sigle"],
        "groupe": course["groupe"],
        "session": session_code,
        "cote": course.get("cote", ""),
        "nbCredits": course.get("nbCredits", 3),
        "titreCours": course["titreCours"],
        "programmeEtudes": course.get("programmeEtudes", "7084"),
    }


def _build_final_exam(
    course: dict,
    sigle: str,
    groupe: str,
    sched: dict,
    semester_courses_end: date,
    semester_end: date,
    rng: random.Random,
) -> tuple[dict, str]:
    exam_day = _exam_date(semester_courses_end + timedelta(days=1), semester_end, rng)
    exam_date_str = exam_day.isoformat()
    hour = int(sched["heureDebut"][:2])
    if hour >= 18:
        exam_start, exam_end = _EXAM_SLOTS["evening"]
    elif rng.random() < 0.5:
        exam_start, exam_end = _EXAM_SLOTS["morning"]
    else:
        exam_start, exam_end = _EXAM_SLOTS["afternoon"]
    override = course.get("finalExam") or {}
    exam_record = {
        "sigle": sigle,
        "groupe": groupe,
        "dateExamen": override.get("dateExamen") or exam_date_str,
        "heureDebut": override.get("heureDebut") or exam_start,
        "heureFin": override.get("heureFin") or exam_end,
        "local": override.get("local") or course.get("examRoom", "A-1518"),
    }
    return exam_record, exam_record["dateExamen"]


def override_target_date(week_date: date, override: dict) -> date:
    target = override.get("targetDate")
    if target:
        return date.fromisoformat(target)
    jour = override.get("jour")
    if not jour:
        return week_date
    monday = week_date - timedelta(days=week_date.isoweekday() - 1)
    return monday + timedelta(days=int(jour) - 1)


def _build_activities(
    course: dict,
    course_group: str,
    title: str,
    room: str,
    sched: dict,
    semester_start: date,
    semester_courses_end: date,
) -> list[dict]:
    activities = []
    overrides = course.get("occurrenceOverrides", [])
    all_schedules = [sched] + course.get("extraActivities", [])
    for block_index, activity_schedule in enumerate(all_schedules):
        iso_weekday = int(activity_schedule["jour"])
        activity_room = activity_schedule.get("room", room)
        is_lab = activity_schedule.get("codeActivite", "C") == "L"
        activity_name = "Labo" if is_lab else "Cours"
        activity_description = activity_schedule.get("nomActivite", "Activité de cours")
        for week_date in _weekly_dates(
            semester_start, semester_courses_end, iso_weekday
        ):
            override = next(
                (
                    ov
                    for ov in overrides
                    if ov.get("block") == block_index
                    and ov.get("date") == week_date.isoformat()
                ),
                None,
            )
            if override and override.get("canceled"):
                continue
            if override:
                occ_date = override_target_date(week_date, override)
                start_hhmm = override.get("heureDebut", activity_schedule["heureDebut"])
                end_hhmm = override.get("heureFin", activity_schedule["heureFin"])
            else:
                occ_date = week_date
                start_hhmm = activity_schedule["heureDebut"]
                end_hhmm = activity_schedule["heureFin"]
            activities.append(
                {
                    "dateDebut": f"{occ_date.isoformat()}T{start_hhmm}:00",
                    "dateFin": f"{occ_date.isoformat()}T{end_hhmm}:00",
                    "coursGroupe": course_group,
                    "nomActivite": activity_name,
                    "local": activity_room,
                    "descriptionActivite": activity_description,
                    "libelleCours": title,
                }
            )
    return activities


def _build_prof_entry(prof: dict) -> dict:
    return {
        "localBureau": prof.get("localBureau", ""),
        "telephone": prof.get("telephone", ""),
        "enseignantPrincipal": "Oui",
        "nom": prof.get("nom", ""),
        "prenom": prof.get("prenom", ""),
        "courriel": prof.get("courriel", ""),
    }


def _make_activity_entry(
    sigle: str,
    groupe: str,
    slot: dict,
    room: str,
    title: str,
    is_primary: bool,
) -> dict:
    return {
        "sigle": sigle,
        "groupe": groupe,
        "jour": slot["jour"],
        "journee": slot["journee"],
        "codeActivite": slot.get("codeActivite", "C"),
        "nomActivite": slot.get("nomActivite", "Activité de cours"),
        "activitePrincipale": "Oui" if is_primary else "Non",
        "heureDebut": slot["heureDebut"],
        "heureFin": slot["heureFin"],
        "local": room,
        "titreCours": title,
    }


def _build_schedule_entries(
    course: dict,
    sched: dict,
    sigle: str,
    groupe: str,
    room: str,
    title: str,
    prof_entry: dict,
    schedule_activity: dict,
) -> dict:
    primary = _make_activity_entry(sigle, groupe, sched, room, title, is_primary=True)
    course_sched_entry = {**primary, "listeProf": [prof_entry]}

    schedule_activity["listeActivites"].append(primary)
    for extra in course.get("extraActivities", []):
        entry = _make_activity_entry(
            sigle, groupe, extra, extra.get("room", room), title, is_primary=False
        )
        schedule_activity["listeActivites"].append(entry)

    register_course_teachers(schedule_activity, sigle, groupe, [prof_entry])

    return course_sched_entry


def _build_course_review(
    sigle: str, groupe: str, prof: dict, semester_courses_end: date
) -> dict:
    review_start = _nearest_weekday(semester_courses_end - timedelta(days=28))
    review_end = _nearest_weekday(semester_courses_end - timedelta(days=18))
    return {
        "Sigle": sigle,
        "Groupe": groupe,
        "Enseignant": f"{prof.get('prenom', '')} {prof.get('nom', '')}",
        "DateDebutEvaluation": f"{review_start.isoformat()}T00:00:00",
        "DateFinEvaluation": f"{review_end.isoformat()}T23:59:00",
        "TypeEvaluation": "Cours",
        "EstComplete": True,
    }


def _build_course_teammates(
    course: dict, course_group: str, teammate_pool: dict
) -> dict | None:
    team_evals = course.get("teammates", {})
    if not team_evals:
        return None
    course_teammates = {}
    for eval_name, member_ids in team_evals.items():
        members = []
        for member_id in member_ids:
            teammate = teammate_pool.get(member_id)
            if teammate:
                members.append(
                    {
                        "nom": teammate["nom"],
                        "prenom": teammate["prenom"],
                        "courriel": teammate["courriel"],
                    }
                )
        if members:
            course_teammates[eval_name] = members
    return course_teammates or None


def build_all_course_data(
    sessions: list[dict],
    courses: list[dict],
    professors: dict,
    pools: dict,
) -> dict[str, object]:
    """Build all computed fixtures from seed data, keyed by filename."""
    session_map = {s["abrege"]: s for s in sessions}
    teammate_pool = {t["id"]: t for t in pools.get("teammatePool", [])}

    all_courses = []
    evaluations: dict = {}
    course_activities: dict = {}
    course_schedule: dict = {}
    schedule_activities: dict = {}
    final_exams: dict = {}
    course_reviews: dict = {}
    teammates: dict = {}

    for course in courses:
        session_code = course["session"]
        session_meta = session_map.get(session_code)
        if session_meta is None:
            continue

        rng = random.Random(course.get("gradeSeed", 0))
        sigle = course["sigle"]
        groupe = course["groupe"]
        course_group = build_course_key(sigle, groupe)
        prof = professors.get(course["professorId"], {})
        room = course["room"]
        title = course["titreCours"]
        sched = course["schedule"]

        semester_start = _parse_date(session_meta["dateDebut"])
        semester_courses_end = _parse_date(session_meta["dateFinCours"])
        semester_end = _parse_date(session_meta["dateFin"])

        all_courses.append(_build_course_entry(course, session_code))

        if sched is None:
            exam_date_str = semester_courses_end.isoformat()
            eval_block = _build_evaluations(course, session_meta, exam_date_str, rng)
            evaluations.setdefault(session_code, {})[course_group] = eval_block
            continue

        exam_record, exam_date_str = _build_final_exam(
            course,
            sigle,
            groupe,
            sched,
            semester_courses_end,
            semester_end,
            rng,
        )
        final_exams.setdefault(session_code, []).append(exam_record)

        eval_block = _build_evaluations(course, session_meta, exam_date_str, rng)
        evaluations.setdefault(session_code, {})[course_group] = eval_block

        activities = _build_activities(
            course,
            course_group,
            title,
            room,
            sched,
            semester_start,
            semester_courses_end,
        )
        activities.append(
            {
                "dateDebut": f"{exam_date_str}T{exam_record['heureDebut']}:00",
                "dateFin": f"{exam_date_str}T{exam_record['heureFin']}:00",
                "coursGroupe": course_group,
                "nomActivite": "Final",
                "local": exam_record["local"],
                "descriptionActivite": "Examen final",
                "libelleCours": title,
            }
        )
        course_activities.setdefault(session_code, []).extend(activities)

        prof_entry = _build_prof_entry(prof)
        schedule_activity = schedule_activities.setdefault(
            session_code,
            empty_schedule_activities(),
        )
        course_sched = _build_schedule_entries(
            course,
            sched,
            sigle,
            groupe,
            room,
            title,
            prof_entry,
            schedule_activity,
        )
        course_schedule.setdefault(session_code, []).append(course_sched)

        course_reviews.setdefault(session_code, []).append(
            _build_course_review(sigle, groupe, prof, semester_courses_end),
        )

        team_data = _build_course_teammates(course, course_group, teammate_pool)
        if team_data:
            teammates.setdefault(session_code, {})[course_group] = team_data

    for session_code in course_activities:
        course_activities[session_code].sort(key=lambda x: x["dateDebut"])

    return {
        COURSES.filename: all_courses,
        EVALUATIONS.filename: evaluations,
        COURSE_ACTIVITIES.filename: course_activities,
        COURSE_SCHEDULE.filename: course_schedule,
        SCHEDULE_ACTIVITIES.filename: schedule_activities,
        FINAL_EXAMS.filename: final_exams,
        COURSE_REVIEWS.filename: course_reviews,
        TEAMMATES.filename: teammates,
    }
