"use client";

import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";

type ResponderFlowProps = {
  onBack: () => void;
};

type Severity = "low" | "medium" | "high";

type DecodedSOS = {
  message: string;
  filename: string | null;
  severity: Severity;
  severity_reason: string;
  classification_source: "groq" | "rule-based";
};

type ResponderCase = DecodedSOS & {
  case_id: string;
  created_at: string;
};

type CasesResponse = {
  cases: ResponderCase[];
  memory_store: "mongo" | "local-demo";
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8123";

function formatTime(value: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export default function ResponderFlow({ onBack }: ResponderFlowProps) {
  const [file, setFile] = useState<File | null>(null);
  const [decoded, setDecoded] = useState<DecodedSOS | null>(null);
  const [cases, setCases] = useState<ResponderCase[]>([]);
  const [storage, setStorage] = useState<"mongo" | "local-demo" | null>(null);
  const [isDecoding, setIsDecoding] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [removingCaseId, setRemovingCaseId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  async function loadCases() {
    try {
      const response = await fetch(`${API_BASE_URL}/responder/cases`);
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.detail ?? "Aegis could not load responder cases.");
      const result = body as CasesResponse;
      setCases(result.cases);
      setStorage(result.memory_store);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Aegis could not load responder cases.");
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadCases();
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null);
    setDecoded(null);
    setError(null);
    setNotice(null);
  }

  function clearSelection() {
    setFile(null);
    setDecoded(null);
    if (fileInput.current) fileInput.current.value = "";
  }

  async function decodeImage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || isDecoding) return;

    setIsDecoding(true);
    setError(null);
    setNotice(null);
    const formData = new FormData();
    formData.append("image", file);

    try {
      const response = await fetch(`${API_BASE_URL}/responder/decode`, { method: "POST", body: formData });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.detail ?? "Aegis could not decode this image.");
      setDecoded(body as DecodedSOS);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Aegis could not decode this image.");
    } finally {
      setIsDecoding(false);
    }
  }

  async function saveCase() {
    if (!decoded || isSaving) return;

    setIsSaving(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE_URL}/responder/cases`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(decoded),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.detail ?? "Aegis could not save this case.");
      const result = body as { case: ResponderCase; memory_store: "mongo" | "local-demo" };
      setCases((current) => [result.case, ...current].sort((left, right) => {
        const rank = { low: 0, medium: 1, high: 2 };
        return rank[right.severity] - rank[left.severity] || new Date(right.created_at).getTime() - new Date(left.created_at).getTime();
      }));
      setStorage(result.memory_store);
      clearSelection();
      setNotice(result.memory_store === "mongo" ? "Case saved to MongoDB." : "Case saved to local storage.");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Aegis could not save this case.");
    } finally {
      setIsSaving(false);
    }
  }

  async function removeCase(caseId: string) {
    if (removingCaseId) return;
    if (typeof window !== "undefined" && !window.confirm("Remove this responder case? This cannot be undone.")) return;

    setRemovingCaseId(caseId);
    setError(null);
    setNotice(null);
    try {
      const response = await fetch(`${API_BASE_URL}/responder/cases/${caseId}`, { method: "DELETE" });
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.detail ?? "Aegis could not remove this case.");
      setCases((current) => current.filter((item) => item.case_id !== caseId));
      setNotice(body?.deleted ? "Responder case removed." : "That responder case was already removed.");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Aegis could not remove this case.");
    } finally {
      setRemovingCaseId(null);
    }
  }

  return (
    <section className="responder-flow" aria-labelledby="responder-title">
      <button className="back-link" type="button" onClick={onBack}>
        <span aria-hidden="true">&larr;</span> Back to toolkit
      </button>

      <div className="responder-heading">
        <div>
          <p className="eyebrow">Trusted contact workspace</p>
          <h2 id="responder-title">Receive the signal.</h2>
          <p>Upload the original Aegis PNG, reveal its message, and save a case for follow-up.</p>
        </div>
        <div className="responder-beacon" aria-hidden="true"><span /></div>
      </div>

      <div className="responder-grid">
        <form className="responder-upload-card" onSubmit={decodeImage}>
          <div className="responder-card-label"><span>01</span><strong>Decode an SOS image</strong></div>
          <p className="responder-helper">Use the exact PNG shared by the sender. Screenshots and JPEGs cannot reveal the hidden message.</p>
          <label className={`responder-file-picker${file ? " has-file" : ""}`}>
            <input ref={fileInput} type="file" accept="image/png" onChange={chooseFile} />
            <span className="responder-file-icon" aria-hidden="true">↑</span>
            <strong>{file ? file.name : "Choose the original PNG"}</strong>
            <small>{file ? `${Math.round(file.size / 1024)} KB ready to decode` : "PNG files only"}</small>
          </label>
          <button className="responder-primary-button" type="submit" disabled={!file || isDecoding}>
            {isDecoding ? "Reading hidden message..." : "Decode image"}
            {!isDecoding && <span aria-hidden="true">&rarr;</span>}
          </button>
        </form>

        <section className="responder-instructions" aria-label="Responder instructions">
          <p className="eyebrow">How it works</p>
          <h3>A quiet handoff.</h3>
          <ol>
            <li><span>1</span><p><strong>Upload</strong> the untouched PNG.</p></li>
            <li><span>2</span><p><strong>Review</strong> the message and urgency signal.</p></li>
            <li><span>3</span><p><strong>Save</strong> the case for your next step.</p></li>
          </ol>
        </section>
      </div>

      {decoded && (
        <section className="decoded-case-card" aria-live="polite">
          <div className="decoded-case-heading">
            <div>
              <p className="eyebrow">Message revealed</p>
              <h3>Review before saving.</h3>
            </div>
            <span className={`severity-badge severity-${decoded.severity}`}>{decoded.severity} urgency</span>
          </div>
          <blockquote>{decoded.message}</blockquote>
          <p className="severity-reason">{decoded.severity_reason} <span>({decoded.classification_source === "groq" ? "AI-assisted" : "rule-based"})</span></p>
          <div className="decoded-case-actions">
            <button className="responder-primary-button" type="button" onClick={() => void saveCase()} disabled={isSaving}>
              {isSaving ? "Saving case..." : "Save responder case"}
            </button>
            <button className="responder-secondary-button" type="button" onClick={clearSelection}>Remove response</button>
          </div>
        </section>
      )}

      <section className="cases-section" aria-labelledby="cases-title">
        <div className="cases-section-heading">
          <div>
            <p className="eyebrow">Case queue</p>
            <h3 id="cases-title">Recent signals</h3>
          </div>
          <span className="case-storage-badge">{storage === "mongo" ? "MongoDB" : storage === "local-demo" ? "Local storage" : "Loading"}</span>
        </div>
        {cases.length === 0 ? (
          <div className="empty-cases"><span aria-hidden="true">◇</span><p>No responder cases yet. Decoded signals will appear here.</p></div>
        ) : (
          <div className="case-list">
            {cases.map((item) => (
              <article className="case-row" key={item.case_id}>
                <span className={`severity-dot severity-dot-${item.severity}`} aria-label={`${item.severity} urgency`} />
                <div className="case-row-content"><div className="case-row-topline"><strong>{item.severity} urgency</strong><time dateTime={item.created_at}>{formatTime(item.created_at)}</time></div><p>{item.message}</p><small>{item.filename ?? "Aegis SOS image"}</small></div>
                <button className="case-remove-button" type="button" onClick={() => void removeCase(item.case_id)} disabled={removingCaseId === item.case_id} aria-label={`Remove ${item.severity} urgency responder case`}>
                  {removingCaseId === item.case_id ? "Removing..." : "Remove"}
                </button>
              </article>
            ))}
          </div>
        )}
      </section>

      {error && <p className="companion-error" role="alert">{error}</p>}
      {notice && <p className="companion-notice" role="status">{notice}</p>}
      <p className="responder-disclaimer">Responder workspace. Access controls for responder teams can be configured separately.</p>
    </section>
  );
}
