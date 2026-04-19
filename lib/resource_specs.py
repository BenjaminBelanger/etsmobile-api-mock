"""Fixture and route metadata for computed and seeded resources."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FixtureSpec:
    filename: str
    shape: str = "plain"
    session_keyed: bool = False
    generated: bool = False
    sigle_field: str | None = None
    sigle_extract: str | None = None
    session_field: str = "session"


@dataclass(frozen=True)
class ListResponseSpec:
    fixture: FixtureSpec
    json_list_key: str
    xml_root: str
    xml_list: str
    xml_item: str
    session_default: object | None = None


STUDENT_INFO = FixtureSpec("student_info.json")
PROGRAMS = FixtureSpec("programs.json")
SESSIONS = FixtureSpec("sessions.json")
COURSES = FixtureSpec(
    "courses.json",
    shape="flat_list",
    generated=True,
    sigle_field="sigle",
    session_field="session",
)
EVALUATIONS = FixtureSpec(
    "evaluations.json",
    shape="session_dict",
    session_keyed=True,
    generated=True,
    sigle_extract="split-dash-0",
)
TEAMMATES = FixtureSpec(
    "teammates.json",
    shape="session_dict",
    session_keyed=True,
    generated=True,
    sigle_extract="split-dash-0",
)
COURSE_ACTIVITIES = FixtureSpec(
    "course_activities.json",
    shape="session_list",
    session_keyed=True,
    generated=True,
    sigle_field="coursGroupe",
    sigle_extract="split-dash-0",
)
COURSE_SCHEDULE = FixtureSpec(
    "course_schedule.json",
    shape="session_list",
    session_keyed=True,
    generated=True,
    sigle_field="sigle",
)
SCHEDULE_ACTIVITIES = FixtureSpec(
    "schedule_activities.json",
    shape="schedule_activities",
    session_keyed=True,
    generated=True,
    sigle_field="sigle",
)
FINAL_EXAMS = FixtureSpec(
    "final_exams.json",
    shape="session_list",
    session_keyed=True,
    generated=True,
    sigle_field="sigle",
)
COURSE_REVIEWS = FixtureSpec(
    "course_reviews.json",
    shape="session_list",
    session_keyed=True,
    generated=True,
    sigle_field="Sigle",
)
REPLACED_DAYS = FixtureSpec(
    "replaced_days.json",
    shape="session_list",
    session_keyed=False,
    sigle_field=None,
)

ALL_FIXTURES = (
    STUDENT_INFO,
    PROGRAMS,
    SESSIONS,
    COURSES,
    EVALUATIONS,
    TEAMMATES,
    COURSE_ACTIVITIES,
    COURSE_SCHEDULE,
    SCHEDULE_ACTIVITIES,
    FINAL_EXAMS,
    COURSE_REVIEWS,
    REPLACED_DAYS,
)

FIXTURE_SPECS = {spec.filename: spec for spec in ALL_FIXTURES}
SESSION_KEYED_FILENAMES = {spec.filename for spec in ALL_FIXTURES if spec.session_keyed}
GENERATED_FILENAMES = {spec.filename for spec in ALL_FIXTURES if spec.generated}

COURSE_LIST_RESPONSE = ListResponseSpec(
    fixture=COURSES,
    json_list_key="liste",
    xml_root="ListeCours",
    xml_list="liste",
    xml_item="Cours",
)
PROGRAM_LIST_RESPONSE = ListResponseSpec(
    fixture=PROGRAMS,
    json_list_key="liste",
    xml_root="ListeProgrammes",
    xml_list="liste",
    xml_item="Programme",
)
SESSION_LIST_RESPONSE = ListResponseSpec(
    fixture=SESSIONS,
    json_list_key="liste",
    xml_root="ListeSessions",
    xml_list="liste",
    xml_item="Session",
)
COURSE_REVIEW_LIST_RESPONSE = ListResponseSpec(
    fixture=COURSE_REVIEWS,
    json_list_key="listeEvaluations",
    xml_root="ListeEvaluationsCours",
    xml_list="listeEvaluations",
    xml_item="EvaluationCours",
    session_default=[],
)
COURSE_ACTIVITY_LIST_RESPONSE = ListResponseSpec(
    fixture=COURSE_ACTIVITIES,
    json_list_key="ListeDesSeances",
    xml_root="ListeSeances",
    xml_list="ListeDesSeances",
    xml_item="Seance",
    session_default=[],
)
COURSE_SCHEDULE_LIST_RESPONSE = ListResponseSpec(
    fixture=COURSE_SCHEDULE,
    json_list_key="listeCours",
    xml_root="ListeCoursHoraire",
    xml_list="listeCours",
    xml_item="CoursHoraire",
    session_default=[],
)
FINAL_EXAM_LIST_RESPONSE = ListResponseSpec(
    fixture=FINAL_EXAMS,
    json_list_key="listeHoraire",
    xml_root="ListeHoraireExamensFinaux",
    xml_list="listeHoraire",
    xml_item="HoraireExamenFinal",
    session_default=[],
)
REPLACED_DAY_LIST_RESPONSE = ListResponseSpec(
    fixture=REPLACED_DAYS,
    json_list_key="listeJours",
    xml_root="ListeJoursRemplaces",
    xml_list="listeJours",
    xml_item="JourRemplace",
    session_default=[],
)
TEAMMATE_LIST_RESPONSE = ListResponseSpec(
    fixture=TEAMMATES,
    json_list_key="liste",
    xml_root="ListeCoequipiers",
    xml_list="liste",
    xml_item="Personne",
    session_default={},
)


def sigle_from_key(spec: FixtureSpec, key: str) -> str:
    if spec.sigle_extract == "split-dash-0":
        return key.split("-")[0]
    return ""


def sigle_from_item(spec: FixtureSpec, item: dict) -> str:
    if spec.sigle_field is None:
        return ""
    field_value = item.get(spec.sigle_field, "")
    if spec.sigle_extract == "split-dash-0":
        return field_value.split("-")[0]
    return field_value
