# Aegis

## A discreet safety and support companion

Aegis is a private safety toolkit for people facing abuse, isolation,
monitoring, harassment, or an unsafe situation. It combines emotional support,
legal information, health guidance, discreet SOS communication, trusted-contact
calling, email alerts, and private messaging in one calm application.

Aegis is designed to help a person choose the safest available next step. It is
not a replacement for emergency services, a doctor, a lawyer, or a trained
responder.

## Problem statement

People in unsafe situations may not be able to openly search for help or make a
visible call. Support is also fragmented: emotional help, legal information,
health guidance, communication, and emergency support usually exist in separate
places.

Aegis addresses this by providing discreet access to multiple forms of support
through one privacy-focused interface. The product is designed for stressful,
low-bandwidth, monitored, or resource-limited situations.

## How we evaluate the solution

The project is evaluated through realistic user scenarios:

- Can a user access help discreetly and exit quickly?
- Does the companion respond naturally and follow the latest message?
- Does the legal assistant provide relevant, cited Indian legal sources?
- Does the health assistant answer intimate questions clearly and without shame?
- Can an SOS message reach a trusted person through more than one channel?
- Are messages and queued emails preserved after refresh or temporary failure?
- Does the interface remain understandable and responsive under stress?

The goal is not only to generate an answer. Each response must be relevant,
clear, honest about its limitations, and appropriate to the user’s situation.

## Key features

### Discreet calculator entry

The application opens as a working calculator. Enter the configured unlock code
(`2580` in the local setup) and press `=` to reveal the private Aegis toolkit.
Quick Exit or `Escape` immediately returns to the calculator.

### Discreet SOS image

The user enters a short situation and selects an ordinary cover such as a flower,
landscape, food, coffee, or sunset. Aegis creates a clear message and hides it
inside a normal-looking PNG using lossless LSB steganography.

The image can be saved or shared through the phone’s native share sheet. A
responder can upload the exact PNG to decode the hidden message. A custom text
message can also be shared.

### AI Companion

A warm, natural emotional-support chatbot for ordinary conversation, loneliness,
creative requests, grounding, and difficult moments. It adapts to the latest
message instead of repeating a fixed emergency script. Optional browser
read-aloud and live voice conversation are also available.

### India-scoped Legal Rights Bot

The legal assistant retrieves relevant passages from a curated India-focused
corpus, including the Domestic Violence Act, BNS, BNSS, BSA, POCSO, POSH,
Dowry Prohibition Act, and legal-aid sources. Answers include sections and source
links rather than unsupported legal claims.

### Health Assistant

Provides direct, judgment-free information about symptoms, sexual health,
periods, contraception, pregnancy, consent, and other adult health questions.
It also highlights warning signs that require professional medical attention.

### Responder workspace

A trusted person or responder can decode an SOS PNG, view the hidden message,
classify urgency, and review saved cases in severity order.

### Trusted-contact voice bridge

The user can provide their name, location, situation, instructions, and optional
chat summary. A live voice agent explains the situation to a trusted contact and
answers factual follow-up questions from the supplied information.

### Email support and offline queue

Help requests can be sent to a trusted person or configured support address. If
the internet or email provider is temporarily unavailable, the request is saved
in a local queue and retried automatically when connectivity returns.

### Private direct messages

Signed-in users can search by username, start one-to-one conversations, send
messages, and retain message history after reloads and account switching.
Realtime updates use WebSockets with polling fallback for reliability.

## Architecture

```text
User
 |
 v
Next.js frontend
calculator, navigation, chat, SOS, responder, email, voice, DMs
 |
 | HTTP + WebSocket
 v
FastAPI backend
routers, validation, AI routing, steganography, queues, integrations
 |
 +--> Gemini / Groq / Ollama
 +--> MongoDB Atlas / SQLite / local corpus
 +--> Clerk authentication
 +--> EmailJS
 +--> Voice-agent provider
```

### Frontend

- Next.js 16 with App Router
- React 19 and TypeScript
- Responsive CSS interface with pink, cream, and white visual language
- GSAP and Lenis for smooth transitions and scrolling
- Browser Web APIs for native sharing, clipboard, read-aloud, and keyboard exit
- Clerk UI integration for username-based authentication

### Backend

- Python 3.12
- FastAPI, Uvicorn, and Pydantic
- Modular routers for SOS, companion, legal, health, responder, voice, email,
  and direct messages
- Provider fallbacks and clear source/provider labels

### Storage and data

- MongoDB Atlas for legal retrieval, responder cases, optional companion memory,
  and remote persistent data when configured
- SQLite for local direct-message persistence and the email queue
- Local official legal corpus for offline retrieval fallback
- Secrets stored only in `.env` and `.env.local` files

## AI provider strategy

Aegis is online-first. When internet access and API keys are available, the
configured online model is used. If an online provider is unavailable, the
system can fall back to another provider or Ollama running locally.

This keeps the online experience high quality while preserving a useful local
development and demonstration path. Every response identifies its provider or
fallback source where relevant.

## Local setup

Start the backend in one PowerShell window:

```powershell
cd D:\MyCodes\Aegis\aegis\backend
.venv\Scripts\uvicorn.exe main:app --host 127.0.0.1 --port 8123
```

Start the frontend in a second window:

```powershell
cd D:\MyCodes\Aegis\aegis\frontend
npm install
npm run dev
```

Open the URL shown by Next.js, usually `http://localhost:3000`. Configure
provider keys in `backend/.env` and frontend public settings in
`frontend/.env.local`. Never commit real keys.

## Suggested judge demonstration

1. Open the calculator and reveal Aegis with `2580 =`.
2. Create a discreet SOS image from a short situation.
3. Show that the image looks ordinary and explain the hidden-message layer.
4. Decode it in the responder workspace.
5. Ask the Companion a short emotional-support question.
6. Ask the Legal Bot a domestic-violence question and show its citations.
7. Demonstrate a trusted-contact voice session or queued help email.
8. Show private messaging between two authenticated usernames.

## Future scope

Aegis will evolve into a moderated support community with:

- Community posts, image sharing, and group conversations
- Verified legal-supporter and responder profiles
- Legal-supporter tags and role-based access control
- Trusted support-organization directory
- More Indian languages and voice support
- Stronger offline-first AI and communication capabilities
- Better consent, encryption, retention, and data-deletion controls
- Secure production deployment and expert review before public use

The long-term vision is a safe, growing community where people can receive
emotional support, understand their rights, contact trusted people, and find
verified human help without being forced into one communication method.

## Project structure

```text
aegis/
├── frontend/        Next.js application and UI flows
├── backend/         FastAPI application and services
├── docs/            Architecture and integration guides
└── plan.md          Phase-by-phase project plan
```

## Safety note

Aegis is a prototype designed around safety and privacy. Legal and health
responses are general information and should be verified with qualified
professionals. In immediate danger, contact the appropriate local emergency
service when it is safe to do so.
