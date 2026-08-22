"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

type EmailAlertFlowProps = {
  onBack: () => void;
};

type RecipientType = "trusted" | "women_support";

type EmailAlertResponse = {
  queued: boolean;
  sent: boolean;
  job_id: string;
  status: "queued" | "sending" | "sent";
  recipient_type: RecipientType;
  recipient_label: string;
  demo_mode: boolean;
};

type EmailQueueStatus = {
  job_id: string;
  status: "queued" | "sending" | "sent";
  sent: boolean;
  attempts: number;
  recipient_type?: RecipientType;
  recipient_label?: string;
  demo_mode?: boolean;
};

type EmailPayload = {
  recipient_type: RecipientType;
  client_request_id: string;
  trusted_email: string | null;
  user_name: string;
  location: string | null;
  situation: string | null;
  instructions: string | null;
  chat_summary: string | null;
  confirmation: boolean;
};

type OfflineOutboxEntry = {
  payload: EmailPayload;
  created_at: string;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8123";
const OFFLINE_EMAIL_OUTBOX_KEY = "aegis.email.outbox.v1";

function readableError(body: unknown, fallback: string) {
  if (typeof body === "string" && body.trim()) return body;
  if (body && typeof body === "object") {
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) => (item && typeof item === "object" ? (item as { msg?: unknown }).msg : item))
        .filter((item): item is string => typeof item === "string" && Boolean(item.trim()));
      if (messages.length) return messages.join(" ");
    }
    const message = (body as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) return message;
  }
  return fallback;
}

function newClientRequestId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `email-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
}

function readOfflineOutbox(): OfflineOutboxEntry[] {
  if (typeof window === "undefined") return [];
  try {
    const parsed = JSON.parse(window.localStorage.getItem(OFFLINE_EMAIL_OUTBOX_KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeOfflineOutbox(entries: OfflineOutboxEntry[]) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(OFFLINE_EMAIL_OUTBOX_KEY, JSON.stringify(entries));
}

async function submitEmailToBackend(payload: EmailPayload): Promise<EmailAlertResponse> {
  const response = await fetch(`${API_BASE_URL}/email/send`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(readableError(body, "Aegis could not queue the email."));
  return body as EmailAlertResponse;
}

export default function EmailAlertFlow({ onBack }: EmailAlertFlowProps) {
  const [recipientType, setRecipientType] = useState<RecipientType>("trusted");
  const [trustedEmail, setTrustedEmail] = useState("");
  const [userName, setUserName] = useState("");
  const [location, setLocation] = useState("");
  const [situation, setSituation] = useState("");
  const [instructions, setInstructions] = useState("");
  const [chatSummary, setChatSummary] = useState("");
  const [confirmation, setConfirmation] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [offlineQueueCount, setOfflineQueueCount] = useState(() => readOfflineOutbox().length);
  const flushingOutbox = useRef(false);

  const refreshOfflineQueueCount = useCallback(() => {
    setOfflineQueueCount(readOfflineOutbox().length);
  }, []);

  const watchQueuedEmail = useCallback(async (jobId: string, demoMode: boolean) => {
    for (let attempt = 0; attempt < 20; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 3_000));
      try {
        const response = await fetch(`${API_BASE_URL}/email/queue/${encodeURIComponent(jobId)}`);
        if (!response.ok) return;
        const status = (await response.json()) as EmailQueueStatus;
        if (status.sent) {
          setNotice(
            demoMode
              ? "Your email was sent to the configured Aegis inbox."
              : "Your help email was sent successfully.",
          );
          return;
        }
        setNotice("Your help email is safely queued. Aegis is waiting for a connection and will retry automatically.");
      } catch {
        // The backend may be temporarily unreachable too. The queue remains
        // on the backend or in the browser outbox; do not turn this into a failure.
        return;
      }
    }
  }, []);

  const flushOfflineOutbox = useCallback(async () => {
    if (flushingOutbox.current) return;
    const entries = readOfflineOutbox();
    if (!entries.length) {
      refreshOfflineQueueCount();
      return;
    }

    flushingOutbox.current = true;
    try {
      const remaining: OfflineOutboxEntry[] = [];
      for (const entry of entries) {
        try {
          const result = await submitEmailToBackend(entry.payload);
          if (result.status !== "sent") {
            void watchQueuedEmail(result.job_id, result.demo_mode);
          } else {
            setNotice("A queued help email was sent successfully.");
          }
        } catch {
          remaining.push(entry);
        }
      }
      writeOfflineOutbox(remaining);
      setOfflineQueueCount(remaining.length);
    } finally {
      flushingOutbox.current = false;
    }
  }, [refreshOfflineQueueCount, watchQueuedEmail]);

  useEffect(() => {
    const retry = () => { void flushOfflineOutbox(); };
    window.addEventListener("online", retry);
    const interval = window.setInterval(retry, 5_000);
    return () => {
      window.removeEventListener("online", retry);
      window.clearInterval(interval);
    };
  }, [flushOfflineOutbox, refreshOfflineQueueCount]);

  async function sendEmail(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanedName = userName.trim();
    const cleanedSituation = situation.trim();
    const cleanedSummary = chatSummary.trim();

    if (!cleanedName || (!cleanedSituation && !cleanedSummary) || !confirmation || isSending) return;

    setError(null);
    setNotice(null);
    setIsSending(true);

    const payload: EmailPayload = {
      recipient_type: recipientType,
      client_request_id: newClientRequestId(),
      trusted_email: recipientType === "trusted" ? trustedEmail.trim() : null,
      user_name: cleanedName,
      location: location.trim() || null,
      situation: cleanedSituation || null,
      instructions: instructions.trim() || null,
      chat_summary: cleanedSummary || null,
      confirmation,
    };

    try {
      const result = await submitEmailToBackend(payload);
      setNotice(
        result.status === "sent"
          ? (result.demo_mode ? "Your email was sent to the configured Aegis inbox." : "Your help email was sent successfully.")
          : "Your help email is safely queued. It will be sent automatically when EmailJS is reachable.",
      );
      if (result.status !== "sent") void watchQueuedEmail(result.job_id, result.demo_mode);
      setConfirmation(false);
    } catch (requestError) {
      if (requestError instanceof TypeError && requestError.message.toLowerCase().includes("fetch")) {
        const entries = readOfflineOutbox();
        if (!entries.some((entry) => entry.payload.client_request_id === payload.client_request_id)) {
          entries.push({ payload, created_at: new Date().toISOString() });
          writeOfflineOutbox(entries);
        }
        setOfflineQueueCount(entries.length);
        setNotice("There is no connection right now. Your help email is saved on this device and will be sent automatically when connection returns.");
        setConfirmation(false);
      } else {
        setError(requestError instanceof Error ? requestError.message : "Aegis could not queue the email.");
      }
    } finally {
      setIsSending(false);
    }
  }

  const canSend = Boolean(
    userName.trim() &&
      (situation.trim() || chatSummary.trim()) &&
      confirmation &&
      (recipientType === "women_support" || trustedEmail.trim()),
  );

  return (
    <section className="email-alert-flow" aria-labelledby="email-alert-title">
      <button className="back-link" type="button" onClick={onBack} disabled={isSending}>
        <span aria-hidden="true">&larr;</span> Back to toolkit
      </button>

      <div className="email-alert-heading">
        <div>
          <p className="eyebrow">Aegis help email</p>
          <h2 id="email-alert-title">Put the important details in one place.</h2>
          <p>Send a clear, consented summary to someone who may be able to help. You choose exactly what to include.</p>
        </div>
        <div className="email-alert-orb" aria-hidden="true"><span>✉</span></div>
      </div>

      <form className="email-alert-panel" onSubmit={sendEmail}>
        <div className="email-alert-panel-topbar">
          <div>
            <div className="companion-status"><span className="companion-status-dot" aria-hidden="true" /> Email help request</div>
            <p>Choose the recipient before you prepare the message.</p>
          </div>
          <div className="email-alert-topbar-badges">
            {offlineQueueCount > 0 && <span className="email-alert-queue-badge">{offlineQueueCount} saved offline</span>}
          </div>
        </div>

        <div className="email-alert-recipient" role="group" aria-label="Email recipient">
          <button
            className={recipientType === "trusted" ? "is-selected" : ""}
            type="button"
            onClick={() => { setRecipientType("trusted"); setNotice(null); setError(null); }}
            disabled={isSending}
          >
            Trusted person
            <small>Use an email you enter</small>
          </button>
          <button
            className={recipientType === "women_support" ? "is-selected" : ""}
            type="button"
            onClick={() => { setRecipientType("women_support"); setNotice(null); setError(null); }}
            disabled={isSending}
          >
            Women&apos;s support inbox
            <small>Routes to the configured support inbox</small>
          </button>
        </div>

        <div className="email-alert-form-grid">
          <label>
            Your name <span>*</span>
            <input value={userName} onChange={(event) => setUserName(event.target.value)} placeholder="e.g. Aisha" maxLength={120} disabled={isSending} required />
          </label>
          {recipientType === "trusted" && (
            <label>
              Trusted person&apos;s email <span>*</span>
              <input type="email" value={trustedEmail} onChange={(event) => setTrustedEmail(event.target.value)} placeholder="trusted@example.com" maxLength={254} disabled={isSending} required />
            </label>
          )}
          <label>
            Location <small>optional</small>
            <input value={location} onChange={(event) => setLocation(event.target.value)} placeholder="e.g. Near home" maxLength={240} disabled={isSending} />
          </label>
          <label className="email-alert-wide-field">
            Situation <small>required unless you add a chat summary</small>
            <textarea value={situation} onChange={(event) => setSituation(event.target.value)} placeholder="What should the recipient know?" maxLength={2_000} rows={4} disabled={isSending} />
          </label>
          <label>
            Specific instructions <small>optional</small>
            <textarea value={instructions} onChange={(event) => setInstructions(event.target.value)} placeholder="Ask them to reply if they can help." maxLength={800} rows={3} disabled={isSending} />
          </label>
          <label>
            Chat summary <small>optional</small>
            <textarea value={chatSummary} onChange={(event) => setChatSummary(event.target.value)} placeholder="Short factual summary from an Aegis chat." maxLength={4_000} rows={3} disabled={isSending} />
          </label>
        </div>

        <label className="email-alert-confirmation">
          <input type="checkbox" checked={confirmation} onChange={(event) => setConfirmation(event.target.checked)} disabled={isSending} />
          <span className="email-alert-check" aria-hidden="true">✓</span>
          <span>I have checked the details and want Aegis to send this email.</span>
        </label>

        <div className="email-alert-actions">
          <button className="email-alert-send" type="submit" disabled={!canSend || isSending}>
            {isSending ? "Sending email..." : "Send help email"}
            {!isSending && <span aria-hidden="true">&rarr;</span>}
          </button>
          <button className="email-alert-clear" type="button" onClick={() => { setSituation(""); setInstructions(""); setChatSummary(""); setNotice(null); setError(null); }} disabled={isSending}>
            Clear message
          </button>
        </div>
        <p className="email-alert-note">Email is not an emergency channel. Share only what is safe, especially if your device or messages are monitored.</p>
      </form>

      {error && <p className="companion-error" role="alert">{error}</p>}
      {notice && <p className="companion-notice" role="status">{notice}</p>}

      <p className="companion-disclaimer">Aegis is not an emergency service. If someone is in immediate danger in India, call 112 when it is safe to do so.</p>
    </section>
  );
}
