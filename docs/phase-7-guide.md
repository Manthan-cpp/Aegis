# Phase 7 beginner guide — integration pass

Phase 7 connects the earlier features into one coherent Aegis demo and makes the
data model ready for the later authentication pass.

## Final MongoDB collections

### `users` — reserved for deferred authentication

The collection is reserved for Phase 6/after the hackathon. The planned document
will contain a Clerk user id, role, per-user stealth PIN settings, and trusted
responder links. No authentication records are created while Phase 6 is deferred.

### `sos_cases`

Stores responder handoffs:

```text
case_id, message, severity, severity_rank, severity_reason,
filename, classification_source, created_at
```

### `companion_sessions`

Stores only consented companion turns:

```text
session_id, turns[{role, content, created_at}], created_at, updated_at
```

When consent is off, active browser context is request-only and is not saved.

### `legal_corpus_chunks`

Stores curated legal retrieval chunks:

```text
chunk_id, title, section, text, source, source_url,
embedding, updated_at
```

The `legal_vector_index` searches the 384-dimensional `embedding` field.

## MongoDB indexes

The indexes are created by:

```powershell
cd D:\MyCodes\Aegis\aegis\backend
.venv\Scripts\python.exe scripts\ensure_indexes.py
```

The script creates indexes for companion sessions, severity/time ordering of SOS
cases, case ids, and legal chunk ids. It does not delete documents.

## Full demo walkthrough

1. Open `http://localhost:3000`.
2. Enter `2580` and press `=` to reveal Aegis.
3. Use **Send a discreet SOS** to create the original PNG.
4. Open **Responder workspace**, upload that PNG, review urgency, and save it.
5. Confirm it appears in **Recent signals**, ordered by urgency.
6. Open **Talk to your companion** and test a multi-turn conversation.
7. Open **Know your rights** and ask a cited India-scoped legal question.
8. Ask a follow-up such as “What about residence rights?” to test continuity.

Phase 6 authentication remains intentionally deferred. Until it is added, the
responder workspace is a demo view and must not be treated as production access
control.
