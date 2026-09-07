"""Question bank import and validation.

Shared by the CLI importer and (in Phase 6) the admin HTTP endpoints, so a
question can never enter the bank through a path that skips validation.

The rules here exist because a bad row is not a cosmetic problem: a question with
two correct answers, or a blank option, mis-scores every student who receives it,
and nobody finds out until after the event.
"""
import csv
import io
from dataclasses import dataclass, field

TYPES = {"mcq", "code_output", "debug", "scenario", "logic"}
DIFFICULTIES = {"easy", "medium", "hard"}
OPTION_COLUMNS = ["option_a", "option_b", "option_c", "option_d", "option_e"]
LETTERS = "ABCDE"

REQUIRED = [
    "external_id", "domain", "type", "topic", "difficulty",
    "question", "option_a", "option_b", "correct", "explanation",
]


@dataclass
class Row:
    external_id: str
    domain: str
    type: str
    topic: str
    difficulty: str
    question: str
    code: str | None
    language: str | None
    explanation: str
    options: list[str]
    correct_index: int


@dataclass
class ImportReport:
    rows: list[Row] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    created: int = 0
    updated: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors


def _clean(value: str | None) -> str:
    return (value or "").strip()


def parse_csv(text: str, known_domains: set[str]) -> ImportReport:
    """Validate every row before touching the database. An import is all-or-
    nothing: a spreadsheet with one bad row imports nothing, so the operator
    fixes the sheet rather than hunting for which half landed."""
    report = ImportReport()
    reader = csv.DictReader(io.StringIO(text))

    if reader.fieldnames is None:
        report.errors.append("file is empty")
        return report

    headers = {h.strip().lower() for h in reader.fieldnames}
    missing = [c for c in REQUIRED if c not in headers]
    if missing:
        report.errors.append(f"missing required column(s): {', '.join(missing)}")
        return report

    seen: dict[tuple[str, str], int] = {}

    for line, raw in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): v for k, v in raw.items()}
        errors: list[str] = []

        external_id = _clean(row.get("external_id"))
        domain = _clean(row.get("domain")).lower()
        qtype = _clean(row.get("type")).lower()
        topic = _clean(row.get("topic"))
        difficulty = _clean(row.get("difficulty")).lower()
        question = _clean(row.get("question"))
        explanation = _clean(row.get("explanation"))
        correct = _clean(row.get("correct")).upper()

        if not external_id:
            errors.append("external_id is required")
        if domain not in known_domains:
            errors.append(f"unknown domain {domain!r}")
        if qtype not in TYPES:
            errors.append(f"type must be one of {sorted(TYPES)}")
        if difficulty not in DIFFICULTIES:
            errors.append(f"difficulty must be one of {sorted(DIFFICULTIES)}")
        if not topic:
            errors.append("topic is required")
        if len(question) < 10:
            errors.append("question text is too short")
        # An explanation is not decoration: it is what makes a flagged question
        # reviewable, and what a student is shown if you ever publish answers.
        if len(explanation) < 10:
            errors.append("explanation is too short")

        options = [_clean(row.get(c)) for c in OPTION_COLUMNS]
        options = [o for o in options if o]
        if len(options) < 2:
            errors.append("at least two options are required")
        if len(set(o.lower() for o in options)) != len(options):
            errors.append("options must be distinct")

        correct_index = -1
        if correct not in LETTERS:
            errors.append(f"correct must be a letter A-{LETTERS[len(options) - 1]}"
                          if options else "correct is required")
        else:
            correct_index = LETTERS.index(correct)
            if correct_index >= len(options):
                errors.append(f"correct={correct} but only {len(options)} options given")

        key = (domain, external_id)
        if key in seen:
            errors.append(f"duplicate external_id {external_id!r} (also on line {seen[key]})")
        else:
            seen[key] = line

        if errors:
            report.errors.append(f"line {line}: " + "; ".join(errors))
            continue

        report.rows.append(
            Row(
                external_id=external_id,
                domain=domain,
                type=qtype,
                topic=topic,
                difficulty=difficulty,
                question=question,
                # Spreadsheets are miserable with embedded newlines, so the
                # import format accepts a literal backslash-n in code snippets.
                code=(_clean(row.get("code")).replace("\\n", "\n") or None),
                language=_clean(row.get("language")) or None,
                explanation=explanation,
                options=options,
                correct_index=correct_index,
            )
        )

    if not report.rows and not report.errors:
        report.errors.append("file contains no data rows")

    # A bank where the answer is nearly always option A is solvable without
    # knowing anything. Per-attempt shuffling hides it at exam time, which is
    # exactly why it goes unnoticed while it quietly degrades every distractor:
    # options nobody expects to be correct get written as filler.
    if len(report.rows) >= 20:
        counts: dict[str, int] = {}
        for row in report.rows:
            letter = LETTERS[row.correct_index]
            counts[letter] = counts.get(letter, 0) + 1
        letter, n = max(counts.items(), key=lambda kv: kv[1])
        share = n / len(report.rows)
        if share > 0.40:
            report.errors.append(
                f"answer key is lopsided: {letter} is correct for {n} of "
                f"{len(report.rows)} questions ({share:.0%}). Spread the correct "
                f"answer across positions — no letter above 40%."
            )

    return report


def apply(report: ImportReport, cur, status: str = "active") -> ImportReport:
    """Write validated rows in one transaction. Options are replaced wholesale on
    update — editing a question's options in place would leave stale answer rows
    pointing at options that no longer belong to it."""
    cur.execute("select id, slug from domains")
    domain_ids = {r["slug"]: r["id"] for r in cur.fetchall()}

    for row in report.rows:
        domain_id = domain_ids[row.domain]
        cur.execute(
            """
            insert into questions
              (domain_id, external_id, type, body, code_snippet, language,
               topic, difficulty, explanation, status)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (domain_id, external_id) where external_id is not null
            do update set
              type = excluded.type, body = excluded.body,
              code_snippet = excluded.code_snippet, language = excluded.language,
              topic = excluded.topic, difficulty = excluded.difficulty,
              explanation = excluded.explanation, status = excluded.status,
              version = questions.version + 1, updated_at = now()
            returning id, (xmax = 0) as inserted
            """,
            (domain_id, row.external_id, row.type, row.question, row.code,
             row.language, row.topic, row.difficulty, row.explanation, status),
        )
        result = cur.fetchone()
        question_id = result["id"]
        if result["inserted"]:
            report.created += 1
        else:
            report.updated += 1

        cur.execute("delete from question_options where question_id = %s", (question_id,))
        for position, body in enumerate(row.options):
            cur.execute(
                """
                insert into question_options (question_id, body, is_correct, position)
                values (%s, %s, %s, %s)
                """,
                (question_id, body, position == row.correct_index, position + 1),
            )

    return report


def bank_coverage(cur, blueprint: dict[str, int]) -> list[dict]:
    """Per domain: can it actually serve the blueprint, and with how much margin?

    'Enough questions' is not one number. A domain with 200 easy questions and
    2 hard ones cannot serve a 5/7/3 blueprint, and finding that out at 9am on
    event day is not an option."""
    cur.execute(
        """
        select d.slug, d.name, q.difficulty, count(*) as n,
               count(distinct q.topic) as topics
        from domains d
        left join questions q on q.domain_id = d.id and q.status = 'active'
        where d.is_active
        group by d.slug, d.name, q.difficulty
        """
    )
    by_domain: dict[str, dict] = {}
    for r in cur.fetchall():
        entry = by_domain.setdefault(
            r["slug"], {"slug": r["slug"], "name": r["name"], "counts": {}, "topics": 0}
        )
        if r["difficulty"]:
            entry["counts"][r["difficulty"]] = r["n"]
            entry["topics"] = max(entry["topics"], r["topics"])

    out = []
    for entry in by_domain.values():
        tiers = []
        ok = True
        for difficulty, needed in blueprint.items():
            have = entry["counts"].get(difficulty, 0)
            # 4x the per-student draw keeps expected overlap between any two
            # students low enough that the exam still feels individual.
            comfortable = needed * 4
            tiers.append(
                {
                    "difficulty": difficulty,
                    "needed": needed,
                    "have": have,
                    "status": "ok" if have >= comfortable
                    else "thin" if have >= needed
                    else "insufficient",
                }
            )
            if have < needed:
                ok = False
        out.append({**entry, "tiers": tiers, "can_serve_blueprint": ok})
    return sorted(out, key=lambda e: e["slug"])
