import os
import re
from dataclasses import dataclass, field

from lib._paths import ROOT

from .context import Context

MODEL = "claude-opus-5"
MAX_TOKENS = 16000
TOOL_NAME = "build_schedule"
API_KEY_VAR = "ANTHROPIC_API_KEY"

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class PlanError(RuntimeError):
    pass


@dataclass
class Plan:
    session: str
    notes: str
    courses: list[dict]
    warnings: list[str] = field(default_factory=list)

    @property
    def activity_count(self) -> int:
        return sum(len(c["activities"]) for c in self.courses)


SYSTEM_PROMPT = """\
You design weekly course schedules for a local mock of the ETS "Signets" \
student API. The schedules are used to test the ETSMobile Flutter app, so both \
realistic and deliberately awkward schedules are valid output.

You author the courses yourself. You decide how many there are, what each one \
is called, which days and times it meets, whether it has a laboratory or TP \
block in addition to its lecture, who teaches it and which room it uses. The \
reference data below is the mock's real seed data: reuse real sigles, \
professors and rooms where they fit so the result looks like a real ETS \
schedule, but you are free to invent a course that is not in the catalogue \
when the description calls for one.

Produce broken or unusual schedules when that is what was asked for. \
Overlapping courses, back-to-back blocks with no gap, a single lonely \
activity, an empty week, activities at odd hours, the same sigle in two \
different groups, a course that meets five days a week -- all of these are \
legitimate output. Never quietly "fix", spread out or tidy a layout the \
description asked for.

Rules:
- Call the {tool} tool exactly once, laying out the whole week in that one call.
- "jour" is the ISO weekday as a string. Times are 24-hour "HH:MM" and \
heureFin must be later than heureDebut.
- activities[0] is the course's main block; the rest are extra blocks such as \
labs and TPs. A course with an empty activities list is a course with no \
meetings at all. An empty courses list is an empty week.
- The course's "room" should match the room of its first activity.
- Use the session the description implies. Default to the active session when \
it does not mention one.
- Put your assumptions in "notes": which session you used, what you defaulted \
to, and anything the description left open. Keep it to a couple of sentences.

=== REFERENCE DATA (from the mock's seed files) ===

{reference}"""


def build_system_prompt(context: Context) -> str:
    return SYSTEM_PROMPT.format(tool=TOOL_NAME, reference=context.describe())


def build_tool(context: Context) -> dict:
    return {
        "name": TOOL_NAME,
        "description": (
            "Write the complete set of courses for one session. This replaces "
            "everything the mock currently serves for that session, so the "
            "course list must describe the entire week, not a delta."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["session", "notes", "courses"],
            "properties": {
                "session": {
                    "type": "string",
                    "enum": context.session_codes(),
                    "description": "Session code the schedule belongs to.",
                },
                "notes": {
                    "type": "string",
                    "description": (
                        "Your assumptions: which session you chose, what you "
                        "defaulted to, what the description left open."
                    ),
                },
                "courses": {
                    "type": "array",
                    "description": (
                        "Every course in the session. An empty list is an "
                        "empty week, which is a valid thing to produce."
                    ),
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "sigle",
                            "titre",
                            "groupe",
                            "professorId",
                            "room",
                            "activities",
                        ],
                        "properties": {
                            "sigle": {
                                "type": "string",
                                "description": (
                                    "Course code such as LOG430. Reuse one "
                                    "from the catalogue when it fits, or "
                                    "invent one in the same style."
                                ),
                            },
                            "titre": {
                                "type": "string",
                                "description": "Course title, in French.",
                            },
                            "groupe": {
                                "type": "string",
                                "description": (
                                    "Group number such as 01. Use the same "
                                    "sigle with two different groups to put a "
                                    "course in the schedule twice."
                                ),
                            },
                            "professorId": {
                                "type": "string",
                                "enum": list(context.professors.keys()),
                                "description": "Who teaches it.",
                            },
                            "room": {
                                "type": "string",
                                "description": (
                                    "The course's main room, normally the "
                                    "room of its first activity."
                                ),
                            },
                            "activities": {
                                "type": "array",
                                "description": (
                                    "Weekly blocks. The first one is the main "
                                    "block; an empty list means the course "
                                    "never meets."
                                ),
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": [
                                        "jour",
                                        "heureDebut",
                                        "heureFin",
                                        "codeActivite",
                                        "room",
                                    ],
                                    "properties": {
                                        "jour": {
                                            "type": "string",
                                            "enum": sorted(context.day_names),
                                            "description": (
                                                "ISO weekday, 1=Monday."
                                            ),
                                        },
                                        "heureDebut": {
                                            "type": "string",
                                            "description": "Start time, HH:MM.",
                                        },
                                        "heureFin": {
                                            "type": "string",
                                            "description": "End time, HH:MM.",
                                        },
                                        "codeActivite": {
                                            "type": "string",
                                            "enum": list(context.activity_codes),
                                            "description": (
                                                "C for a lecture, L for a lab, "
                                                "TP for practical work."
                                            ),
                                        },
                                        "room": {
                                            "type": "string",
                                            "description": "Room for this block.",
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    }


def _minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PlanError(message)


def _validate_time(value, where: str) -> str:
    _require(
        isinstance(value, str) and bool(_TIME_RE.match(value)),
        f"{where}: '{value}' is not a well-formed 24-hour HH:MM time.",
    )
    return value


def _validate_activity(raw, context: Context, where: str) -> dict:
    _require(isinstance(raw, dict), f"{where}: expected an object, got {type(raw).__name__}.")

    jour = str(raw.get("jour", "")).strip()
    _require(
        jour in context.day_names,
        f"{where}: day '{jour}' is out of range. "
        f"Valid days are {', '.join(sorted(context.day_names))}.",
    )

    start = _validate_time(raw.get("heureDebut"), f"{where} heureDebut")
    end = _validate_time(raw.get("heureFin"), f"{where} heureFin")
    _require(
        _minutes(end) > _minutes(start),
        f"{where}: end time {end} is not after start time {start}.",
    )

    code = str(raw.get("codeActivite", "")).strip()
    _require(
        code in context.activity_codes,
        f"{where}: activity code '{code}' is not valid. "
        f"Valid codes are {', '.join(context.activity_codes)}.",
    )

    room = raw.get("room", "")
    _require(isinstance(room, str), f"{where}: room must be a string.")

    return {
        "jour": jour,
        "heureDebut": start,
        "heureFin": end,
        "codeActivite": code,
        "room": room.strip(),
    }


def _activity_warnings(activity: dict, context: Context, where: str) -> list[str]:
    warnings = []
    if activity["jour"] not in context.editable_days:
        warnings.append(
            f"{where}: {context.day_names[activity['jour']]} is outside the "
            f"editor grid, so this block is served by the API but not drawn in /editor."
        )
    if (
        _minutes(activity["heureDebut"]) < _minutes(context.day_start)
        or _minutes(activity["heureFin"]) > _minutes(context.day_end)
    ):
        warnings.append(
            f"{where}: {activity['heureDebut']}-{activity['heureFin']} falls outside "
            f"the editor's {context.day_start}-{context.day_end} window, so it is "
            f"served by the API but clipped in /editor."
        )
    return warnings


def _validate_course(raw, context: Context, index: int) -> tuple[dict, list[str]]:
    where = f"courses[{index}]"
    _require(isinstance(raw, dict), f"{where}: expected an object, got {type(raw).__name__}.")

    sigle = str(raw.get("sigle", "")).strip().upper()
    _require(bool(sigle), f"{where}: sigle is required.")

    groupe = str(raw.get("groupe", "")).strip()
    _require(bool(groupe), f"{where} ({sigle}): groupe is required.")
    if groupe.isdigit():
        groupe = groupe.zfill(2)

    professor_id = str(raw.get("professorId", "")).strip()
    _require(
        professor_id in context.professors,
        f"{where} ({sigle}-{groupe}): unknown professorId '{professor_id}'. "
        f"Valid ids are {', '.join(context.professors)}.",
    )

    catalog_entry = context.catalog_entry(sigle) or {}
    titre = str(raw.get("titre", "")).strip() or catalog_entry.get("titre", "") or sigle

    raw_activities = raw.get("activities", [])
    _require(
        isinstance(raw_activities, list),
        f"{where} ({sigle}-{groupe}): activities must be a list.",
    )

    warnings = []
    activities = []
    for position, raw_activity in enumerate(raw_activities):
        label = f"{where} ({sigle}-{groupe}) activities[{position}]"
        activity = _validate_activity(raw_activity, context, label)
        warnings.extend(
            _activity_warnings(activity, context, f"{sigle}-{groupe} block {position + 1}")
        )
        activities.append(activity)

    room = str(raw.get("room", "")).strip()
    if activities and activities[0]["room"]:
        room = activities[0]["room"]

    course = {
        "sigle": sigle,
        "groupe": groupe,
        "titre": titre,
        "professorId": professor_id,
        "room": room,
        "nbCredits": catalog_entry.get("nbCredits", 3),
        "activities": activities,
    }
    return course, warnings


def validate_plan(raw, context: Context) -> Plan:
    _require(isinstance(raw, dict), "The model did not return a schedule object.")

    session = str(raw.get("session", "")).strip()
    valid_sessions = context.session_codes()
    _require(
        session in valid_sessions,
        f"Unknown session '{session}'. Valid sessions are {', '.join(valid_sessions)}.",
    )

    notes = str(raw.get("notes", "")).strip()

    raw_courses = raw.get("courses", [])
    _require(isinstance(raw_courses, list), "'courses' must be a list.")

    warnings = []
    courses = []
    seen: dict[tuple[str, str], int] = {}
    for index, raw_course in enumerate(raw_courses):
        course, course_warnings = _validate_course(raw_course, context, index)
        key = (course["sigle"], course["groupe"])
        _require(
            key not in seen,
            f"courses[{index}]: {course['sigle']}-{course['groupe']} is already "
            f"defined at courses[{seen.get(key)}]. Two courses cannot share a "
            f"sigle and a group; use a different group number.",
        )
        seen[key] = index
        warnings.extend(course_warnings)
        courses.append(course)

    if session != context.active_session:
        warnings.append(
            f"{session} is not the active session ({context.active_session}); "
            f"the app opens on the active one."
        )
    if not courses:
        warnings.append(
            f"No courses: {session} will have an empty week and will drop out of "
            f"listeSessions."
        )

    return Plan(session=session, notes=notes, courses=courses, warnings=warnings)


def load_dotenv(path=None) -> None:
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, separator, value = line.partition("=")
        if not separator:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


def require_api_key() -> str:
    load_dotenv()
    key = os.environ.get(API_KEY_VAR, "").strip()
    if not key:
        raise PlanError(
            f"{API_KEY_VAR} is not set.\n"
            f"  Put it in a .env file at the root of the repo:\n"
            f"      {API_KEY_VAR}=sk-ant-...\n"
            f"  (.env is gitignored. Only this tool needs the key -- the mock "
            f"server itself runs without it.)"
        )
    return key


def _call_model(system: str, user: str, tools: list[dict], forced_tool: str) -> dict:
    api_key = require_api_key()
    try:
        import anthropic
    except ImportError as exc:
        raise PlanError(
            "The anthropic package is not installed.\n"
            "      pip install -r requirements-dev.txt"
        ) from exc

    client = anthropic.Anthropic(api_key=api_key)

    def send(tool_choice: dict):
        return client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=tools,
            tool_choice=tool_choice,
        )

    try:
        try:
            response = send(
                {
                    "type": "tool",
                    "name": forced_tool,
                    "disable_parallel_tool_use": True,
                }
            )
        except anthropic.BadRequestError:
            response = send({"type": "auto", "disable_parallel_tool_use": True})
    except anthropic.APIError as exc:
        raise PlanError(f"The model call failed: {exc}") from exc

    for block in response.content:
        if block.type == "tool_use" and block.name == forced_tool:
            return block.input

    text = " ".join(b.text for b in response.content if b.type == "text").strip()
    raise PlanError(
        f"The model did not call {forced_tool}"
        + (f". It said: {text}" if text else f" (stop reason: {response.stop_reason}).")
    )


def translate(sentence: str, context: Context) -> Plan:
    sentence = (sentence or "").strip()
    _require(bool(sentence), "Describe the schedule you want in a sentence.")

    raw = _call_model(
        system=build_system_prompt(context),
        user=f"Build a schedule for this description:\n\n{sentence}",
        tools=[build_tool(context)],
        forced_tool=TOOL_NAME,
    )
    return validate_plan(raw, context)
