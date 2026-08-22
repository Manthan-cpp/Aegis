"""Download official Indian statutes and build section-level local retrieval files.

The generated Markdown keeps the official India Code URL beside every act. It is
used for retrieval only; Gemini still has to answer from the retrieved excerpts
and cite them. Run this script when the official source files change.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "data" / "legal_sources"
CORPUS_DIR = ROOT / "data" / "legal_corpus"

OFFICIAL_SOURCES = (
    {
        "slug": "bns-2023-full",
        "filename": "bns-2023.pdf",
        "title": "Bharatiya Nyaya Sanhita, 2023 — complete official text",
        "short_title": "BNS 2023",
        "status": "current criminal law; in force from 1 July 2024",
        "url": "https://www.indiacode.nic.in/bitstream/123456789/20062/1/a202345.pdf",
    },
    {
        "slug": "bnss-2023-full",
        "filename": "bnss-2023.pdf",
        "title": "Bharatiya Nagarik Suraksha Sanhita, 2023 — complete official text",
        "short_title": "BNSS 2023",
        "status": "current criminal procedure law; in force from 1 July 2024",
        "url": "https://www.indiacode.nic.in/bitstream/123456789/20335/1/a2023-46.pdf",
    },
    {
        "slug": "bsa-2023-full",
        "filename": "bsa-2023.pdf",
        "title": "Bharatiya Sakshya Adhiniyam, 2023 — complete official text",
        "short_title": "BSA 2023",
        "status": "current evidence law; in force from 1 July 2024",
        "url": "https://www.indiacode.nic.in/indiacode/bitstream/123456789/20063/1/aa202347.pdf",
    },
    {
        "slug": "ipc-1860-historical",
        "filename": "ipc-1860.pdf",
        "title": "Indian Penal Code, 1860 — complete historical official text",
        "short_title": "IPC 1860",
        "status": "historical reference; do not present as the current criminal code",
        "url": "https://www.indiacode.nic.in/bitstream/123456789/15407/1/ipc1860.pdf",
    },
    {
        "slug": "pwdva-2005-full",
        "filename": "pwdva-2005.pdf",
        "title": "Protection of Women from Domestic Violence Act, 2005 — complete official text",
        "short_title": "PWDVA 2005",
        "status": "current central legislation",
        "url": "https://www.indiacode.nic.in/bitstream/123456789/2021/5/A2005-43.pdf",
    },
    {
        "slug": "legal-services-authorities-1987",
        "filename": "legal-services-authorities-1987.pdf",
        "title": "Legal Services Authorities Act, 1987 — complete official text",
        "short_title": "Legal Services Authorities Act 1987",
        "status": "current central legislation",
        "url": "https://www.indiacode.nic.in/bitstream/123456789/16128/1/198739.pdf",
    },
    {
        "slug": "posh-2013",
        "filename": "posh-2013.pdf",
        "title": "Sexual Harassment of Women at Workplace Act, 2013 — complete official text",
        "short_title": "POSH Act 2013",
        "status": "current central legislation",
        "url": "https://www.indiacode.nic.in/bitstream/123456789/2104/1/A2013-14.pdf",
    },
    {
        "slug": "pocso-2012",
        "filename": "pocso-2012.pdf",
        "title": "Protection of Children from Sexual Offences Act, 2012 — complete official text",
        "short_title": "POCSO 2012",
        "status": "current central legislation; relevant only when the person is under 18",
        "url": "https://www.indiacode.nic.in/bitstream/123456789/2079/1/AA2012-32.pdf?sequence=1",
    },
    {
        "slug": "dowry-prohibition-1961",
        "filename": "dowry-prohibition-1961.pdf",
        "title": "Dowry Prohibition Act, 1961 — complete official text",
        "short_title": "Dowry Prohibition Act 1961",
        "status": "current central legislation",
        "url": "https://www.indiacode.nic.in/bitstream/123456789/16243/1/196128.pdf",
    },
)

SECTION_RE = re.compile(r"(?<![\w()])(\d{1,3}[A-Z]?)\.\s+([A-Z][^\n]{2,180})")
PAGE_NUMBER_RE = re.compile(r"(?m)^\s*\d+\s*$")


def _download(url: str, destination: Path) -> None:
    request = Request(url, headers={"User-Agent": "Aegis legal corpus builder/1.0"})
    with urlopen(request, timeout=60) as response:  # noqa: S310 - URLs are the checked-in official manifest.
        destination.write_bytes(response.read())


def _extract_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    pages: list[str] = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    text = "\n".join(pages).replace("\r", "\n")
    text = PAGE_NUMBER_RE.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text


def _sections(text: str) -> list[tuple[str, str]]:
    matches = list(SECTION_RE.finditer(text))
    candidates: dict[str, tuple[str, str]] = {}
    for index, match in enumerate(matches):
        number = match.group(1).strip()
        heading = match.group(2).strip().rstrip(".—- ")
        if heading.startswith(("[", "(", "Explanation", "Illustration")):
            continue
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = re.sub(r"\s+", " ", text[body_start:body_end]).strip()
        if len(body) < 20:
            continue
        candidate = (f"Section {number} — {heading}", body)
        previous = candidates.get(number)
        # The table of contents appears before the real text in several India
        # Code PDFs. The real section has a materially longer body; keep that
        # candidate when duplicate section numbers are encountered.
        if previous is None or len(body) > len(previous[1]):
            candidates[number] = candidate
    # India Code's BNS PDF has two headings where the section number is joined
    # directly to the title punctuation (for example ``114. Hurt.``). The
    # general heading regex intentionally avoids treating ordinary numbered
    # references inside a section as new sections, so recover these known
    # formatting variants explicitly.
    for number, title, next_number in (
        ("20", "Act of a child under seven years of age", "21"),
        ("114", "Hurt", "115"),
    ):
        heading_pattern = re.compile(
            rf"(?m)^\s*{number}\.\s*{re.escape(title)}\s*[.\-\u2013\u2014\ufffd]+\s*"
        )
        for match in heading_pattern.finditer(text):
            next_match = re.search(rf"(?m)^\s*{next_number}\.\s*", text[match.end():])
            body_end = match.end() + next_match.start() if next_match else len(text)
            body = re.sub(r"\s+", " ", text[match.end():body_end]).strip()
            if len(body) < 20:
                continue
            previous = candidates.get(number)
            candidate = (f"Section {number} — {title}", body)
            if previous is None or len(body) > len(previous[1]):
                candidates[number] = candidate
    sections = list(candidates.values())
    if sections:
        return sections
    # A scanned or unusually formatted government PDF is still useful as a
    # page-level source rather than silently disappearing from retrieval.
    pages = [part.strip() for part in text.split("\n\n") if len(part.strip()) >= 80]
    return [(f"Official text excerpt {index}", re.sub(r"\s+", " ", page)) for index, page in enumerate(pages, 1)]


def _write_markdown(source: dict[str, str], sections: list[tuple[str, str]]) -> Path:
    output = CORPUS_DIR / f"official-{source['slug']}.md"
    lines = [
        "---",
        f"title: {source['title']}",
        f"short_title: {source['short_title']}",
        "source: India Code (official text)",
        f"source_url: {source['url']}",
        f"status: {source['status']}",
        "scope: India; central legislation",
        "---",
        "",
    ]
    for heading, body in sections:
        lines.extend([f"## {heading}", "", body, ""])
    output.write_text("\n".join(lines), encoding="utf-8")
    return output


def main() -> None:
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    generated = 0
    for source in OFFICIAL_SOURCES:
        pdf_path = SOURCE_DIR / source["filename"]
        print(f"Downloading/checking {source['short_title']}...")
        _download(source["url"], pdf_path)
        sections = _sections(_extract_text(pdf_path))
        output = _write_markdown(source, sections)
        generated += len(sections)
        print(f"  wrote {output.name} with {len(sections)} sections")
    print(f"Generated {generated} official legal sections.")
    print("Next: run scripts/ingest_legal_corpus.py after MongoDB Atlas is reachable.")


if __name__ == "__main__":
    sys.exit(main())
