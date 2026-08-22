"""Small, lossless PNG steganography helpers for the Aegis SOS flow.

The message is stored in the least-significant bit of each RGB byte. This is
deliberately simple and transparent: it works for the exact PNG produced here,
but JPEG compression, screenshots, resizing, or social-media re-encoding can
destroy the hidden message.
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image, UnidentifiedImageError


MAGIC = b"AEGIS01\x00"
HEADER_SIZE = len(MAGIC) + 4
MAX_MESSAGE_BYTES = 8_192


class SteganographyError(ValueError):
    """Raised when an image cannot safely carry or reveal an Aegis message."""


def _load_rgb(image_bytes: bytes) -> Image.Image:
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            return image.convert("RGB")
    except (UnidentifiedImageError, OSError) as error:
        raise SteganographyError("The uploaded file is not a readable image.") from error


def _bytes_to_bits(value: bytes):
    for byte in value:
        for bit_index in range(7, -1, -1):
            yield (byte >> bit_index) & 1


def _bits_to_bytes(bits: list[int]) -> bytes:
    if len(bits) % 8 != 0:
        raise SteganographyError("The hidden message is incomplete.")

    output = bytearray()
    for offset in range(0, len(bits), 8):
        byte = 0
        for bit in bits[offset : offset + 8]:
            byte = (byte << 1) | bit
        output.append(byte)
    return bytes(output)


def _read_bytes(pixel_bytes: bytes, byte_count: int, *, offset_bits: int = 0) -> bytes:
    bit_count = byte_count * 8
    if offset_bits + bit_count > len(pixel_bytes):
        raise SteganographyError("This image does not contain a complete Aegis message.")

    bits = [pixel_bytes[offset_bits + index] & 1 for index in range(bit_count)]
    return _bits_to_bytes(bits)


def encode_message(image_bytes: bytes, message: str) -> bytes:
    """Return a PNG containing ``message`` hidden in the image's RGB bytes."""

    cleaned_message = message.strip()
    if not cleaned_message:
        raise SteganographyError("The message cannot be empty.")

    payload = cleaned_message.encode("utf-8")
    if len(payload) > MAX_MESSAGE_BYTES:
        raise SteganographyError("The message is too long for a demo SOS image.")

    image = _load_rgb(image_bytes)
    pixel_bytes = bytearray(image.tobytes())
    packet = MAGIC + len(payload).to_bytes(4, "big") + payload
    required_bits = len(packet) * 8

    if required_bits > len(pixel_bytes):
        available_bytes = max(0, (len(pixel_bytes) // 8) - HEADER_SIZE)
        raise SteganographyError(
            f"This cover image is too small. It can carry about {available_bytes} message bytes."
        )

    for bit_index, bit in enumerate(_bytes_to_bits(packet)):
        pixel_bytes[bit_index] = (pixel_bytes[bit_index] & 0xFE) | bit

    encoded_image = Image.frombytes("RGB", image.size, bytes(pixel_bytes))
    output = BytesIO()
    encoded_image.save(output, format="PNG", optimize=False)
    return output.getvalue()


def decode_message(image_bytes: bytes) -> str:
    """Extract and return an Aegis message from an exact PNG image."""

    image = _load_rgb(image_bytes)
    pixel_bytes = image.tobytes()

    magic = _read_bytes(pixel_bytes, len(MAGIC))
    if magic != MAGIC:
        raise SteganographyError(
            "No Aegis message was found. Upload the original PNG file, not a screenshot or JPEG."
        )

    payload_length = int.from_bytes(
        _read_bytes(pixel_bytes, 4, offset_bits=len(MAGIC) * 8),
        "big",
    )
    if payload_length <= 0 or payload_length > MAX_MESSAGE_BYTES:
        raise SteganographyError("The hidden message length is not valid.")

    payload = _read_bytes(
        pixel_bytes,
        payload_length,
        offset_bits=HEADER_SIZE * 8,
    )
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SteganographyError("The hidden message is corrupted.") from error
