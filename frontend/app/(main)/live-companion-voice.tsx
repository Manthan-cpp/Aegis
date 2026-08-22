"use client";

import { useEffect, useRef, useState } from "react";
import { WebSession, type SessionStatus } from "@omnidim-ai/client";

type LiveCompanionVoiceProps = {
  chatSummary: string;
  onClose: () => void;
};

type WebVoiceSessionResponse = {
  ws_url: string;
  session_id: number | string | null;
  expires_at: string | null;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8123";

function apiErrorMessage(detail: unknown, fallback: string) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const firstMessage = detail.find(
      (item): item is { msg: string } =>
        typeof item === "object" && item !== null && "msg" in item && typeof item.msg === "string",
    );
    if (firstMessage) return firstMessage.msg;
  }
  if (
    typeof detail === "object" &&
    detail !== null &&
    "message" in detail &&
    typeof detail.message === "string"
  ) {
    return detail.message;
  }
  return fallback;
}

function statusText(status: SessionStatus) {
  if (status === "connecting") return "Connecting to Aegis voice companion";
  if (status === "active") return "Live companion conversation";
  if (status.reason === "not_started") return "Preparing a private browser conversation";
  if (status.reason === "stopped") return "Conversation ended";
  if (status.reason === "insufficient_balance") return "OmniDimension balance or account limit reached";
  if (status.reason === "connection_lost") return "Connection lost — conversation ended";
  return `Conversation ended: ${status.reason}`;
}

export default function LiveCompanionVoice({ chatSummary, onClose }: LiveCompanionVoiceProps) {
  const [status, setStatus] = useState<SessionStatus>({ state: "ended", reason: "not_started" });
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const sessionRef = useRef<WebSession | null>(null);

  const isBusy = status === "connecting";
  const isLive = status === "active";

  useEffect(() => {
    let isMounted = true;

    function handleStatus(nextStatus: SessionStatus) {
      if (!isMounted) return;
      setStatus(nextStatus);
      if (typeof nextStatus === "object" && nextStatus.state === "ended" && nextStatus.reason !== "not_started") {
        setNotice(nextStatus.reason === "stopped" ? "The live conversation has ended." : statusText(nextStatus));
      }
    }

    async function startSession() {
      setError(null);
      setNotice(null);
      setStatus("connecting");

      try {
        const response = await fetch(`${API_BASE_URL}/voice/companion-session`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            chat_summary: chatSummary || "No previous text chat context was provided.",
            language: "English/Hindi",
          }),
        });
        const body = await response.json().catch(() => null);
        if (!response.ok) {
          throw new Error(apiErrorMessage(body?.detail, "Aegis could not start the live voice conversation."));
        }
        if (!isMounted) return;

        const sessionDetails = body as WebVoiceSessionResponse;
        const session = new WebSession();
        sessionRef.current = session;
        session.on("status", handleStatus);
        session.on("error", (sessionError) => {
          if (isMounted) setError(sessionError.message);
        });
        await session.start({ wsUrl: sessionDetails.ws_url });
      } catch (requestError) {
        sessionRef.current?.stop();
        sessionRef.current = null;
        if (!isMounted) return;
        setStatus({ state: "ended", reason: "start_failed" });
        setError(
          requestError instanceof Error
            ? `${requestError.message} Make sure the backend is running on port 8123.`
            : "Aegis could not start the live voice conversation.",
        );
      }
    }

    void startSession();

    return () => {
      isMounted = false;
      sessionRef.current?.stop();
      sessionRef.current = null;
    };
  }, [chatSummary]);

  function endConversation() {
    sessionRef.current?.stop();
    sessionRef.current = null;
    setStatus({ state: "ended", reason: "stopped" });
    onClose();
  }

  return (
    <section className="live-companion-voice" aria-label="Live voice conversation with Aegis">
      <div className="live-companion-voice-topbar">
        <div className="companion-status">
          <span className={`companion-status-dot${isLive ? " is-live" : ""}`} aria-hidden="true" />
          {statusText(status)}
        </div>
        <button className="live-companion-end" type="button" onClick={endConversation}>
          {isBusy ? "Cancel" : "End conversation"}
        </button>
      </div>

      <div className={`live-companion-stage${isLive ? " is-live" : ""}`}>
        <div className="live-companion-orb" aria-hidden="true">
          <span className="live-companion-orb-core" />
          <span className="live-companion-orb-ring live-companion-orb-ring-one" />
          <span className="live-companion-orb-ring live-companion-orb-ring-two" />
        </div>
        <p className="live-companion-stage-title">
          {isLive ? "I’m listening" : isBusy ? "Getting things ready…" : "Voice conversation"}
        </p>
        <p className="live-companion-stage-note">
          Speak naturally and interrupt when you need to. Use headphones or a quiet setting only if that is safe for you.
        </p>
      </div>

      <p className="live-companion-note">
        This is a live browser conversation, not a phone call. Audio is streamed to the configured voice agent for this session;
        it is not sent to the text-chat endpoint.
      </p>

      {error && <p className="companion-error" role="alert">{error}</p>}
      {notice && !error && <p className="companion-notice" role="status">{notice}</p>}
    </section>
  );
}
