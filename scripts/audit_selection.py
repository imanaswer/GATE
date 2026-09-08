#!/usr/bin/env python
"""Measure what question selection actually does against the live bank.

  python scripts/audit_selection.py [papers_per_domain]

bank:check predicts overlap from pool sizes. This measures it, by generating
papers and comparing them. Re-run it after replacing the seed bank with curated
questions — the prediction assumes uniform topics, and a real bank never is.

What the numbers mean:
  mean overlap   questions two students share, of 15. Low is good.
  max overlap    the worst pair seen. A tail, not the typical experience.
  coverage       how much of the bank ever gets used. Anything short of all
                 of it means some questions are unreachable.
  topic dupes    extra questions on an already-used topic, per paper. High
                 means the domain has too few distinct topics.
"""
import itertools
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import db  # noqa: E402
from server.exam import select_questions  # noqa: E402
from server.settings import settings  # noqa: E402


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    db.pool.open()
    try:
        with db.cursor() as cur:
            cur.execute("select blueprint from exam_events where slug = %s",
                        (settings.event_slug,))
            row = cur.fetchone()
            blueprint = row["blueprint"] if row else {"easy": 5, "medium": 7, "hard": 3}
            draw = sum(blueprint.values())

            cur.execute("select id, name from domains where is_active order by position")
            domains = cur.fetchall()

            print(f"{n} papers per domain, blueprint {blueprint}\n")
            print(f"{'domain':<24} {'mean':>6} {'max':>4} {'coverage':>10} {'topic dupes':>12}")
            print("-" * 60)

            worst = 0
            for d in domains:
                papers, dupes = [], []
                for _ in range(n):
                    picked = select_questions(cur, d["id"], blueprint)
                    if len(picked) != draw:
                        print(f"FAIL {d['name']}: got {len(picked)} questions")
                        return 1
                    ids = {p["id"] for p in picked}
                    if len(ids) != draw:
                        print(f"FAIL {d['name']}: a question appeared twice in one paper")
                        return 1
                    if dict(Counter(p["difficulty"] for p in picked)) != blueprint:
                        print(f"FAIL {d['name']}: blueprint not honoured")
                        return 1
                    papers.append(ids)
                    cur.execute("select topic from questions where id = any(%s)", (list(ids),))
                    counts = Counter(r["topic"] for r in cur.fetchall())
                    dupes.append(sum(c - 1 for c in counts.values() if c > 1))

                pairs = list(itertools.islice(itertools.combinations(papers, 2), 4000))
                overlaps = [len(a & b) for a, b in pairs]
                seen = len(set().union(*papers))
                cur.execute(
                    "select count(*) as n from questions where domain_id = %s and status = 'active'",
                    (d["id"],),
                )
                total = cur.fetchone()["n"]
                worst = max(worst, statistics.mean(overlaps))
                print(f"{d['name']:<24} {statistics.mean(overlaps):>6.2f} {max(overlaps):>4} "
                      f"{seen:>5}/{total:<4} {statistics.mean(dupes):>12.2f}")

            print()
            if worst > draw / 3:
                print(f"⚠ mean overlap {worst:.2f} of {draw} is high — grow the bank")
                return 1
            print(f"✓ blueprint exact on every paper; worst mean overlap {worst:.2f} of {draw}")
            return 0
    finally:
        db.pool.close()


if __name__ == "__main__":
    raise SystemExit(main())
