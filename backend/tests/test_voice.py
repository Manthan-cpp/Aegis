import json
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

os.environ["MONGODB_URI"] = ""

from main import app  # noqa: E402
from services.omnidim_client import create_web_session  # noqa: E402


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return b'{"ws_url":"wss://example.test/session","session_id":42,"expires_at":"2030-01-01T00:00:00Z"}'


class VoiceIntegrationTests(unittest.TestCase):
    def test_companion_session_requires_its_own_agent_id(self):
        client = TestClient(app)
        with patch.dict(
            os.environ,
            {"OMNIDIM_API_KEY": "configured-for-test", "OMNIDIM_COMPANION_AGENT_ID": ""},
            clear=False,
        ):
            response = client.post("/voice/companion-session", json={"chat_summary": "A short context."})

        self.assertEqual(response.status_code, 503)
        self.assertIn("OMNIDIM_COMPANION_AGENT_ID", response.json()["detail"])

    def test_companion_session_uses_the_separate_agent_id(self):
        with patch.dict(
            os.environ,
            {"OMNIDIM_API_KEY": "configured-for-test", "OMNIDIM_COMPANION_AGENT_ID": "#654321"},
            clear=False,
        ), patch("services.omnidim_client.urlopen", return_value=_FakeResponse()) as open_url:
            session = create_web_session(
                {"mode": "live companion conversation"},
                agent_env_name="OMNIDIM_COMPANION_AGENT_ID",
            )

        request = open_url.call_args.args[0]
        request_payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(request_payload["agent_id"], 654321)
        self.assertEqual(session["session_id"], 42)
        self.assertTrue(session["ws_url"].startswith("wss://"))


if __name__ == "__main__":
    unittest.main()
