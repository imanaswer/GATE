"""Participation certificates.

Two halves. `issue()` writes the row — that row *is* the certificate: valid and
verifiable the instant it exists, with no PDF work on the submit path. The PDF
is drawn on demand from that row, because most students never download theirs
and provisioning a render fleet for the ones who don't is how event day breaks.
"""
import hashlib
import re
import secrets
from datetime import date

from fastapi import APIRouter, HTTPException, Request, Response, status

from server import db
from server.settings import settings

router = APIRouter()

# Crockford-style: no I, L, O, U, 0 or 1. Students type this off a printed
# certificate, and 0/O is the transcription error that generates support tickets.
ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"
ID_LENGTH = 10


def _event_year() -> str:
    """From the event slug, not the wall clock: the cron sweep that finalises the
    last abandoned attempts can easily run after midnight on New Year, and
    "TA-2027-" on a 2026 certificate is wrong on paper forever."""
    match = re.search(r"(20\d{2})", settings.event_slug)
    return match.group(1) if match else str(date.today().year)


def _new_id() -> str:
    body = "".join(secrets.choice(ALPHABET) for _ in range(ID_LENGTH))
    return f"TA-{_event_year()}-{body}"


def _hash(certificate_id: str, attempt_id) -> str:
    """A checksum printed on the certificate so a person holding a printout can
    eyeball-match it against /verify. Deliberately not an HMAC: /verify reads the
    database, which is the only authority, and a secret here would protect
    nothing while adding a required env var that fails the deploy without it."""
    return hashlib.sha256(f"{certificate_id}{attempt_id}".encode()).hexdigest()


def canonical(certificate_id: str) -> str | None:
    """A pasted ID arrives lowercased, with stray spaces, or with the dashes
    dropped — all three name the same certificate. Rebuilding the canonical form
    (rather than matching on `replace(certificate_id, '-', '')`) keeps the unique
    index usable: that column expression cannot use it, which would make the one
    unauthenticated endpoint in the app a sequential scan per request.

    None for anything the wrong shape, so a malformed ID never reaches the
    database at all."""
    stripped = "".join(certificate_id.upper().split()).replace("-", "")
    if len(stripped) != 6 + ID_LENGTH or not stripped.startswith("TA"):
        return None
    if not stripped[2:6].isdigit() or any(c not in ALPHABET for c in stripped[6:]):
        return None
    return f"TA-{stripped[2:6]}-{stripped[6:]}"


def issue(cur, attempt_id) -> str:
    """Idempotent: a double-click on submit, a cron sweep and a result read all
    land on the same certificate. Must run inside a transaction — every caller
    is already in one."""
    cert_id = _new_id()
    cur.execute(
        """
        insert into certificates (attempt_id, certificate_id, verify_hash)
        values (%s, %s, %s)
        on conflict (attempt_id) do nothing
        returning certificate_id
        """,
        (attempt_id, cert_id, _hash(cert_id, attempt_id)),
    )
    row = cur.fetchone()
    if row:
        return row["certificate_id"]
    cur.execute(
        "select certificate_id from certificates where attempt_id = %s", (attempt_id,)
    )
    return cur.fetchone()["certificate_id"]


def _lookup(certificate_id: str) -> dict:
    """The public face of the platform, and the only endpoint with no identity
    behind it. Every column is named literally: a `select a.*` here would publish
    scores and email addresses to anyone holding a certificate number."""
    wanted = canonical(certificate_id)
    row = wanted and db.fetch_one(
        """
        select c.certificate_id, c.verify_hash, c.issued_at,
               u.name as student_name, co.name as college_name,
               d.name as domain_name
        from certificates c
        join exam_attempts a on a.id = c.attempt_id
        join users u on u.id = a.user_id
        join domains d on d.id = a.domain_id
        left join colleges co on co.id = u.college_id
        where c.certificate_id = %s
        """,
        (wanted,),
    )
    if not row:
        # Identical response for malformed and unknown, so the endpoint cannot be
        # used as an oracle for which ID shapes exist.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No certificate with that ID.")
    return row


def _public(row: dict) -> dict:
    return {
        "valid": True,
        "certificate_id": row["certificate_id"],
        "student_name": row["student_name"],
        "college_name": row["college_name"],
        "domain_name": row["domain_name"],
        "issued_at": row["issued_at"].date().isoformat(),
        "verify_code": row["verify_hash"][:12].upper(),
    }


@router.get("/certificates/{certificate_id}")
def show(certificate_id: str):
    return _public(_lookup(certificate_id))


def _site_url(request: Request) -> str:
    """Vercel terminates TLS at the edge, so the scheme the function sees is the
    internal one — printing `http://` into a QR that outlives the page. Prefer
    the configured URL, then the forwarded headers, and only then the socket."""
    if settings.site_url:
        return settings.site_url
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    return f"{proto}://{host}" if host else str(request.base_url).rstrip("/")


@router.get("/certificates/{certificate_id}/pdf")
def pdf(certificate_id: str, request: Request):
    row = _lookup(certificate_id)
    cert = _public(row)
    verify_url = f"{_site_url(request)}/verify/{cert['certificate_id']}"
    # ponytail: renders per download (~20ms of CPU). The pdf_path/pdf_generated_at
    # columns are left NULL — cache to Supabase Storage if download volume ever
    # shows up in the CPU numbers.
    return Response(
        render(cert, verify_url),
        media_type="application/pdf",
        headers={
            "Content-Disposition":
                f'attachment; filename="{cert["certificate_id"]}.pdf"',
            "Cache-Control": "public, max-age=86400",
        },
    )


def render(cert: dict, verify_url: str) -> bytes:
    from fpdf import FPDF

    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(False)
    pdf.add_page()
    w = pdf.w

    pdf.set_draw_color(180, 150, 60)
    pdf.set_line_width(1.2)
    pdf.rect(10, 10, w - 20, pdf.h - 20)
    pdf.set_line_width(0.3)
    pdf.rect(14, 14, w - 28, pdf.h - 28)

    def centred(text: str, y: float, size: int, style: str = "", rgb=(30, 30, 30)):
        """Shrinks to fit rather than overflowing the border. A student with a
        long name gets a smaller name, never a clipped one."""
        pdf.set_text_color(*rgb)
        while size > 7:
            pdf.set_font("Helvetica", style, size)
            if pdf.get_string_width(text) <= w - 44:
                break
            size -= 1
        pdf.set_xy(20, y)
        pdf.cell(w - 40, size * 0.4, text, align="C")

    centred("TECH ARENA", 30, 14, "B", (140, 115, 40))
    centred("CERTIFICATE OF PARTICIPATION", 42, 26, "B")
    centred("This is to certify that", 62, 11, "", (110, 110, 110))
    centred(cert["student_name"], 74, 30, "B")
    pdf.set_draw_color(140, 115, 40)
    pdf.line(w / 2 - 60, 88, w / 2 + 60, 88)
    centred(cert["college_name"] or "", 95, 12, "", (90, 90, 90))
    centred("participated in the Tech Arena examination in", 112, 11, "", (110, 110, 110))
    centred(cert["domain_name"], 124, 18, "B")

    _qr(pdf, verify_url, x=w - 62, y=pdf.h - 62, size=34)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(120, 120, 120)
    pdf.set_xy(24, pdf.h - 46)
    pdf.multi_cell(
        90, 5,
        f"Certificate ID: {cert['certificate_id']}\n"
        f"Issued: {cert['issued_at']}\n"
        f"Verify: {verify_url}\n"
        f"Check code: {cert['verify_code']}",
    )
    return bytes(pdf.output())


def _qr(pdf, url: str, x: float, y: float, size: float) -> None:
    """Drawn as vector rectangles from segno's bit matrix. No raster encode, no
    image pipeline, no Pillow — and it stays sharp when printed."""
    import segno

    qr = segno.make(url, error="m")
    matrix = list(qr.matrix)
    module = size / len(matrix)
    pdf.set_fill_color(0, 0, 0)
    for r, row in enumerate(matrix):
        for c, bit in enumerate(row):
            if bit:
                pdf.rect(x + c * module, y + r * module, module, module, style="F")
