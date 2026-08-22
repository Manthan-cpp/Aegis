# Phase 4 beginner guide — legal rights search

Phase 4 adds a separate **Know your rights** screen. It is India-scoped and
answers only from a small, cited corpus. It is not a lawyer, a court, or an
emergency service.

## What was added

- Curated official-source files in `backend/data/legal_corpus/`.
- A local `all-MiniLM-L6-v2` embedding model, installed with CPU-only PyTorch.
- `scripts/ingest_legal_corpus.py`, which chunks the files, creates 384-number
  embeddings, and stores them in MongoDB's `legal_corpus_chunks` collection.
- Atlas Vector Search index named `legal_vector_index` on the `embedding` field.
- `POST /legal/ask`, which retrieves relevant chunks, asks Groq to summarize only
  those chunks, and returns source citations.
- A local cosine-search fallback for development if the Atlas index is temporarily
  unavailable.
- A frontend legal question screen with source links and an explicit out-of-scope
  state.

## Current corpus

1. Protection of Women from Domestic Violence Act, 2005 — selected definitions,
   duties, applications, and reliefs.
2. Bharatiya Nyaya Sanhita, 2023 — selected sections 80, 85, and 86.
3. Bharatiya Nagarik Suraksha Sanhita, 2023 — selected section 220.
4. NALSA official information on accessing free legal aid.

## If the corpus changes later

From `backend/`, run:

```powershell
.venv\Scripts\python.exe scripts\ingest_legal_corpus.py
```

The existing Vector Search index remains usable because every embedding uses the
same 384-dimensional model.

## Run Phase 4 locally

Backend terminal:

```powershell
cd D:\MyCodes\Aegis\aegis\backend
.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8123
```

Frontend terminal:

```powershell
cd D:\MyCodes\Aegis\aegis\frontend
npm run dev
```

Open `http://localhost:3000`, enter `2580`, press `=`, then choose **Explore legal help**.

## Important safety boundary

The legal screen must refuse questions that are not supported by the corpus. Do
not expand the corpus by copying random websites. Add an official or carefully
verified source, record its URL in the document front matter, then rerun ingestion.
