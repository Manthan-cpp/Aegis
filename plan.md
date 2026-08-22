# Aegis — Discreet Safety Companion
### Master Build Plan (Zero-Cost Stack)

> **Read this before touching any code.** This file is the single source of truth for the project. Every phase is self-contained: it states what exists before the phase starts, what must exist after it ends, and exactly which files/services it touches. If you are an agent (or Manthan) resuming work, read the "Context Recap" of the last completed phase and the "Goal" of the next one before writing anything.

---

## 0. What We're Actually Building

**Aegis** is a stealth safety companion for people in abusive/monitored situations. It is *inspired by* the publicly documented project "Haven" (MongoDB AI Hackathon winner) but is **not a clone** — the core interaction model, disguise mechanism, and scope are deliberately different, both for originality and because parts of Haven's original design (live social-media hashtag scanning via a cron job) require paid/restricted APIs that don't fit our zero-cost constraint.

### Core differentiation from Haven
| Haven | Aegis |
|---|---|
| Public web app, share SOS image on social media, authority side scans hashtags | **Disguised as an innocuous phone app** (calculator/notes lock screen), SOS image is shared directly to a trusted contact or NGO — no social scanning, no third-party API dependency |
| Full photorealistic 3D avatar w/ ElevenLabs voice + lip-sync | Lightweight stylized companion (2D/low-poly) using free browser TTS, no paid voice API |
| Broad "Indian constitution + global laws" legal bot | Scoped legal bot: **specifically DV-relevant Indian law** (PWDVA 2005, relevant IPC/BNS sections, dowry law) — narrower, more accurate, easier to demo without embarrassing gaps |
| AWS Bedrock (Titan) for everything | Groq (Llama 3.3 70B) + free embeddings + free image gen — genuinely $0 |

### The three pillars (what judges will see)
1. **Stealth SOS via steganography** — app looks like a calculator; a secret PIN/gesture unlocks the real app. User types a short distress phrase, AI expands it into a full message, picks a cover image (auto-generated, looks like a normal photo), message is invisibly embedded (LSB steganography), and the image is sent to a pre-configured trusted contact/NGO channel.
2. **AI Companion** — a calm, always-available chat companion (Groq/Llama) for emotional support, grounding techniques, and coping strategies, with optional voice (browser TTS) and a simple animated presence.
3. **Legal Rights Bot** — RAG chatbot answering DV-specific legal questions, grounded in a small curated corpus (PWDVA, relevant penal code sections) stored as embeddings in MongoDB Atlas Vector Search, so answers are cited to actual provisions instead of hallucinated.

A fourth, judge-facing piece ties it together:
4. **Responder Dashboard** — a separate, simple view (for the "trusted contact / NGO" role) where a received image can be uploaded and decoded to reveal the hidden message and severity flag.

---

## 1. Zero-Cost Stack — Verified

Every service below was checked for a genuine no-card, no-trial-expiry free tier before being chosen. Do not swap in a paid service without updating this table and flagging it to Manthan.

| Layer | Choice | Why / Free-tier facts |
|---|---|---|
| LLM (text expansion, chat, severity scoring) | **Groq API — `llama-3.3-70b-versatile`** | No credit card required. Free tier: ~30 requests/min, ~1,000 requests/day, ~12K tokens/min. Plenty for a hackathon demo (already used successfully in your swarm-simulation plan). |
| Embeddings (for legal RAG) | **`sentence-transformers/all-MiniLM-L6-v2`, run locally in the FastAPI backend** | Fully open-source, runs on CPU, no API key, no cost, no rate limit. Avoids depending on Gemini/OpenAI embedding quota. |
| Vector store | **MongoDB Atlas M0 (free forever tier)** | Confirmed: M0 free cluster (512MB storage) supports Atlas Vector Search natively — no separate paid Search Node needed at this scale. |
| Cover image generation (steganography carrier) | **Pollinations.ai image API** | Free, no API key, no signup, simple GET request returns an image. |
| Steganography engine | **Custom LSB implementation (Python/Pillow, or `stegano` package)** | Pure math on pixel data, runs anywhere, $0. |
| Text-to-speech (companion voice) | **Browser Web Speech API** | Free, built into Chrome/Edge, zero backend cost — same approach already used successfully in SignSpeak. |
| Companion visual | **CSS/Lottie or lightweight Three.js low-poly avatar** | Free assets (e.g. Mixamo/Kenney free-license models), no paid TTS/lip-sync pipeline needed. |
| Frontend framework | **Next.js + Tailwind CSS** | Free, deploys free on Vercel. |
| Backend framework | **FastAPI (Python)** | Free, deploys free on Render (cold start ~30s on free tier — acceptable for a demo). |
| Auth | **Clerk (free tier)** | Enough for a hackathon-scale user count. |
| Hosting | **Vercel (frontend) + Render (backend), both free tiers** | $0, matches what Haven itself used. |

**Known free-tier limitations to design around:**
- Render free web services sleep after inactivity — first request after idle takes ~30–50s. Plan the demo script around this (see Phase 9).
- Groq free tier is per-organization, not per-user — during the live demo, keep requests sequential, not parallel, to avoid rate-limit errors.
- MongoDB M0 caps at 512MB — fine for a small legal corpus + demo case data, not for production scale. This is explicitly a hackathon/MVP build, not a production claim.

---

## 2. Repository Structure (target, built up phase by phase)

```
aegis/
├── plan.md                      ← this file, never deleted, updated as phases complete
├── frontend/                    ← Next.js app (stealth shell + real app + responder dashboard)
│   ├── app/
│   │   ├── (stealth)/           ← calculator disguise, PIN gate
│   │   ├── (main)/              ← real app: SOS flow, companion chat, legal bot
│   │   └── (responder)/         ← NGO/trusted-contact decode dashboard
│   ├── components/
│   └── lib/
├── backend/                     ← FastAPI app
│   ├── main.py
│   ├── routers/
│   │   ├── sos.py               ← text expansion, image fetch, encode/decode
│   │   ├── companion.py         ← chat + severity scoring
│   │   ├── legal.py             ← RAG query endpoint
│   │   └── cases.py             ← responder dashboard data
│   ├── services/
│   │   ├── groq_client.py
│   │   ├── steganography.py
│   │   ├── embeddings.py
│   │   └── mongo.py
│   ├── data/legal_corpus/       ← curated PDFs/text (PWDVA etc.)
│   └── requirements.txt
└── docs/
    ├── architecture.md
    └── demo_script.md
```

---

## 3. Phases

Each phase below has: **Goal**, **Prerequisites**, **Tasks**, **Deliverables/Acceptance Criteria**, and a **Context Recap** block to write once the phase is done (so the next session/agent has zero ambiguity about where things stand).

---

### Phase 0 — Project Scaffolding & Environment
**Goal:** Empty-but-runnable skeleton for both frontend and backend, with all free-tier accounts created and keys collected (never committed).

**Tasks**
- Create GitHub repo (private until ready), initialize with the folder structure above.
- `npx create-next-app` for frontend (TypeScript, Tailwind, App Router).
- `fastapi` + `uvicorn` scaffold for backend, with a `/health` endpoint.
- Create accounts: Groq, MongoDB Atlas (M0 cluster), Render, Vercel, Clerk.
- `.env.example` files for both frontend and backend listing every required key (no real values committed).
- Basic CI-less setup is fine — no paid CI needed at this stage.

**Deliverables / Acceptance Criteria**
- `GET /health` on backend returns `200`.
- Frontend renders a placeholder home page locally.
- All accounts created, keys stored locally in `.env` (gitignored).

**Context Recap — DONE (2026-08-13):**
- Repo scaffolded at `aegis/` with `frontend/` (Next.js 15, App Router, TypeScript, Tailwind) and `backend/` (FastAPI).
- Route groups created and empty, ready for Phase 1/2-4/5: `app/(stealth)/`, `app/(main)/`, `app/(responder)/`.
- Backend `main.py` has CORS wired to `ALLOWED_ORIGINS` env var (defaults to `localhost:3000`) and a working `GET /health` → verified locally returning `{"status":"ok","service":"aegis-backend"}` on port 8123.
- `requirements.txt` lists the full eventual dependency set (fastapi, uvicorn, pymongo, pillow, groq, sentence-transformers, stegano) — only fastapi/uvicorn/dotenv actually installed and tested so far; the heavier ML deps (sentence-transformers) are deferred to Phase 4 since they're slow to install and unused until then.
- `.env.example` created for both frontend and backend listing every key the plan will eventually need (Groq, MongoDB URI, Clerk, allowed origins). **No real accounts/keys created yet** — that's on Manthan to do before Phase 2 (Groq, MongoDB Atlas M0) and Phase 6 (Clerk). Render/Vercel accounts needed before Phase 9 deploy.
- `docs/architecture.md` started as a living doc, updated with each phase.
- Not yet done, by design: no dependencies installed beyond the smoke test, no git init/remote pushed yet, no deployment.

---

### Phase 1 — Stealth Shell (the disguise)
**Goal:** The app opens looking like an ordinary, boring calculator. A specific input sequence (e.g. typing a PIN then pressing `=`) reveals the real app underneath. This is the signature differentiator from Haven and should be built early since it frames every later demo.

**Tasks**
- Build a fully functional basic calculator UI in `app/(stealth)/`.
- Implement a hidden trigger: e.g., entering a configured 4–6 digit code and pressing `=` navigates (client-side, no visible URL change) into `app/(main)/`.
- Add a quick "panic exit" — one tap/key returns instantly to the calculator and clears any visible app state, in case the phone is grabbed.
- Store the unlock code client-side only for now (hardcoded/local storage) — real per-user config comes in Phase 7 with auth.

**Deliverables / Acceptance Criteria**
- Calculator does real arithmetic (so it survives casual scrutiny).
- Correct code reveals the real app; wrong input just behaves like a normal calculator.
- Panic exit works instantly with no visible transition delay.

**Context Recap — DONE and VERIFIED on Manthan's machine (2026-08-13):**
- The calculator lives at the root URL through `frontend/app/(stealth)/page.tsx`. The real Aegis screen is mounted as a client-side view from `frontend/app/(main)/main-app.tsx`, so unlocking does not change the visible URL.
- Calculator behavior is implemented in `frontend/app/(stealth)/calculator.tsx`: decimal arithmetic, operator precedence, percent, sign toggle, backspace, keyboard input, divide-by-zero handling, and an unlock check on `=`.
- The default demo unlock code is `2580`. The client checks `localStorage` key `aegis.unlock-code` first and falls back to `2580` when no valid 4–6 digit code is stored. The code is intentionally client-only for Phase 1 and is not sent to the backend.
- Panic exit is available through the visible `Quick exit` button and the `Escape` key. It switches back to the calculator and unmounts the real app, clearing the real app's in-memory state immediately.
- Visual direction: the calculator is deliberately dark, neutral, and stock-looking; the revealed app uses a calm, light, spacious interface with a minimal shield mark and clear toolkit cards. The calculator remains the disguise, while the real app is allowed to feel intentional and trustworthy.
- Verified in the browser: `12 + 3 × 4 = 24`, `1.5 + 0.5 = 2`, an incorrect `1111` input remains a normal calculation, `2580 =` reveals Aegis, and `Escape` returns to the calculator. `npm run lint` and `npm run build` both pass.

---

### Phase 2 — Steganography Engine (core SOS pipeline)
**Goal:** End-to-end: short keywords → full distress message → cover image → message invisibly embedded → downloadable/shareable image. And the reverse: image → extracted message.

**Tasks**
- Backend `services/groq_client.py`: wrapper around Groq chat completions for message expansion ("help, locked in, scared" → full sentence), using a tightly scoped system prompt (no legal/medical claims, just distress articulation).
- Backend `services/steganography.py`: implement LSB encode/decode over PNG images (bit-depth-safe, verify message survives re-encoding to PNG but document that JPEG/social-media re-compression would destroy it — be upfront about this limitation, don't oversell it).
- Cover image sourcing: call Pollinations.ai with a user-chosen theme ("flower", "landscape", "food") to fetch a plausible cover image.
- `POST /sos/generate`: keywords + theme → returns encoded image (base64 or URL).
- `POST /sos/decode`: image → returns extracted message (used later by the Responder Dashboard).
- Frontend: SOS flow screen inside `(main)/` — keyword input → theme picker → preview encoded image → "Save/Share" action.

**Deliverables / Acceptance Criteria**
- Given a 3–6 word input, produces a full sentence and a visually normal-looking image.
- Decoding that exact image (same file, not re-compressed) recovers the exact message losslessly, verified with an automated test on at least 5 sample inputs.
- Explicitly test and document what breaks the hidden message (e.g. screenshotting, re-saving as JPEG) so the demo avoids those pitfalls.

**Context Recap — DONE and VERIFIED on Manthan's machine (2026-08-13):**
- `backend/services/steganography.py` uses a custom RGB LSB implementation. It writes an `AEGIS01` magic header, a four-byte UTF-8 payload length, and the message bits into a normalized PNG.
- `POST /sos/generate` expands keywords through Groq when `GROQ_API_KEY` is configured, fetches a Pollinations cover image, embeds the message, and returns a PNG data URL. Without a key or if Groq is unavailable, a clearly labeled local demo fallback keeps the flow runnable.
- `POST /sos/decode` accepts the original image file as multipart upload and returns the hidden message. The API explicitly rejects missing/corrupted messages and oversized uploads.
- Cover themes currently available: flower, landscape, food, coffee, and sunset. Pollinations images are normalized to PNG before encoding; a local generated cover is used if Pollinations is unavailable.
- The frontend SOS screen is `frontend/app/(main)/sos-flow.tsx`. It supports keyword entry, theme selection, preview, save, share when the browser supports file sharing, and visible warnings about JPEG conversion, screenshots, resizing, and social-media re-compression.
- Verified with five automated lossless round trips, a live `/sos/generate` → `/sos/decode` API test, and a browser walkthrough from calculator unlock to generated image. `npm run lint`, `npm run build`, and the backend unittest suite all pass.

---

### Phase 3 — AI Companion (emotional support chat)
**Goal:** A calm, always-on chat companion with a lightweight visual presence and optional voice, scoped strictly to grounding/coping support (not diagnosis, not crisis-only — should also gently point to real hotlines when appropriate).

**Tasks**
- Backend `routers/companion.py`: chat endpoint using Groq, system prompt built around active listening, grounding techniques, and — importantly — a rule to surface real crisis resources when severity language appears (not to replace them).
- Conversation memory: store recent turns in MongoDB per session (consent-gated, mirroring Haven's "only with user consent" approach) so responses stay contextual.
- Frontend: chat UI with a simple animated companion (CSS/Lottie breathing animation, or a minimal Three.js low-poly figure if time allows — do not over-invest here relative to the RAG/stego pieces, which are more technically differentiating).
- Voice: wire up Web Speech API for both STT (optional, if time allows) and TTS (read companion replies aloud), reusing the pattern from SignSpeak.

**Deliverables / Acceptance Criteria**
- Multi-turn conversation stays coherent and on-topic across at least 5 turns.
- Companion never gives legal or medical instructions (that's the Legal Bot's job) — verify with a few adversarial test prompts.
- TTS reads responses aloud correctly in Chrome.

**Context Recap — DONE and VERIFIED on Manthan's machine (2026-08-13):**
- `POST /companion/chat` accepts a browser-generated session ID, a message, and an explicit `memory_consent` flag. It uses Groq for ordinary support conversations and returns a clearly labeled local fallback if Groq is unavailable.
- The final companion system prompt is in `backend/services/companion_client.py`. It permits active listening and grounding only; it explicitly refuses medical diagnosis/treatment and legal guidance, forbids invented facts and false safety assurances, and never claims the assistant can stay on a call or line.
- Urgent language is detected in `backend/routers/companion.py`. High-risk messages receive a fixed safety-reviewed companion response plus an on-screen India support card with 112 emergency and 181 women&apos;s helpline actions. The core emergency number was verified against the official ERSS site before implementation.
- Conversation memory is opt-in and defaults off. When `MONGODB_URI` is configured, the `companion_sessions` MongoDB collection stores the last 12 user/assistant turns per anonymous session ID. Until MongoDB Atlas is configured, an explicitly labeled in-process local-demo fallback keeps the feature usable but clears when the backend restarts. The clear-memory endpoint deletes either store.
- Frontend companion UI is `frontend/app/(main)/companion-flow.tsx`: multi-turn chat, a lightweight CSS breathing presence, a Read aloud/Stop reading control using the browser Web Speech API, memory consent toggle, clear-memory action, and panic exit inherited from the main shell. STT was intentionally deferred; browser TTS provides the useful voice capability without microphone permissions or extra complexity.
- Verified: six automated backend tests pass (including memory consent/no-consent, urgent detection, fixed urgent response, and SOS tests); a live five-turn Groq conversation was coherent; live adversarial prompts declined medication and legal instructions; browser test showed urgent support with the 112/181 actions; `npm run lint` and `npm run build` pass. Durable MongoDB persistence is implemented but awaits Manthan&apos;s Atlas URI in `backend/.env`.

---

### Phase 4 — Legal Rights RAG Bot
**Goal:** A chatbot that answers DV-relevant legal questions grounded in an actual small corpus, with citations, instead of freeform LLM legal claims.

**Tasks**
- Curate corpus: Protection of Women from Domestic Violence Act 2005 (PWDVA), relevant IPC/BNS sections (cruelty, dowry-related provisions), and 1–2 plain-language government/NGO explainer documents. Keep this small and verifiable — quality over breadth, and note this is India-scoped for the demo (not the "global laws" claim Haven made, which is unrealistic to verify).
- Preprocessing script: chunk documents (LangChain's `RecursiveCharacterTextSplitter` or manual chunking), embed each chunk with local `sentence-transformers`, store vector + text + source citation in MongoDB Atlas with a Vector Search index.
- `routers/legal.py`: `POST /legal/ask` — embed the user query, run `$vectorSearch` against the corpus collection, pass top-N chunks + query to Groq with a "answer only from the provided context, cite the section" system prompt.
- Frontend: simple chat UI, each answer displayed with its cited source section underneath.

**Deliverables / Acceptance Criteria**
- At least 10 test questions answered correctly and traceably to a real section of the corpus.
- Bot explicitly declines (rather than hallucinates) when asked something outside the corpus's scope.
- Vector Search index created and verified working on the M0 cluster.

**Context Recap:** exact corpus files used, chunk size/overlap chosen, embedding dimension, index name.

---

### Phase 5 — Trusted Contact / Responder Flow
**Goal:** Close the loop — someone on the receiving end (trusted contact or NGO demo account) can decode an SOS image and see the situation.

**Tasks**
- `routers/cases.py`: endpoint to submit a decoded case (message + severity + timestamp) into MongoDB, replacing Haven's "cron scans social media" approach with a direct, consented "share to responder" action from the sender's app.
- Severity scoring: reuse Groq to classify the decoded message into an urgency tier (e.g. low/medium/high) — mirrors Haven's severity-sorting idea but computed at decode time, not via separate NLP pipeline.
- Frontend `(responder)/`: a separate, simply-styled dashboard — upload an image, see the decoded message, severity tag, and timestamp; list of past cases sorted by severity.

**Deliverables / Acceptance Criteria**
- Uploading a real encoded image from Phase 2 through this dashboard correctly reveals the message and a sensible severity tag.
- Case list persists across reloads (stored in MongoDB, not just client state).

**Context Recap:** severity tiers used, how cases are keyed/sorted, any auth applied to this dashboard (see Phase 7).

---

### Phase 6 — Auth & Access Control
**Goal:** Separate identity for the "user" role vs the "responder" role, and move the stealth-shell unlock code from hardcoded to per-account config.

**Tasks**
- Integrate Clerk for both roles (can use Clerk's organizations/roles feature, or two simple separate flows if time is short).
- Store per-user unlock PIN and trusted contact/responder link in MongoDB, tied to Clerk user ID.
- Lock the Responder Dashboard behind responder-role auth so it's not just an open URL.

**Deliverables / Acceptance Criteria**
- A user can sign up, set their stealth PIN, and link a responder.
- A responder can only see cases explicitly linked to them.

**Context Recap:** Clerk config decisions, schema for the user↔responder link.

---

### Phase 7 — Data Model Finalization & Integration Pass
**Goal:** Everything built in isolation across Phases 2–6 now talks to the same MongoDB schema and works as one coherent app end-to-end.

**Tasks**
- Finalize MongoDB collections: `users`, `sos_cases`, `companion_sessions`, `legal_corpus_chunks`.
- Full integration test: stealth unlock → generate SOS → decode on responder side → chat with companion → ask legal bot a question, all in one uninterrupted session.
- Fix any cross-phase bugs (auth gating, session handling, CORS between Vercel and Render).

**Deliverables / Acceptance Criteria**
- One continuous walkthrough of all four pillars works without manual intervention or console errors.

**Context Recap:** final schema (paste actual Mongo collection shapes), any integration bugs found and fixed.

---

### Phase 8 — UI Polish & Design Pass
**Goal:** Make the real app (not the calculator, which should stay deliberately boring) look intentional and trustworthy — calm colors, clear typography, no visual clutter. The calculator should look *exactly* like a stock calculator; the real app should look like a considered product.

**Tasks**
- Apply a consistent design system (reuse patterns from your SignSpeak UI work where relevant — constellation-style calm backgrounds, GSAP micro-transitions on entering the real app).
- Accessibility pass: color contrast, readable font sizes, since this app may be used under stress.
- Mobile-first check — the stealth disguise only makes sense if it works convincingly on a phone screen.

**Deliverables / Acceptance Criteria**
- App is usable and coherent on a phone-sized viewport.
- Transition from calculator → real app feels deliberate, not glitchy.

**Context Recap:** design tokens/colors chosen, any animation libraries added.

---

### Phase 9 — Demo Script & Pitch Prep
**Goal:** A judge-proof live demo sequence plus a short deck, accounting for free-tier quirks (Render cold start, Groq rate limits).

**Tasks**
- Write `docs/demo_script.md`: exact click-by-click sequence, ~4–5 minutes, covering all three pillars plus the responder view.
- "Warm up" the Render backend a minute or two before presenting (hit `/health` manually) so there's no cold-start delay live.
- Prepare 2–3 pre-generated SOS images as backups in case live Groq calls hit a rate limit or network hiccup during judging.
- Build a short pitch deck (reuse `pptxgenjs` approach from the SignSpeak deck) covering: problem statement, the three pillars, the zero-cost architecture (judges like seeing real constraints handled well), and what's different from prior art like Haven (be upfront and confident about this — "inspired by, differentiated by X/Y/Z" is a stronger story than pretending no prior art exists).

**Deliverables / Acceptance Criteria**
- Full demo rehearsed at least twice, end-to-end, under 5 minutes.
- Backups ready for any live-API flakiness.

**Context Recap:** final demo flow, backup assets location, deck file path.

---

## 4. How This Gets Demoed to Judges (summary)

1. **Open the phone/laptop showing a plain calculator.** Type the unlock code, hit `=`. The real app appears — this alone is a strong hook.
2. **Trigger an SOS:** type 3–4 words ("help scared locked in"), pick "flower" as the cover theme. Show the AI-expanded message, then the generated image — visually a normal flower photo.
3. **Switch to the Responder Dashboard** (second browser tab/device, framed as "this is what the trusted contact/NGO sees"). Upload that same image — the hidden message and an AI-assigned severity tag appear instantly. This is the "aha" moment.
4. **Show the AI Companion:** have a short supportive exchange, with the reply read aloud via TTS.
5. **Show the Legal Bot:** ask a real DV-law question ("What can I do if my husband threatens me?"), and point out the answer is grounded in an actual cited section, not a generic LLM guess.
6. **Close with the architecture slide:** everything shown just ran on Groq's free tier, MongoDB's free M0 cluster, and free hosting — zero recurring cost, which is itself part of the pitch (a tool for people with no resources shouldn't require resources to run).

---

## 5. Open Decisions (flag to Manthan before proceeding past Phase 2)

- ~~Final project name~~ — **decided: Aegis.**
- Whether the 2D/low-poly companion visual is worth the time budget versus a simpler chat-only companion — recommend deciding this at the start of Phase 3 based on remaining time.
- Whether Phase 6 (Auth) is done before or after the hackathon deadline — if time is tight, a demo can fake two roles with two hardcoded accounts and Auth can be marked "future work" on the pitch deck without hurting the demo.
