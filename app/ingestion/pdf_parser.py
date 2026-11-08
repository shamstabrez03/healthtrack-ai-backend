"""PDF text extraction using PyMuPDF — page-level with metadata."""

import fitz  # PyMuPDF
from typing import List, Dict, Optional
from pathlib import Path


class PageContent:
    """Represents extracted text from a single PDF page."""
    def __init__(self, page_number: int, text: str, width: float = 0, height: float = 0):
        self.page_number = page_number  # 1-indexed
        self.text = text
        self.width = width
        self.height = height

    def __repr__(self):
        return f"PageContent(page={self.page_number}, chars={len(self.text)})"


def extract_pdf_text(file_path: str) -> List[PageContent]:
    """
    Extract text from a PDF file, page by page.
    Returns a list of PageContent objects with 1-indexed page numbers.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {file_path}")

    if not path.suffix.lower() == ".pdf":
        raise ValueError(f"Not a PDF file: {file_path}")

    pages = []
    try:
        doc = fitz.open(file_path)
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            text = page.get_text("text")
            pages.append(PageContent(
                page_number=page_idx + 1,
                text=text.strip(),
                width=page.rect.width,
                height=page.rect.height,
            ))
        doc.close()
    except Exception as e:
        raise RuntimeError(f"Failed to extract text from PDF: {e}")

    return pages


def get_full_text(pages: List[PageContent]) -> str:
    """Combine all page texts into a single string with page markers."""
    parts = []
    for page in pages:
        if page.text:
            parts.append(f"--- Page {page.page_number} ---\n{page.text}")
    return "\n\n".join(parts)


def get_page_count(file_path: str) -> int:
    """Get the total number of pages in a PDF."""
    doc = fitz.open(file_path)
    count = len(doc)
    doc.close()
    return count
