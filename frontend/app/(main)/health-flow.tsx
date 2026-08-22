"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

type HealthFlowProps = {
  onBack: () => void;
};

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  source?: "gemini" | "groq" | "ollama" | "context-guided";
};

type HealthResponse = {
  reply: string;
  reply_source: "gemini" | "groq" | "ollama" | "context-guided";
  warning: string | null;
};

type ContextTurn = {
  role: "user" | "assistant";
  content: string;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8123";

const starterMessage: ChatMessage = {
  id: "health-welcome",
  role: "assistant",
  text: "Ask me directly about your body, sex, periods, contraception, pregnancy, symptoms, or anything intimate. I’ll answer plainly and without judgment.",
};

function newMessageId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export default function HealthFlow({ onBack }: HealthFlowProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([starterMessage]);
  const [draft, setDraft] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const messageList = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messageList.current?.scrollTo({ top: messageList.current.scrollHeight, behavior: "smooth" });
  }, [messages, isSending]);

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanedDraft = draft.trim();
    if (!cleanedDraft || isSending) return;

    setError(null);
    setNotice(null);
    setDraft("");
    setIsSending(true);
    setMessages((current) => [...current, { id: newMessageId(), role: "user", text: cleanedDraft }]);

    try {
      const response = await fetch(`${API_BASE_URL}/health/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: cleanedDraft,
          context_turns: messages.slice(-6).map<ContextTurn>(({ role, text }) => ({ role, content: text })),
        }),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.detail ?? "The health assistant could not respond just now.");

      const healthResponse = body as HealthResponse;
      setMessages((current) => [
        ...current,
        { id: newMessageId(), role: "assistant", text: healthResponse.reply, source: healthResponse.reply_source },
      ]);
      if (healthResponse.warning) setNotice(healthResponse.warning);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? `${requestError.message} Make sure the backend is running on port 8123.`
          : "The health assistant could not reach the backend.",
      );
    } finally {
      setIsSending(false);
    }
  }

  return (
    <section className="health-flow" aria-labelledby="health-title">
      <button className="back-link" type="button" onClick={onBack}>
        <span aria-hidden="true">&larr;</span> Back to toolkit
      </button>

      <div className="health-heading">
        <div>
          <p className="eyebrow">Aegis Health</p>
          <h2 id="health-title">Ask without embarrassment.</h2>
          <p>Direct, private health information for intimate questions, symptoms, and everyday decisions.</p>
        </div>
        <div className="health-seal" aria-hidden="true">✚</div>
      </div>

      <aside className="health-boundary" role="note">
        <strong>Plain information, not a diagnosis.</strong>
        <span>If someone has severe symptoms or is in immediate danger, seek urgent medical help.</span>
      </aside>

      <section className="health-panel" aria-label="Conversation with Aegis Health">
        <div className="health-panel-topbar">
          <div className="health-status"><span className="health-status-dot" aria-hidden="true" /> Online first · offline fallback</div>
          <span className="health-scope-badge">Judgment-free</span>
        </div>

        <div className="health-messages" ref={messageList} data-lenis-prevent aria-live="polite">
          {messages.map((message) => (
            <div className={`chat-row chat-row-${message.role}`} key={message.id}>
              {message.role === "assistant" && <span className="chat-avatar health-chat-avatar" aria-hidden="true">+</span>}
              <div className={`chat-bubble chat-bubble-${message.role} health-chat-bubble`}>
                <p>{message.text}</p>
                {message.source && (
                  <span className="chat-source">
                    Aegis Health · {message.source === "gemini" ? "Gemini" : message.source === "groq" ? "online fallback" : message.source === "ollama" ? "offline Ollama" : "offline health guidance"}
                  </span>
                )}
              </div>
            </div>
          ))}
          {isSending && (
            <div className="chat-row chat-row-assistant" aria-label="Aegis Health is thinking">
              <span className="chat-avatar health-chat-avatar" aria-hidden="true">+</span>
              <div className="chat-bubble chat-bubble-assistant chat-typing"><span /><span /><span /></div>
            </div>
          )}
        </div>

        <form className="health-composer" onSubmit={sendMessage}>
          <label className="sr-only" htmlFor="health-message">Ask Aegis Health</label>
          <textarea
            id="health-message"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Ask your question plainly..."
            maxLength={2_000}
            rows={2}
            disabled={isSending}
          />
          <button type="submit" disabled={isSending || !draft.trim()}>{isSending ? "Thinking..." : "Ask"}<span aria-hidden="true">&uarr;</span></button>
        </form>
      </section>

      {error && <p className="health-error" role="alert">{error}</p>}
      {notice && <p className="health-notice" role="status">{notice}</p>}
      <p className="health-disclaimer">Aegis Health provides general information. It does not replace a qualified doctor or emergency service.</p>
    </section>
  );
}
