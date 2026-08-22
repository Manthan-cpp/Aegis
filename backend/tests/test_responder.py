import os
import unittest
from io import BytesIO
from unittest.mock import patch

from PIL import Image
from fastapi.testclient import TestClient

os.environ["MONGODB_URI"] = ""

from main import app  # noqa: E402
from services.cases import clear_local_cases_for_tests  # noqa: E402
from services.severity import SeverityResult, classify_severity  # noqa: E402
from services.steganography import encode_message  # noqa: E402


def encoded_png(message: str) -> bytes:
    cover = Image.new("RGB", (640, 420), color=(220, 232, 242))
    output = BytesIO()
    cover.save(output, format="PNG")
    return encode_message(output.getvalue(), message)


class ResponderApiTests(unittest.TestCase):
    def setUp(self):
        clear_local_cases_for_tests()
        self.client = TestClient(app)

    def tearDown(self):
        clear_local_cases_for_tests()

    def test_decode_reveals_message_and_classifies_it(self):
        classification = SeverityResult(
            level="medium",
            reason="The message contains monitoring language without an explicit immediate-danger signal.",
            source="rule-based",
        )
        with patch("routers.responder.classify_severity", return_value=classification):
            response = self.client.post(
                "/responder/decode",
                files={"image": ("aegis-sos.png", encoded_png("I am being monitored strictly."), "image/png")},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "I am being monitored strictly.")
        self.assertEqual(response.json()["severity"], "medium")
        self.assertEqual(response.json()["filename"], "aegis-sos.png")

    def test_case_is_saved_and_highest_severity_lists_first(self):
        low = self.client.post(
            "/responder/cases",
            json={
                "message": "Please check in with me when you can.",
                "severity": "low",
                "severity_reason": "No explicit danger signal.",
                "filename": "low.png",
            },
        )
        high = self.client.post(
            "/responder/cases",
            json={
                "message": "I am trapped and need help now.",
                "severity": "high",
                "severity_reason": "Immediate danger language detected.",
                "filename": "high.png",
            },
        )
        cases = self.client.get("/responder/cases")

        self.assertEqual(low.status_code, 200)
        self.assertEqual(high.status_code, 200)
        self.assertEqual(cases.status_code, 200)
        self.assertEqual(cases.json()["memory_store"], "local-demo")
        self.assertEqual(cases.json()["cases"][0]["severity"], "high")
        self.assertEqual(len(cases.json()["cases"]), 2)

    def test_invalid_image_is_rejected(self):
        response = self.client.post(
            "/responder/decode",
            files={"image": ("not-an-image.png", b"not a png", "image/png")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("readable image", response.json()["detail"])

    def test_saved_case_can_be_removed(self):
        saved = self.client.post(
            "/responder/cases",
            json={
                "message": "Please remove this test case.",
                "severity": "low",
                "severity_reason": "Test record.",
            },
        )
        case_id = saved.json()["case"]["case_id"]
        removed = self.client.delete(f"/responder/cases/{case_id}")
        cases = self.client.get("/responder/cases")

        self.assertEqual(removed.status_code, 200)
        self.assertTrue(removed.json()["deleted"])
        self.assertEqual(cases.json()["cases"], [])

    def test_invalid_case_id_cannot_be_deleted(self):
        response = self.client.delete("/responder/cases/not-a-case-id")
        self.assertEqual(response.status_code, 422)

    def test_rule_based_classifier_never_understates_immediate_danger(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": ""}, clear=False):
            result = classify_severity("I am trapped and someone has a knife.")
        self.assertEqual(result.level, "high")
        self.assertEqual(result.source, "rule-based")


if __name__ == "__main__":
    unittest.main()
