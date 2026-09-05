import json
import random
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from lib import data_store
from lib._paths import ROOT

from .context import Context
from .translate import Plan

WORK_DIR = ROOT / ".nl_schedule"
BACKUP_PATH = WORK_DIR / "backup.json"
RELOAD_URL = "http://localhost:8080/reload"

_ROW_MINUTES = 30
_MIN_CELL_WIDTH = 11


def _build_block(activity: dict, context: Context, *, primary: bool) -> dict:
    block = {
        "jour": activity["jour"],
        "journee": context.day_names[activity["jour"]],
        "heureDebut": activity["heureDebut"],
        "heureFin": activity["heureFin"],
        "codeActivite": activity["codeActivite"],
        "nomActivite": context.activity_codes[activity["codeActivite"]],
    }
    if not primary:
        block["room"] = activity["room"]
    return block


def build_records(plan: Plan, context: Context) -> list[dict]:
    records = []
    for course in plan.courses:
        rng = random.Random(f"{plan.session}-{course['sigle']}-{course['groupe']}")
        blocks = [
            _build_block(activity, context, primary=(index == 0))
            for index, activity in enumerate(course["activities"])
        ]
        records.append(
            {
                "sigle": course["sigle"],
                "groupe": course["groupe"],
                "session": plan.session,
                "titreCours": course["titre"],
                "nbCredits": course["nbCredits"],
                "programmeEtudes": context.programme,
                "cote": "",
                "professorId": course["professorId"],
                "room": course["room"],
                "examRoom": (
                    rng.choice(context.exam_rooms) if context.exam_rooms else ""
                ),
                "schedule": blocks[0] if blocks else None,
                "extraActivities": blocks[1:],
                "evaluations": (
                    rng.choice(context.eval_templates) if context.eval_templates else []
                ),
                "teammates": {},
                "gradePublishRatio": 0.6,
                "gradeSeed": rng.randint(1000, 9999),
            }
        )
    return records


def _minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def _hhmm(total_minutes: int) -> str:
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def _grid_blocks(records: list[dict]) -> list[dict]:
    blocks = []
    for course in records:
        schedule = course.get("schedule")
        raw_blocks = ([schedule] if schedule else []) + course.get("extraActivities", [])
        for raw in raw_blocks:
            blocks.append(
                {
                    "jour": raw["jour"],
                    "start": _minutes(raw["heureDebut"]),
                    "end": _minutes(raw["heureFin"]),
                    "label": (
                        f"{course['sigle']}-{course['groupe']} "
                        f"{raw.get('codeActivite', 'C')}"
                    ),
                    "room": raw.get("room", course.get("room", "")),
                }
            )
    return blocks


def _lanes(day_blocks: list[dict]) -> list[list[dict]]:
    lanes: list[list[dict]] = []
    for block in sorted(day_blocks, key=lambda b: (b["start"], b["end"])):
        for lane in lanes:
            if lane[-1]["end"] <= block["start"]:
                lane.append(block)
                break
        else:
            lanes.append([block])
    return lanes


def _cell(lane: list[dict], row_start: int, width: int) -> str:
    row_end = row_start + _ROW_MINUTES
    for block in lane:
        if block["start"] < row_end and block["end"] > row_start:
            first_row = block["start"] - block["start"] % _ROW_MINUTES
            if row_start == first_row:
                return block["label"][:width].ljust(width)
            if row_start == first_row + _ROW_MINUTES and block["room"]:
                return block["room"][:width].ljust(width)
            return "·".ljust(width)
    return " " * width


def render_week(records: list[dict], context: Context) -> str:
    blocks = _grid_blocks(records)
    if not blocks:
        return "  (empty week -- no activities at all)"

    by_day: dict[str, list[dict]] = {}
    for block in blocks:
        by_day.setdefault(block["jour"], []).append(block)
    days = sorted(by_day, key=int)
    lanes_by_day = {day: _lanes(by_day[day]) for day in days}

    width = max(
        _MIN_CELL_WIDTH,
        max(len(b["label"]) for b in blocks),
        max(len(b["room"]) for b in blocks),
    )
    gutter = " " * 6
    day_widths = {
        day: len(lanes_by_day[day]) * width + (len(lanes_by_day[day]) - 1) * 2
        for day in days
    }

    header = gutter + "| " + " | ".join(
        context.day_short[day].center(day_widths[day]) for day in days
    )
    lines = [header, "-" * len(header)]

    first_row = min(b["start"] for b in blocks) // _ROW_MINUTES * _ROW_MINUTES
    last_row = -(-max(b["end"] for b in blocks) // _ROW_MINUTES) * _ROW_MINUTES
    for row_start in range(first_row, last_row, _ROW_MINUTES):
        cells = [
            "  ".join(_cell(lane, row_start, width) for lane in lanes_by_day[day])
            for day in days
        ]
        lines.append(f"{_hhmm(row_start)} | " + " | ".join(cells).rstrip())

    return "\n".join(lines)


def describe_records(records: list[dict], context: Context) -> str:
    if not records:
        return "  (no courses)"
    lines = []
    for course in records:
        lines.append(
            f"  {course['sigle']}-{course['groupe']}  {course['titreCours']}"
            f"  [{context.professor_label(course['professorId'])}]"
        )
        schedule = course.get("schedule")
        blocks = ([schedule] if schedule else []) + course.get("extraActivities", [])
        if not blocks:
            lines.append("      (no meetings)")
        for block in blocks:
            lines.append(
                f"      {block['codeActivite']:<3}"
                f"{block['journee']:<10}"
                f"{block['heureDebut']}-{block['heureFin']}"
                f"  {block.get('room', course.get('room', ''))}"
            )
    return "\n".join(lines)


def target_path() -> Path:
    return data_store.overrides_path()


def _read_overrides() -> dict:
    path = target_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_backup() -> None:
    path = target_path()
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    envelope = {
        "target": str(path),
        "savedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "existed": path.exists(),
        "content": path.read_text(encoding="utf-8") if path.exists() else None,
    }
    BACKUP_PATH.write_text(
        json.dumps(envelope, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def notify_server() -> bool:
    try:
        request = urllib.request.Request(RELOAD_URL, method="POST")
        urllib.request.urlopen(request, timeout=2)
        return True
    except (urllib.error.URLError, OSError):
        return False


def apply_plan(plan: Plan, records: list[dict]) -> Path:
    _write_backup()
    payload = _read_overrides()
    payload[plan.session] = {"courses": records, "trash": []}
    path = target_path()
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


def restore() -> str:
    if not BACKUP_PATH.exists():
        raise FileNotFoundError(
            f"No backup to restore from ({BACKUP_PATH} does not exist). "
            f"A backup is written every time a schedule is applied."
        )
    envelope = json.loads(BACKUP_PATH.read_text(encoding="utf-8"))
    path = target_path()
    if envelope.get("existed"):
        path.write_text(envelope.get("content") or "", encoding="utf-8")
        return f"Restored {path} to its state before the last run."
    path.unlink(missing_ok=True)
    return f"Removed {path}; there was no override file before the last run."
