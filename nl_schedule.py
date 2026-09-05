import argparse
import sys

from scenario_ai.context import build_context
from scenario_ai.execute import (
    apply_plan,
    build_records,
    describe_records,
    notify_server,
    render_week,
    restore,
)
from scenario_ai.translate import PlanError, translate


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="nl_schedule.py",
        description="Generate a week of mock courses from a description.",
    )
    parser.add_argument(
        "sentence",
        nargs="?",
        help="The schedule you want, in plain English.",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Apply without asking for confirmation.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the generated week and exit without writing anything.",
    )
    parser.add_argument(
        "--restore",
        action="store_true",
        help="Roll back the previous run and exit.",
    )
    return parser.parse_args(argv)


def _confirm(session: str) -> bool:
    prompt = f"\nApply this schedule to {session}? [y/N] "
    try:
        return input(prompt).strip().lower() in ("y", "yes", "o", "oui")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def _print_plan(plan, records, context) -> None:
    meta = context.session_meta(plan.session) or {}
    print(f"\nSession: {plan.session} {meta.get('auLong', '')}".rstrip())
    if meta.get("dateDebut"):
        print(f"  {meta['dateDebut']} -> {meta.get('dateFinCours', '')} (classes)")

    if plan.notes:
        print(f"\nNotes from the model:\n  {plan.notes}")

    print(f"\n{render_week(records, context)}\n")
    print(f"{len(records)} course(s), {plan.activity_count} weekly activity block(s):")
    print(describe_records(records, context))

    if plan.warnings:
        print("\nHeads up:")
        for warning in plan.warnings:
            print(f"  - {warning}")


def main(argv=None) -> int:
    args = _parse_args(argv)

    if args.restore:
        try:
            print(restore())
        except (OSError, ValueError) as exc:
            print(f"Cannot restore: {exc}", file=sys.stderr)
            return 1
        if not notify_server():
            print("Server not running -- changes apply on next start.")
        return 0

    if not args.sentence:
        print(
            "Describe the schedule you want, for example:\n"
            '  python nl_schedule.py "four courses, mornings only, nothing on Friday"',
            file=sys.stderr,
        )
        return 2

    context = build_context()
    try:
        plan = translate(args.sentence, context)
    except PlanError as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 2

    records = build_records(plan, context)
    _print_plan(plan, records, context)

    if args.dry_run:
        print("\nDry run -- nothing written.")
        return 0

    if not args.yes and not _confirm(plan.session):
        print("Cancelled.")
        return 1

    path = apply_plan(plan, records)
    print(f"\nWrote {len(records)} course(s) for {plan.session} to {path}")
    print("  Roll back with: python nl_schedule.py --restore")
    if not notify_server():
        print("  Server not running -- changes apply on next start.")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    sys.exit(main())
