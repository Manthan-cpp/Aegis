"use client";

import { FormEvent, useEffect, useState } from "react";
import Image from "next/image";
import { canShareSOSImage, canShareSOSMessage, shareSOSImage, shareSOSMessage } from "./sos-share";

type SOSFlowProps = {
  onBack: () => void;
};

type SOSResponse = {
  message: string;
  theme: string;
  image_data_url: string;
  cover_source: "pollinations" | "local-fallback";
  expansion_source: "groq" | "local-fallback";
  warning: string | null;
  encoded_bytes: number;
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8123";

const themes = [
  { value: "flower", label: "Flower", note: "soft and ordinary" },
  { value: "landscape", label: "Landscape", note: "quiet and natural" },
  { value: "food", label: "Food", note: "casual and familiar" },
  { value: "coffee", label: "Coffee", note: "everyday and warm" },
  { value: "sunset", label: "Sunset", note: "peaceful and simple" },
] as const;

function prettySource(source: SOSResponse["cover_source"] | SOSResponse["expansion_source"]) {
  return source === "local-fallback" ? "local fallback" : source;
}

function dataUrlToBlob(dataUrl: string): Blob {
  const [header, encoded] = dataUrl.split(",", 2);
  const mimeType = header.match(/^data:([^;]+);base64$/i)?.[1] ?? "image/png";
  const binary = window.atob(encoded ?? "");
  const bytes = new Uint8Array(binary.length);

  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }

  return new Blob([bytes], { type: mimeType });
}

export default function SosFlow({ onBack }: SOSFlowProps) {
  const [keywords, setKeywords] = useState("");
  const [theme, setTheme] = useState<(typeof themes)[number]["value"]>("flower");
  const [customMessage, setCustomMessage] = useState("");
  const [result, setResult] = useState<SOSResponse | null>(null);
  const [generatedImageBlob, setGeneratedImageBlob] = useState<Blob | null>(null);
  const [supportsFileShare, setSupportsFileShare] = useState(false);
  const [supportsTextShare, setSupportsTextShare] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      setSupportsFileShare(canShareSOSImage());
      setSupportsTextShare(canShareSOSMessage());
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);

  async function generateSOS(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    setResult(null);
    setGeneratedImageBlob(null);
    setCustomMessage("");
    setIsGenerating(true);

    try {
      const response = await fetch(`${API_BASE_URL}/sos/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ keywords: keywords.trim(), theme }),
      });
      const body = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(body?.detail ?? "Aegis could not prepare the SOS image.");
      }

      const sosResult = body as SOSResponse;
      setResult(sosResult);
      setGeneratedImageBlob(dataUrlToBlob(sosResult.image_data_url));
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? `${requestError.message} Make sure the backend is running on port 8123.`
          : "Aegis could not reach the backend. Make sure it is running on port 8123.",
      );
    } finally {
      setIsGenerating(false);
    }
  }

  function saveImage() {
    if (!result) return;
    const link = document.createElement("a");
    link.href = result.image_data_url;
    link.download = "aegis-sos.png";
    link.click();
    setNotice("Saved as a PNG. Keep this exact file for decoding later.");
  }

  async function sendViaSMS() {
    if (!generatedImageBlob) return;

    try {
      const outcome = await shareSOSImage(generatedImageBlob);
      if (outcome === "shared") {
        setNotice("Choose Messages in the share sheet, then select the trusted contact. Keep the PNG unchanged.");
      } else if (outcome === "downloaded") {
        setNotice("File sharing is unavailable here. The original PNG was downloaded; attach it manually in Messages.");
      }
    } catch {
      setNotice("Sharing was unavailable here. Use Save image and attach the original PNG manually in Messages.");
    }
  }

  async function sendCustomMessage() {
    if (!customMessage.trim()) {
      setNotice("Write a custom message first.");
      return;
    }

    try {
      const outcome = await shareSOSMessage(customMessage);
      if (outcome === "shared") {
        setNotice("Choose Messages in the share sheet, then select the trusted contact.");
      } else if (outcome === "copied") {
        setNotice("This browser cannot open the share sheet. Your message was copied; open Messages and paste it.");
      }
    } catch (shareError) {
      setNotice(shareError instanceof Error ? shareError.message : "Text sharing was unavailable here.");
    }
  }

  return (
    <section className="sos-flow" aria-labelledby="sos-title">
      <button className="back-link" type="button" onClick={onBack}>
        <span aria-hidden="true">←</span> Back to toolkit
      </button>

      <div className="sos-heading">
        <div>
          <p className="eyebrow">Discreet SOS</p>
          <h2 id="sos-title">Prepare a private message.</h2>
          <p>
            Use a few ordinary words. Aegis will turn them into a clear message
            and hide it inside a normal-looking PNG image.
          </p>
        </div>
        <div className="sos-step-badge">Step 1 of 2</div>
      </div>

      <form className="sos-form" onSubmit={generateSOS}>
        <label className="sos-label" htmlFor="sos-keywords">
          What do you want your trusted contact to know?
        </label>
        <textarea
          id="sos-keywords"
          className="sos-textarea"
          value={keywords}
          onChange={(event) => setKeywords(event.target.value)}
          placeholder="help, locked in, scared"
          maxLength={240}
          required
          rows={3}
        />
        <div className="sos-field-footer">
          <span>Short words are enough. The AI expansion keeps to the facts you provide.</span>
          <span>{keywords.length}/240</span>
        </div>

        <fieldset className="theme-picker">
          <legend className="sos-label">Choose an ordinary cover</legend>
          <div className="theme-options">
            {themes.map((option) => (
              <label className={`theme-option${theme === option.value ? " is-selected" : ""}`} key={option.value}>
                <input
                  type="radio"
                  name="cover-theme"
                  value={option.value}
                  checked={theme === option.value}
                  onChange={() => setTheme(option.value)}
                />
                <span className="theme-option-dot" aria-hidden="true" />
                <span>
                  <strong>{option.label}</strong>
                  <small>{option.note}</small>
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        <button className="sos-generate-button" type="submit" disabled={isGenerating || !keywords.trim()}>
          {isGenerating ? "Preparing your image..." : "Create discreet image"}
          {!isGenerating && <span aria-hidden="true">→</span>}
        </button>
      </form>

      {error && <p className="sos-error" role="alert">{error}</p>}

      {result && (
        <section className="sos-result" aria-labelledby="sos-result-title">
          <div className="sos-result-heading">
            <div>
              <p className="eyebrow">Ready to share</p>
              <h3 id="sos-result-title">Your message is hidden.</h3>
            </div>
            <span className="sos-success-mark" aria-hidden="true">✓</span>
          </div>

          <div className="sos-result-grid">
            <div className="sos-preview-wrap">
              <Image className="sos-preview" src={result.image_data_url} alt={`A ${result.theme} cover image containing a hidden message`} width={640} height={420} unoptimized />
              <span className="sos-preview-caption">Looks ordinary. Carries your message.</span>
            </div>
            <div className="sos-message-panel">
              <p className="sos-label">Expanded message</p>
              <blockquote>{result.message}</blockquote>
              <div className="sos-meta-grid">
                <span>Cover: <strong>{prettySource(result.cover_source)}</strong></span>
                <span>Message: <strong>{prettySource(result.expansion_source)}</strong></span>
              </div>
              <label className="sos-label sos-custom-message-label" htmlFor="sos-custom-message">
                Custom message (optional)
              </label>
              <textarea
                id="sos-custom-message"
                className="sos-textarea"
                value={customMessage}
                onChange={(event) => setCustomMessage(event.target.value)}
                placeholder="Write the message you want to send..."
                maxLength={500}
                rows={3}
              />
              <div className="sos-field-footer sos-custom-message-footer">
                <span>Only your words are shared.</span>
                <span>{customMessage.length}/500</span>
              </div>
              <div className="sos-actions">
                <button className="sos-secondary-button" type="button" onClick={saveImage}>Save image</button>
                <button className="sos-secondary-button" type="button" onClick={sendViaSMS}>Share</button>
                <button className="sos-primary-button" type="button" onClick={sendViaSMS}>Send via SMS</button>
                <button className="sos-primary-button" type="button" onClick={sendCustomMessage} disabled={!customMessage.trim()}>
                  Send custom message
                </button>
              </div>
              <p className="sos-share-support-note">
                {supportsFileShare
                  ? "On a phone, Send via SMS opens the native share sheet. Choose Messages to send the image as MMS."
                  : "This browser will download the PNG so you can attach it manually in Messages."}
                {supportsTextShare
                  ? " Custom messages use the same share sheet."
                  : " Custom messages will be copied so you can paste them into Messages."}
              </p>
            </div>
          </div>

          {result.warning && <p className="sos-warning">{result.warning}</p>}
          {notice && <p className="sos-notice" role="status">{notice}</p>}

          <p className="sos-integrity-note">
            Keep this exact PNG file. Screenshots, JPEG conversion, resizing, and
            social-media re-compression can erase the hidden message.
          </p>
        </section>
      )}
    </section>
  );
}
