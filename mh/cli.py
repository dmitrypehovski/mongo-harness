"""Command line entry point.

    python -m mh.cli init                 prepare collections, the starting version and reference answers
    python -m mh.cli status               where the harness is right now
    python -m mh.cli run [--split train]  measure the current version without changing it
    python -m mh.cli generation [--want N] [--forced FILE]
    python -m mh.cli loop --generations N
    python -m mh.cli edits                the ledger of every proposal and its fate
    python -m mh.cli rollback [--steps N]
    python -m mh.cli demo                 the scripted end-to-end demonstration
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from mh import agent, loop, ruler, scorer, store, tasks

LINE = "-" * 78


def _setup_logging(verbose: bool) -> None:
    """Configure logging for the command line."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _database():
    """Open the sample database the questions are asked against."""
    uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
    name = os.environ.get("MH_MFLIX_DB", "sample_mflix")
    return scorer.connect(uri).get_database(name)


def _banner(title: str) -> None:
    """Print a section banner."""
    print()
    print(LINE)
    print(title)
    print(LINE)


def command_init(args) -> int:
    """Prepare the database, the starting version and the reference answers."""
    db = _database()
    loop.init_db()
    store.ensure_vector_index()
    answers = loop.expected_answers(db, refresh=args.refresh)
    print(f"schema ready, {len(answers)} reference answers computed")
    print(json.dumps(store.ok(), indent=2))
    return 0


def command_status(args) -> int:
    """Show the current version and the recorded history."""
    version = store.latest_version()
    if version is None:
        print("no version yet: run `python -m mh.cli init`")
        return 1
    database = store.get_db()
    _banner(f"version {version['version_id']}  (promoted by {version.get('promoted_by')})")
    print(json.dumps(version["config"], indent=2, ensure_ascii=False))

    for split in ("train", "holdout"):
        latest = list(
            database.runs.find({"version_id": version["version_id"], "suite": split}).sort("started_at", -1).limit(1)
        )
        if latest:
            run = latest[0]
            print(f"last {split} run: {run['passed']}/{run['total']} = {run['rate']:.1%}")

    edits = list(database.edits.find({}).sort("created_at", -1).limit(10))
    _banner("recent proposals")
    for edit in edits:
        print(
            f"v{edit.get('version_from')} -> v{edit.get('version_to')}  "
            f"{edit.get('decision', ''):<22} {str(edit.get('strategy', ''))[:40]:<42} {str(edit.get('reason', ''))[:60]}"
        )
    return 0


def command_run(args) -> int:
    """Measure the current version over one or both splits."""
    db = _database()
    answers = loop.expected_answers(db)
    version = store.latest_version()
    for split in ([args.split] if args.split else ["train", "holdout"]):
        result = loop.evaluate(version["config"], split, db, answers, version["version_id"])
        print(f"{split:<8} {result['passed']}/{result['total']} = {result['rate']:.1%}")
        if args.show_failures:
            for item in result["results"]:
                if not item.get("passed"):
                    print(f"  {item['task_id']}  {item['question'][:80]}")
                    print(f"      produced: {str(item.get('readable_query') or item.get('query') or '')[:110]}")
                    print(f"      reason:   {str(item.get('reason') or item.get('error') or '')[:110]}")
    return 0


def _print_generation(summary: dict) -> None:
    """Print one generation's outcome the way the demonstration shows it."""
    incumbent = summary["incumbent"]
    print(
        f"current version {summary['version_id']}: "
        f"selection set {incumbent['train_passed']}/{incumbent['train_total']} "
        f"({incumbent['train_rate']:.1%}), verification set {incumbent['holdout_rate']:.1%} "
        f"over {incumbent['repeats']} run(s) of {incumbent['holdout_total']} questions"
    )
    for index, item in enumerate(summary["proposals"], 1):
        print()
        print(f"  proposal {index}: {item['strategy']}")
        if item.get("rationale"):
            print(f"    reasoning: {item['rationale'][:200]}")
        print(f"    decision:  {item['decision']}")
        print(f"    reason:    {item['reason'][:200]}")
        evidence = item.get("evidence") or {}
        if evidence:
            print(
                f"    evidence:  selection {evidence.get('train_rate_before')} -> "
                f"{evidence.get('train_rate_after')}, verification {evidence.get('holdout_rate_before')} -> "
                f"{evidence.get('holdout_rate_after')}, p={evidence.get('p_value')}"
            )
    print()
    if summary["promoted"]:
        print(f"=> promoted version {summary['promoted']} ({summary['promoted_strategy']})")
    else:
        print("=> nothing was promoted this generation")


def _generation(args) -> dict:
    """Run one generation, optionally with a seeded proposal list."""
    db = _database()
    answers = loop.expected_answers(db)
    forced = None
    if args.forced:
        forced = json.loads(Path(args.forced).read_text(encoding="utf-8"))
    summary = loop.run_generation(db, answers, want=args.want, forced=forced)
    _print_generation(summary)
    return summary


def command_generation(args) -> int:
    """Run a single generation."""
    _generation(args)
    return 0


def command_loop(args) -> int:
    """Run several generations in a row."""
    for index in range(args.generations):
        _banner(f"generation {index + 1} of {args.generations}")
        _generation(args)
    return 0


def command_edits(args) -> int:
    """Print the ledger of proposals."""
    database = store.get_db()
    for edit in database.edits.find({}).sort("created_at", 1):
        _banner(
            f"v{edit.get('version_from')} -> v{edit.get('version_to')}   "
            f"{edit.get('decision')}   (rolled back: {edit.get('rolled_back')})"
        )
        print(f"strategy:  {edit.get('strategy')}")
        print(f"reason:    {edit.get('reason')}")
        print(f"proposal:  {json.dumps(edit.get('proposal', {}), ensure_ascii=False)[:600]}")
        print(f"evidence:  {json.dumps(edit.get('evidence', {}), ensure_ascii=False)}")
    return 0


def command_rollback(args) -> int:
    """Undo the last promotion."""
    result = loop.rollback(_database(), steps=args.steps)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def command_demo(args) -> int:
    """Run the demonstration end to end, printing what a viewer needs to see."""
    db = _database()
    loop.init_db()
    store.ensure_vector_index()
    answers = loop.expected_answers(db)

    _banner("1. the starting harness, measured on questions it has never been tuned for")
    version = store.latest_version()
    train = loop.evaluate(version["config"], "train", db, answers, version["version_id"])
    holdout = loop.evaluate(version["config"], "holdout", db, answers, version["version_id"])
    print(f"  selection set:   {train['passed']}/{train['total']} = {train['rate']:.1%}")
    print(f"  verification set: {holdout['passed']}/{holdout['total']} = {holdout['rate']:.1%}")

    _banner("2. the harness proposes changes to itself, and the gate decides")
    summary = _generation(args)

    _banner("3. the ledger: every proposal with its reason, kept in MongoDB")
    command_edits(args)

    if summary["promoted"]:
        _banner("4. the promoted version, measured again")
        promoted = store.latest_version()
        after_train = loop.evaluate(promoted["config"], "train", db, answers, promoted["version_id"])
        after_holdout = loop.evaluate(promoted["config"], "holdout", db, answers, promoted["version_id"])
        print(f"  selection set:   {after_train['passed']}/{after_train['total']} = {after_train['rate']:.1%}")
        print(f"  verification set: {after_holdout['passed']}/{after_holdout['total']} = {after_holdout['rate']:.1%}")

        _banner("5. rolling the change back, because every promotion can be undone")
        result = loop.rollback(db, steps=1)
        print(json.dumps(result, indent=2))
        restored = store.latest_version()
        restored_holdout = loop.evaluate(restored["config"], "holdout", db, answers, restored["version_id"])
        print(f"  verification set after rollback: {restored_holdout['rate']:.1%} (version {restored['version_id']})")

    print()
    print(f"tasks: {tasks.summary()}")
    return 0


def command_audit_ruler(args) -> int:
    """Check the instrument itself, before believing any number it produces."""
    db = _database()
    outcomes, text = ruler.run(db, faults=args.inject or "")
    print(text)
    return 1 if ruler.defects(outcomes) else 0


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(prog="mh", description="the harness that earns its edits")
    parser.add_argument("--verbose", action="store_true", help="log model and database calls")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="prepare collections and reference answers")
    init.add_argument("--refresh", action="store_true", help="recompute the cached reference answers")
    init.set_defaults(func=command_init)

    status = sub.add_parser("status", help="show the current version")
    status.set_defaults(func=command_status)

    run = sub.add_parser("run", help="measure the current version")
    run.add_argument("--split", choices=["train", "holdout"])
    run.add_argument("--show-failures", action="store_true")
    run.set_defaults(func=command_run)

    for name, function, help_text in (
        ("generation", command_generation, "propose, measure and decide once"),
        ("loop", command_loop, "run several generations"),
        ("demo", command_demo, "run the scripted demonstration"),
    ):
        sub_parser = sub.add_parser(name, help=help_text)
        sub_parser.add_argument("--want", type=int, default=4, help="how many proposals to ask for")
        sub_parser.add_argument("--forced", help="JSON file with a seeded list of proposals")
        if name == "loop":
            sub_parser.add_argument("--generations", type=int, default=2)
        sub_parser.set_defaults(func=function)

    edits = sub.add_parser("edits", help="print the ledger")
    edits.set_defaults(func=command_edits)

    rollback = sub.add_parser("rollback", help="undo the last promotion")
    rollback.add_argument("--steps", type=int, default=1)
    rollback.set_defaults(func=command_rollback)

    ruler_parser = sub.add_parser(
        "audit-ruler", help="check the scoring sandbox against the database itself"
    )
    ruler_parser.add_argument(
        "--inject",
        help="fault injection for the detector: 'regex' or 'oid' disables part of the parser",
    )
    ruler_parser.set_defaults(func=command_audit_ruler)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and dispatch."""
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
