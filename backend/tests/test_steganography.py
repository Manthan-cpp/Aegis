import unittest
from io import BytesIO

from PIL import Image

from services.steganography import decode_message, encode_message


def make_cover_image() -> bytes:
    image = Image.new("RGB", (320, 240))
    pixels = image.load()
    for y in range(240):
        for x in range(320):
            pixels[x, y] = (80 + (x % 120), 120 + (y % 90), 180)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class SteganographyRoundTripTests(unittest.TestCase):
    def test_five_messages_survive_png_round_trip(self):
        cover = make_cover_image()
        messages = [
            "I need help.",
            "Please call me when you can.",
            "I am scared and locked inside.",
            "Can you check in with me soon?",
            "I need someone I trust to come by and help me leave safely.",
        ]

        for message in messages:
            with self.subTest(message=message):
                encoded = encode_message(cover, message)
                self.assertEqual(decode_message(encoded), message)


if __name__ == "__main__":
    unittest.main()
