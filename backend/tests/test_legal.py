import os
import unittest
from unittest.mock import patch

os.environ["MONGODB_URI"] = ""

from fastapi.testclient import TestClient  # noqa: E402
from main import app  # noqa: E402
from services.legal_client import OUT_OF_SCOPE_REPLY, generate_legal_answer  # noqa: E402
from services.legal_search import LegalChunk, local_corpus_chunks, search_legal_chunks  # noqa: E402


class LegalApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.chunk = LegalChunk(
            chunk_id="chunk-1",
            title="Protection of Women from Domestic Violence Act, 2005",
            section="Section 18 — protection orders",
            text="Section 18 concerns protection orders.",
            source="India Code",
            source_url="https://www.indiacode.nic.in/",
            score=0.82,
            status="current central legislation",
        )

    def test_grounded_question_returns_citation(self):
        with patch("routers.legal.search_legal_chunks", return_value=([self.chunk], "atlas-vector")), patch(
            "routers.legal.generate_legal_answer",
            return_value=generate_legal_answer("What is a protection order?", [self.chunk], "atlas-vector"),
        ):
            response = self.client.post("/legal/ask", json={"question": "What is a protection order?"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["in_scope"])
        self.assertEqual(response.json()["citations"][0]["section"], "Section 18 — protection orders")

    def test_weak_retrieval_refuses(self):
        weak_chunk = self.chunk.__class__(**{**self.chunk.__dict__, "score": 0.12})
        answer = generate_legal_answer("What is the tax procedure for a company?", [weak_chunk], "local-cosine")
        self.assertEqual(answer.text, OUT_OF_SCOPE_REPLY)
        self.assertEqual(answer.citations, [])

    def test_legal_request_requires_a_question(self):
        response = self.client.post("/legal/ask", json={"question": "?"})
        self.assertEqual(response.status_code, 422)

    def test_follow_up_context_is_accepted(self):
        with patch("routers.legal.search_legal_chunks", return_value=([self.chunk], "atlas-vector")), patch(
            "routers.legal.generate_legal_answer",
            return_value=generate_legal_answer("What about residence rights?", [self.chunk], "atlas-vector"),
        ) as answer_mock:
            response = self.client.post(
                "/legal/ask",
                json={
                    "question": "What about residence rights?",
                    "context_turns": [
                        {"role": "user", "content": "What can a protection order do?"},
                        {"role": "assistant", "content": "It can include several types of relief."},
                    ],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(answer_mock.call_args.args[0], "What about residence rights?")
        self.assertEqual(answer_mock.call_args.args[3][0]["role"], "user")

    def test_invalid_generated_citations_use_a_source_guided_fallback(self):
        fake_response = type(
            "Response",
            (),
            {"choices": [type("Choice", (), {"message": type("Message", (), {"content": "The law says this [Source 99]."})()})()]},
        )()
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GROQ_API_KEY": "test-key", "OLLAMA_ENABLED": "false"}, clear=False), patch(
            "services.legal_client.Groq"
        ) as groq_class:
            groq_class.return_value.chat.completions.create.return_value = fake_response
            answer = generate_legal_answer("What is a protection order?", [self.chunk], "atlas-vector")

        self.assertEqual(answer.source, "retrieval-guided")
        self.assertIn("Section 18", answer.text)

    def test_gemini_generates_a_cited_legal_answer(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "false"}, clear=False), patch(
            "services.legal_client.generate_gemini_text",
            return_value="A protection order can restrict specified acts of domestic violence [Source 1].",
        ):
            answer = generate_legal_answer("What is a protection order?", [self.chunk], "atlas-vector")

        self.assertEqual(answer.source, "gemini-atlas-vector")
        self.assertEqual(len(answer.citations), 1)
        self.assertIn("[Source 1]", answer.text)

    def test_invalid_gemini_draft_allows_groq_to_answer_before_retrieval_fallback(self):
        fake_response = type(
            "Response",
            (),
            {"choices": [type("Choice", (), {"message": type("Message", (), {"content": "A protection order can restrict specified acts [Source 1]."})()})()]},
        )()
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", "GROQ_API_KEY": "test-key", "OLLAMA_ENABLED": "false"}, clear=False), patch(
            "services.legal_client.generate_gemini_text",
            return_value="The answer is unclear.",
        ), patch("services.legal_client.Groq") as groq_class:
            groq_class.return_value.chat.completions.create.return_value = fake_response
            answer = generate_legal_answer("What is a protection order?", [self.chunk], "atlas-vector")

        self.assertEqual(answer.source, "groq-atlas-vector")
        self.assertIn("[Source 1]", answer.text)
        self.assertIn("Gemini was unavailable", answer.warning or "")

    def test_sexual_abuse_retrieves_domestic_violence_and_bns_sources(self):
        chunks, retrieval_source = search_legal_chunks("What if I am sexually abused?")
        sections = {chunk.section for chunk in chunks if chunk.score >= 0.38}

        self.assertEqual(retrieval_source, "local-corpus")
        self.assertTrue(any(section.startswith("Section 3") and "domestic violence" in section.casefold() for section in sections))
        self.assertTrue(
            any(section.startswith("Section 63") or section.startswith("Sections 74") for section in sections)
        )

    def test_generator_does_not_turn_retrieved_sexual_abuse_sources_into_out_of_scope(self):
        chunks, retrieval_source = search_legal_chunks("What if I am sexually abused?")
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "false"}, clear=False), patch(
            "services.legal_client.generate_gemini_text",
            return_value="OUT_OF_SCOPE",
        ):
            answer = generate_legal_answer("What if I am sexually abused?", chunks, retrieval_source)

        self.assertEqual(answer.source, "retrieval-guided")
        self.assertTrue(answer.citations)
        self.assertIn("domestic violence", answer.text.casefold())

    def test_rape_justice_retrieval_prefers_bns_and_bnss_over_same_numbered_evidence_law(self):
        chunks, retrieval_source = search_legal_chunks("I have been raped, and want justice")

        self.assertEqual(retrieval_source, "local-corpus")
        self.assertTrue(chunks[0].section.startswith("Section 64"))
        self.assertTrue(any(chunk.section.startswith("Section 63") for chunk in chunks))
        self.assertTrue(any(chunk.section.startswith("Section 173") for chunk in chunks))
        self.assertTrue(any(chunk.section.startswith("Section 184") for chunk in chunks))
        self.assertFalse(any("Sakshya" in chunk.title for chunk in chunks))

    def test_rape_question_gets_a_grounded_answer_when_gemini_refuses(self):
        chunks, retrieval_source = search_legal_chunks("I have been raped, and want justice")
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "false"}, clear=False), patch(
            "services.legal_client.generate_gemini_text",
            return_value="I can't help with legal questions about rape.",
        ):
            answer = generate_legal_answer("I have been raped, and want justice", chunks, retrieval_source)

        self.assertEqual(answer.source, "retrieval-guided")
        self.assertIn("BNS Section 64", answer.text)
        self.assertIn("BNSS Section 173", answer.text)
        self.assertIn("[Source 1]", answer.text)
        self.assertNotIn("I could not find", answer.text)

    def test_rape_question_prompt_explicitly_requires_an_answer(self):
        chunks, retrieval_source = search_legal_chunks("How can I get legal protection after rape?")
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "false"}, clear=False), patch(
            "services.legal_client.generate_gemini_text",
            return_value="The relevant criminal provision is BNS Section 64 [Source 1].",
        ) as gemini_mock:
            answer = generate_legal_answer("How can I get legal protection after rape?", chunks, retrieval_source)

        self.assertEqual(answer.source, "gemini-local-corpus")
        prompt = gemini_mock.call_args.kwargs["system_instruction"]
        self.assertIn("Do not refuse merely", prompt)
        self.assertIn("sexual violence or a crime", prompt)

    def test_kidnapping_and_assault_retrieval_excludes_unrelated_sections(self):
        chunks, retrieval_source = search_legal_chunks("I was kidnapped yesterday, and then brutally assaulted")
        sections = {chunk.section.casefold() for chunk in chunks}

        self.assertEqual(retrieval_source, "local-corpus")
        self.assertTrue(any("section 140" in section and "kidnapping" in section for section in sections))
        self.assertTrue(any("section 137" in section for section in sections))
        self.assertTrue(any("section 138" in section for section in sections))
        self.assertTrue(any("section 117" in section for section in sections))
        self.assertTrue(any("section 173" in section for section in sections))
        self.assertFalse(any("Sakshya" in chunk.title for chunk in chunks))
        self.assertFalse(any(chunk.section.startswith("Section 303") for chunk in chunks))
        self.assertFalse(any(chunk.section.startswith("Section 101") for chunk in chunks))

    def test_kidnapping_fallback_answers_instead_of_dumping_unrelated_sources(self):
        chunks, retrieval_source = search_legal_chunks("I was kidnapped yesterday, and then brutally assaulted")
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "false"}, clear=False), patch(
            "services.legal_client.generate_gemini_text",
            return_value="I can't answer that reliably from the current sources.",
        ):
            answer = generate_legal_answer("I was kidnapped yesterday, and then brutally assaulted", chunks, retrieval_source)

        self.assertEqual(answer.source, "retrieval-guided")
        self.assertIn("BNS Section 140", answer.text)
        self.assertIn("BNS Section 117", answer.text)
        self.assertIn("BNSS Section 173", answer.text)
        self.assertNotIn("BSA Section 63", answer.text)
        self.assertNotIn("Theft", answer.text)

    def test_vague_legal_follow_up_retrieves_only_the_immediately_previous_topic(self):
        with patch("routers.legal.search_legal_chunks", return_value=([self.chunk], "atlas-vector")) as search_mock, patch(
            "routers.legal.generate_legal_answer",
            return_value=generate_legal_answer("I don't get it", [self.chunk], "atlas-vector"),
        ):
            response = self.client.post(
                "/legal/ask",
                json={
                    "question": "I don't get it",
                    "context_turns": [
                        {"role": "user", "content": "I was kidnapped yesterday and assaulted."},
                        {"role": "assistant", "content": "BNS Sections may apply."},
                        {"role": "user", "content": "I don't get it"},
                    ],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(search_mock.call_args.args[0], "I was kidnapped yesterday and assaulted. I don't get it")

    def test_ollama_generates_a_cited_answer_from_retrieved_sources(self):
        with patch.dict(
            os.environ,
            {"GEMINI_API_KEY": "", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "true"},
            clear=False,
        ), patch(
            "services.legal_client.generate_ollama_text",
            return_value="The supplied provision describes protection orders and the conduct they may restrict [Source 1].",
        ) as ollama_mock:
            answer = generate_legal_answer("What is a protection order?", [self.chunk], "local-corpus")

        self.assertEqual(answer.source, "ollama-local-corpus")
        self.assertIn("Offline local model", answer.warning or "")
        self.assertEqual(len(answer.citations), 1)
        ollama_mock.assert_called_once()

    def test_confinement_and_verbal_abuse_retrieves_current_sources(self):
        chunks, retrieval_source = search_legal_chunks(
            "I am locked in a room for so many days and being verbally abused"
        )
        relevant = [chunk for chunk in chunks if chunk.score >= 0.38]
        sections = {chunk.section.casefold() for chunk in relevant}

        self.assertEqual(retrieval_source, "local-corpus")
        self.assertTrue(any("wrongful confinement" in section for section in sections))
        self.assertTrue(any("domestic violence" in section for section in sections))
        self.assertTrue(all(chunk.status for chunk in relevant))

    def test_current_evidence_law_is_available_for_evidence_questions(self):
        chunks, retrieval_source = search_legal_chunks(
            "What evidence can I preserve if it is safe?"
        )
        self.assertEqual(retrieval_source, "local-corpus")
        self.assertTrue(any("sakshya" in chunk.title.casefold() for chunk in chunks))
        self.assertTrue(chunks[0].section.startswith("Section 63"))

    def test_private_defence_question_retrieves_private_defence_sections(self):
        chunks, retrieval_source = search_legal_chunks(
            "What if he comes to kill me and in self defence I kill him?"
        )
        sections = {chunk.section.casefold() for chunk in chunks}

        self.assertEqual(retrieval_source, "local-corpus")
        self.assertTrue(any("private defence" in section for section in sections))
        self.assertTrue(chunks[0].section.startswith("Section 38"))

    def test_bns_corpus_contains_every_numbered_section(self):
        sections = {
            chunk.section.split(" —", 1)[0]
            for chunk in local_corpus_chunks()
            if chunk.title.startswith("Bharatiya Nyaya Sanhita")
        }
        self.assertEqual(len({int(section.split()[1]) for section in sections}), 358)
        self.assertIn("Section 20", sections)
        self.assertIn("Section 114", sections)


if __name__ == "__main__":
    unittest.main()
