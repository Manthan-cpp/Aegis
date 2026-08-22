from __future__ import annotations

import base64
from typing import Literal

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from services.cover_image import CoverImageResult, fetch_cover_image
from services.groq_client import ExpansionResult, expand_distress_message
from services.steganography import SteganographyError, decode_message, encode_message


router = APIRouter(prefix="/sos", tags=["sos"])

Theme = Literal["flower", "landscape", "food", "coffee", "sunset"]


class SOSGenerateRequest(BaseModel):
    keywords: str = Field(min_length=3, max_length=240)
    theme: Theme = "flower"


class SOSGenerateResponse(BaseModel):
    message: str
    theme: Theme
    image_data_url: str
    image_mime_type: Literal["image/png"] = "image/png"
    cover_source: str
    expansion_source: str
    warning: str | None = None
    encoded_bytes: int


class SOSDecodeResponse(BaseModel):
    message: str
    filename: str | None = None


def _data_url(png_bytes: bytes) -> str:
    encoded = base64.b64encode(png_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded}"


@router.post("/generate", response_model=SOSGenerateResponse)
def generate_sos(payload: SOSGenerateRequest):
    expansion: ExpansionResult = expand_distress_message(payload.keywords)
    cover: CoverImageResult = fetch_cover_image(payload.theme)

    try:
        encoded_image = encode_message(cover.png_bytes, expansion.message)
    except SteganographyError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    return SOSGenerateResponse(
        message=expansion.message,
        theme=payload.theme,
        image_data_url=_data_url(encoded_image),
        cover_source=cover.source,
        expansion_source=expansion.source,
        warning=expansion.warning,
        encoded_bytes=len(encoded_image),
    )


@router.post("/decode", response_model=SOSDecodeResponse)
async def decode_sos(image: UploadFile = File(...)):
    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Please upload an image file.")
    if len(image_bytes) > 12 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="That image is too large for the demo.")

    try:
        message = decode_message(image_bytes)
    except SteganographyError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return SOSDecodeResponse(message=message, filename=image.filename)
