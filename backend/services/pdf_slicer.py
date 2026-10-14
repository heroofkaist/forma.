import base64
from dataclasses import dataclass
from io import BytesIO

import pymupdf
from PIL import Image
from pydantic import BaseModel, Field


class NormalizedBox(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    x1: float = Field(ge=0, le=1)
    y1: float = Field(ge=0, le=1)
    x2: float = Field(gt=0, le=1)
    y2: float = Field(gt=0, le=1)


@dataclass
class PdfPreview:
    page_count: int
    width: float
    height: float
    preview_data_url: str


def open_pdf(pdf_bytes: bytes) -> pymupdf.Document:
    try:
        document = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except (pymupdf.FileDataError, ValueError) as exc:
        raise ValueError("The uploaded file is not a readable PDF.") from exc

    if document.page_count == 0:
        document.close()
        raise ValueError("The uploaded PDF has no pages.")
    return document


def render_preview(pdf_bytes: bytes) -> PdfPreview:
    document = open_pdf(pdf_bytes)
    try:
        page = document[0]
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
        encoded = base64.b64encode(pixmap.tobytes("png")).decode("ascii")
        return PdfPreview(
            page_count=document.page_count,
            width=page.rect.width,
            height=page.rect.height,
            preview_data_url=f"data:image/png;base64,{encoded}",
        )
    finally:
        document.close()


def _render_page_png(page: pymupdf.Page, rotation: int = 0) -> bytes:
    if rotation not in {0, 90, 180, 270}:
        raise ValueError("Rotation must be 0, 90, 180, or 270 degrees.")
    if rotation:
        page.set_rotation((page.rotation + rotation) % 360)
    bounds = page.rect
    pixel_budget = 12_000_000
    scale = min(200 / 72, (pixel_budget / (bounds.width * bounds.height)) ** 0.5)
    return page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).tobytes("png")


def render_page(pdf_bytes: bytes, page_index: int, rotation: int = 0) -> bytes:
    document = open_pdf(pdf_bytes)
    try:
        if page_index < 0 or page_index >= document.page_count:
            raise ValueError(f"Page index {page_index} is outside the PDF.")
        return _render_page_png(document[page_index], rotation)
    finally:
        document.close()


def crop_page(pdf_bytes: bytes, page_index: int, box: NormalizedBox, rotation: int = 0) -> bytes:
    document = open_pdf(pdf_bytes)
    try:
        if page_index < 0 or page_index >= document.page_count:
            raise ValueError(f"Page index {page_index} is outside the PDF.")
        if box.x1 >= box.x2 or box.y1 >= box.y2:
            raise ValueError(f"Box '{box.id}' must have positive width and height.")
        if rotation not in {0, 90, 180, 270}:
            raise ValueError("Rotation must be 0, 90, 180, or 270 degrees.")

        page = document[page_index]
        if rotation:
            with Image.open(BytesIO(_render_page_png(page, rotation))) as image:
                left = round(box.x1 * image.width)
                top = round(box.y1 * image.height)
                right = round(box.x2 * image.width)
                bottom = round(box.y2 * image.height)
                output = BytesIO()
                image.crop((left, top, right, bottom)).save(output, format="PNG")
                return output.getvalue()

        bounds = page.rect
        clip = pymupdf.Rect(
            box.x1 * bounds.width,
            box.y1 * bounds.height,
            box.x2 * bounds.width,
            box.y2 * bounds.height,
        )
        pixmap = page.get_pixmap(clip=clip, dpi=200, alpha=False)
        return pixmap.tobytes("png")
    finally:
        document.close()
