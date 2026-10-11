"""Audit the measuring instrument before believing anything it reports.

The harness is only as good as the sandbox that scores it. If the sandbox refuses a
query that MongoDB would have run, the harness is punished for output the database
accepts, and every number it reports is wrong in a direction nobody is watching. That
is not a hypothesis: it happened here. The parser rejected JavaScript regular
expressions, 38 answers were recorded as failures, and the same untouched version
scored 65.6% under the broken ruler and 75.0% after the repair.

So the instrument gets its own check, run before any improvement is believed.

Two kinds of probe:

* **equivalence** — the same question written twice, once with the JavaScript sugar a
  model naturally emits (``/pattern/i``, ``ObjectId("...")``, ``ISODate("...")``) and
  once in strict Extended JSON. MongoDB accepts both. The harness must accept both and
  return the same rows. Any disagreement is a ruler defect, reported with the
  construct that caused it.
* **policy** — statements the envelope is *supposed* to refuse (``$where``, ``$out``,
  writes). Here the audit is checking the opposite direction: a gate that starts
  letting these through is equally a defect, because the results it produces after
  that point are not comparable to the ones before.

Fault injection: set ``MH_RULER_DISABLE`` to ``regex`` or ``oid`` to switch off part
of the parser and watch the audit find the historical defect instead of reporting that
everything is fine. A detector that cannot fail is not a detector.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from mh import scorer

log = logging.getLogger(__name__)

LINE = "-" * 92


@dataclass
class Probe:
    """One check of the instrument.

    ``build`` receives a live database so a probe can anchor itself in real data
    instead of in a value that happens to be present today.
    """

    name: str
    kind: str  # equivalence | policy
    note: str
    build: Callable[[Any], tuple[str, str]] | None = None
    sugar: str = ""
    canonical: str = ""

    def texts(self, db) -> tuple[str, str]:
        """Return the (sugar, canonical) texts for this probe."""
        if self.build is not None:
            return self.build(db)
        return self.sugar, self.canonical


@dataclass
class Outcome:
    """What the audit found for one probe."""

    probe: Probe
    verdict: str  # agrees | diverges | refused | admitted | unusable
    detail: str = ""
    rows: int = 0


def _first_movie_id(db) -> str:
    """A comment's movie_id, so the ObjectId probe points at a real document."""
    row = db.comments.find_one({"movie_id": {"$exists": True}}, {"movie_id": 1})
    return str(row["movie_id"]) if row else "000000000000000000000000"


def _first_release_date(db) -> str:
    """A real release date, so the ISODate probe returns rows."""
    row = db.movies.find_one({"released": {"$type": "date"}}, {"released": 1})
    if not row:
        return "2000-01-01T00:00:00Z"
    return row["released"].strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_objectid(db) -> tuple[str, str]:
    oid = _first_movie_id(db)
    return (
        f'db.comments.find({{"movie_id": ObjectId("{oid}")}}, {{"movie_id": 1}}).limit(2)',
        f'db.comments.find({{"movie_id": {{"$oid": "{oid}"}}}}, {{"movie_id": 1}}).limit(2)',
    )


def _build_isodate(db) -> tuple[str, str]:
    when = _first_release_date(db)
    return (
        f'db.movies.find({{"released": ISODate("{when}")}}, {{"title": 1, "released": 1}}).limit(2)',
        f'db.movies.find({{"released": {{"$date": "{when}"}}}}, {{"title": 1, "released": 1}}).limit(2)',
    )


def _email_domain(db) -> str:
    """A domain that really occurs in the dataset, with regex-safe characters only."""
    row = db.comments.find_one({"email": {"$type": "string"}}, {"email": 1})
    domain = (row["email"].split("@")[-1] if row else "example.com").split(".")[0]
    cleaned = re.sub(r"[^A-Za-z0-9]", "", domain)
    return cleaned or "example"


def _build_email_regex(db) -> tuple[str, str]:
    domain = _email_domain(db)
    return (
        f'db.comments.find({{"email": /@{domain}/i}}, {{"email": 1}}).limit(3)',
        f'db.comments.find({{"email": {{"$regex": "@{domain}", "$options": "i"}}}}, {{"email": 1}}).limit(3)',
    )


def _build_email_escaped(db) -> tuple[str, str]:
    """The escaped-dot case: the backslash must survive the rewrite into Extended JSON."""
    domain = _email_domain(db)
    return (
        f'db.comments.find({{"email": /@{domain}\\.com$/i}}, {{"email": 1}}).limit(3)',
        f'db.comments.find({{"email": {{"$regex": "@{domain}\\\\.com$", "$options": "i"}}}}, '
        f'{{"email": 1}}).limit(3)',
    )


def _cast_forename(db) -> str:
    """A real cast member's first name, letters only."""
    row = db.movies.find_one({"cast.0": {"$type": "string"}}, {"cast": 1})
    name = row["cast"][0] if row else "Robert"
    cleaned = re.sub(r"[^A-Za-z]", "", name.split()[0])
    return cleaned or "Robert"


def _build_cast_regex(db) -> tuple[str, str]:
    """A regex over an array field, on a name that is really in the data."""
    name = _cast_forename(db)
    return (
        f'db.movies.find({{"cast": /{name}/i}}, {{"title": 1}}).sort({{"title": 1}}).limit(3)',
        f'db.movies.find({{"cast": {{"$regex": "{name}", "$options": "i"}}}}, {{"title": 1}})'
        f'.sort({{"title": 1}}).limit(3)',
    )


EQUIVALENCE_PROBES: list[Probe] = [
    Probe(
        name="javascript regex literal",
        kind="equivalence",
        note="/the/i in a filter is what a model writes; MongoDB runs it",
        sugar='db.movies.find({"title": /the/i}, {"title": 1}).sort({"title": 1}).limit(3)',
        canonical=(
            'db.movies.find({"title": {"$regex": "the", "$options": "i"}}, {"title": 1})'
            '.sort({"title": 1}).limit(3)'
        ),
    ),
    Probe(
        name="regex literal with escaped dot",
        kind="equivalence",
        note="an escaped dot must survive the rewrite into Extended JSON",
        build=_build_email_escaped,
    ),
    Probe(
        name="regex literal on an array field",
        kind="equivalence",
        note="a regex over cast, on a name that is really in the data",
        build=_build_cast_regex,
    ),
    Probe(
        name="regex literal with a wildcard prefix",
        kind="equivalence",
        note="/^The / anchors, and the anchor must not be lost",
        sugar=r'db.movies.find({"title": /^The /}, {"title": 1}).sort({"title": 1}).limit(3)',
        canonical=r'db.movies.find({"title": {"$regex": "^The "}}, {"title": 1}).sort({"title": 1}).limit(3)',
    ),
    Probe(
        name="ObjectId() in a filter",
        kind="equivalence",
        note="a real identifier from the dataset, not a made-up one",
        build=_build_objectid,
    ),
    Probe(
        name="ISODate() in a filter",
        kind="equivalence",
        note="a real release date, so both forms must return the same rows",
        build=_build_isodate,
    ),
    Probe(
        name="dotted path into a subdocument",
        kind="equivalence",
        note="the highest rated films, written the same way twice",
        sugar='db.movies.find({"imdb.rating": {"$gt": 8.5}}, {"title": 1, "imdb.rating": 1}).sort({"imdb.rating": -1}).limit(3)',
        canonical='db.movies.find({"imdb.rating": {"$gt": 8.5}}, {"title": 1, "imdb.rating": 1}).sort({"imdb.rating": -1}).limit(3)',
    ),
    Probe(
        name="$in over a scalar field",
        kind="equivalence",
        note="a list membership filter",
        sugar='db.movies.find({"year": {"$in": [1994, 1995, 1996]}}, {"title": 1, "year": 1}).sort({"year": 1, "title": 1}).limit(4)',
        canonical='db.movies.find({"year": {"$in": [1994, 1995, 1996]}}, {"title": 1, "year": 1}).sort({"year": 1, "title": 1}).limit(4)',
    ),
    Probe(
        name="aggregation with a group",
        kind="equivalence",
        note="the average rating shape the questions ask for",
        sugar='db.movies.aggregate([{"$match": {"year": {"$gte": 2000}}}, {"$group": {"_id": null, "avg": {"$avg": "$imdb.rating"}}}])',
        canonical='db.movies.aggregate([{"$match": {"year": {"$gte": 2000}}}, {"$group": {"_id": null, "avg": {"$avg": "$imdb.rating"}}}])',
    ),
    Probe(
        name="aggregation with a join",
        kind="equivalence",
        note="the join that needs an index on the foreign side",
        sugar=(
            'db.movies.aggregate([{"$lookup": {"from": "comments", "localField": "_id", '
            '"foreignField": "movie_id", "as": "c"}}, {"$addFields": {"n": {"$size": "$c"}}}, '
            '{"$sort": {"n": -1}}, {"$limit": 2}, {"$project": {"title": 1, "n": 1}}])'
        ),
        canonical=(
            'db.movies.aggregate([{"$lookup": {"from": "comments", "localField": "_id", '
            '"foreignField": "movie_id", "as": "c"}}, {"$addFields": {"n": {"$size": "$c"}}}, '
            '{"$sort": {"n": -1}}, {"$limit": 2}, {"$project": {"title": 1, "n": 1}}])'
        ),
    ),
    Probe(
        name="countDocuments",
        kind="equivalence",
        note="the counting tool the envelope grants",
        sugar='db.movies.countDocuments({"year": {"$gt": 2000}})',
        canonical='db.movies.countDocuments({"year": {"$gt": 2000}})',
    ),
]


POLICY_PROBES: list[Probe] = [
    Probe(name="$where is refused", kind="policy", note="server-side JavaScript",
          sugar='db.movies.find({"$where": "this.year > 2000"}).limit(1)'),
    Probe(name="$function is refused", kind="policy", note="server-side JavaScript",
          sugar='db.movies.aggregate([{"$match": {}}, {"$addFields": {"x": {"$function": {"body": "return 1", "args": [], "lang": "js"}}}}])'),
    Probe(name="$out is refused", kind="policy", note="a pipeline that writes",
          sugar='db.movies.aggregate([{"$match": {}}, {"$out": "exfiltrated"}])'),
    Probe(name="a write method is refused", kind="policy", note="not a read method",
          sugar='db.movies.deleteMany({})'),
    Probe(name="an update is refused", kind="policy", note="not a read method",
          sugar='db.movies.updateMany({}, {"$set": {"title": "x"}})'),
]


def inject_fault(kind: str) -> None:
    """Switch off part of the parser, to prove the audit can fail.

    This exists to keep the detector honest. An audit that has never reported a defect
    is indistinguishable from an audit that cannot report one.
    """
    if kind == "regex":
        scorer._regex_literals = lambda text: text  # type: ignore[assignment]
        log.warning("fault injected: the regex rewrite is disabled")
    elif kind == "oid":
        scorer._JS_CALLS = ()  # type: ignore[assignment]
        log.warning("fault injected: ObjectId()/ISODate() rewrites are disabled")
    else:
        raise ValueError(f"unknown fault {kind!r}; use 'regex' or 'oid'")


def _run_text(db, text: str) -> tuple[scorer.Execution | None, str]:
    """Push one statement through the exact path the harness uses to score answers."""
    try:
        mql = scorer.parse_mql(text)
    except scorer.ParseError as exc:
        return None, str(exc)
    except Exception as exc:  # anything the parser does besides a clean refusal
        return None, f"{type(exc).__name__}: {exc}"
    return scorer.execute(db, mql), ""


def audit(db) -> list[Outcome]:
    """Run every probe against a live database and report what the instrument did."""
    outcomes: list[Outcome] = []

    for probe in EQUIVALENCE_PROBES:
        sugar, canonical = probe.texts(db)
        left, left_error = _run_text(db, sugar)
        right, right_error = _run_text(db, canonical)
        if left is None or right is None:
            detail = f"sugar: {left_error or 'ok'} / strict: {right_error or 'ok'}"
            outcomes.append(Outcome(probe, "diverges", detail))
            continue
        if not left.ok or not right.ok:
            detail = f"sugar: {left.status} {left.error[:60]} / strict: {right.status} {right.error[:60]}"
            outcomes.append(Outcome(probe, "unusable", detail, len(left.rows)))
            continue
        if left.digest != right.digest:
            detail = (
                f"the two spellings of one query disagree: {len(left.rows)} rows against "
                f"{len(right.rows)}. MongoDB accepts both; the sandbox must too."
            )
            outcomes.append(Outcome(probe, "diverges", detail, len(left.rows)))
            continue
        outcomes.append(Outcome(probe, "agrees", f"{len(left.rows)} row(s), identical", len(left.rows)))

    for probe in POLICY_PROBES:
        sugar, _ = probe.texts(db)
        execution, error = _run_text(db, sugar)
        if execution is None:
            outcomes.append(Outcome(probe, "refused", error[:70]))
            continue
        if execution.ok:
            detail = f"admitted with status {execution.status}: the envelope let it through"
            outcomes.append(Outcome(probe, "admitted", detail, len(execution.rows)))
            continue
        outcomes.append(Outcome(probe, "refused", f"{execution.status}: {execution.error[:52]}"))

    return outcomes


def defects(outcomes: list[Outcome]) -> list[Outcome]:
    """The outcomes that mean the instrument cannot be trusted as it stands."""
    return [o for o in outcomes if o.verdict in ("diverges", "unusable", "admitted")]


def report(outcomes: list[Outcome]) -> str:
    """Render the audit as a table a human can read in a hurry."""
    width = max(len(o.probe.name) for o in outcomes)
    lines = [LINE, "ruler audit: does the sandbox accept what MongoDB accepts?", LINE]
    for outcome in outcomes:
        mark = "ok  " if outcome.verdict in ("agrees", "refused") else "FAIL"
        lines.append(f"{mark}  {outcome.probe.name:<{width}}  {outcome.verdict:<9} {outcome.detail}")
    broken = defects(outcomes)
    equivalence = [o for o in outcomes if o.probe.kind == "equivalence"]
    policy = [o for o in outcomes if o.probe.kind == "policy"]
    lines.append(LINE)
    lines.append(
        f"{len(equivalence)} equivalence probe(s): "
        f"{len([o for o in equivalence if o.verdict == 'agrees'])} agreed, "
        f"{len([o for o in equivalence if o.verdict != 'agrees'])} diverged"
    )
    lines.append(
        f"{len(policy)} policy probe(s): "
        f"{len([o for o in policy if o.verdict == 'refused'])} refused, "
        f"{len([o for o in policy if o.verdict != 'refused'])} admitted"
    )
    if broken:
        lines.append("")
        lines.append("The instrument is lying. Fix this before trusting any measurement:")
        for outcome in broken:
            lines.append(f"  * {outcome.probe.name}: {outcome.detail}")
    else:
        lines.append("")
        lines.append("The instrument agrees with the database on every probe. Measurements stand.")
    lines.append("")
    lines.append(json.dumps({"probes": len(outcomes), "defects": len(broken)}, sort_keys=True))
    lines.append(LINE)
    return "\n".join(lines)


def run(db, faults: str = "") -> tuple[list[Outcome], str]:
    """Inject the requested faults, audit, and return the outcomes and the report."""
    for kind in [part.strip() for part in faults.split(",") if part.strip()]:
        inject_fault(kind)
    outcomes = audit(db)
    return outcomes, report(outcomes)


def connection():
    """Open the sample database, the same way the harness does."""
    uri = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
    name = os.environ.get("MH_MFLIX_DB", "sample_mflix")
    return scorer.connect(uri).get_database(name)
