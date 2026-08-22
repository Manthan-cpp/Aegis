# Phase 3 beginner guide

The companion is now part of the same two-server setup as Phase 2.

## Run the app

Backend terminal:

```powershell
cd D:\MyCodes\Aegis\aegis\backend
.venv\Scripts\uvicorn main:app --reload --port 8123
```

Frontend terminal:

```powershell
cd D:\MyCodes\Aegis\aegis\frontend
npm run dev
```

Open `http://localhost:3000`, enter `2580` and press `=`, then select
**Open companion**.

## What is private by default

The **Remember this conversation** switch starts off. When it is off, new chat
messages are sent to Groq to generate a reply but are not kept by the Aegis
backend after that request finishes. The active browser chat sends up to the last
six visible turns with each new message so replies stay coherent; this temporary
context is not saved.

Turning it on allows Aegis to send recent turns back with your next message so
the companion can remember the conversation. Use **Clear saved memory** at any
time to delete the saved turns and turn the switch off.

## Why sensitive conversations respond differently

Aegis recognizes immediate danger, possible abuse, and monitoring/control language
as different situations. For abuse, it asks one specific question instead of
immediately repeating a generic referral. If someone says they are monitored or
cannot safely contact anyone, it acknowledges that constraint and avoids pushing
calls, messages, hidden activity, or breathing exercises. A quality check replaces
an AI reply if it falls back into those canned patterns.

## Enable durable MongoDB memory

Until you connect MongoDB Atlas, memory is a local demo feature that disappears
when the backend restarts. To make it durable:

1. Create an Atlas free cluster and a **database user**. A database user is
   separate from your normal Atlas login.
2. In Atlas, add your current IP address to the project IP access list.
3. On the cluster page, choose **Connect**, then **Drivers**, and copy the
   `mongodb+srv://...` connection string.
4. Replace `<password>` in that string with your database-user password. Keep
   this entire string secret.
5. In `backend/.env`, set:

```text
MONGODB_URI=mongodb+srv://your_database_user:your_password@your_cluster/...
MONGODB_DB_NAME=aegis
```

6. Stop and restart the backend. Send two messages with memory turned on; the
   app will confirm that memory is being saved for conversation continuity.

You do not need to create a table manually. Aegis creates the
`companion_sessions` collection on its first consented memory save. MongoDB
Atlas requires both a database user and an allowed IP address for an app to
connect. See the official [Atlas connection guide](https://www.mongodb.com/docs/atlas/driver-connection/).

## Why urgent messages behave differently

If a message indicates immediate danger, the companion shows direct 112 and
181 actions. This part does not rely on an AI-generated answer. India&apos;s
official ERSS identifies 112 as the national emergency number; Aegis also
offers 181 as a women&apos;s/domestic-violence support route. See [ERSS 112](https://112.gov.in/)
and the [National Portal helpline directory](https://www.india.gov.in/directory/helpline).

## Read aloud

The **Read aloud** button uses the Web Speech API built into Chrome and Edge.
It does not record your microphone. Speech-to-text is intentionally not added
yet because it needs microphone permission and would add complexity without
improving the core companion demo.
