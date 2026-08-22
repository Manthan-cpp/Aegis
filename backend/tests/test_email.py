import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

os.environ["MONGODB_URI"] = ""

from main import app  # noqa: E402
from services.email_queue import clear_email_queue_for_tests, get_email_job, process_email_queue_once  # noqa: E402


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return b"OK"


class EmailApiTests(unittest.TestCase):
    def setUp(self):
        self.queue_directory = tempfile.TemporaryDirectory()
        self.queue_path = os.path.join(self.queue_directory.name, "email_queue.sqlite3")
        self.queue_env = patch.dict(
            os.environ,
            {"EMAIL_QUEUE_DB_PATH": self.queue_path, "EMAIL_QUEUE_WORKER_ENABLED": "false"},
            clear=False,
        )
        self.queue_env.start()
        clear_email_queue_for_tests()
        self.client = TestClient(app)
        self.common = {
            "user_name": "Demo User",
            "situation": "This is a controlled hackathon test message.",
            "confirmation": True,
        }

    def tearDown(self):
        clear_email_queue_for_tests()
        self.queue_env.stop()
        self.queue_directory.cleanup()

    def test_email_requires_confirmation(self):
        payload = {**self.common, "recipient_type": "women_support", "confirmation": False}
        response = self.client.post("/email/send", json=payload)
        self.assertEqual(response.status_code, 422)
        self.assertIn("confirm", response.json()["detail"].lower())

    def test_email_requires_situation_or_summary(self):
        payload = {"user_name": "Demo User", "recipient_type": "women_support", "confirmation": True}
        response = self.client.post("/email/send", json=payload)
        self.assertEqual(response.status_code, 422)
        self.assertIn("situation", response.json()["detail"].lower())

    def test_demo_women_support_always_uses_demo_inbox(self):
        with patch.dict(
            os.environ,
            {
                "EMAILJS_SERVICE_ID": "service_test",
                "EMAILJS_TEMPLATE_ID": "template_test",
                "EMAILJS_PUBLIC_KEY": "public_test",
                "EMAIL_DEMO_MODE": "true",
                "EMAIL_DEMO_RECIPIENT": "demo@example.com",
                "EMAIL_WOMEN_SUPPORT_RECIPIENT": "should-not-be-used@example.com",
            },
            clear=False,
        ), patch("services.emailjs_client.urlopen", return_value=_FakeResponse()) as open_url:
            response = self.client.post(
                "/email/send",
                json={**self.common, "recipient_type": "women_support"},
            )
            process_email_queue_once()

        self.assertEqual(response.status_code, 202)
        self.assertTrue(response.json()["demo_mode"])
        self.assertTrue(response.json()["queued"])

        request_payload = json.loads(open_url.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(request_payload["template_params"]["to_email"], "demo@example.com")
        self.assertIn("[DEMO]", request_payload["template_params"]["subject"])

    def test_trusted_contact_uses_the_entered_email(self):
        with patch.dict(
            os.environ,
            {
                "EMAILJS_SERVICE_ID": "service_test",
                "EMAILJS_TEMPLATE_ID": "template_test",
                "EMAILJS_PUBLIC_KEY": "public_test",
                "EMAIL_DEMO_MODE": "true",
                "EMAIL_DEMO_RECIPIENT": "demo@example.com",
            },
            clear=False,
        ), patch("services.emailjs_client.urlopen", return_value=_FakeResponse()) as open_url:
            response = self.client.post(
                "/email/send",
                json={
                    **self.common,
                    "recipient_type": "trusted",
                    "trusted_email": "trusted@example.com",
                },
            )
            process_email_queue_once()

        self.assertEqual(response.status_code, 202)
        self.assertFalse(response.json()["demo_mode"])
        request_payload = json.loads(open_url.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(request_payload["template_params"]["to_email"], "trusted@example.com")

    def test_missing_emailjs_configuration_is_kept_in_queue(self):
        with patch.dict(
            os.environ,
            {
                "EMAILJS_SERVICE_ID": "",
                "EMAILJS_TEMPLATE_ID": "",
                "EMAILJS_PUBLIC_KEY": "",
            },
            clear=False,
        ):
            response = self.client.post(
                "/email/send",
                json={**self.common, "recipient_type": "women_support"},
            )
            process_email_queue_once()

        self.assertEqual(response.status_code, 202)
        self.assertTrue(response.json()["queued"])
        job = get_email_job(response.json()["job_id"])
        self.assertIsNotNone(job)
        self.assertEqual(job["status"], "queued")
        self.assertIn("EMAILJS_SERVICE_ID", job["last_error"] or "")

    def test_email_is_accepted_when_emailjs_cannot_be_reached(self):
        from urllib.error import URLError

        with patch.dict(
            os.environ,
            {
                "EMAILJS_SERVICE_ID": "service_test",
                "EMAILJS_TEMPLATE_ID": "template_test",
                "EMAILJS_PUBLIC_KEY": "public_test",
                "EMAIL_DEMO_MODE": "true",
                "EMAIL_DEMO_RECIPIENT": "demo@example.com",
            },
            clear=False,
        ), patch("services.emailjs_client.urlopen", side_effect=URLError("offline")):
            response = self.client.post("/email/send", json={**self.common, "recipient_type": "women_support"})
            process_email_queue_once()

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "queued")
        job = get_email_job(response.json()["job_id"])
        self.assertEqual(job["status"], "queued")
        self.assertGreaterEqual(job["attempts"], 1)

    def test_queue_retries_after_connection_returns(self):
        from urllib.error import URLError

        payload = {**self.common, "recipient_type": "women_support", "client_request_id": "retry-test-123"}
        with patch.dict(
            os.environ,
            {
                "EMAILJS_SERVICE_ID": "service_test",
                "EMAILJS_TEMPLATE_ID": "template_test",
                "EMAILJS_PUBLIC_KEY": "public_test",
                "EMAIL_DEMO_MODE": "true",
                "EMAIL_DEMO_RECIPIENT": "demo@example.com",
            },
            clear=False,
        ), patch("services.emailjs_client.urlopen", side_effect=URLError("offline")):
            response = self.client.post("/email/send", json=payload)
            process_email_queue_once()

        connection = sqlite3.connect(self.queue_path)
        try:
            connection.execute("UPDATE email_queue SET next_attempt_at = 0 WHERE job_id = ?", (response.json()["job_id"],))
            connection.commit()
        finally:
            connection.close()

        with patch.dict(
            os.environ,
            {
                "EMAILJS_SERVICE_ID": "service_test",
                "EMAILJS_TEMPLATE_ID": "template_test",
                "EMAILJS_PUBLIC_KEY": "public_test",
                "EMAIL_DEMO_MODE": "true",
                "EMAIL_DEMO_RECIPIENT": "demo@example.com",
            },
            clear=False,
        ), patch(
            "services.emailjs_client.urlopen",
            return_value=_FakeResponse(),
        ) as open_url:
            process_email_queue_once()

        job = get_email_job(response.json()["job_id"])
        self.assertEqual(job["status"], "sent")
        self.assertGreaterEqual(job["attempts"], 2)
        self.assertTrue(open_url.called)

    def test_client_request_id_prevents_duplicate_queue_jobs(self):
        payload = {**self.common, "recipient_type": "women_support", "client_request_id": "same-request-123"}
        with patch.dict(
            os.environ,
            {
                "EMAILJS_SERVICE_ID": "service_test",
                "EMAILJS_TEMPLATE_ID": "template_test",
                "EMAILJS_PUBLIC_KEY": "public_test",
                "EMAIL_DEMO_MODE": "true",
                "EMAIL_DEMO_RECIPIENT": "demo@example.com",
            },
            clear=False,
        ):
            first = self.client.post("/email/send", json=payload)
            second = self.client.post("/email/send", json=payload)

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 202)
        self.assertEqual(first.json()["job_id"], second.json()["job_id"])
        connection = sqlite3.connect(self.queue_path)
        try:
            count = connection.execute("SELECT COUNT(*) FROM email_queue").fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(count, 1)

    def test_queue_status_endpoint_reports_pending_delivery(self):
        payload = {**self.common, "recipient_type": "women_support", "client_request_id": "status-test-123"}
        with patch.dict(
            os.environ,
            {
                "EMAILJS_SERVICE_ID": "service_test",
                "EMAILJS_TEMPLATE_ID": "template_test",
                "EMAILJS_PUBLIC_KEY": "public_test",
                "EMAIL_DEMO_MODE": "true",
                "EMAIL_DEMO_RECIPIENT": "demo@example.com",
            },
            clear=False,
        ):
            queued = self.client.post("/email/send", json=payload)
            job_id = queued.json()["job_id"]
            status_response = self.client.get(f"/email/queue/{job_id}")

        self.assertEqual(queued.status_code, 202)
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()["status"], "queued")
        self.assertFalse(status_response.json()["sent"])


if __name__ == "__main__":
    unittest.main()
