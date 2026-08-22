# Phase 5 beginner guide — responder flow

Phase 5 closes the loop on the SOS image. A trusted contact can upload the
original PNG, reveal the hidden message, review a conservative urgency level,
and save the handoff as a case.

## What was added

- `POST /responder/decode` accepts the original PNG and reuses the Phase 2
  steganography decoder.
- `POST /responder/cases` saves a reviewed message, severity, timestamp, and
  filename.
- `GET /responder/cases` loads recent cases sorted high, medium, then low.
- MongoDB collection: `sos_cases`.
- A rule-based urgency floor catches immediate-danger language. Groq may assist
  with classification, but it can never downgrade a rule-based high or medium
  signal.
- A new Responder workspace is available from the revealed Aegis toolkit.

## Test the flow

1. Open `http://localhost:3000`.
2. Enter `2580` and press `=`.
3. Open **Send a discreet SOS**.
4. Create and save an SOS image as the exact PNG file.
5. Return to the toolkit and open **Responder workspace**.
6. Upload the saved PNG.
7. Review the decoded message and urgency.
8. Click **Save responder case**.

The saved case should appear under **Recent signals**. Because MongoDB is now
configured, the storage badge should say **MongoDB**.

## Important image rule

Upload the exact PNG produced by Aegis. Screenshots, JPEG conversion, resizing,
and social-media re-compression can erase the hidden message. If that happens,
the responder screen rejects the file instead of showing a made-up message.

## Current Phase 5 boundary

This dashboard is intentionally open inside the demo. Phase 6 adds Clerk
authentication, responder roles, and case access limited to explicitly linked
responders. Do not treat the current demo dashboard as a production access
control system.
