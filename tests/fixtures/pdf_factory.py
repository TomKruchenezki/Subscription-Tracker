"""
Synthetic text-based PDF builder for tests.

Produces minimal, valid, text-based PDF bytes (standard Helvetica font, real content
stream with Tj operators) so tests exercise the full pipeline:
    pdfminer.six text extraction → pdf_extractor field parsing.

These are SYNTHETIC fixtures — no real PII. Generated at test time rather than checked
in as opaque binaries so the fixture content is fully reviewable in source.
"""
from __future__ import annotations


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_text_pdf(lines: list[str]) -> bytes:
    """Build a single-page PDF containing the given text lines (one per line)."""
    parts = ["BT", "/F1 12 Tf", "72 720 Td", "14 TL"]
    for i, ln in enumerate(lines):
        if i > 0:
            parts.append("T*")
        parts.append(f"({_esc(ln)}) Tj")
    parts.append("ET")
    content = "\n".join(parts).encode("latin-1", errors="replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"

    xref_pos = len(out)
    size = len(objects) + 1
    out += f"xref\n0 {size}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += b"trailer\n<< /Size " + str(size).encode() + b" /Root 1 0 R >>\n"
    out += b"startxref\n" + str(xref_pos).encode() + b"\n%%EOF"
    return bytes(out)


def make_empty_image_pdf() -> bytes:
    """A PDF page with NO text content — simulates a scanned/image-only PDF."""
    return make_text_pdf([])
