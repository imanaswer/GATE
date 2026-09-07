#!/usr/bin/env python
"""Question bank CLI.

  python scripts/questions.py import data/questions/*.csv
  python scripts/questions.py check
  python scripts/questions.py export ai-ml > ai-ml.csv

Deliberately a CLI, not an HTTP endpoint: loading the bank is an operator task
done once before the event, and a CLI keeps a bulk-write path off the public
API surface entirely. Admin HTTP CRUD arrives with the dashboard in Phase 6.
"""
import csv
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import db  # noqa: E402
from server.questions import (  # noqa: E402
    LETTERS, OPTION_COLUMNS, apply, bank_coverage, parse_csv,
)
from server.settings import settings  # noqa: E402


def cmd_import(patterns: list[str]) -> int:
    paths = sorted({p for pattern in patterns for p in glob.glob(pattern)})
    if not paths:
        print("no files matched", file=sys.stderr)
        return 1

    with db.cursor() as cur:
        cur.execute("select slug from domains where is_active")
        known = {r["slug"] for r in cur.fetchall()}

    failed = False
    for path in paths:
        report = parse_csv(Path(path).read_text(encoding="utf-8"), known)
        if not report.ok:
            print(f"\n✗ {path} — {len(report.errors)} problem(s), nothing imported:")
            for err in report.errors[:25]:
                print(f"    {err}")
            if len(report.errors) > 25:
                print(f"    … and {len(report.errors) - 25} more")
            failed = True
            continue

        with db.transaction() as cur:
            apply(report, cur)
        print(f"✓ {path} — {report.created} created, {report.updated} updated")

    return 1 if failed else 0


def cmd_check() -> int:
    with db.cursor() as cur:
        cur.execute("select blueprint from exam_events where slug = %s", (settings.event_slug,))
        row = cur.fetchone()
        blueprint = row["blueprint"] if row else {"easy": 5, "medium": 7, "hard": 3}
        coverage = bank_coverage(cur, blueprint)

    total_needed = sum(blueprint.values())
    print(f"blueprint: {json.dumps(blueprint)}  ({total_needed} questions per student)\n")

    problems = 0
    for domain in coverage:
        flag = "✓" if domain["can_serve_blueprint"] else "✗"
        counts = "  ".join(
            f"{t['difficulty']}: {t['have']:>4} / {t['needed']} {_mark(t['status'])}"
            for t in domain["tiers"]
        )
        total = sum(t["have"] for t in domain["tiers"])
        print(f"{flag} {domain['name']:<24} {counts}   total {total:>4}  topics {domain['topics']:>3}")
        if not domain["can_serve_blueprint"]:
            problems += 1
        problems += sum(1 for t in domain["tiers"] if t["status"] == "thin")

    print()
    if any(not d["can_serve_blueprint"] for d in coverage):
        print("✗ at least one domain CANNOT serve the blueprint — exam start would fail")
        return 1
    if problems:
        print("⚠ thin tiers: students will see noticeably overlapping questions")
        return 0
    print("✓ every domain can serve the blueprint with room to randomise")
    return 0


def _mark(status: str) -> str:
    return {"ok": "", "thin": "(thin)", "insufficient": "(INSUFFICIENT)"}[status]


def cmd_export(domain_slug: str) -> int:
    rows = db.fetch_all(
        """
        select q.external_id, d.slug as domain, q.type, q.topic, q.difficulty,
               q.body as question, q.code_snippet as code, q.language,
               q.explanation, q.status,
               array_agg(o.body order by o.position) as options,
               array_position(array_agg(o.is_correct order by o.position), true) as correct_pos
        from questions q
        join domains d on d.id = q.domain_id
        join question_options o on o.question_id = q.id
        where d.slug = %s
        group by q.id, d.slug
        order by q.difficulty, q.topic, q.external_id
        """,
        (domain_slug,),
    )
    writer = csv.writer(sys.stdout)
    writer.writerow(
        ["external_id", "domain", "type", "topic", "difficulty", "question",
         "code", "language", *OPTION_COLUMNS, "correct", "explanation", "status"]
    )
    for r in rows:
        options = list(r["options"]) + [""] * (len(OPTION_COLUMNS) - len(r["options"]))
        writer.writerow(
            [r["external_id"], r["domain"], r["type"], r["topic"], r["difficulty"],
             r["question"], r["code"] or "", r["language"] or "", *options,
             LETTERS[r["correct_pos"] - 1], r["explanation"], r["status"]]
        )
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    command, args = sys.argv[1], sys.argv[2:]

    db.pool.open()
    try:
        if command == "import":
            return cmd_import(args or ["data/questions/*.csv"])
        if command == "check":
            return cmd_check()
        if command == "export":
            if not args:
                print("export needs a domain slug", file=sys.stderr)
                return 1
            return cmd_export(args[0])
        print(f"unknown command {command!r}", file=sys.stderr)
        return 1
    finally:
        db.pool.close()


if __name__ == "__main__":
    raise SystemExit(main())
