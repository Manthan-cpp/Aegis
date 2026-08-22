import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

os.environ["MONGODB_URI"] = ""

from main import app  # noqa: E402
from routers.companion import has_abuse_language, has_monitoring_language, has_urgent_language  # noqa: E402
from services.companion_client import CompanionReply, classify_support_mode, generate_companion_reply  # noqa: E402
from services.mongo import clear_local_sessions_for_tests, load_recent_turns  # noqa: E402


class CompanionSafetyTests(unittest.TestCase):
    def test_urgent_language_detection(self):
        self.assertTrue(has_urgent_language("I am not safe right now and cannot leave."))
        self.assertTrue(has_urgent_language("Someone is threatening me with a knife."))
        self.assertTrue(has_urgent_language("I am being sexually assaulted daily."))
        self.assertTrue(has_urgent_language("I am thinking about suicide."))
        self.assertTrue(has_urgent_language("I am being kidnapped right now."))
        self.assertFalse(has_urgent_language("I had a difficult day and need someone to listen."))

    def test_kidnapping_is_classified_as_urgent_and_gets_specific_local_guidance(self):
        message = "I have been kidnapped, what can I do to prevent myself?"
        self.assertEqual(classify_support_mode(message, []), "urgent")
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "false"}, clear=False):
            reply = generate_companion_reply(message, [], "urgent")

        self.assertEqual(reply.source, "safety-guided")
        self.assertIn("112", reply.text)
        self.assertIn("phone", reply.text.casefold())
        self.assertNotIn("what part of this moment feels hardest", reply.text.casefold())

    def test_refused_gemini_draft_does_not_reach_the_user_as_a_companion_answer(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "false"}, clear=False), patch(
            "services.companion_client.generate_gemini_text",
            return_value="I can't answer that.",
        ):
            reply = generate_companion_reply("I am being kidnapped right now.", [], "urgent")

        self.assertEqual(reply.source, "safety-guided")
        self.assertNotIn("I can't answer", reply.text)

    def test_offline_ollama_writes_requested_creative_content(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "true"}, clear=False), patch(
            "services.companion_client.generate_ollama_text",
            return_value="Hunger is a quiet river / Loneliness is the moon / Still, a small light rises / And finds its way to you.",
        ):
            reply = generate_companion_reply(
                "Write me a poem based on my situation.",
                [{"role": "user", "content": "I am alone and hungry."}],
                "normal",
            )

        self.assertEqual(reply.source, "ollama")
        self.assertIn("quiet river", reply.text)
        self.assertNotIn("reach out", reply.text.casefold())

    def test_creative_request_has_a_writing_fallback_when_models_are_unavailable(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "false"}, clear=False):
            reply = generate_companion_reply(
                "Generate a poem based on my situation.",
                [{"role": "user", "content": "I feel alone and hungry."}],
                "normal",
            )

        self.assertEqual(reply.source, "local-fallback")
        self.assertIn("A small light stays awake", reply.text)
        self.assertNotIn("What part of this moment", reply.text)

    def test_harmless_reaction_does_not_inherit_old_emergency_state(self):
        history = [
            {"role": "user", "content": "I was locked in a room earlier."},
            {"role": "assistant", "content": "Here is a small poem for that moment."},
        ]
        self.assertEqual(classify_support_mode("I like thattt", history), "normal")
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "false"}, clear=False):
            reply = generate_companion_reply("I like thattt", history, "normal")

        self.assertEqual(reply.source, "local-fallback")
        self.assertIn("glad it landed", reply.text.casefold())
        self.assertNotIn("112", reply.text)
        self.assertNotIn("safety-guided", reply.source)

    def test_offline_refusal_to_a_harmless_reaction_is_not_shown(self):
        history = [
            {"role": "user", "content": "I asked for a poem."},
            {"role": "assistant", "content": "A small light stays awake."},
        ]
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "true"}, clear=False), patch(
            "services.companion_client.generate_ollama_text",
            return_value="I cannot generate content that depicts intimate scenes between adults and minors.",
        ):
            reply = generate_companion_reply("I like thattt", history, "normal")

        self.assertEqual(reply.source, "local-fallback")
        self.assertIn("glad it landed", reply.text.casefold())
        self.assertNotIn("cannot generate", reply.text.casefold())

    def test_roleplay_request_overrides_stale_incident_in_offline_fallback(self):
        history = [
            {"role": "user", "content": "I was mugged earlier."},
            {"role": "assistant", "content": "Are you in shock or panic?"},
        ]
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "false"}, clear=False):
            reply = generate_companion_reply(
                "Can you pretend to be my father and talk to me like him?",
                history,
                "normal",
            )

        self.assertEqual(reply.source, "local-fallback")
        self.assertIn("fatherly", reply.text.casefold())
        self.assertNotIn("mugged", reply.text.casefold())
        self.assertNotIn("panic", reply.text.casefold())

    def test_model_label_is_removed_from_roleplay_reply(self):
        history = [
            {"role": "user", "content": "I was mugged earlier."},
            {"role": "assistant", "content": "That sounds frightening."},
        ]
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "false"}, clear=False), patch(
            "services.companion_client.generate_gemini_text",
            return_value="Assistant: I can speak to you in a gentle, fatherly way. Tell me what is on your heart.",
        ):
            reply = generate_companion_reply(
                "Can you talk to me like my father?",
                history,
                "normal",
            )

        self.assertEqual(reply.source, "gemini")
        self.assertFalse(reply.text.casefold().startswith("assistant:"))
        self.assertNotIn("mugged", reply.text.casefold())

    def test_exact_romantic_male_soulmate_request_gets_the_requested_voice_offline(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "false"}, clear=False):
            reply = generate_companion_reply(
                "I want you to act as a romantic male soulmate of mine",
                [{"role": "user", "content": "good but feeling alone"}],
                "normal",
            )

        self.assertEqual(reply.source, "local-fallback")
        self.assertIn("warm", reply.text.casefold())
        self.assertNotIn("hardest to carry", reply.text.casefold())

    def test_neutral_room_statement_stays_friend_like_after_old_risk_context(self):
        history = [{"role": "user", "content": "I was locked in a room earlier."}]
        self.assertEqual(classify_support_mode("I am inside a room.", history), "normal")
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "false"}, clear=False):
            reply = generate_companion_reply("I am inside a room.", history, "normal")

        self.assertEqual(reply.source, "local-fallback")
        self.assertIn("quiet little moment", reply.text.casefold())
        self.assertNotIn("112", reply.text)

    def test_creative_follow_up_is_not_labelled_as_safety_guided(self):
        history = [
            {"role": "user", "content": "I was locked in a room earlier."},
            {"role": "assistant", "content": "That was frightening."},
        ]
        message = "I want you to generate me a poem based on my situation."
        self.assertEqual(classify_support_mode(message, history), "normal")
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "false"}, clear=False):
            reply = generate_companion_reply(message, history, "normal")

        self.assertEqual(reply.source, "local-fallback")
        self.assertIn("A small light stays awake", reply.text)

    def test_abuse_and_monitoring_context_detection(self):
        self.assertTrue(has_abuse_language("My family is very abusive towards me."))
        self.assertTrue(has_monitoring_language("I am being monitored strictly."))
        self.assertEqual(classify_support_mode("I am being monitored strictly.", []), "monitored")
        self.assertEqual(
            classify_support_mode(
                "I cannot reach anyone.",
                [{"role": "user", "content": "My family is abusive."}],
            ),
            "monitored",
        )
        self.assertEqual(classify_support_mode("I have been locked in a dark room without food for two days.", []), "urgent")
        self.assertEqual(classify_support_mode("I am being sexually assaulted daily.", []), "urgent")
        self.assertEqual(classify_support_mode("Should I attack him and run?", []), "urgent")

    def test_urgent_messages_use_local_safety_fallback_when_no_provider(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "false"}, clear=False):
            reply = generate_companion_reply("I am not safe right now.", [], support_mode="urgent")
        self.assertEqual(reply.source, "safety-guided")
        self.assertNotIn("safe right now", reply.text.casefold())

    def test_urgent_advisor_does_not_turn_attack_into_a_plan(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "false"}, clear=False):
            reply = generate_companion_reply("Should I attack him and run?", [], support_mode="urgent")
        self.assertEqual(reply.source, "safety-guided")
        self.assertIn("Do not attack him as a plan", reply.text)
        self.assertIn("112", reply.text)

    def test_locked_room_response_does_not_invent_assault_or_hunger(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "false"}, clear=False):
            reply = generate_companion_reply("I am locked in a room for two days straight.", [], support_mode="urgent")

        self.assertEqual(reply.source, "safety-guided")
        self.assertIn("locked in a room for two days", reply.text.casefold())
        self.assertNotIn("being assaulted", reply.text.casefold())
        self.assertNotIn("without food", reply.text.casefold())
        self.assertIn("112", reply.text)

    def test_locked_window_follow_up_answers_the_window_detail(self):
        history = [{"role": "user", "content": "I am locked in a room for two days straight."}]
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "false"}, clear=False):
            reply = generate_companion_reply("There is a window but it is locked tightly.", history, support_mode="urgent")

        self.assertEqual(reply.source, "safety-guided")
        self.assertIn("tightly locked window", reply.text.casefold())
        self.assertIn("do not break", reply.text.casefold())
        self.assertNotIn("being assaulted", reply.text.casefold())
        self.assertNotIn("without food", reply.text.casefold())

    def test_urgent_offline_turn_uses_ollama_before_fallback(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "true"}, clear=False), patch(
            "services.companion_client.generate_ollama_text",
            return_value="The locked-room detail matters. Do not try to break a window; use a phone only if that is safe. Can you safely use one?",
        ) as ollama_mock:
            reply = generate_companion_reply("I am locked in a room for two days straight.", [], support_mode="urgent")

        self.assertEqual(reply.source, "ollama")
        self.assertIn("locked-room", reply.text.casefold())
        ollama_mock.assert_called_once()

    def test_urgent_advisor_answers_wild_rat_question_directly(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "false"}, clear=False):
            reply = generate_companion_reply("There is a rat here. Can I eat it?", [], support_mode="urgent")
        self.assertEqual(reply.source, "safety-guided")
        self.assertIn("Do not eat a wild rat", reply.text)

    def test_urgent_follow_up_uses_the_latest_question(self):
        history = [
            {"role": "user", "content": "I am being sexually assaulted daily."},
            {"role": "assistant", "content": "Daily sexual assault is an emergency."},
            {"role": "user", "content": "Should I attack the assaulter and run?"},
            {"role": "assistant", "content": "Do not attack him as a plan to escape."},
        ]
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "false"}, clear=False), patch(
            "services.companion_client.generate_gemini_text",
            return_value="Right now, make distance and a safe exit the priority. Seek medical care if sexual assault happened, and ask only whether you are physically away from him.",
        ):
            reply = generate_companion_reply("So what should I do?", history, support_mode="urgent")
        self.assertIn("distance", reply.text.casefold())
        self.assertIn("medical care", reply.text.casefold())
        self.assertNotIn("Do not attack him as a plan to escape", reply.text)

    def test_gemini_generates_urgent_turns_instead_of_the_fixed_reply(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "false"}, clear=False), patch(
            "services.companion_client.generate_gemini_text",
            return_value="If he is gone for now, use this window to move somewhere he cannot reach and decide whether you need medical care. Are you physically away from him?",
        ):
            reply = generate_companion_reply("Okay, he is gone now.", [{"role": "user", "content": "He was attacking me."}], "urgent")

        self.assertEqual(reply.source, "gemini")
        self.assertIn("gone", reply.text.casefold())

    def test_safe_transition_does_not_repeat_the_previous_emergency_reply(self):
        history = [
            {"role": "user", "content": "I am being assaulted."},
            {"role": "assistant", "content": "Call 112 if it is safe."},
        ]
        self.assertEqual(classify_support_mode("Ok, now I am safe.", history), "normal")
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "false"}, clear=False):
            reply = generate_companion_reply("Ok, now I am safe.", history, support_mode="normal")
        self.assertIn("stay away", reply.text.casefold())

    def test_local_companion_handles_a_request_for_listening_without_a_script(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "false"}, clear=False):
            reply = generate_companion_reply("Please just listen. I do not want advice.", [], "normal")
        self.assertEqual(reply.source, "local-fallback")
        self.assertIn("won't try to fix", reply.text)

    def test_local_companion_varies_a_thank_you_reply(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "false"}, clear=False):
            reply = generate_companion_reply("Thanks, that helps.", [], "normal")
        self.assertIn("welcome", reply.text.casefold())

    def test_gemini_is_preferred_for_normal_companion_messages(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", "GROQ_API_KEY": "fallback-key", "OLLAMA_ENABLED": "false"}, clear=False), patch(
            "services.companion_client.generate_gemini_text",
            return_value="You can say it plainly. What has been weighing on you today?",
        ), patch("services.companion_client.Groq") as groq_class:
            reply = generate_companion_reply("I feel lonely today.", [], "normal")

        self.assertEqual(reply.source, "gemini")
        self.assertIn("weighing", reply.text)
        groq_class.assert_not_called()

    def test_ollama_is_used_only_after_online_providers_fail(self):
        with patch.dict(
            os.environ,
            {"GEMINI_API_KEY": "", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "true"},
            clear=False,
        ), patch(
            "services.companion_client.generate_ollama_text",
            return_value="You can say it plainly. What feels most difficult right now?",
        ) as ollama_mock:
            reply = generate_companion_reply("I feel lonely today.", [], "normal")

        self.assertEqual(reply.source, "ollama")
        self.assertIn("local Ollama", reply.warning or "")
        ollama_mock.assert_called_once()

    def test_gemini_wins_without_calling_ollama(self):
        with patch.dict(
            os.environ,
            {"GEMINI_API_KEY": "test-key", "GROQ_API_KEY": "", "OLLAMA_ENABLED": "true"},
            clear=False,
        ), patch(
            "services.companion_client.generate_gemini_text",
            return_value="I can hear how heavy today feels. What would help this moment feel a little less lonely?",
        ), patch("services.companion_client.generate_ollama_text") as ollama_mock:
            reply = generate_companion_reply("I feel lonely today.", [], "normal")

        self.assertEqual(reply.source, "gemini")
        ollama_mock.assert_not_called()

    def test_online_groq_wins_over_ollama_when_gemini_quota_is_unavailable(self):
        with patch.dict(
            os.environ,
            {"GEMINI_API_KEY": "test-key", "GROQ_API_KEY": "fallback-key", "OLLAMA_ENABLED": "true"},
            clear=False,
        ), patch(
            "services.companion_client.generate_gemini_text",
            side_effect=RuntimeError("Gemini quota exhausted"),
        ), patch("services.companion_client.Groq") as groq_class, patch(
            "services.companion_client.generate_ollama_text"
        ) as ollama_mock:
            groq_class.return_value.chat.completions.create.return_value.choices[0].message.content = (
                "I can stay with you in this conversation. What kind of company would feel good right now?"
            )
            reply = generate_companion_reply("I feel lonely today.", [], "normal")

        self.assertEqual(reply.source, "groq")
        self.assertIn("company", reply.text.casefold())
        ollama_mock.assert_not_called()


class CompanionApiTests(unittest.TestCase):
    def setUp(self):
        clear_local_sessions_for_tests()
        self.client = TestClient(app)
        self.reply_patch = patch(
            "routers.companion.generate_companion_reply",
            return_value=CompanionReply(text="I hear you. Let us take one calm breath.", source="groq"),
        )
        self.reply_mock = self.reply_patch.start()

    def tearDown(self):
        self.reply_patch.stop()
        clear_local_sessions_for_tests()

    def test_consent_saves_a_multi_turn_conversation(self):
        session_id = "companion-test-session"
        first = self.client.post(
            "/companion/chat",
            json={"session_id": session_id, "message": "I feel anxious today.", "memory_consent": True},
        )
        second = self.client.post(
            "/companion/chat",
            json={"session_id": session_id, "message": "It has been going on all morning.", "memory_consent": True},
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["memory_saved"])
        history, store = load_recent_turns(session_id)
        self.assertEqual(store, "local-demo")
        self.assertEqual(len(history), 4)
        self.assertEqual(history[0]["content"], "I feel anxious today.")

    def test_no_consent_does_not_save_the_turn(self):
        session_id = "no-memory-session"
        response = self.client.post(
            "/companion/chat",
            json={"session_id": session_id, "message": "Please listen.", "memory_consent": False},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["memory_saved"])
        history, _ = load_recent_turns(session_id)
        self.assertEqual(history, [])

    def test_no_consent_uses_recent_context_without_saving_it(self):
        session_id = "context-session"
        response = self.client.post(
            "/companion/chat",
            json={
                "session_id": session_id,
                "message": "I am being monitored strictly.",
                "memory_consent": False,
                "context_turns": [
                    {"role": "user", "content": "My family is very abusive towards me."},
                    {"role": "assistant", "content": "Can you reach out to someone you trust?"},
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        called_message, called_history, called_mode = self.reply_mock.call_args.args
        self.assertEqual(called_message, "I am being monitored strictly.")
        self.assertEqual(called_history[0]["content"], "My family is very abusive towards me.")
        self.assertEqual(called_mode, "monitored")
        self.assertFalse(response.json()["memory_saved"])
        history, _ = load_recent_turns(session_id)
        self.assertEqual(history, [])

    def test_urgent_response_includes_india_support_flag(self):
        response = self.client.post(
            "/companion/chat",
            json={"session_id": "urgent-test-session", "message": "I am not safe right now.", "memory_consent": False},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["urgent_support"])
        self.assertIn("112", response.json()["urgent_support_message"])

    def test_urgent_support_is_preserved_for_a_follow_up_turn(self):
        response = self.client.post(
            "/companion/chat",
            json={
                "session_id": "urgent-follow-up",
                "message": "What should I do?",
                "memory_consent": False,
                "context_turns": [
                    {"role": "user", "content": "I am trapped and not safe right now."},
                    {"role": "assistant", "content": "I hear you."},
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["urgent_support"])


if __name__ == "__main__":
    unittest.main()
