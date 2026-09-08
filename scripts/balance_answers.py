#!/usr/bin/env python
"""Spread the correct answer across option positions in a question CSV.

  python scripts/balance_answers.py data/questions/full-stack.csv

Rotating a question's options is content-preserving: same stem, same
distractors, different letter. It fixes the 'answer is usually A' tell that
`bank:check` rejects.

It does NOT fix the deeper version of that problem — a correct option written
with more care than the distractors around it, so it reads as right without
any knowledge. Only authoring fixes that one.

The rotation is derived from the external_id, so it is deterministic for a
given input file. It is a rotation, not a normalisation: running it twice
rotates twice. Run it once on a file that bank:check rejects, then leave it.
"""
import csv
import hashlib
import sys
from collections import Counter
from pathlib import Path

LETTERS = "ABCDE"


def main() -> int:
    path = Path(sys.argv[1])
    rows = list(csv.reader(path.open(encoding="utf-8")))
    header, body = rows[0], rows[1:]

    option_cols = [header.index(c) for c in header if c.startswith("option_")]
    correct_col = header.index("correct")
    id_col = header.index("external_id")

    for row in body:
        options = [row[i] for i in option_cols if row[i]]
        n = len(options)
        old = LETTERS.index(row[correct_col])
        shift = int(hashlib.md5(row[id_col].encode()).hexdigest(), 16) % n
        rotated = options[shift:] + options[:shift]
        for slot, col in enumerate(option_cols):
            row[col] = rotated[slot] if slot < n else ""
        row[correct_col] = LETTERS[(old - shift) % n]

    with path.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows([header] + body)

    spread = Counter(r[correct_col] for r in body)
    top, n = spread.most_common(1)[0]
    print(f"{path}: {dict(sorted(spread.items()))}  (max {top} at {n / len(body):.0%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
