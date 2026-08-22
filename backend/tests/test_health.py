import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app
from services.health_client import generate_health_reply


class HealthAssistantTests(unittest.TestCase):
    def test_online_gemini_answers_intimate_question_directly(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", "GROQ_API_KEY": ""}, clear=False), patch(
            "services.health_client.generate_gemini_text",
            return_value="Yes, masturbation is generally a normal part of sexual health. Stop and seek care if there is persistent pain or injury.",
        ):
            reply = generate_health_reply("Is masturbation normal?", [])

        self.assertEqual(reply.source, "gemini")
        self.assertIn("normal", reply.text.casefold())
        self.assertNotIn("I can't answer", reply.text)

    def test_groq_is_used_when_gemini_is_unavailable(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", "GROQ_API_KEY": "test-key"}, clear=False), patch(
            "services.health_client.generate_gemini_text",
            side_effect=RuntimeError("offline"),
        ), patch("services.health_client.Groq") as groq:
            groq.return_value.chat.completions.create.return_value.choices[0].message.content = "A missed period can have many causes, including stress, pregnancy, or cycle variation."
            reply = generate_health_reply("Why is my period late?", [])

        self.assertEqual(reply.source, "groq")
        self.assertIn("period", reply.text.casefold())

    def test_online_groq_wins_over_ollama_when_gemini_quota_is_unavailable(self):
        with patch.dict(
            os.environ,
            {"GEMINI_API_KEY": "test-key", "GROQ_API_KEY": "test-key", "OLLAMA_ENABLED": "true"},
            clear=False,
        ), patch(
            "services.health_client.generate_gemini_text",
            side_effect=RuntimeError("Gemini quota exhausted"),
        ), patch("services.health_client.Groq") as groq_class, patch(
            "services.health_client.generate_ollama_text"
        ) as ollama_mock:
            groq_class.return_value.chat.completions.create.return_value.choices[0].message.content = (
                "Masturbation is generally normal. Seek medical advice if it causes pain, injury, or persistent distress."
            )
            reply = generate_health_reply("Is masturbation normal?", [])

        self.assertEqual(reply.source, "groq")
        self.assertIn("normal", reply.text.casefold())
        ollama_mock.assert_not_called()

    def test_health_endpoint_returns_a_clear_error_without_online_provider(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "false"}, clear=False):
            with TestClient(app) as client:
                response = client.post("/health/chat", json={"message": "What is an STI?"})

        self.assertEqual(response.status_code, 503)
        self.assertIn("health assistant", response.json()["detail"])

    def test_ollama_answers_when_online_providers_are_unavailable(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "true"}, clear=False), patch(
            "services.health_client.generate_ollama_text",
            return_value="Yes, sexual desire and masturbation can be normal. Pain, bleeding, sores, or persistent discomfort should be checked by a clinician.",
        ):
            reply = generate_health_reply("Is it normal to masturbate?", [])

        self.assertEqual(reply.source, "ollama")
        self.assertIn("normal", reply.text.casefold())
        self.assertIn("Offline local", reply.warning or "")

    def test_offline_refusal_is_retried_with_clinical_wording(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "true"}, clear=False), patch(
            "services.health_client.generate_ollama_text",
            side_effect=[
                "I can't answer that.",
                "Pain after consensual anal penetration can come from irritated hemorrhoids or a small tear. Avoid further penetration and seek care for severe pain, heavy bleeding, fever, or pus.",
            ],
        ) as ollama:
            reply = generate_health_reply("I had anal sex yesterday and my ass is hurting.", [])

        self.assertEqual(reply.source, "ollama")
        self.assertIn("hemorrhoids", reply.text.casefold())
        self.assertEqual(ollama.call_count, 2)

    def test_offline_refusal_has_a_direct_symptom_fallback(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "true"}, clear=False), patch(
            "services.health_client.generate_ollama_text",
            return_value="I can't answer that.",
        ):
            reply = generate_health_reply("I had anal sex yesterday and my piles are hurting.", [])

        self.assertEqual(reply.source, "context-guided")
        self.assertIn("Avoid further anal penetration", reply.text)
        self.assertNotIn("I can't answer", reply.text)

    def test_offline_fallback_handles_paining_wording(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "true"}, clear=False), patch(
            "services.health_client.generate_ollama_text",
            return_value="I can't answer that.",
        ):
            reply = generate_health_reply("I had anal sex today but my ass is paining.", [])

        self.assertEqual(reply.source, "context-guided")
        self.assertIn("hemorrhoids", reply.text.casefold())

    def test_offline_fallback_answers_masturbation_question(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "true"}, clear=False), patch(
            "services.health_client.generate_ollama_text",
            return_value="I can't answer that.",
        ):
            reply = generate_health_reply("Is masturbation normal?", [])

        self.assertEqual(reply.source, "context-guided")
        self.assertIn("normal", reply.text.casefold())


if __name__ == "__main__":
    unittest.main()
