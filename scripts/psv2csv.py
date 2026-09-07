#!/usr/bin/env python
"""Append ~~-delimited rows to a question CSV, quoting correctly.

Authoring questions straight into CSV means hand-quoting every option that
contains a comma, and a missed quote silently shifts the correct-answer column.
Author with a separator, let csv.writer do the quoting.

The separator is ~~ rather than a single pipe because question text legitimately
contains pipes: JavaScript ||, shell pipelines, SQL, and P(y|X) in statistics.

  python scripts/psv2csv.py rows.psv data/questions/ai-ml.csv
"""
import csv
import sys
from pathlib import Path

HEADER = ["external_id", "domain", "type", "topic", "difficulty", "question",
          "code", "language", "option_a", "option_b", "option_c", "option_d",
          "correct", "explanation"]


def main() -> int:
    src, dest = Path(sys.argv[1]), Path(sys.argv[2])
    new = not dest.exists()

    rows = []
    for n, line in enumerate(src.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        fields = line.split("~~")
        if len(fields) != len(HEADER):
            print(f"{src}:{n}: {len(fields)} fields, expected {len(HEADER)}", file=sys.stderr)
            return 1
        rows.append([f.strip() for f in fields])

    with dest.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if new:
            writer.writerow(HEADER)
        writer.writerows(rows)

    print(f"+{len(rows)} rows → {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
