"""Embed the curated legal markdown files and upsert them into MongoDB."""

from __future__ import annotations

import hashlib
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.legal_search import LEGAL_COLLECTION, embed_text, mongo_client


CORPUS_DIR = Path(__file__).resolve().parents[1] / "data" / "legal_corpus"
CHUNK_SIZE = 900
CHUNK_OVERLAP = 120


def parse_document(path: Path) -> tuple[dict[str, str], str]:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---"):
        return {}, raw
    _, front_matter, body = raw.split("---", 2)
    metadata: dict[str, str] = {}
    for line in front_matter.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip()
    return metadata, body.strip()


def split_chunks(text: str) -> list[tuple[str, str]]:
    sections = re.split(r"(?m)^(?=## )", text)
    chunks: list[tuple[str, str]] = []
    for section_text in sections:
        section_text = section_text.strip()
        if not section_text:
            continue
        heading = section_text.splitlines()[0].removeprefix("## ").strip()
        start = 0
        while start < len(section_text):
            end = min(start + CHUNK_SIZE, len(section_text))
            chunk = section_text[start:end].strip()
            if chunk:
                chunks.append((heading, chunk))
            if end == len(section_text):
                break
            start = max(end - CHUNK_OVERLAP, start + 1)
    return chunks


def main() -> None:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    client = mongo_client()
    if client is None:
        raise SystemExit("MONGODB_URI is not configured in backend/.env")

    collection = client["aegis"][LEGAL_COLLECTION]
    total = 0
    for path in sorted(CORPUS_DIR.glob("*.md")):
        if path.name == "README.md":
            continue
        metadata, body = parse_document(path)
        for section, text in split_chunks(body):
            chunk_id = hashlib.sha256(f"{path.name}:{section}:{text}".encode("utf-8")).hexdigest()[:24]
            collection.update_one(
                {"chunk_id": chunk_id},
                {
                    "$set": {
                        "chunk_id": chunk_id,
                        "title": metadata.get("title", path.stem),
                        "section": section,
                        "text": text,
                        "source": metadata.get("source", "Official source"),
                        "source_url": metadata.get("source_url", ""),
                        "status": metadata.get("status", ""),
                        "embedding": embed_text(text),
                        "updated_at": datetime.now(UTC),
                    }
                },
                upsert=True,
            )
            total += 1
    print(f"Ingested {total} legal chunks into {LEGAL_COLLECTION}.")
    print("Next: create the legal_vector_index in MongoDB Atlas using docs/phase-4-guide.md.")


if __name__ == "__main__":
    main()
