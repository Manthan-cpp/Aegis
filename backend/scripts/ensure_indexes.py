"""Create the stable Phase 7 MongoDB indexes without touching document data."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from pymongo import ASCENDING, DESCENDING

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.cases import CASES_COLLECTION
from services.legal_search import LEGAL_COLLECTION
from services.mongo import mongo_database


def main() -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    load_dotenv(backend_dir / ".env")
    database = mongo_database()
    if database is None:
        raise SystemExit("MONGODB_URI is not configured in backend/.env")

    database["companion_sessions"].create_index("session_id", unique=True, name="companion_session_id")
    database[CASES_COLLECTION].create_index(
        [("severity_rank", DESCENDING), ("created_at", DESCENDING)],
        name="sos_cases_severity_created",
    )
    database[CASES_COLLECTION].create_index("case_id", unique=True, name="sos_case_id")
    database[LEGAL_COLLECTION].create_index("chunk_id", unique=True, name="legal_chunk_id")
    print("Phase 7 MongoDB indexes are ready.")
    print(f"Collections: users (reserved for Phase 6), sos_cases, companion_sessions, {LEGAL_COLLECTION}")


if __name__ == "__main__":
    main()
