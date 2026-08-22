"use client";

import { FormEvent, useState } from "react";

type LegalFlowProps = {
  onBack: () => void;
};

type Citation = {
  title: string;
  section: string;
  source: string;
  source_url: string;
  relevance: number;
  status: string;
};

type LegalResponse = {
  answer: string;
  answer_source: string;
  in_scope: boolean;
  citations: Citation[];
  retrieval_source: "atlas-vector" | "local-cosine" | "local-corpus" | "not-configured";
  warning: string | null;
};

type LegalMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  response?: LegalResponse;
};

type ContextTurn = {
  role: "user" | "assistant";
  content: string;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8123";

const starterMessage: LegalMessage = {
  id: "legal-welcome",
  role: "assistant",
  text: "Ask me about the India-scoped sources in this workspace. I’ll keep the answer plain and show you exactly where it came from.",
};

const quickQuestions = [
  "What can a protection order do?",
  "What counts as domestic violence?",
  "How can I access free legal aid?",
];

function newMessageId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export default function LegalFlow({ onBack }: LegalFlowProps) {
  const [messages, setMessages] = useState<LegalMessage[]>([starterMessage]);
  const [question, setQuestion] = useState("");
  const [isAsking, setIsAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function askQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanedQuestion = question.trim();
    if (!cleanedQuestion || isAsking) return;

    const contextTurns = messages.slice(-6).map<ContextTurn>(({ role, text }) => ({ role, content: text }));
    setMessages((current) => [...current, { id: newMessageId(), role: "user", text: cleanedQuestion }]);
    setQuestion("");
    setIsAsking(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE_URL}/legal/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: cleanedQuestion, context_turns: contextTurns }),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.detail ?? "Aegis could not answer that question.");
      const legalResponse = body as LegalResponse;
      setMessages((current) => [
        ...current,
        { id: newMessageId(), role: "assistant", text: legalResponse.answer, response: legalResponse },
      ]);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? `${requestError.message} Make sure the backend is running on port 8123.`
          : "Aegis could not reach the legal service.",
      );
    } finally {
      setIsAsking(false);
    }
  }

  function setQuickQuestion(value: string) {
    setQuestion(value);
  }

  return (
    <section className="legal-flow" aria-labelledby="legal-title">
      <button className="back-link" type="button" onClick={onBack}>
        <span aria-hidden="true">&larr;</span> Back to toolkit
      </button>

      <div className="legal-heading">
        <div>
          <p className="eyebrow">India-scoped legal information</p>
          <h2 id="legal-title">Know what the law says.</h2>
          <p>Have a real follow-up conversation about selected domestic-violence protections and official legal-aid routes. Every grounded answer shows its source.</p>
        </div>
        <div className="legal-seal" aria-hidden="true"><span>§</span></div>
      </div>

      <section className="legal-chat-panel" aria-label="Conversation with Aegis Legal">
        <div className="legal-chat-topbar">
          <div className="companion-status"><span className="companion-status-dot" aria-hidden="true" />Source-grounded conversation</div>
          <span className="legal-chat-scope">India only</span>
        </div>

        <div className="legal-chat-messages" data-lenis-prevent aria-live="polite">
          {messages.map((message) => (
            <div className={`chat-row chat-row-${message.role}`} key={message.id}>
              {message.role === "assistant" && <span className="chat-avatar legal-chat-avatar" aria-hidden="true">§</span>}
              <div className={`chat-bubble chat-bubble-${message.role} legal-chat-bubble`}>
                <p>{message.text}</p>
                {message.response && (
                  <>
                    <span className={`legal-inline-status ${message.response.in_scope ? "is-grounded" : "is-limited"}`}>
                      {message.response.in_scope ? "Grounded in official sources" : "Outside current sources"}
                    </span>
                    {message.response.citations.length > 0 && (
                      <div className="legal-chat-citations">
                        {message.response.citations.map((citation, index) => (
                          <a href={citation.source_url} target="_blank" rel="noreferrer" key={`${citation.source_url}-${citation.section}`}>
                            <strong>Source {index + 1} · {citation.section}</strong><small>{citation.source}{citation.status ? ` · ${citation.status}` : ""}</small>
                          </a>
                        ))}
                      </div>
                    )}
                    {message.response.warning && <small className="legal-chat-warning">{message.response.warning}</small>}
                  </>
                )}
              </div>
            </div>
          ))}
          {isAsking && (
            <div className="chat-row chat-row-assistant" aria-label="Aegis Legal is searching official sources">
              <span className="chat-avatar legal-chat-avatar" aria-hidden="true">§</span>
              <div className="chat-bubble chat-bubble-assistant legal-typing"><span /><span /><span /></div>
            </div>
          )}
        </div>

        {messages.length === 1 && (
          <div className="legal-quick-questions" aria-label="Suggested questions">
            {quickQuestions.map((value) => <button type="button" key={value} onClick={() => setQuickQuestion(value)}>{value}</button>)}
          </div>
        )}

        <form className="legal-composer" onSubmit={askQuestion}>
          <label className="sr-only" htmlFor="legal-question">Ask Aegis Legal</label>
          <textarea
            id="legal-question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Ask a legal question or follow up..."
            maxLength={1_200}
            rows={2}
            disabled={isAsking}
          />
          <button type="submit" disabled={isAsking || !question.trim()}>{isAsking ? "Searching..." : "Ask"}<span aria-hidden="true">&uarr;</span></button>
        </form>
      </section>

      {error && <p className="companion-error" role="alert">{error}</p>}
      <p className="legal-disclaimer">Aegis provides general information, not legal advice. Laws, procedures, and eligibility depend on facts and jurisdiction.</p>
    </section>
  );
}
