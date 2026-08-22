# Phase 2 beginner guide

Phase 2 is the first time the frontend talks to a backend. You need two
terminals because they are two separate programs:

## Terminal 1: backend

```powershell
cd D:\MyCodes\Aegis\aegis\backend
.venv\Scripts\activate
.venv\Scripts\uvicorn main:app --reload --port 8123
```

Leave this terminal running. The backend should be available at
`http://127.0.0.1:8123`.

## Terminal 2: frontend

```powershell
cd D:\MyCodes\Aegis\aegis\frontend
npm run dev
```

Open `http://localhost:3000`, enter `2580` and press `=`, then choose
**Prepare a message**.

## Groq setup

The app works without a Groq key using a local demo sentence. To enable the
real AI expansion, copy `backend/.env.example` to `backend/.env` and add your
Groq key:

```text
GROQ_API_KEY=your_key_here
GROQ_MODEL=llama-3.3-70b-versatile
```

Restart the backend after changing `.env`. The SOS result labels whether the
message came from `groq` or the `local demo` fallback.

## What the backend is doing

1. The browser sends keywords and a cover theme as JSON to `/sos/generate`.
2. The backend expands the keywords into one careful message.
3. It gets a normal-looking cover image from Pollinations and converts it to PNG.
4. It writes the message into the least-significant bits of the PNG pixels.
5. It sends the finished PNG back to the browser as a data URL.
6. Later, `/sos/decode` can read the message from that exact PNG file.

The hidden message is not magic encryption. It is steganography: the message
is concealed inside tiny pixel changes that are visually hard to notice. The
file must stay as the original PNG for lossless decoding.
