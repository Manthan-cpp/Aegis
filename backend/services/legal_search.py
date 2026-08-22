"""Embedding and retrieval helpers for the India-scoped legal corpus."""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from pymongo import MongoClient
from pymongo.errors import PyMongoError


MODEL_NAME = os.getenv("LEGAL_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
LEGAL_COLLECTION = "legal_corpus_chunks"
LEGAL_VECTOR_INDEX = "legal_vector_index"
LOCAL_CORPUS_DIR = Path(__file__).resolve().parents[1] / "data" / "legal_corpus"
LOCAL_CHUNK_SIZE = 1_800
LOCAL_CHUNK_OVERLAP = 220
LEGACY_SUMMARY_STEMS = {"bns-2023", "bnss-2023", "pwdva-2005"}
LOCAL_QUERY_STOPWORDS = {
    "a", "about", "am", "an", "and", "are", "can", "do", "does", "for", "how", "i",
    "if", "in", "is", "it", "me", "my", "of", "on", "should", "the", "then", "to", "what", "when", "where", "which", "with",
    "he", "she", "they", "him", "her", "his", "their", "be", "being", "by", "been", "have", "has",
    "want", "give", "get", "justice", "acts", "act", "please", "tell", "me",
    "yesterday", "today", "then", "brutally",
}
LOCAL_QUERY_ALIASES = {
    "defense": "defence",
    "self-defense": "private-defence",
    "selfdefense": "private-defence",
    "self-defence": "private-defence",
}
LOCAL_TOKEN_ALIASES = {
    "sexually": "sexual",
    "abused": "abuse",
    "abusing": "abuse",
    "assaulted": "assault",
    "assaulting": "assault",
    "attack": "assault",
    "attacked": "assault",
    "attacking": "assault",
    "kidnap": "kidnapping",
    "kidnapped": "kidnapping",
    "kidnapping": "kidnapping",
    "abducted": "abduction",
    "abducting": "abduction",
    "abduction": "abduction",
    "raped": "rape",
    "kill": "death",
    "killed": "death",
    "killing": "death",
    "beaten": "beat",
    "beating": "beat",
    "harmed": "harm",
    "hurting": "hurt",
    "locked": "confine",
    "locking": "confine",
    "lock": "confine",
    "confined": "confine",
    "confinement": "confine",
    "verbally": "verbal",
    "humiliated": "humiliation",
    "threatened": "threat",
    "spouse": "husband",
    "pati": "husband",
    "balatkar": "rape",
    "yaun": "sexual",
    "shoshan": "abuse",
    "hinsa": "violence",
    "aatmaraksha": "private-defence",
}


@dataclass(frozen=True)
class LegalChunk:
    chunk_id: str
    title: str
    section: str
    text: str
    source: str
    source_url: str
    score: float
    status: str = ""


@lru_cache(maxsize=1)
def embedding_model():
    # Import lazily: Phase 0–3 routes must not pay the ML startup cost.
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL_NAME)


@lru_cache(maxsize=1)
def mongo_client() -> MongoClient | None:
    uri = os.getenv("MONGODB_URI", "").strip()
    if not uri:
        return None
    client = MongoClient(uri, serverSelectionTimeoutMS=2_500)
    client.admin.command("ping")
    return client


def embed_text(text: str) -> list[float]:
    vector = embedding_model().encode(text, normalize_embeddings=True)
    return [float(value) for value in vector]


def _as_chunk(document: dict[str, Any], score: float) -> LegalChunk:
    return LegalChunk(
        chunk_id=str(document.get("chunk_id", "")),
        title=str(document.get("title", "Legal source")),
        section=str(document.get("section", "")),
        text=str(document.get("text", "")),
        source=str(document.get("source", "Official source")),
        source_url=str(document.get("source_url", "")),
        score=float(score),
        status=str(document.get("status", "")),
    )


def _local_cosine(query: list[float], candidate: list[float]) -> float:
    if not query or not candidate or len(query) != len(candidate):
        return 0.0
    dot = sum(left * right for left, right in zip(query, candidate))
    query_norm = math.sqrt(sum(value * value for value in query))
    candidate_norm = math.sqrt(sum(value * value for value in candidate))
    if not query_norm or not candidate_norm:
        return 0.0
    return dot / (query_norm * candidate_norm)


@lru_cache(maxsize=1)
def local_corpus_chunks() -> tuple[LegalChunk, ...]:
    """Load the checked-in official summaries used when Atlas is unavailable."""

    chunks: list[LegalChunk] = []
    for path in sorted(LOCAL_CORPUS_DIR.glob("*.md")):
        if path.stem in LEGACY_SUMMARY_STEMS and (LOCAL_CORPUS_DIR / f"official-{path.stem}-full.md").exists():
            continue
        raw = path.read_text(encoding="utf-8")
        front_matter = re.match(r"^---\s*(.*?)\s*---\s*(.*)$", raw, flags=re.DOTALL)
        if not front_matter:
            continue

        metadata: dict[str, str] = {}
        for line in front_matter.group(1).splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                metadata[key.strip()] = value.strip()

        sections = re.split(r"(?m)^##\s+", front_matter.group(2))
        for section in sections[1:]:
            lines = section.strip().splitlines()
            if len(lines) < 2:
                continue
            heading = lines[0].strip()
            text = " ".join(line.strip() for line in lines[1:] if line.strip())
            start = 0
            part = 0
            while start < len(text):
                end = min(start + LOCAL_CHUNK_SIZE, len(text))
                excerpt = text[start:end].strip()
                if excerpt:
                    chunks.append(
                        LegalChunk(
                            chunk_id=f"{path.stem}:{heading.casefold().replace(' ', '-')}:part-{part}",
                            title=metadata.get("title", path.stem),
                            section=heading,
                            text=excerpt,
                            source=metadata.get("source", "Official source"),
                            source_url=metadata.get("source_url", ""),
                            score=0.0,
                            status=metadata.get("status", ""),
                        )
                    )
                if end == len(text):
                    break
                start = max(end - LOCAL_CHUNK_OVERLAP, start + 1)
                part += 1
    return tuple(chunks)


def _local_keyword_score(query: str, chunk: LegalChunk) -> float:
    normalized_query = query.casefold()
    for source, target in LOCAL_QUERY_ALIASES.items():
        normalized_query = normalized_query.replace(source, target)
    query_terms = {
        LOCAL_TOKEN_ALIASES.get(term, term)
        for term in re.findall(r"[a-z0-9]+", normalized_query)
        if term not in LOCAL_QUERY_STOPWORDS
    }
    document = f"{chunk.section} {chunk.text}".casefold()
    document_terms = {
        LOCAL_TOKEN_ALIASES.get(term, term)
        for term in re.findall(r"[a-z0-9]+", document)
    }
    query_text = normalized_query
    title = chunk.title.casefold()
    section = chunk.section.casefold()
    if not query_terms:
        return 0.0

    overlap = query_terms & document_terms
    score = len(overlap) / len(query_terms)
    if "protection" in query_terms and "order" in query_terms and "protection order" in document:
        score += 0.25
    if "legal" in query_terms and "aid" in query_terms and "legal aid" in document:
        score += 0.25
    evidence_intent = bool(
        re.search(r"\b(?:evidence|proof|screenshot|message|messages|recording|photo|photos|document|preserve|preserved|digital|electronic)\b", query_text)
    )
    if evidence_intent and "bharatiya sakshya adhiniyam" in title:
        score += 0.55
        if section.startswith(("section 2", "section 61", "section 62", "section 63", "section 64", "section 66", "section 73")) or "electronic" in section or "digital" in section:
            score += 0.35
    if evidence_intent and "bharatiya sakshya adhiniyam" not in title and "electronic" not in section and "evidence" not in section:
        score *= 0.45
    defence_intent = bool(
        re.search(r"\b(?:self[- ]?defen[sc]e|private\s+defen[sc]e|defend\w*|attack\w*|fight\w*|kill\w*|dead|death|protect\w*)\b", normalized_query)
    )
    if defence_intent and query_terms & {"defence", "private", "assault", "death", "confine"} and "private defence" in document:
        # This is a high-signal legal intent. A generic overlap such as
        # “attack” or “death” must not push the actual private-defence provisions
        # below unrelated murder, theft, or procedure sections.
        score += 0.85
    if defence_intent:
        core_private_defence_section = bool(
            re.search(r"^section (?:3[4-9]|4[0-4])\b", section)
        )
        if "bharatiya nyaya sanhita" in title and not core_private_defence_section:
            score *= 0.25
        elif "bharatiya nyaya sanhita" not in title and not core_private_defence_section:
            score *= 0.18
    if query_terms & {"sexual", "rape", "assault", "abuse"} and query_terms & {"husband", "partner", "domestic", "woman"}:
        if "domestic violence" in document or "sexual abuse" in document or "cruelty" in document:
            score += 0.45
    if query_terms & {"sexual", "rape", "assault"} and (
        chunk.section.casefold().startswith("section 63")
        or "sexual harassment" in document
        or "criminal force against a woman" in document
    ):
        score += 0.35
    if query_terms & {"protection", "residence", "order", "magistrate"} and "domestic violence" in document:
        score += 0.2
    if query_terms & {"confine", "room", "days", "secret"} and "wrongful confinement" in document:
        score += 0.5
    if query_terms & {"confine", "room", "days", "secret"} and (
        "wrongful confinement" not in section and "domestic violence" not in document
    ):
        score *= 0.35
    if query_terms & {"verbal", "emotional", "abuse", "humiliation", "insult", "threat"} and (
        "domestic violence" in document or "verbal and emotional abuse" in document or "cruelty" in document
    ):
        score += 0.45

    mentions_child = bool(re.search(r"\b(?:child|minor|under\s+18|underage|pocso)\b", query_text))
    mentions_workplace = bool(re.search(r"\b(?:workplace|office|employer|colleague|internal committee|posh)\b", query_text))
    mentions_trafficking = bool(re.search(r"\b(?:traffick|forced labour|slavery)\b", query_text))
    mentions_dowry = bool(re.search(r"\b(?:dowry|dahej)\b", query_text))
    mentions_historical = bool(re.search(r"\b(?:ipc|indian penal code|old law|before 2024)\b", query_text))
    sexual_query = bool(query_terms & {"sexual", "rape"}) or bool(
        re.search(r"\b(?:sexual assault|sexual abuse|sexually assaulted|sexually abused|rape|raped)\b", query_text)
    )
    justice_intent = bool(
        re.search(r"\b(?:justice|legal|law|laws|protection|complaint|police|report|help|aid)\b", query_text)
    )
    kidnapping_query = bool(re.search(
        r"\b(?:kidnap(?:ping|ped)?|abduct(?:ed|ion|ing)?|held against my will|taken by force)\b",
        query_text,
    ))
    physical_assault_query = bool(re.search(
        r"\b(?:brutally assaulted|physically assaulted|beaten|beating|assaulted|assault|hurt|injured|injury|attacked|attack)\b",
        query_text,
    ))

    # A broad word such as “abuse” appears in many statutes. Topic guardrails
    # prevent a trafficking, POSH, POCSO or historical IPC chunk from outranking
    # the current domestic-violence and sexual-offence provisions unless the
    # question actually supplies that context.
    if "protection of children from sexual offences" in title and not mentions_child:
        score *= 0.12
    if "sexual harassment of women at workplace" in title and sexual_query and not mentions_workplace:
        score *= 0.25
    if sexual_query and "traffick" in section and not mentions_trafficking:
        score *= 0.2
    if mentions_trafficking and "traffick" not in section and "traffick" not in title:
        score *= 0.3
    if "dowry" in title and not mentions_dowry:
        score *= 0.25
    if chunk.status.casefold().startswith("historical") and not mentions_historical:
        score *= 0.2
    if "repeal and savings" in section and not mentions_historical and not re.search(r"\b(?:repeal|savings|old law)\b", query_text):
        score *= 0.05
    if sexual_query and "bharatiya nyaya sanhita" in title:
        sexual_sections = ("section 63", "section 64", "section 65", "section 66", "section 67", "section 68", "section 69", "section 70", "section 71", "section 74", "section 75", "section 76", "section 77", "section 78", "section 79")
        domestic_sections = ("section 85", "section 86")
        if not section.startswith(sexual_sections) and not (query_terms & {"husband", "partner", "domestic"} and section.startswith(domestic_sections)):
            score *= 0.25
    if sexual_query and justice_intent and ("nalsa" in title or "legal services" in title):
        score = max(score, 0.55)
    if sexual_query and justice_intent and "bharatiya nagarik suraksha sanhita" in title:
        if section.startswith(("section 173", "section 175", "section 176", "section 183", "section 184", "section 193")):
            score = max(score, 0.5)
    if kidnapping_query:
        if "bharatiya nyaya sanhita" in title:
            kidnapping_sections = ("section 137", "section 138", "section 140", "section 142")
            harm_sections = ("section 115", "section 117", "section 118", "section 130", "section 131", "section 135")
            if section.startswith(kidnapping_sections):
                score = max(score, 0.9)
            elif physical_assault_query and section.startswith(harm_sections):
                score = max(score, 0.78)
            else:
                score *= 0.12
        elif "bharatiya nagarik suraksha sanhita" in title:
            if section.startswith("section 173"):
                score = max(score, 0.62)
            elif section.startswith(("section 175", "section 193")) and justice_intent:
                score = max(score, 0.62)
            else:
                score *= 0.18
        elif "bharatiya sakshya adhiniyam" in title and not evidence_intent:
            score *= 0.08
        elif "protection of women from domestic violence" in title and not re.search(
            r"\b(?:husband|partner|domestic|home|family)\b", query_text
        ):
            score *= 0.2
    if "private defence" in document and not defence_intent:
        score *= 0.45
    return min(score, 1.0)


def _search_local_corpus(query: str, limit: int) -> tuple[list[LegalChunk], str]:
    def topic_priority(chunk: LegalChunk) -> int:
        normalized = query.casefold()
        sexual_query = bool(
            re.search(r"\b(?:sexual|rape|raped|assault|abuse|consent|forced\s+sex)\b", normalized)
        )
        rape_query = bool(re.search(r"\b(?:rape|raped)\b", normalized))
        justice_intent = bool(
            re.search(r"\b(?:justice|legal|law|laws|protection|complaint|police|report|help|aid)\b", normalized)
        )
        section_match = re.match(r"(?:sections?|sec\.?)[\s-]*(\d+)", chunk.section.casefold())
        section_number = int(section_match.group(1)) if section_match else 0
        title = chunk.title.casefold()

        kidnapping_query = bool(re.search(
            r"\b(?:kidnap(?:ping|ped)?|abduct(?:ed|ion|ing)?|held against my will|taken by force)\b",
            normalized,
        ))
        physical_assault_query = bool(re.search(
            r"\b(?:brutally assaulted|physically assaulted|beaten|beating|assaulted|assault|hurt|injured|injury|attacked|attack)\b",
            normalized,
        ))
        justice_intent = bool(
            re.search(r"\b(?:justice|legal|law|laws|protection|complaint|police|report|help|aid)\b", normalized)
        )

        if kidnapping_query:
            if "bharatiya nyaya sanhita" in title:
                if physical_assault_query and section_number in {115, 117, 118, 130, 131, 135}:
                    return {117: 120, 118: 118, 115: 116, 135: 108, 131: 106, 130: 104}[section_number]
                if section_number in {140, 137, 138, 142}:
                    return {140: 125, 137: 123, 138: 121, 142: 110}[section_number]
                return 8
            if "bharatiya nagarik suraksha sanhita" in title:
                return {173: 114, 193: 110, 175: 106}.get(section_number, 18)
            if "nalsa" in title or "legal services" in title:
                return 98 if justice_intent else 40
            if "bharatiya sakshya adhiniyam" in title:
                return 6 if re.search(r"\b(?:evidence|proof|message|recording|digital|electronic)\b", normalized) else 1
            if "protection of women from domestic violence" in title:
                return 32

        # Sexual-violence questions need a stable, legally coherent set of
        # provisions. A vector result for “Section 63” from the evidence law
        # must never outrank BNS rape provisions simply because the number is
        # the same. Keep the current criminal-law and procedure provisions
        # together and rank them by what the question is asking.
        if sexual_query:
            if "protection of women from domestic violence" in title:
                if "husband" in normalized or "partner" in normalized or "domestic" in normalized or "abuse" in normalized:
                    return {3: 120, 5: 116, 12: 114, 18: 112, 19: 110, 20: 108, 22: 106, 23: 104}.get(section_number, 80)
                return 45
            if "bharatiya nyaya sanhita" in title:
                if rape_query:
                    return {
                        64: 119, 63: 117, 65: 115, 70: 113, 67: 111, 68: 109,
                        69: 107, 66: 105, 71: 103, 74: 96, 75: 94, 76: 92,
                        77: 90, 78: 88, 79: 86, 85: 82, 86: 80,
                    }.get(section_number, 20)
                return {
                    75: 112, 74: 110, 76: 108, 63: 106, 67: 104, 68: 102,
                    69: 100, 70: 98, 77: 96, 78: 94, 79: 92, 85: 90, 86: 88,
                }.get(section_number, 20)
            if "bharatiya nagarik suraksha sanhita" in title:
                return {
                    173: 116, 184: 114, 176: 112, 183: 110, 175: 108, 193: 106,
                }.get(section_number, 35)
            if "nalsa" in title or "legal services" in title:
                return 102 if justice_intent else 45
            if "bharatiya sakshya adhiniyam" in title:
                return 35 if re.search(r"\b(?:evidence|proof|message|recording|digital|electronic)\b", normalized) else 5

        if "bharatiya sakshya adhiniyam" in chunk.title.casefold() and re.search(
            r"\b(?:evidence|proof|screenshot|message|messages|recording|photo|photos|document|preserve|preserved|digital|electronic)\b",
            normalized,
        ):
            match = re.match(r"section\s+(\d+)", chunk.section.casefold())
            number = int(match.group(1)) if match else 0
            return {63: 6, 62: 5, 61: 4, 64: 3, 66: 2, 73: 2, 2: 1}.get(number, 0)
        if "bharatiya nyaya sanhita" not in chunk.title.casefold() or not re.search(
            r"\b(?:self[- ]?defen[sc]e|private\s+defen[sc]e|defend\w*|attack\w*|fight\w*|kill\w*|death)\b",
            normalized,
        ):
            return 0
        match = re.match(r"section\s+(\d+)", chunk.section.casefold())
        number = int(match.group(1)) if match else 0
        if re.search(r"\b(?:kill\w*|death|dead)\b", normalized):
            return {38: 6, 37: 5, 35: 4, 34: 3, 40: 3, 44: 2, 36: 1, 39: 1}.get(number, 0)
        return {35: 6, 37: 5, 40: 4, 34: 3, 38: 3, 44: 2, 36: 1, 39: 1}.get(number, 0)

    ranked = sorted(
        (
            (score, chunk)
            for chunk in local_corpus_chunks()
            if (score := _local_keyword_score(query, chunk)) > 0
        ),
        key=lambda item: (topic_priority(item[1]), item[0]),
        reverse=True,
    )
    selected: list[LegalChunk] = []
    seen_sections: set[tuple[str, str]] = set()
    family_counts: dict[str, int] = {}

    def family(chunk: LegalChunk) -> str:
        title = chunk.title.casefold()
        if "bharatiya nyaya sanhita" in title:
            return "bns"
        if "bharatiya nagarik suraksha sanhita" in title:
            return "bnss"
        if "protection of women from domestic violence" in title:
            return "pwdva"
        if "nalsa" in title or "legal services" in title:
            return "legal-aid"
        if "bharatiya sakshya adhiniyam" in title:
            return "bsa"
        return chunk.title.casefold()

    sexual_query = bool(re.search(r"\b(?:sexual|rape|raped|assault|abuse|consent|forced\s+sex)\b", query.casefold()))
    kidnapping_query = bool(re.search(
        r"\b(?:kidnap(?:ping|ped)?|abduct(?:ed|ion|ing)?|held against my will|taken by force)\b",
        query.casefold(),
    ))
    family_limits = (
        {"bns": 4, "bnss": 2, "pwdva": 1, "legal-aid": 1, "bsa": 0}
        if kidnapping_query
        else {"bns": 2, "bnss": 2, "pwdva": 1, "legal-aid": 1, "bsa": 1}
    )
    for score, chunk in ranked:
        key = (chunk.title.casefold(), chunk.section.casefold())
        if key in seen_sections:
            continue
        chunk_family = family(chunk)
        if (sexual_query or kidnapping_query) and family_counts.get(chunk_family, 0) >= family_limits.get(chunk_family, 1):
            continue
        seen_sections.add(key)
        family_counts[chunk_family] = family_counts.get(chunk_family, 0) + 1
        selected.append(LegalChunk(**{**chunk.__dict__, "score": score}))
        if len(selected) >= limit:
            break

    # If a family cap left room because a source family did not match, fill the
    # remaining slots with the next unique ranked chunks.
    if len(selected) < limit:
        for score, chunk in ranked:
            key = (chunk.title.casefold(), chunk.section.casefold())
            if key in seen_sections:
                continue
            seen_sections.add(key)
            selected.append(LegalChunk(**{**chunk.__dict__, "score": score}))
            if len(selected) >= limit:
                break
    return selected, "local-corpus"


def _merge_local_grounding(query: str, atlas_chunks: list[LegalChunk], limit: int) -> list[LegalChunk]:
    """Supplement Atlas results with strong matches from the checked-in corpus."""

    local_chunks, _ = _search_local_corpus(query, limit)
    combined = list(atlas_chunks)
    existing_sections = {chunk.section.casefold() for chunk in combined}
    for chunk in local_chunks:
        if chunk.score >= 0.45 and chunk.section.casefold() not in existing_sections:
            combined.append(chunk)
            existing_sections.add(chunk.section.casefold())
    return combined[:limit]


def search_legal_chunks(query: str, limit: int = 5) -> tuple[list[LegalChunk], str]:
    """Search Atlas first, then the checked-in official corpus if needed."""

    # For high-stakes violence questions, prefer the checked-in official corpus.
    # Broad vector similarity can otherwise return identically numbered but
    # unrelated provisions (for example BSA Section 63 for a kidnapping report).
    if re.search(
        r"\b(?:rape|raped|sexual\s+assault|sexual\s+abuse|sexually\s+assaulted|forced\s+sex|"
        r"kidnap(?:ping|ped)?|abduct(?:ed|ion|ing)?|held\s+against\s+my\s+will|"
        r"brutally\s+assaulted|physically\s+assaulted|wrongful\s+confinement)\b",
        query.casefold(),
    ):
        local_chunks, _ = _search_local_corpus(query, limit)
        if local_chunks:
            return local_chunks, "local-corpus"

    try:
        client = mongo_client()
    except PyMongoError:
        # Atlas can be temporarily unavailable. Keep the legal chat grounded
        # while the database connection is repaired.
        return _search_local_corpus(query, limit)
    if client is None:
        return _search_local_corpus(query, limit)
    
    collection = client[os.getenv("MONGODB_DB_NAME", "aegis")][LEGAL_COLLECTION]
    try:
        query_vector = embed_text(query)
    except Exception:  # noqa: BLE001 - missing ML assets must not crash the API.
        return _search_local_corpus(query, limit)

    try:
        pipeline = [
            {
                "$vectorSearch": {
                    "index": LEGAL_VECTOR_INDEX,
                    "path": "embedding",
                    "queryVector": query_vector,
                    "numCandidates": max(limit * 12, 60),
                    "limit": limit,
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "chunk_id": 1,
                    "title": 1,
                    "section": 1,
                    "text": 1,
                    "source": 1,
                    "source_url": 1,
                    "status": 1,
                    "score": {"$meta": "vectorSearchScore"},
                }
            },
        ]
        documents = list(collection.aggregate(pipeline))
        atlas_chunks = [_as_chunk(document, document.get("score", 0.0)) for document in documents]
        return _merge_local_grounding(query, atlas_chunks, limit), "atlas-vector"
    except PyMongoError:
        # The app stays usable before the owner creates the Atlas index. This is
        # also useful for automated tests; production acceptance still requires
        # verifying the Atlas Vector Search index.
        try:
            candidates = list(collection.find({}, {"_id": 0, "embedding": 1, "chunk_id": 1, "title": 1, "section": 1, "text": 1, "source": 1, "source_url": 1, "status": 1}))
        except PyMongoError:
            return _search_local_corpus(query, limit)
        ranked = sorted(
            ((_local_cosine(query_vector, document.get("embedding", [])), document) for document in candidates),
            key=lambda item: item[0],
            reverse=True,
        )
        return [_as_chunk(document, score) for score, document in ranked[:limit]], "local-cosine"


def chunk_is_relevant(chunk: LegalChunk | None, threshold: float = 0.38) -> bool:
    return chunk is not None and chunk.score >= threshold
