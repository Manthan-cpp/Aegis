"""Cover-image sourcing for the Phase 2 SOS pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw, UnidentifiedImageError


POLLINATIONS_BASE_URL = "https://image.pollinations.ai/prompt"

THEME_PROMPTS = {
    "flower": "a natural close-up photograph of a soft pink flower in morning light, no text",
    "landscape": "a peaceful natural landscape photograph with soft afternoon light, no text",
    "food": "a normal casual photograph of a warm bowl of food on a kitchen table, no text",
    "coffee": "a normal casual photograph of a cup of coffee beside a window, no text",
    "sunset": "a peaceful photograph of a sunset over distant hills, no text",
}


@dataclass(frozen=True)
class CoverImageResult:
    png_bytes: bytes
    source: str


def _as_png(image_bytes: bytes) -> bytes:
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            normalized = image.convert("RGB")
            output = BytesIO()
            normalized.save(output, format="PNG", optimize=False)
            return output.getvalue()
    except (UnidentifiedImageError, OSError) as error:
        raise ValueError("The cover-image service returned an unreadable image.") from error


def _fallback_cover(theme: str) -> bytes:
    palettes = {
        "flower": ((249, 226, 226), (208, 151, 177), (120, 154, 197)),
        "landscape": ((199, 221, 226), (116, 157, 167), (84, 113, 125)),
        "food": ((245, 222, 184), (210, 147, 92), (127, 83, 62)),
        "coffee": ((228, 211, 190), (170, 126, 94), (84, 67, 60)),
        "sunset": ((250, 209, 154), (225, 126, 107), (74, 74, 111)),
    }
    top, middle, bottom = palettes.get(theme, palettes["flower"])
    width, height = 640, 420
    image = Image.new("RGB", (width, height), top)
    pixels = image.load()
    for y in range(height):
        progress = y / (height - 1)
        if progress < 0.55:
            start, end, local_progress = top, middle, progress / 0.55
        else:
            start, end, local_progress = middle, bottom, (progress - 0.55) / 0.45
        color = tuple(int(start[index] + (end[index] - start[index]) * local_progress) for index in range(3))
        for x in range(width):
            pixels[x, y] = color

    draw = ImageDraw.Draw(image, "RGBA")
    draw.ellipse((width * 0.66, height * 0.08, width * 0.86, height * 0.32), fill=(255, 245, 217, 120))
    draw.ellipse((width * 0.08, height * 0.62, width * 0.55, height * 1.18), fill=(34, 59, 78, 80))
    draw.rounded_rectangle((width * 0.18, height * 0.52, width * 0.46, height * 0.93), radius=18, fill=(255, 255, 255, 32))
    draw.line((width * 0.02, height * 0.72, width * 0.92, height * 0.42), fill=(255, 255, 255, 42), width=3)

    output = BytesIO()
    image.save(output, format="PNG", optimize=False)
    return output.getvalue()


def fetch_cover_image(theme: str) -> CoverImageResult:
    """Fetch a plausible Pollinations cover and normalize it to PNG.

    A generated local cover is returned if the free image endpoint is
    unavailable, which makes local development deterministic and offline-safe.
    """

    prompt = THEME_PROMPTS[theme]
    url = f"{POLLINATIONS_BASE_URL}/{quote(prompt, safe='')}?width=640&height=420&nologo=true"
    request = Request(url, headers={"User-Agent": "Aegis/0.1"})

    try:
        with urlopen(request, timeout=25) as response:  # noqa: S310 - URL is built from our fixed prompt map.
            remote_bytes = response.read()
        return CoverImageResult(png_bytes=_as_png(remote_bytes), source="pollinations")
    except (OSError, URLError, TimeoutError, ValueError):
        return CoverImageResult(png_bytes=_fallback_cover(theme), source="local-fallback")
