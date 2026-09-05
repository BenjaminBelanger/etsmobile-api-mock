from collections import Counter
from dataclasses import dataclass

from lib import data_store, sessions
from lib.schedule_editor import (
    ACTIVITY_KINDS,
    ACTIVITY_LABELS,
    DAY_END_MIN,
    DAY_NAMES,
    DAY_SHORT,
    DAY_START_MIN,
    EDITABLE_DAYS,
)

_DEFAULT_PROGRAMME = "7084"


def _hhmm(total_minutes: int) -> str:
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def blocks_of(course: dict) -> list[dict]:
    blocks = []
    schedule = course.get("schedule")
    if schedule:
        blocks.append(schedule)
    blocks.extend(course.get("extraActivities", []) or [])
    return blocks


@dataclass(frozen=True)
class Context:
    active_session: str
    sessions: list[dict]
    professors: dict[str, dict]
    rooms: list[str]
    exam_rooms: list[str]
    eval_templates: list[list[dict]]
    catalog: list[dict]
    activity_codes: dict[str, str]
    day_names: dict[str, str]
    day_short: dict[str, str]
    editable_days: list[str]
    day_start: str
    day_end: str
    programme: str
    existing_courses: list[dict]

    def session_codes(self) -> list[str]:
        return [s["abrege"] for s in self.sessions]

    def session_meta(self, code: str) -> dict | None:
        return next((s for s in self.sessions if s["abrege"] == code), None)

    def catalog_entry(self, sigle: str) -> dict | None:
        return next((c for c in self.catalog if c["sigle"] == sigle), None)

    def professor_label(self, professor_id: str) -> str:
        prof = self.professors.get(professor_id)
        if not prof:
            return professor_id
        return f"{prof.get('prenom', '')} {prof.get('nom', '')}".strip()

    def describe(self) -> str:
        return "\n\n".join(
            section
            for section in (
                self._describe_sessions(),
                self._describe_days(),
                self._describe_activity_codes(),
                self._describe_professors(),
                self._describe_rooms(),
                self._describe_catalog(),
                self._describe_existing(),
            )
            if section
        )

    def _describe_sessions(self) -> str:
        lines = [
            "SESSIONS (code | name | first day | last class day | last exam day):"
        ]
        for entry in self.sessions:
            lines.append(
                f"  {entry['abrege']} | {entry.get('auLong', '')} | "
                f"{entry.get('dateDebut', '')} | {entry.get('dateFinCours', '')} | "
                f"{entry.get('dateFin', '')}"
            )
        lines.append(f"  Active session (computed from today's date): {self.active_session}")
        return "\n".join(lines)

    def _describe_days(self) -> str:
        days = ", ".join(f"{code}={name}" for code, name in sorted(self.day_names.items()))
        editable = ", ".join(self.editable_days)
        return (
            f"DAYS (the 'jour' field, ISO weekday as a string): {days}\n"
            f"  The visual editor only draws days {editable} between "
            f"{self.day_start} and {self.day_end}. Activities outside that window "
            f"are still served by the API, they just do not show up in the editor."
        )

    def _describe_activity_codes(self) -> str:
        lines = ["ACTIVITY CODES (the 'codeActivite' field):"]
        for code, label in self.activity_codes.items():
            lines.append(f"  {code:<3}| {label}")
        return "\n".join(lines)

    def _describe_professors(self) -> str:
        lines = ["PROFESSORS (professorId | name | office):"]
        for professor_id, prof in self.professors.items():
            lines.append(
                f"  {professor_id} | {self.professor_label(professor_id)} | "
                f"{prof.get('localBureau', '')}"
            )
        return "\n".join(lines)

    def _describe_rooms(self) -> str:
        return (
            f"ROOMS: {', '.join(self.rooms)}\n"
            f"EXAM ROOMS: {', '.join(self.exam_rooms)}"
        )

    def _describe_catalog(self) -> str:
        lines = [
            "COURSE CATALOGUE (sigle | title | credits). Reference material for "
            "realism, not a menu: reuse an entry when it fits, invent a course "
            "when the description calls for one that is not here."
        ]
        for entry in self.catalog:
            lines.append(
                f"  {entry['sigle']} | {entry['titre']} | {entry.get('nbCredits', 3)}"
            )
        return "\n".join(lines)

    def _describe_existing(self) -> str:
        header = f"COURSES CURRENTLY IN {self.active_session}:"
        if not self.existing_courses:
            return f"{header}\n  (none)"
        lines = [header]
        for course in self.existing_courses:
            blocks = blocks_of(course)
            if blocks:
                detail = "; ".join(
                    f"{b.get('codeActivite', 'C')} {b.get('journee', '')} "
                    f"{b.get('heureDebut', '')}-{b.get('heureFin', '')} "
                    f"({b.get('room', course.get('room', ''))})"
                    for b in blocks
                )
            else:
                detail = "no meetings"
            lines.append(
                f"  {course['sigle']}-{course['groupe']} {course.get('titreCours', '')} "
                f": {detail}"
            )
        return "\n".join(lines)


def _activity_codes() -> dict[str, str]:
    observed: dict[str, str] = {}
    for session_code in data_store.get_sessions_with_courses():
        for course in data_store.get_session_courses(session_code):
            for block in blocks_of(course):
                code = block.get("codeActivite", "C")
                label = block.get("nomActivite", "")
                if label and code not in observed:
                    observed[code] = label

    codes = {}
    for code in sorted(set(ACTIVITY_KINDS) | set(observed)):
        codes[code] = (
            ACTIVITY_LABELS.get(code)
            or observed.get(code)
            or f"Activité ({ACTIVITY_KINDS.get(code, code)})"
        )
    return codes


def _programme() -> str:
    counter = Counter()
    for session_code in data_store.get_sessions_with_courses():
        for course in data_store.get_session_courses(session_code):
            code = course.get("programmeEtudes")
            if code:
                counter[code] += 1
    if not counter:
        return _DEFAULT_PROGRAMME
    return counter.most_common(1)[0][0]


def build_context() -> Context:
    pools = data_store.get_pools()
    active = data_store.ACTIVE_SESSION
    return Context(
        active_session=active,
        sessions=[dict(s) for s in sessions.get_raw_sessions()],
        professors=data_store.get_professors(),
        rooms=list(pools.get("rooms", [])),
        exam_rooms=list(pools.get("examRooms", [])),
        eval_templates=list(pools.get("evalTemplates", [])),
        catalog=list(pools.get("courseCatalog", [])),
        activity_codes=_activity_codes(),
        day_names=dict(DAY_NAMES),
        day_short=dict(DAY_SHORT),
        editable_days=list(EDITABLE_DAYS),
        day_start=_hhmm(DAY_START_MIN),
        day_end=_hhmm(DAY_END_MIN),
        programme=_programme(),
        existing_courses=data_store.get_session_courses(active),
    )
