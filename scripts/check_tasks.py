"""Check the ground-truth suite against the database.

For every task this script

1. parses and runs the reference query through the same sandbox the harness uses,
2. runs it a second time and confirms the result digest is stable,
3. for sorted queries with a limit, looks one row past the cut-off and warns when
   the primary sort key ties there, because such a task could flip between runs,
4. reports the size of the expected result set, so empty or huge answers are caught.

Run:  python scripts/check_tasks.py
"""

from __future__ import annotations

import copy
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mh import scorer, tasks  # noqa: E402

ALL_TOOLS = ["find", "aggregate", "count"]


def _sort_keys(mql: scorer.Mql) -> list[str]:
    """Ordered sort keys of the statement, empty when it does not sort."""
    for name, value in mql.chain:
        if name == "sort" and isinstance(value, dict) and value:
            return list(value)
    if mql.method == "aggregate" and mql.args and isinstance(mql.args[0], list):
        for stage in mql.args[0]:
            if isinstance(stage, dict) and "$sort" in stage and stage["$sort"]:
                return list(stage["$sort"])
    return []


def _limit_of(mql: scorer.Mql) -> int | None:
    """Limit of the statement, if it has one."""
    for name, value in mql.chain:
        if name == "limit":
            return int(value)
    if mql.method == "aggregate" and mql.args and isinstance(mql.args[0], list):
        for stage in mql.args[0]:
            if isinstance(stage, dict) and "$limit" in stage:
                return int(stage["$limit"])
    return None


def _with_limit(mql: scorer.Mql, limit: int) -> scorer.Mql:
    """Copy of the statement with its limit raised."""
    clone = copy.deepcopy(mql)
    for index, (name, _) in enumerate(clone.chain):
        if name == "limit":
            clone.chain[index] = ("limit", limit)
            return clone
    if clone.method == "aggregate" and clone.args and isinstance(clone.args[0], list):
        pipeline = clone.args[0]
        for index, stage in enumerate(pipeline):
            if isinstance(stage, dict) and "$limit" in stage:
                pipeline[index] = {"$limit": limit}
                return clone
        pipeline.append({"$limit": limit})
    return clone


def _value_at(row, path: str):
    """Read a dotted path out of a result row."""
    node = row
    for part in path.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    return node


def main() -> int:
    """Run every check and print a readable report."""
    once = "--once" in sys.argv
    db = scorer.connect().get_database(os.environ.get("MH_MFLIX_DB", "sample_mflix"))
    report: list[tuple[str, str, str]] = []
    problems = 0
    empty = []
    slow = []
    ambiguous: list[str] = []

    for task in tasks.TASKS:
        started = time.time()
        try:
            mql = scorer.parse_mql(task["reference"])
        except scorer.ParseError as exc:
            report.append((task["id"], "PARSE-FAIL", str(exc)))
            problems += 1
            continue

        first = scorer.execute(db, mql, ALL_TOOLS)
        if not first.ok:
            report.append((task["id"], "RUN-FAIL", first.error))
            problems += 1
            continue

        if not once:
            second = scorer.execute(db, mql, ALL_TOOLS)
            if first.digest != second.digest:
                report.append((task["id"], "UNSTABLE", "two runs gave different digests"))
                problems += 1
                continue

        elapsed = time.time() - started
        if elapsed > 5:
            slow.append((task["id"], round(elapsed, 1)))

        note = f"{len(first.rows)} rows in {elapsed:.1f}s"
        if not first.rows:
            empty.append(task["id"])
        limit = _limit_of(mql)
        keys = _sort_keys(mql)
        if limit and keys:
            wider = scorer.execute(db, _with_limit(mql, limit + 1), ALL_TOOLS)
            if wider.ok and len(wider.rows) > limit:
                primary = _value_at(wider.rows[limit - 1], keys[0])
                primary_next = _value_at(wider.rows[limit], keys[0])
                if primary == primary_next:
                    note += (
                        f" | AMBIGUOUS at cut-off: {keys[0]} ties at {primary!r} between rows "
                        f"{limit} and {limit + 1}, so a correct query may order them differently"
                    )
                    ambiguous.append(task["id"])
                full = tuple(_value_at(wider.rows[limit - 1], key) for key in keys)
                full_next = tuple(_value_at(wider.rows[limit], key) for key in keys)
                if full == full_next:
                    note += " | UNSTABLE: every sort key ties at the cut-off"
                    problems += 1
        report.append((task["id"], "ok", note))

    width = max(len(row[0]) for row in report)
    for task_id, status, note in report:
        print(f"{task_id:<{width}}  {status:<10}  {note}")

    print()
    print("summary:", tasks.summary())
    print(f"checked {len(tasks.TASKS)} tasks, problems: {problems}")
    if slow:
        print("slow tasks:", ", ".join(f"{task_id} {seconds}s" for task_id, seconds in slow))
    if ambiguous:
        print("AMBIGUOUS at the cut-off (a correct query may order these differently):", ", ".join(ambiguous))
    if empty:
        print("tasks whose expected result is EMPTY (suspicious):", ", ".join(empty))
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
