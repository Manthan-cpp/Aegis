"""Grounded legal answer generation for the India-scoped official corpus."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Literal

from groq import Groq

from services.gemini_client import generate_gemini_text
from services.legal_search import LegalChunk, chunk_is_relevant
from services.ollama_client import generate_ollama_text, ollama_enabled


DEFAULT_MODEL = "llama-3.3-70b-versatile"
OUT_OF_SCOPE_REPLY = (
    "I could not find an official India-scoped provision in Aegis's current legal library "
    "that answers that question. I will not invent a section or procedure. "
    "Try adding the conduct, relationship, location, timing, or whether the person is under 18."
)


@dataclass(frozen=True)
class LegalAnswer:
    text: str
    source: str
    citations: list[LegalChunk]
    warning: str | None = None


SYSTEM_PROMPT = """You are Aegis Legal, an India-scoped legal information assistant.
Answer only from the source excerpts provided in the user message. Do not use
outside knowledge, fill gaps, predict outcomes, or invent section numbers.
The recent conversation is only for understanding a follow-up question; it is not
evidence and must never override the source excerpts.
Treat a source marked current as current legislation and a source marked
historical as historical context. The Indian Penal Code is historical in this
library; for a current criminal-law question, prefer the current BNS/BNSS
excerpts when they are supplied and say when an IPC section is only an older
reference.
Explain this is general legal information, not legal advice, when useful.
Never tell the person that a crime definitely occurred or that a court will grant
relief. Use cautious language such as “the cited provision says” and “a lawyer or
legal-aid service can assess the facts.”

Conversation style:
- Start with the direct answer in plain language; do not start with a disclaimer.
- Explain only the one to three provisions that answer the question.
- Use a short paragraph or two short bullets when that makes the answer clearer.
- If the question is personal, separate what the provision says from what depends
  on facts. Ask one clarifying question only when it would change the explanation.
- For self-defence questions, answer directly when the supplied provisions cover
  them. Distinguish an immediate assault from revenge, retaliation, or a plan to
  attack someone later; explain the necessity and proportionality limits. Do not
  provide tactics for killing, ambushing, or incapacitating anyone.
- For sexual-abuse or sexual-assault questions, do not go silent and do not
  classify the report yourself. Explain plainly which supplied provisions may be
  relevant, including domestic-violence protections and any supplied BNS sexual
  offence provisions, then state what depends on facts such as consent, conduct,
  relationship, age, injury, and timing. Mention urgent safety or medical help
  only when the question describes an ongoing or immediate threat.
- A request for legal information about rape, sexual assault, protection,
  reporting, evidence, or justice is an allowed request. Do not refuse merely
  because the subject is sexual violence or a crime. Answer from the supplied
  official excerpts in plain language; avoid graphic detail and do not invent
  facts about the person asking.
- For confinement, being locked in, threats, verbal abuse, emotional abuse or
  controlling conduct, explain the supplied domestic-violence and/or wrongful-
  confinement provisions plainly. Do not say "outside sources" merely because
  the user did not use the statute's exact words.
- For kidnapping, abduction, being held against one's will, or assault after being
  taken, answer directly from the supplied BNS provisions on kidnapping,
  abduction, aggravated detention, hurt, and the supplied BNSS reporting route.
  Do not replace those provisions with unrelated evidence, theft, or property
  offences merely because a section number is similar.
- When supplied official support routes are relevant, distinguish emergency
  response (112), women-support information (181), and legal aid (NALSA 15100).
  Do not claim that any service has been contacted or that a result is assured.
- When two or more supplied sources genuinely apply, use separate citations for
  the separate legal points. Do not cite only Source 1 by habit.
- Do not refuse merely because a question mentions death or violence if the source
  excerpts answer the legal issue. State the legal limit plainly and then explain
  what depends on the facts.
- Do not repeat the same disclaimer or say “according to the sources” in every line.
- Cite each legal claim with [Source 1], [Source 2], etc. Use only markers that
  exist in the supplied excerpts.
- If the excerpts do not answer the latest question, reply exactly: OUT_OF_SCOPE.
The latest question controls. If it is a vague follow-up such as “I don’t get it,”
explain the immediately previous substantive legal answer; do not switch to an
older topic from the conversation.
Keep the answer under 180 words."""


def _context(chunks: list[LegalChunk]) -> str:
    return "\n\n".join(
        f"[Source {index}] {chunk.title} — {chunk.section}\n"
        f"Status: {chunk.status or 'not specified'}\n{chunk.text}\nOfficial source: {chunk.source_url}"
        for index, chunk in enumerate(chunks, start=1)
    )


def _conversation_context(history: list[dict[str, str]]) -> str:
    if not history:
        return "No earlier conversation."
    return "\n".join(
        f"{turn['role'].title()}: {turn['content']}"
        for turn in history[-6:]
        if turn.get("role") in {"user", "assistant"} and turn.get("content")
    )


def _citation_numbers(text: str) -> set[int]:
    return {int(value) for value in re.findall(r"\[Source\s+(\d+)\]", text, flags=re.IGNORECASE)}


def _section_number(chunk: LegalChunk) -> int:
    match = re.match(r"(?:sections?|sec\.?)[\s-]*(\d+)", chunk.section.casefold())
    return int(match.group(1)) if match else 0


def _prioritize_relevant_chunks(query: str, chunks: list[LegalChunk]) -> list[LegalChunk]:
    """Keep the model's context legally coherent when several sources match."""

    normalized = query.casefold()
    sexual_query = bool(
        re.search(r"\b(?:sexual|rape|raped|assault|abuse|consent|forced\s+sex)\b", query.casefold())
    )
    kidnapping_query = bool(re.search(
        r"\b(?:kidnap(?:ping|ped)?|abduct(?:ed|ion|ing)?|held\s+against\s+my\s+will|taken\s+by\s+force)\b",
        normalized,
    ))
    if not sexual_query and not kidnapping_query:
        return chunks

    rape_query = bool(re.search(r"\b(?:rape|raped)\b", normalized))

    def priority(chunk: LegalChunk) -> int:
        title = chunk.title.casefold()
        number = _section_number(chunk)
        if kidnapping_query:
            if "bharatiya nyaya sanhita" in title:
                if number in {115, 117, 118, 130, 131, 135}:
                    return {117: 120, 118: 118, 115: 116, 135: 108, 131: 106, 130: 104}[number]
                if number in {140, 137, 138, 142}:
                    return {140: 125, 137: 123, 138: 121, 142: 110}[number]
                return 8
            if "bharatiya nagarik suraksha sanhita" in title:
                return {173: 114, 193: 110, 175: 106}.get(number, 18)
            if "nalsa" in title or "legal services" in title:
                return 98
            if "bharatiya sakshya adhiniyam" in title:
                return 5
            return 10
        if "bharatiya nyaya sanhita" in title:
            if rape_query:
                return {64: 119, 63: 117, 65: 115, 70: 113, 67: 111, 68: 109, 69: 107, 74: 96, 75: 94}.get(number, 20)
            return {75: 112, 74: 110, 76: 108, 63: 106, 67: 104, 68: 102, 69: 100, 70: 98, 85: 90, 86: 88}.get(number, 20)
        if "bharatiya nagarik suraksha sanhita" in title:
            return {173: 116, 184: 114, 176: 112, 183: 110, 175: 108, 193: 106}.get(number, 30)
        if "protection of women from domestic violence" in title:
            return {3: 120, 5: 116, 12: 114, 18: 112, 19: 110, 20: 108, 22: 106, 23: 104}.get(number, 80)
        if "nalsa" in title or "legal services" in title:
            return 102 if re.search(r"\b(?:justice|legal|protection|help|aid)\b", normalized) else 45
        if "bharatiya sakshya adhiniyam" in title:
            return 35 if re.search(r"\b(?:evidence|proof|message|recording|digital|electronic)\b", normalized) else 5
        return 10

    return sorted(chunks, key=lambda chunk: (priority(chunk), chunk.score), reverse=True)[:5]


def _grounded_fallback(chunks: list[LegalChunk], query: str = "") -> str:
    normalized = query.casefold()
    rape_query = bool(re.search(r"\b(?:rape|raped)\b", normalized))
    kidnapping_query = bool(re.search(
        r"\b(?:kidnap(?:ping|ped)?|abduct(?:ed|ion|ing)?|held\s+against\s+my\s+will|taken\s+by\s+force)\b",
        normalized,
    ))
    sexual_query = bool(re.search(r"\b(?:sexual|rape|raped|assault|abuse|consent)\b", normalized))
    if kidnapping_query:
        lines = ["For a report of kidnapping or forcible abduction with assault in India, the supplied official sources point to these legal routes:"]
    elif rape_query:
        lines = ["For a rape report in India, the supplied official sources point to these legal routes:"]
    elif sexual_query:
        lines = ["For a sexual-abuse or sexual-assault question, these supplied official provisions may be relevant:"]
    else:
        lines = ["These supplied official provisions are relevant to the question:"]

    fallback_limit = 5 if kidnapping_query else (4 if rape_query else 3)
    for index, chunk in enumerate(chunks[:fallback_limit], start=1):
        title = chunk.title.casefold()
        number = _section_number(chunk)
        if kidnapping_query and "bharatiya nyaya sanhita" in title and number == 137:
            summary = "BNS Section 137 defines kidnapping and provides punishment for kidnapping from India or from lawful guardianship; whether it applies depends on the facts, including how the person was taken."
        elif kidnapping_query and "bharatiya nyaya sanhita" in title and number == 138:
            summary = "BNS Section 138 defines abduction as compelling a person by force or inducing the person by deceitful means to go from a place."
        elif kidnapping_query and "bharatiya nyaya sanhita" in title and number == 140:
            summary = "BNS Section 140 covers aggravated kidnapping or abduction, including detention with threats of death or hurt, ransom, secret wrongful confinement, or danger of grievous hurt; the exact subsection depends on the facts."
        elif kidnapping_query and "bharatiya nyaya sanhita" in title and number == 142:
            summary = "BNS Section 142 addresses knowingly concealing or keeping a kidnapped or abducted person in confinement."
        elif kidnapping_query and "bharatiya nyaya sanhita" in title and number == 115:
            summary = "BNS Section 115 concerns voluntarily causing hurt; the provision and punishment depend on the injury and the facts proved."
        elif kidnapping_query and "bharatiya nyaya sanhita" in title and number == 117:
            summary = "BNS Section 117 concerns voluntarily causing grievous hurt, with more serious consequences where the injury meets the statutory definition."
        elif kidnapping_query and "bharatiya nyaya sanhita" in title and number == 118:
            summary = "BNS Section 118 covers voluntarily causing hurt or grievous hurt by dangerous weapons or other listed dangerous means."
        elif kidnapping_query and "bharatiya nagarik suraksha sanhita" in title and number == 173:
            summary = "BNSS Section 173 covers giving information about a cognizable offence, including oral or electronic reporting, receiving a free copy, and escalation if the information is not recorded."
        elif kidnapping_query and "bharatiya nagarik suraksha sanhita" in title and number == 193:
            summary = "BNSS Section 193 concerns the police report after investigation; the investigating agency records the result and sends the report through the procedure stated there."
        elif rape_query and "bharatiya nyaya sanhita" in title and number == 63:
            summary = "BNS Section 63 defines rape by specified sexual acts carried out against a woman's will, without consent, or in other listed circumstances; the facts and consent question must be assessed in the case."
        elif rape_query and "bharatiya nyaya sanhita" in title and number == 64:
            summary = "BNS Section 64 provides the punishment provision for rape, including the ordinary offence and aggravated circumstances listed in the section."
        elif rape_query and "bharatiya nyaya sanhita" in title and number == 65:
            summary = "BNS Section 65 addresses rape of a girl under sixteen or under twelve and provides the aggravated punishments stated there."
        elif rape_query and "bharatiya nagarik suraksha sanhita" in title and number == 173:
            summary = "BNSS Section 173 covers information about a cognizable offence, including oral or electronic reporting, a free copy of the recorded information, and escalation to the Superintendent of Police or Magistrate if recording is refused."
        elif rape_query and "bharatiya nagarik suraksha sanhita" in title and number == 176:
            summary = "BNSS Section 176 says that, in a rape investigation, the victim's statement should as far as practicable be recorded by a woman police officer at her residence or a place of her choice."
        elif rape_query and "bharatiya nagarik suraksha sanhita" in title and number == 184:
            summary = "BNSS Section 184 covers medical examination of a rape victim, including consent, examination by a registered medical practitioner, and forwarding the report to the investigating officer."
        elif "nalsa" in title or "legal services" in title:
            summary = "The official legal-aid source says women can seek free legal assistance through the Taluk, District, or State Legal Services Authority and lists the NALSA helpline 15100."
        else:
            summary = re.sub(r"^##[^\n]*\n?", "", chunk.text.strip())
            summary = " ".join(summary.split())
            if len(summary) > 210:
                summary = f"{summary[:207].rstrip()}..."
        if "bharatiya nyaya sanhita" in title:
            label = f"BNS Section {number}"
        elif "bharatiya nagarik suraksha sanhita" in title:
            label = f"BNSS Section {number}"
        elif "bharatiya sakshya adhiniyam" in title:
            label = f"BSA Section {number}"
        elif number:
            label = f"{chunk.title.split('—', 1)[0].strip()} Section {number}"
        else:
            label = chunk.section.split("—", 1)[0].strip()
        lines.append(f"• {label}: {summary} [Source {index}]")
    lines.append("This is general legal information, not a finding about the facts or a guarantee of outcome; a lawyer or free legal-aid service can help with the next step.")
    return "\n\n".join(lines)


def generate_legal_answer(
    query: str,
    chunks: list[LegalChunk],
    retrieval_source: str,
    history: list[dict[str, str]] | None = None,
) -> LegalAnswer:
    relevant = _prioritize_relevant_chunks(query, [chunk for chunk in chunks if chunk_is_relevant(chunk)])
    if not relevant:
        return LegalAnswer(text=OUT_OF_SCOPE_REPLY, source="out-of-scope", citations=[])

    recent_history = history or []
    user_prompt = (
        f"Latest question: {query.strip()}\n\n"
        f"Recent conversation (context only, not evidence):\n{_conversation_context(recent_history)}\n\n"
        f"Source excerpts:\n{_context(relevant)}"
    )

    def interpret_answer(raw_answer: str, provider: str) -> LegalAnswer | None:
        answer = " ".join(raw_answer.split()).strip()
        refusal_phrases = (
            "i can't help", "i cannot help", "i can't answer", "i cannot answer",
            "unable to answer", "not able to answer", "outside my scope",
            "outside current sources", "i won't answer",
        )
        if not answer or answer.upper() == "OUT_OF_SCOPE" or any(phrase in answer.casefold() for phrase in refusal_phrases):
            # Do not stop the provider chain here. A temporary model refusal or
            # empty answer should give the next configured provider a chance;
            # only the final fallback should be called source-guided.
            return None
        citation_numbers = _citation_numbers(answer)
        if not citation_numbers or not citation_numbers.issubset(set(range(1, len(relevant) + 1))):
            return None
        # Keep the full ordered list so [Source N] markers remain aligned with
        # the source cards displayed by the frontend. The model may cite only
        # the controlling source when the other retrieved provisions do not add
        # anything to that particular answer.
        return LegalAnswer(text=answer[:1_500], source=f"{provider}-{retrieval_source}", citations=relevant)

    gemini_error: Exception | None = None
    if os.getenv("GEMINI_API_KEY", "").strip():
        for attempt in range(2):
            try:
                retry_instruction = ""
                if attempt:
                    retry_instruction = (
                        "\n\nRewrite the answer. Your previous draft was rejected because it was empty, refused, or lacked valid citation markers. "
                        "Answer the latest question directly from the supplied excerpts, and put [Source N] after every legal claim. "
                        "Do not return OUT_OF_SCOPE when the excerpts contain a relevant provision."
                    )
                generated = generate_gemini_text(
                    system_instruction=SYSTEM_PROMPT,
                    prompt=user_prompt + retry_instruction,
                    temperature=0.1,
                    max_output_tokens=260,
                )
                interpreted = interpret_answer(generated, "gemini")
                if interpreted is not None:
                    return interpreted
                gemini_error = RuntimeError("Gemini draft failed Aegis legal citation checks")
            except Exception as error:  # noqa: BLE001 - Groq/retrieval fallback keeps legal help available.
                gemini_error = error

    groq_error: Exception | None = None
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if api_key:
        try:
            response = Groq(api_key=api_key).chat.completions.create(
                model=os.getenv("GROQ_MODEL", DEFAULT_MODEL),
                temperature=0.1,
                max_tokens=260,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
            interpreted = interpret_answer(response.choices[0].message.content or "", "groq")
            if interpreted is not None:
                if gemini_error and interpreted.warning is None:
                    return LegalAnswer(
                        text=interpreted.text,
                        source=interpreted.source,
                        citations=interpreted.citations,
                        warning=f"Gemini was unavailable, so Aegis used Groq as a fallback ({type(gemini_error).__name__}).",
                    )
                return interpreted
            groq_error = RuntimeError("Groq draft failed Aegis legal citation checks")
        except Exception as error:  # noqa: BLE001 - continue to the optional local provider.
            groq_error = error

    ollama_error: Exception | None = None
    if ollama_enabled():
        try:
            generated = generate_ollama_text(
                system_instruction=SYSTEM_PROMPT,
                prompt=user_prompt,
                temperature=0.1,
                max_output_tokens=260,
            )
            interpreted = interpret_answer(generated, "ollama")
            if interpreted is not None:
                warning = "Offline local model used with the retrieved official excerpts. Verify current law with a qualified lawyer."
                return LegalAnswer(
                    text=interpreted.text,
                    source=interpreted.source,
                    citations=interpreted.citations,
                    warning=warning,
                )
        except Exception as error:
            # Keep the final warning accurate when the local model is unavailable.
            ollama_error = error
        else:
            ollama_error = RuntimeError("Ollama draft failed Aegis legal citation checks")

    if not api_key:
        warning = (
            f"Gemini was unavailable ({type(gemini_error).__name__})."
            if gemini_error
            else "No online AI key is configured."
        )
        return LegalAnswer(
            text=_grounded_fallback(relevant, query),
            source="retrieval-guided",
            citations=relevant,
            warning=warning,
        )

    failures = [
        name
        for name, error in (
            ("Gemini", gemini_error),
            ("Groq", groq_error),
            ("Ollama", ollama_error),
        )
        if error is not None
    ]
    provider = f"{', '.join(failures)} could not produce a cited answer; Aegis used the retrieved official sources directly." if failures else "Aegis used the retrieved official sources directly."
    return LegalAnswer(
        text=_grounded_fallback(relevant, query),
        source="retrieval-guided",
        citations=relevant,
        warning=provider,
    )
