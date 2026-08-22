# Architecture (living doc)

Filled in incrementally as phases complete.

## Phase 0 status

- Frontend: Next.js (App Router, TypeScript, Tailwind) at `frontend/`
- Backend: FastAPI at `backend/`, single `/health` route confirmed working
- Route groups scaffolded: `(stealth)`, `(main)`, `(responder)`
- No database, auth, or external API wired up yet; that starts in Phase 2 onward

## Phase 1 status - Stealth shell

- The root screen is the calculator disguise. `app/(stealth)/page.tsx` owns a small client-side mode switch between the calculator and the revealed Aegis view.
- The revealed view is a component at `app/(main)/main-app.tsx`, rather than a second page route. This is deliberate: Next.js route groups do not change URL paths, so keeping both screens in one client-side shell preserves the plan's no-visible-URL-change behavior.
- The calculator is fully local. Its expression parser uses tokenization and operator precedence; it does not use `eval` and does not contact the backend.
- Phase 1 stores the unlock code in browser `localStorage` under `aegis.unlock-code`, falling back to the demo code `2580`. This is only a disguise trigger, not a security boundary. Phase 6 will replace it with an authenticated per-user setting.
- Panic exit unmounts the private view and returns to the calculator through either the `Quick exit` button or `Escape`. Because the private view is unmounted, its in-memory UI state is discarded.

## Next boundary

Phase 2 is the first backend-backed feature. It will introduce request bodies,
FastAPI routers, and small service modules for message expansion and
steganography. The Phase 1 screen keeps the SOS card visual-only until that
pipeline exists end to end.

## Phase 2 status - SOS pipeline

- `backend/routers/sos.py` exposes `POST /sos/generate` and `POST /sos/decode`.
- `backend/services/groq_client.py` owns the LLM call and has a clearly labeled local fallback for development without a Groq key.
- `backend/services/cover_image.py` owns Pollinations fetching and converts every cover to PNG before encoding. It also supplies a deterministic local cover if the network service is unavailable.
- `backend/services/steganography.py` owns the lossless RGB LSB format. The exact PNG is required for decoding; JPEG conversion, screenshots, resizing, and social-media re-compression are documented as destructive.
- The frontend sends JSON to `NEXT_PUBLIC_API_BASE_URL` (default `http://127.0.0.1:8123`) and keeps the encoded image in memory until the user saves or shares it. No image or message is stored in MongoDB yet.
- No MongoDB work is needed for this phase. Persistence and responder case records begin in Phase 5.

## Phase 3 status - AI companion

- `backend/routers/companion.py` exposes `POST /companion/chat` and `DELETE /companion/sessions/{session_id}`. It applies urgent-language detection before a reply is generated.
- `backend/services/companion_client.py` uses Groq for ordinary support chats. The system prompt limits it to listening and grounding, declines legal/medical instructions, and forbids false claims about safety, location, or active real-time presence. Abuse and monitoring modes include a post-generation quality check that replaces generic or risky referral language with a context-guided response.
- The browser sends up to six recent visible turns for coherence even when saved memory is off; these turns are request-only context and are not persisted. Consent-gated Mongo memory remains a separate opt-in feature.
- Urgent conversations do not use free-form LLM guidance. They get a fixed safety-reviewed reply and the frontend renders verified India help actions: 112 for immediate emergency support and 181 for the domestic-violence/women&apos;s helpline.
- `backend/services/mongo.py` provides consent-gated conversation storage. A configured Atlas URI uses the `companion_sessions` collection; without it, a clearly labeled in-process local-demo store allows development but is wiped on backend restart.
- `frontend/app/(main)/companion-flow.tsx` holds only the visible chat state and calls the API. Web Speech API provides optional read-aloud; speech-to-text is intentionally deferred.

## Phase 4 status — India-scoped legal rights RAG

- `backend/data/legal_corpus/` contains a small curated corpus based on India
  Code and official NALSA information. It records source URLs in each document.
- `backend/scripts/ingest_legal_corpus.py` splits the corpus into the current
  curated chunk set,
  embeds them with local `all-MiniLM-L6-v2` (384 dimensions), and upserts them
  into MongoDB's `legal_corpus_chunks` collection.
- MongoDB Atlas Vector Search index `legal_vector_index` is configured on the
  `embedding` field with cosine similarity.
- `backend/routers/legal.py` exposes `POST /legal/ask`. It retrieves top chunks,
  sends only those excerpts to a separate legal Groq prompt, returns citations,
  and refuses when retrieval is below the relevance threshold. It does not reuse
  companion memory.
- `frontend/app/(main)/legal-flow.tsx` provides the cited question-and-answer UI.

## Next boundary

Phase 5 will add the trusted-contact/responder flow. It should reuse the existing
SOS decode service but store responder cases separately from legal chunks and
companion memory.

## Phase 5 status — trusted contact / responder flow

- `backend/routers/responder.py` exposes `/responder/decode`, `/responder/cases`
  POST, and `/responder/cases` GET. It decodes an exact Phase 2 PNG, classifies
  urgency, saves reviewed cases, and returns cases in severity order.
- `backend/services/severity.py` combines conservative keyword rules with Groq
  classification. Explicit immediate danger cannot be downgraded by the model.
- `backend/services/cases.py` stores cases in MongoDB's `sos_cases`
  collection and uses a labeled local-demo fallback when MongoDB is unavailable.
- `frontend/app/(main)/responder-flow.tsx` provides upload, review, save, and
  recent-case queue views. It is intentionally not authenticated until Phase 6.
- The live handoff test decoded an SOS, classified it as high, saved it to MongoDB,
  verified it appeared first, and removed the temporary test record afterward.

## Next boundary

Phase 6 will add Clerk authentication and access control. It must protect the
responder dashboard and replace the shared demo access with explicit responder
identity and linked-case permissions.

## Phase 7 status — data model and integration pass

- The canonical MongoDB collection names are now `sos_cases`,
  `companion_sessions`, and `legal_corpus_chunks`. `users` is reserved for the
  deferred authentication phase.
- `backend/scripts/ensure_indexes.py` creates stable indexes for session ids,
  SOS severity/time ordering, case ids, and legal chunk ids. It does not delete
  documents.
- The legal corpus was re-ingested after improving Sections 17–19 coverage. The
  Atlas `legal_vector_index` on `legal_corpus_chunks` is READY and queryable.
- The legal UI is now a source-grounded follow-up chat instead of a one-shot
  form. It sends only active browser context, shows citations per answer, and
  keeps an explicit out-of-scope refusal.
- The companion prompt now varies its conversational shape, follows requests to
  listen without advice, avoids repetitive openings, and retains the existing
  abuse/monitoring safeguards.
- A full live walkthrough passed: health → SOS generation → responder decode →
  MongoDB case save → companion reply → cited legal answer → case cleanup.

## Next boundary

Phase 6 authentication remains intentionally deferred by product decision. The
next planned work after the hackathon decision is either Clerk access control or
Phase 8 UI polish and accessibility.

## Health assistant status

- `backend/routers/health.py` exposes `POST /health/chat` for a separate online
  health-information conversation. It does not reuse companion or legal memory.
- `backend/services/health_client.py` uses Gemini first, Groq as an online
  fallback, and Ollama only when both online providers are unavailable. It
  answers adult intimate-health questions directly and without shame, while
  retaining narrow medical-safety boundaries around emergencies, dangerous
  treatment instructions, self-harm, and minors.
- `frontend/app/(main)/health-flow.tsx` provides the health chat UI. Offline
- The health chat labels the actual provider used, so the user can distinguish
  Gemini, online fallback, and offline Ollama responses.
