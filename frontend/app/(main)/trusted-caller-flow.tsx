"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { WebSession, type SessionStatus } from "@omnidim-ai/client";

type TrustedCallerFlowProps = {
  onBack: () => void;
};

type WebVoiceSessionResponse = {
  ws_url: string;
  session_id: string | null;
  expires_at: string | null;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8123";

function statusText(status: SessionStatus) {
  if (status === "connecting") return "Connecting to your trusted-contact agent";
  if (status === "active") return "Live browser voice call";
  if (status.reason === "not_started") return "Ready for a browser voice call";
  if (status.reason === "stopped") return "Call ended";
  if (status.reason === "insufficient_balance") return "OmniDimension balance or account limit reached";
  if (status.reason === "connection_lost") return "Connection lost — call ended";
  return `Call ended: ${status.reason}`;
}

export default function TrustedCallerFlow({ onBack }: TrustedCallerFlowProps) {
  const [userName, setUserName] = useState("");
  const [location, setLocation] = useState("");
  const [situation, setSituation] = useState("");
  const [instructions, setInstructions] = useState("");
  const [chatSummary, setChatSummary] = useState("");
  const [status, setStatus] = useState<SessionStatus>({ state: "ended", reason: "not_started" });
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const sessionRef = useRef<WebSession | null>(null);

  const isBusy = status === "connecting";
  const isLive = status === "active";

  useEffect(() => {
    return () => {
      sessionRef.current?.stop();
      sessionRef.current = null;
    };
  }, []);

  function handleStatus(nextStatus: SessionStatus) {
    setStatus(nextStatus);
    if (typeof nextStatus === "object" && nextStatus.state === "ended" && nextStatus.reason !== "not_started") {
      setNotice(nextStatus.reason === "stopped" ? "The browser voice call has ended." : statusText(nextStatus));
    }
  }

  async function startCall(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanedName = userName.trim();
    if (!cleanedName || isBusy || isLive) return;

    setError(null);
    setNotice(null);
    setStatus("connecting");

    try {
      const response = await fetch(`${API_BASE_URL}/voice/web-session`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_name: cleanedName,
          location: location.trim() || null,
          situation: situation.trim() || null,
          instructions: instructions.trim() || null,
          chat_summary: chatSummary.trim() || null,
        }),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.detail ?? "Aegis could not start the browser voice call.");

      const sessionDetails = body as WebVoiceSessionResponse;
      const session = new WebSession();
      sessionRef.current = session;
      session.on("status", handleStatus);
      session.on("error", (sessionError) => setError(sessionError.message));
      await session.start({ wsUrl: sessionDetails.ws_url });
    } catch (requestError) {
      sessionRef.current?.stop();
      sessionRef.current = null;
      setStatus({ state: "ended", reason: "start_failed" });
      setError(
        requestError instanceof Error
          ? `${requestError.message} Make sure the backend is running on port 8123.`
          : "Aegis could not start the browser voice call.",
      );
    }
  }

  function endCall() {
    sessionRef.current?.stop();
    sessionRef.current = null;
    setStatus({ state: "ended", reason: "stopped" });
  }

  return (
    <section className="trusted-caller-flow" aria-labelledby="trusted-caller-title">
      <button className="back-link" type="button" onClick={onBack} disabled={isLive}>
        <span aria-hidden="true">&larr;</span> Back to toolkit
      </button>

      <div className="trusted-caller-heading">
        <div>
          <p className="eyebrow">Aegis voice bridge</p>
          <h2 id="trusted-caller-title">Reach someone you trust.</h2>
          <p>This opens a live browser voice session. It does not place a phone call and does not need a phone number.</p>
        </div>
        <div className={`trusted-caller-orb${isLive ? " is-live" : ""}`} aria-hidden="true"><span /></div>
      </div>

      <form className="trusted-caller-panel" onSubmit={startCall}>
        <div className="trusted-caller-panel-topbar">
          <div className="companion-status">
            <span className={`companion-status-dot${isLive ? " is-live" : ""}`} aria-hidden="true" />
            {statusText(status)}
          </div>
          {isLive && <button className="trusted-caller-end" type="button" onClick={endCall}>End call</button>}
        </div>

        <div className="trusted-caller-form-grid">
          <label>
            Your name <span>*</span>
            <input value={userName} onChange={(event) => setUserName(event.target.value)} placeholder="e.g. Aisha" maxLength={120} disabled={isBusy || isLive} required />
          </label>
          <label>
            Location <small>optional</small>
            <input value={location} onChange={(event) => setLocation(event.target.value)} placeholder="e.g. Near home" maxLength={240} disabled={isBusy || isLive} />
          </label>
          <label className="trusted-caller-wide-field">
            Situation <small>optional</small>
            <textarea value={situation} onChange={(event) => setSituation(event.target.value)} placeholder="What should the trusted contact know?" maxLength={1_200} rows={3} disabled={isBusy || isLive} />
          </label>
          <label>
            Specific instructions <small>optional</small>
            <textarea value={instructions} onChange={(event) => setInstructions(event.target.value)} placeholder="Ask whether they can help and answer follow-up questions." maxLength={800} rows={3} disabled={isBusy || isLive} />
          </label>
          <label>
            Chat summary <small>optional</small>
            <textarea value={chatSummary} onChange={(event) => setChatSummary(event.target.value)} placeholder="Short factual summary from the Aegis chat." maxLength={2_000} rows={3} disabled={isBusy || isLive} />
          </label>
        </div>

        <div className="trusted-caller-actions">
          <button className="trusted-caller-start" type="submit" disabled={!userName.trim() || isBusy || isLive}>
            {isBusy ? "Starting voice session..." : isLive ? "Call in progress" : "Start browser voice call"}
            {!isBusy && !isLive && <span aria-hidden="true">&rarr;</span>}
          </button>
        </div>
        <p className="trusted-caller-note">Aegis is not an emergency service. Browser voice calls require an internet connection and microphone permission.</p>
      </form>

      {error && <p className="companion-error" role="alert">{error}</p>}
      {notice && <p className="companion-notice" role="status">{notice}</p>}

      <p className="companion-disclaimer">Only share information you choose to share. If someone is in immediate danger in India, contact 112 when it is safe to do so.</p>
    </section>
  );
}
