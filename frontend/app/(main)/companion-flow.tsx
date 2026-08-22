"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import LiveCompanionVoice from "./live-companion-voice";

type CompanionFlowProps = {
  onBack: () => void;
};

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  source?: "gemini" | "groq" | "ollama" | "local-fallback" | "safety-guided" | "context-guided";
};

type CompanionResponse = {
  reply: string;
  reply_source: "gemini" | "groq" | "ollama" | "local-fallback" | "safety-guided" | "context-guided";
  urgent_support: boolean;
  urgent_support_message: string | null;
  memory_saved: boolean;
  memory_store: "mongo" | "local-demo" | "not-saved";
  warning: string | null;
};

type CompanionSummaryResponse = {
  summary: string;
  source: "groq" | "local-fallback";
  warning: string | null;
};

type ContextTurn = {
  role: "user" | "assistant";
  content: string;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8123";

const starterMessage: ChatMessage = {
  id: "welcome",
  role: "assistant",
  text: "You don't have to explain everything perfectly. What is happening for you right now?",
};

function newMessageId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function createSessionId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `aegis-${newMessageId()}`;
}

function buildVoiceContext(messages: ChatMessage[]) {
  const relevantMessages = messages.filter((message) => message.id !== "welcome").slice(-10);
  if (!relevantMessages.length) return "No previous text chat context was provided.";

  return relevantMessages
    .map((message) => `${message.role === "user" ? "User" : "Aegis"}: ${message.text}`)
    .join("\n")
    .slice(-4_000);
}

async function copyTextToClipboard(text: string) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textArea = document.createElement("textarea");
  textArea.value = text;
  textArea.style.position = "fixed";
  textArea.style.opacity = "0";
  document.body.appendChild(textArea);
  textArea.focus();
  textArea.select();
  const copied = document.execCommand("copy");
  textArea.remove();

  if (!copied) throw new Error("Clipboard access is not available in this browser.");
}

export default function CompanionFlow({ onBack }: CompanionFlowProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([starterMessage]);
  const [draft, setDraft] = useState("");
  const [memoryConsent, setMemoryConsent] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isVoiceOpen, setIsVoiceOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [urgentMessage, setUrgentMessage] = useState<string | null>(null);
  const [isSummaryGenerating, setIsSummaryGenerating] = useState(false);
  const [isSummaryCopied, setIsSummaryCopied] = useState(false);
  const sessionId = useRef("");
  const messageList = useRef<HTMLDivElement>(null);

  useEffect(() => {
    return () => {
      if (typeof window !== "undefined") window.speechSynthesis?.cancel();
    };
  }, []);

  useEffect(() => {
    messageList.current?.scrollTo({ top: messageList.current.scrollHeight, behavior: "smooth" });
  }, [messages, isSending]);

  function speak(text: string) {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) {
      setNotice("Read-aloud is not available in this browser.");
      return;
    }

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.9;
    utterance.pitch = 1;
    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);
    setIsSpeaking(true);
    window.speechSynthesis.speak(utterance);
  }

  function stopSpeaking() {
    window.speechSynthesis?.cancel();
    setIsSpeaking(false);
  }

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanedDraft = draft.trim();
    if (!cleanedDraft || isSending) return;

    if (!sessionId.current) sessionId.current = createSessionId();
    setError(null);
    setNotice(null);
    setUrgentMessage(null);
    setDraft("");
    setIsSending(true);
    setMessages((currentMessages) => [
      ...currentMessages,
      { id: newMessageId(), role: "user", text: cleanedDraft },
    ]);

    try {
      const response = await fetch(`${API_BASE_URL}/companion/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId.current,
          message: cleanedDraft,
          memory_consent: memoryConsent,
          context_turns: messages.slice(-6).map<ContextTurn>(({ role, text }) => ({ role, content: text })),
        }),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(body?.detail ?? "Aegis could not respond just now.");
      }

      const companionResponse = body as CompanionResponse;
      setMessages((currentMessages) => [
        ...currentMessages,
        {
          id: newMessageId(),
          role: "assistant",
          text: companionResponse.reply,
          source: companionResponse.reply_source,
        },
      ]);
      setUrgentMessage(companionResponse.urgent_support_message);
      if (companionResponse.warning) setNotice(companionResponse.warning);
      if (companionResponse.memory_saved) {
        setNotice(
          companionResponse.memory_store === "mongo"
            ? "Memory is on. Recent turns are saved only to keep this conversation coherent."
            : "Memory is on for this session and will clear when the backend restarts.",
        );
      }
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? `${requestError.message} Make sure the backend is running on port 8123.`
          : "Aegis could not reach the backend. Make sure it is running on port 8123.",
      );
    } finally {
      setIsSending(false);
    }
  }

  async function clearMemory() {
    setError(null);
    setNotice(null);
    if (!sessionId.current) {
      setNotice("There is no saved memory in this chat yet.");
      return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/companion/sessions/${sessionId.current}`, {
        method: "DELETE",
      });
      if (!response.ok) throw new Error("Aegis could not clear the saved memory.");
      setMemoryConsent(false);
      setNotice("Saved companion memory was cleared.");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Aegis could not clear saved memory.");
    }
  }

  async function copySessionSummary() {
    setError(null);
    setNotice(null);
    const userMessages = messages
      .filter((message) => message.role === "user" && message.text.trim())
      .map((message) => message.text.trim());

    if (!userMessages.length) {
      setNotice("Share something about your situation first, then Aegis can prepare a summary.");
      return;
    }

    setIsSummaryGenerating(true);
    try {
      const response = await fetch(`${API_BASE_URL}/companion/summary`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_messages: userMessages }),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.detail ?? "Aegis could not create the session summary.");

      const summaryResponse = body as CompanionSummaryResponse;
      await copyTextToClipboard(summaryResponse.summary);
      setIsSummaryCopied(true);
      setNotice(
        summaryResponse.source === "groq"
          ? "Groq created the summary and copied it. Paste it into the Email Support or Trusted Caller situation field."
          : "Groq was unavailable, so a local factual summary was copied instead. Paste it into the Email Support or Trusted Caller situation field.",
      );
      window.setTimeout(() => setIsSummaryCopied(false), 2_000);
    } catch (copyError) {
      setError(
        copyError instanceof Error
          ? `${copyError.message} Make sure the backend is running on port 8123.`
          : "Aegis could not create or copy the session summary.",
      );
    } finally {
      setIsSummaryGenerating(false);
    }
  }

  const lastAssistantMessage = [...messages].reverse().find((message) => message.role === "assistant");

  return (
    <section className="companion-flow" aria-labelledby="companion-title">
      <button className="back-link" type="button" onClick={onBack}>
        <span aria-hidden="true">&larr;</span> Back to toolkit
      </button>

      <div className="companion-heading">
        <div>
          <p className="eyebrow">A calm companion</p>
          <h2 id="companion-title">A little room to breathe.</h2>
          <p>Talk through what is on your mind. Aegis offers grounding support, not medical or legal advice.</p>
        </div>
      </div>

      <section className="companion-panel" aria-label="Conversation with Aegis">
        <div className="companion-panel-topbar">
          <div>
            <div className="companion-status">
              <span className="companion-status-dot" aria-hidden="true" />
              Here with you
            </div>
            <p className="companion-voice-hint">You can also talk with Aegis live.</p>
          </div>
          <div className="companion-panel-actions">
            <button className="live-companion-launch" type="button" onClick={() => setIsVoiceOpen(true)} disabled={isVoiceOpen}>
              Start live voice
            </button>
            <button
              className="listen-button"
              type="button"
              onClick={() => (isSpeaking ? stopSpeaking() : lastAssistantMessage && speak(lastAssistantMessage.text))}
              disabled={!lastAssistantMessage}
            >
              {isSpeaking ? "Stop reading" : "Read aloud"}
            </button>
          </div>
        </div>

        {isVoiceOpen && (
          <LiveCompanionVoice chatSummary={buildVoiceContext(messages)} onClose={() => setIsVoiceOpen(false)} />
        )}

        {urgentMessage && (
          <aside className="urgent-support" aria-live="assertive">
            <strong>Immediate support</strong>
            <p>{urgentMessage}</p>
            <div>
              <a href="tel:112">Call 112</a>
              <a href="tel:181">Women&apos;s helpline 181</a>
              <a href="https://112.gov.in/" target="_blank" rel="noreferrer">India emergency support</a>
            </div>
          </aside>
        )}

        <div className="companion-messages" ref={messageList} data-lenis-prevent aria-live="polite">
          {messages.map((message) => (
            <div className={`chat-row chat-row-${message.role}`} key={message.id}>
              {message.role === "assistant" && <span className="chat-avatar" aria-hidden="true">A</span>}
              <div className={`chat-bubble chat-bubble-${message.role}`}>
                <p>{message.text}</p>
                {message.role === "assistant" && message.source && (
                  <span className="chat-source">
                    {message.source === "gemini"
                      ? "Aegis response · Gemini"
                      : message.source === "groq"
                        ? "Aegis response · fallback"
                        : message.source === "ollama"
                          ? "Aegis response · offline Ollama"
                      : message.source === "safety-guided"
                        ? "Safety-guided response"
                        : message.source === "context-guided"
                          ? "Context-guided response"
                          : "Aegis response · local fallback"}
                  </span>
                )}
              </div>
            </div>
          ))}
          {isSending && (
            <div className="chat-row chat-row-assistant" aria-label="Aegis is thinking">
              <span className="chat-avatar" aria-hidden="true">A</span>
              <div className="chat-bubble chat-bubble-assistant chat-typing"><span /><span /><span /></div>
            </div>
          )}
        </div>

        <form className="companion-composer" onSubmit={sendMessage}>
          <label className="sr-only" htmlFor="companion-message">Message Aegis</label>
          <textarea
            id="companion-message"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Share what is on your mind..."
            maxLength={1_600}
            rows={2}
            disabled={isSending}
          />
          <button type="submit" disabled={isSending || !draft.trim()}>
            {isSending ? "Sending..." : "Send"}
            {!isSending && <span aria-hidden="true">&uarr;</span>}
          </button>
        </form>

        <div className="companion-session-actions">
          <div>
            <button
              className="companion-summary-button"
              type="button"
              onClick={copySessionSummary}
              disabled={isSending || isSummaryGenerating || !messages.some((message) => message.role === "user")}
            >
              {isSummaryGenerating ? "Preparing summary..." : isSummaryCopied ? "Summary copied" : "Copy session summary"}
              <span aria-hidden="true">&rarr;</span>
            </button>
            <small>Groq turns your messages into a clear handoff summary that you can paste into Email Support or Trusted Caller.</small>
          </div>
        </div>
      </section>

      <section className="memory-control" aria-label="Companion memory settings">
        <label className="memory-toggle">
          <input
            type="checkbox"
            checked={memoryConsent}
            onChange={(event) => setMemoryConsent(event.target.checked)}
          />
          <span className="memory-toggle-track" aria-hidden="true"><span /></span>
          <span>
            <strong>Remember this conversation</strong>
            <small>
              {memoryConsent
                ? "Aegis may use recent turns to keep this chat coherent."
                : "Off by default. New messages are not saved by the backend."}
            </small>
          </span>
        </label>
        <button className="clear-memory-button" type="button" onClick={clearMemory}>Clear saved memory</button>
      </section>

      {error && <p className="companion-error" role="alert">{error}</p>}
      {notice && <p className="companion-notice" role="status">{notice}</p>}

      <p className="companion-disclaimer">
        Aegis is not an emergency service, therapist, doctor, or legal advisor. If you are in immediate danger in India, call 112.
      </p>
    </section>
  );
}
