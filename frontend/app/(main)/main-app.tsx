"use client";

import { useEffect, useState } from "react";

import AuthControls from "./auth-controls";
import CompanionFlow from "./companion-flow";
import EmailAlertFlow from "./email-alert-flow";
import LegalFlow from "./legal-flow";
import HealthFlow from "./health-flow";
import ResponderFlow from "./responder-flow";
import SosFlow from "./sos-flow";
import TrustedCallerFlow from "./trusted-caller-flow";
import DirectMessagesFlow from "./direct-messages-flow";
import MotionProvider from "../../components/motion/motion-provider";
import { TextReveal } from "../../components/motion/reveal";

type MainAppProps = {
  onPanicExit: () => void;
};

type ToolId = "home" | "sos" | "companion" | "legal" | "responder" | "caller" | "email" | "health" | "messages";
type NavGroup = "chatbots" | "sos" | null;

function ShieldMark() {
  return (
    <svg aria-hidden="true" className="aegis-mark" viewBox="0 0 40 44" fill="none">
      <path d="M20 2.5 35 8v10.8c0 10.1-6.1 18.8-15 22.7C11.1 37.6 5 28.9 5 18.8V8l15-5.5Z" fill="currentColor" opacity=".15" />
      <path d="M20 2.5 35 8v10.8c0 10.1-6.1 18.8-15 22.7C11.1 37.6 5 28.9 5 18.8V8l15-5.5Z" stroke="currentColor" strokeWidth="2.2" />
      <path d="m13.2 21.3 4.2 4.2 9.5-10" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.8" />
    </svg>
  );
}

export default function MainApp({ onPanicExit }: MainAppProps) {
  const [activeTool, setActiveTool] = useState<ToolId>("home");
  const [isNavOpen, setIsNavOpen] = useState(false);
  const [expandedGroup, setExpandedGroup] = useState<NavGroup>(null);

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "instant" });
  }, [activeTool]);

  useEffect(() => {
    document.body.classList.toggle("aegis-menu-open", isNavOpen);
    return () => document.body.classList.remove("aegis-menu-open");
  }, [isNavOpen]);

  function goTo(tool: ToolId) {
    setActiveTool(tool);
    setIsNavOpen(false);
    setExpandedGroup(null);
  }

  function toggleGroup(group: Exclude<NavGroup, null>) {
    setExpandedGroup((current) => current === group ? null : group);
  }

  return (
    <MotionProvider>
      <main className="aegis-stage">
        <div className="aegis-glow aegis-glow-one" aria-hidden="true" />
        <div className="aegis-glow aegis-glow-two" aria-hidden="true" />

        <section className="aegis-app" data-active-tool={activeTool} aria-label="Aegis safety companion">
          <header className="aegis-header">
            <div className="aegis-brand">
              <ShieldMark />
              <div>
                <p className="eyebrow">Private safety space</p>
                <h1>Aegis</h1>
              </div>
            </div>

            <button
              className={`aegis-menu-button${isNavOpen ? " is-open" : ""}`}
              type="button"
              onClick={() => setIsNavOpen((open) => !open)}
              aria-label={isNavOpen ? "Close navigation" : "Open navigation"}
              aria-expanded={isNavOpen}
              aria-controls="aegis-navigation"
            >
              <span aria-hidden="true" />
              <span aria-hidden="true" />
              <span aria-hidden="true" />
            </button>
          </header>

          <nav id="aegis-navigation" className={`aegis-nav${isNavOpen ? " is-open" : ""}`} aria-label="Aegis navigation" aria-hidden={!isNavOpen}>
            <div className="aegis-nav-heading">
              <p className="eyebrow">Aegis navigation</p>
              <h2>What do you need<br />right now?</h2>
              <p>Choose a quiet path. You can return here at any time.</p>
            </div>

            <div className="aegis-nav-list">
              <button className={`aegis-nav-button${activeTool === "home" ? " is-active" : ""}`} type="button" onClick={() => goTo("home")}>
                <span><small>01</small> Home</span><b aria-hidden="true">↗</b>
              </button>

              <div className={`aegis-nav-group${expandedGroup === "chatbots" ? " is-expanded" : ""}`}>
                <button className="aegis-nav-button aegis-nav-group-button" type="button" onClick={() => toggleGroup("chatbots")} aria-expanded={expandedGroup === "chatbots"} aria-controls="chatbot-submenu">
                  <span><small>02</small> Chatbots</span><b aria-hidden="true">{expandedGroup === "chatbots" ? "−" : "+"}</b>
                </button>
                <div id="chatbot-submenu" className="aegis-nav-submenu" aria-hidden={expandedGroup !== "chatbots"}>
                  <button className={`aegis-nav-subbutton${activeTool === "companion" ? " is-active" : ""}`} type="button" onClick={() => goTo("companion")}><span className="nav-sub-icon">✦</span> Emotional support</button>
                  <button className={`aegis-nav-subbutton${activeTool === "legal" ? " is-active" : ""}`} type="button" onClick={() => goTo("legal")}><span className="nav-sub-icon">§</span> Legal support</button>
                  <button className={`aegis-nav-subbutton${activeTool === "health" ? " is-active" : ""}`} type="button" onClick={() => goTo("health")}><span className="nav-sub-icon">＋</span> Health support</button>
                </div>
              </div>

              <div className={`aegis-nav-group${expandedGroup === "sos" ? " is-expanded" : ""}`}>
                <button className="aegis-nav-button aegis-nav-group-button is-sos" type="button" onClick={() => toggleGroup("sos")} aria-expanded={expandedGroup === "sos"} aria-controls="sos-submenu">
                  <span><small>03</small> SOS</span><b aria-hidden="true">{expandedGroup === "sos" ? "−" : "+"}</b>
                </button>
                <div id="sos-submenu" className="aegis-nav-submenu" aria-hidden={expandedGroup !== "sos"}>
                  <button className={`aegis-nav-subbutton${activeTool === "sos" ? " is-active" : ""}`} type="button" onClick={() => goTo("sos")}><span className="nav-sub-icon">♡</span> Send SOS message</button>
                  <button className={`aegis-nav-subbutton${activeTool === "responder" ? " is-active" : ""}`} type="button" onClick={() => goTo("responder")}><span className="nav-sub-icon">↗</span> Decode an SOS message</button>
                </div>
              </div>

              <button className={`aegis-nav-button${activeTool === "messages" ? " is-active" : ""}`} type="button" onClick={() => goTo("messages")}>
                <span><small>04</small> Private messages</span><b aria-hidden="true">↗</b>
              </button>
              <button className={`aegis-nav-button${activeTool === "caller" ? " is-active" : ""}`} type="button" onClick={() => goTo("caller")}>
                <span><small>05</small> Call a trusted person</span><b aria-hidden="true">↗</b>
              </button>
              <button className={`aegis-nav-button${activeTool === "email" ? " is-active" : ""}`} type="button" onClick={() => goTo("email")}>
                <span><small>06</small> Email support</span><b aria-hidden="true">↗</b>
              </button>
            </div>

            <div className="aegis-nav-footer">
              <AuthControls />
              <button className="panic-button" type="button" onClick={onPanicExit}>
                <span className="panic-dot" aria-hidden="true" />
                Quick exit
                <span className="panic-key">Esc</span>
              </button>
            </div>
          </nav>

          {activeTool !== "home" && (
            <div className="aegis-view-shell" data-motion-route key={activeTool}>
              {activeTool === "sos" && <SosFlow onBack={() => setActiveTool("home")} />}
              {activeTool === "companion" && <CompanionFlow onBack={() => setActiveTool("home")} />}
              {activeTool === "email" && <EmailAlertFlow onBack={() => setActiveTool("home")} />}
              {activeTool === "legal" && <LegalFlow onBack={() => setActiveTool("home")} />}
              {activeTool === "health" && <HealthFlow onBack={() => setActiveTool("home")} />}
              {activeTool === "responder" && <ResponderFlow onBack={() => setActiveTool("home")} />}
              {activeTool === "caller" && <TrustedCallerFlow onBack={() => setActiveTool("home")} />}
              {activeTool === "messages" && <DirectMessagesFlow onBack={() => setActiveTool("home")} />}
            </div>
          )}

          {activeTool === "home" && (
            <div className="aegis-view-shell aegis-home-view" data-motion-route key="home">
              <section className="landing-hero" aria-labelledby="landing-title">
                <div className="landing-hero-copy" data-motion-intro id="landing-title">
                  <p className="eyebrow">A private place to begin again</p>
                  <TextReveal as="h2" className="aegis-hero-title">When the world feels unsafe,<br /><em>you still deserve a quiet place.</em></TextReveal>
                  <p className="landing-hero-lede">Aegis brings calm conversation, clear rights information, and discreet ways to reach someone you trust into one gentle space.</p>
                  <div className="landing-hero-actions">
                    <button className="landing-primary-button" type="button" onClick={() => goTo("companion")}>Start with support <span aria-hidden="true">→</span></button>
                  </div>
                </div>
                <div className="landing-hero-art" aria-label="A calm Aegis presence">
                  <div className="landing-art-orbit landing-art-orbit-one" />
                  <div className="landing-art-orbit landing-art-orbit-two" />
                  <div className="landing-art-core"><ShieldMark /></div>
                  <span className="landing-art-note">quiet<br />is a form<br />of safety</span>
                </div>
              </section>

              <section className="landing-section landing-how" id="how-it-works" aria-labelledby="how-title">
                <div className="landing-section-intro">
                  <p className="eyebrow">How it works</p>
                  <h3 id="how-title">Support that meets you<br /><em>where you are.</em></h3>
                </div>
                <div className="landing-steps" data-motion-stagger>
                  <div className="landing-step" data-motion-item><span className="landing-step-number">01</span><div><h4>Enter quietly</h4><p>Aegis appears as a familiar calculator until you choose to reveal your private space.</p></div></div>
                  <div className="landing-step" data-motion-item><span className="landing-step-number">02</span><div><h4>Find the right support</h4><p>Talk to a companion, understand your rights, ask a health question, or prepare an SOS.</p></div></div>
                  <div className="landing-step" data-motion-item><span className="landing-step-number">03</span><div><h4>Choose your next step</h4><p>Share only what feels safe through an image, email, voice bridge, or private message.</p></div></div>
                </div>
              </section>

              <section className="landing-section landing-features" aria-labelledby="features-title">
                <div className="landing-section-intro landing-feature-intro">
                  <p className="eyebrow">Inside Aegis</p>
                  <h3 id="features-title">A toolkit built around<br /><em>real moments.</em></h3>
                  <p>Every feature has one purpose: to make information, connection, and choice feel a little closer.</p>
                </div>
                <div className="landing-feature-list">
                  <button className="landing-feature-row" type="button" onClick={() => goTo("companion")}><span>01</span><strong>Emotional support</strong><p>A natural conversation when you need someone to listen.</p><b aria-hidden="true">↗</b></button>
                  <button className="landing-feature-row" type="button" onClick={() => goTo("legal")}><span>02</span><strong>Legal clarity</strong><p>India-scoped answers grounded in official sources and sections.</p><b aria-hidden="true">↗</b></button>
                  <button className="landing-feature-row" type="button" onClick={() => goTo("sos")}><span>03</span><strong>Discreet SOS</strong><p>A hidden message inside an ordinary-looking image.</p><b aria-hidden="true">↗</b></button>
                  <button className="landing-feature-row" type="button" onClick={() => goTo("caller")}><span>04</span><strong>Trusted connection</strong><p>Reach someone through a live voice bridge or queued help email.</p><b aria-hidden="true">↗</b></button>
                  <button className="landing-feature-row" type="button" onClick={() => goTo("messages")}><span>05</span><strong>Private messages</strong><p>A quiet line to another signed-in Aegis user, with history preserved.</p><b aria-hidden="true">↗</b></button>
                </div>
              </section>

              <section className="landing-closing" aria-label="Aegis closing message">
                <p className="eyebrow">Your pace. Your choice.</p>
                <h3>You do not have to<br /><em>figure everything out at once.</em></h3>
                <button className="landing-primary-button" type="button" onClick={() => goTo("companion")}>Open your private space <span aria-hidden="true">→</span></button>
              </section>
            </div>
          )}
        </section>
      </main>
    </MotionProvider>
  );
}
