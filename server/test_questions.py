"""Importer validation. Every assertion here is a way a bad spreadsheet could
mis-score a real student if it reached the bank."""
import textwrap

import pytest

from server.questions import bank_coverage, parse_csv

DOMAINS = {"ai-ml", "full-stack"}

HEADER = ("external_id,domain,type,topic,difficulty,question,code,language,"
          "option_a,option_b,option_c,option_d,correct,explanation")


def sheet(*rows: str) -> str:
    return HEADER + "\n" + "\n".join(textwrap.dedent(r).strip() for r in rows) + "\n"


GOOD = ('AIML-001,ai-ml,mcq,overfitting,easy,"What does a high training accuracy '
        'with low validation accuracy indicate?",,,Overfitting,Underfitting,'
        'Data leakage,Class imbalance,A,'
        '"The model has memorised the training set rather than learning a general rule."')


def test_valid_row_parses():
    r = parse_csv(sheet(GOOD), DOMAINS)
    assert r.ok, r.errors
    assert len(r.rows) == 1
    row = r.rows[0]
    assert row.correct_index == 0
    assert row.options == ["Overfitting", "Underfitting", "Data leakage", "Class imbalance"]


def test_missing_columns_rejected():
    r = parse_csv("external_id,domain\nX,ai-ml\n", DOMAINS)
    assert not r.ok
    assert "missing required column" in r.errors[0]


def test_empty_file_rejected():
    assert not parse_csv("", DOMAINS).ok
    assert not parse_csv(HEADER + "\n", DOMAINS).ok


@pytest.mark.parametrize(
    "mutation,expected",
    [
        (lambda s: s.replace(",ai-ml,", ",astrology,"), "unknown domain"),
        (lambda s: s.replace(",mcq,", ",essay,"), "type must be one of"),
        (lambda s: s.replace(",easy,", ",trivial,"), "difficulty must be one of"),
        (lambda s: s.replace("AIML-001", ""), "external_id is required"),
        (lambda s: s.replace(",overfitting,", ",,"), "topic is required"),
        (lambda s: s.replace(",A,", ",Z,"), "correct must be a letter"),
        (lambda s: s.replace(",A,", ",E,"), "only 4 options given"),
    ],
)
def test_bad_rows_rejected(mutation, expected):
    r = parse_csv(sheet(mutation(GOOD)), DOMAINS)
    assert not r.ok
    assert expected in r.errors[0], r.errors


def test_duplicate_options_rejected():
    """Two identical options means one of them is unmarked-correct."""
    bad = GOOD.replace(",Underfitting,", ",Overfitting,")
    r = parse_csv(sheet(bad), DOMAINS)
    assert not r.ok
    assert "distinct" in r.errors[0]


def test_single_option_rejected():
    bad = GOOD.replace("Overfitting,Underfitting,Data leakage,Class imbalance", "Overfitting,,,")
    r = parse_csv(sheet(bad), DOMAINS)
    assert not r.ok
    assert "at least two options" in r.errors[0]


def test_missing_explanation_rejected():
    bad = GOOD.replace(
        '"The model has memorised the training set rather than learning a general rule."', "n/a")
    r = parse_csv(sheet(bad), DOMAINS)
    assert not r.ok
    assert "explanation is too short" in r.errors[0]


def test_duplicate_external_id_rejected():
    r = parse_csv(sheet(GOOD, GOOD), DOMAINS)
    assert not r.ok
    assert "duplicate external_id" in r.errors[0]


def test_one_bad_row_blocks_the_whole_file():
    """All-or-nothing: a half-imported spreadsheet is worse than a rejected one,
    because the operator cannot tell which half landed."""
    r = parse_csv(sheet(GOOD, GOOD.replace("AIML-001", "AIML-002").replace(",easy,", ",???,")),
                  DOMAINS)
    assert not r.ok
    assert len(r.rows) == 1        # parsed, but the caller must not apply() a failed report


def test_code_newlines_unescaped():
    row = ('FS-001,full-stack,code_output,javascript,medium,What does this print?,'
           '"console.log(1)\\nconsole.log(2)",javascript,'
           '1 then 2,2 then 1,Nothing,A TypeError,A,'
           '"Statements run top to bottom."')
    r = parse_csv(sheet(row), DOMAINS)
    assert r.ok, r.errors
    assert r.rows[0].code == "console.log(1)\nconsole.log(2)"


def test_coverage_flags_a_lopsided_bank(monkeypatch):
    """200 easy questions and two hard ones cannot serve a 5/7/3 blueprint."""
    class FakeCursor:
        def execute(self, *_): pass
        def fetchall(self):
            return [
                {"slug": "ai-ml", "name": "AI", "difficulty": "easy", "n": 200, "topics": 12},
                {"slug": "ai-ml", "name": "AI", "difficulty": "medium", "n": 50, "topics": 12},
                {"slug": "ai-ml", "name": "AI", "difficulty": "hard", "n": 2, "topics": 12},
            ]

    out = bank_coverage(FakeCursor(), {"easy": 5, "medium": 7, "hard": 3})
    assert out[0]["can_serve_blueprint"] is False
    tiers = {t["difficulty"]: t["status"] for t in out[0]["tiers"]}
    assert tiers == {"easy": "ok", "medium": "ok", "hard": "insufficient"}


# ------------------------------------------------------------------ integration

def test_import_is_idempotent(conn):
    """Re-importing the same sheet must UPDATE, never duplicate. Without this a
    second run silently doubles the bank and wrecks the difficulty blueprint."""
    from server.questions import apply

    known = {"ai-ml", "full-stack"}
    with conn.cursor() as cur:
        first = parse_csv(sheet(GOOD), known)
        assert first.ok, first.errors
        apply(first, cur)
        conn.commit()
        assert (first.created, first.updated) == (1, 0)

        cur.execute("select count(*) as n from questions where external_id = 'AIML-001'")
        assert cur.fetchone()["n"] == 1

        # Same sheet again, with an edited option.
        edited = GOOD.replace("Class imbalance", "Poor regularisation")
        second = parse_csv(sheet(edited), known)
        apply(second, cur)
        conn.commit()
        assert (second.created, second.updated) == (0, 1)

        cur.execute("select count(*) as n from questions where external_id = 'AIML-001'")
        assert cur.fetchone()["n"] == 1

        cur.execute(
            """
            select o.body, o.is_correct, q.version from question_options o
            join questions q on q.id = o.question_id
            where q.external_id = 'AIML-001' order by o.position
            """
        )
        options = cur.fetchall()
        assert [o["body"] for o in options] == [
            "Overfitting", "Underfitting", "Data leakage", "Poor regularisation"]
        assert [o["is_correct"] for o in options] == [True, False, False, False]
        assert options[0]["version"] == 2


def test_import_keeps_exactly_one_correct_option(conn):
    """The DB's one-correct-option index must survive an update that moves the
    correct answer to a different position."""
    from server.questions import apply

    known = {"ai-ml", "full-stack"}
    with conn.cursor() as cur:
        apply(parse_csv(sheet(GOOD.replace("AIML-001", "AIML-050")), known), cur)
        conn.commit()
        moved = GOOD.replace("AIML-001", "AIML-050").replace(",A,", ",C,")
        apply(parse_csv(sheet(moved), known), cur)
        conn.commit()

        cur.execute(
            """
            select o.position from question_options o
            join questions q on q.id = o.question_id
            where q.external_id = 'AIML-050' and o.is_correct
            """
        )
        assert [r["position"] for r in cur.fetchall()] == [3]


def test_lopsided_answer_key_rejected():
    """A bank where the answer is nearly always A is solvable without knowing
    anything, and the per-attempt shuffle hides the problem rather than fixing
    the filler distractors it produces."""
    rows = [GOOD.replace("AIML-001", f"AIML-{i:03d}") for i in range(25)]
    r = parse_csv(sheet(*rows), DOMAINS)
    assert not r.ok
    assert "lopsided" in r.errors[-1]


def test_spread_answer_key_accepted():
    rows = []
    for i in range(28):
        letter = "ABCD"[i % 4]
        rows.append(GOOD.replace("AIML-001", f"AIML-{i:03d}").replace(",A,", f",{letter},"))
    r = parse_csv(sheet(*rows), DOMAINS)
    assert r.ok, r.errors
