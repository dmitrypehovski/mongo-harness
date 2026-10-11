"""Dataset packs: what makes this harness usable on data that is not sample_mflix.

Everything the gate does is generic: it measures two versions of an agent on the same
cases and decides whether a change is real. What is specific to a dataset is the questions,
the reference answers, and the probes that check the instrument against that particular
collection. A pack is where those live, so the harness can be pointed at another database
without touching the gate.

A pack is a JSON file:

    {
      "name": "theaters",
      "database": "sample_mflix",
      "description": "one line about the data and the questions",
      "tasks": [
        {
          "id": "t01",
          "family": "find",
          "split": "train",
          "collection": "theaters",
          "question": "How many theatres are in California?",
          "reference": "db.theaters.countDocuments({\"location.address.state\": \"CA\"})"
        }
      ]
    }

The rules a pack has to satisfy are the same rules the built-in suite follows: the case is
scored on the rows the reference query returns, never on the text of the agent's query, and
a reference query must be deterministic, so a top-k boundary cannot flip between runs and
turn into a phantom improvement.

    from mh import datasets

    pack = datasets.load("datasets/theaters.json")
    print(datasets.validate(pack))          # [] when the pack is sound
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

REQUIRED_TASK_KEYS = ("id", "question", "reference", "split", "collection")
SPLITS = ("train", "holdout")


@dataclass
class Pack:
    """One dataset's questions and reference answers."""

    name: str
    tasks: list[dict]
    database: str | None = None
    description: str = ""
    audit_probes: list[dict] = field(default_factory=list)
    source: str | None = None

    def summary(self) -> dict:
        """What the pack contains, for printing and for the record."""
        families = sorted({task.get("family", "?") for task in self.tasks})
        collections = sorted({task["collection"] for task in self.tasks if task.get("collection")})
        return {
            "name": self.name,
            "database": self.database,
            "tasks": len(self.tasks),
            "splits": {split: sum(1 for t in self.tasks if t.get("split") == split) for split in SPLITS},
            "families": families,
            "collections": collections,
        }


def load(path: str | Path) -> Pack:
    """Read a pack from disk and check it before anything measures with it."""
    location = Path(path)
    data = json.loads(location.read_text(encoding="utf-8"))
    pack = Pack(
        name=data.get("name") or location.stem,
        tasks=list(data.get("tasks") or []),
        database=data.get("database"),
        description=data.get("description", ""),
        audit_probes=list(data.get("audit_probes") or []),
        source=str(location),
    )
    problems = validate(pack)
    if problems:
        raise ValueError(f"{location}: " + "; ".join(problems))
    return pack


def validate(pack: Pack) -> list[str]:
    """Return every reason this pack cannot be trusted, rather than the first."""
    problems: list[str] = []
    if not pack.tasks:
        problems.append("the pack has no tasks")
        return problems

    seen: set[str] = set()
    for index, task in enumerate(pack.tasks):
        where = f"task {index + 1}"
        for key in REQUIRED_TASK_KEYS:
            if not task.get(key):
                problems.append(f"{where}: missing {key}")
        task_id = task.get("id")
        if task_id:
            where = f"task {task_id}"
            if task_id in seen:
                problems.append(f"{where}: duplicate id")
            seen.add(task_id)
        if task.get("split") and task["split"] not in SPLITS:
            problems.append(f"{where}: split must be one of {SPLITS}")
        if task.get("reference") and not str(task["reference"]).strip().startswith("db."):
            problems.append(f"{where}: the reference must be a db.<collection> query")

    for split in SPLITS:
        if not any(task.get("split") == split for task in pack.tasks):
            problems.append(f"nothing is assigned to the {split} split; the gate needs both")
    return problems


def write(pack: Pack, path: str | Path) -> Path:
    """Write a pack back out, e.g. after generating reference answers elsewhere."""
    location = Path(path)
    location.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "name": pack.name,
        "database": pack.database,
        "description": pack.description,
        "tasks": pack.tasks,
    }
    if pack.audit_probes:
        payload["audit_probes"] = pack.audit_probes
    location.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return location
