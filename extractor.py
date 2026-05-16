"""
extractor.py — Extract plain text from uploaded resume files.
Supports PDF (via pypdf) and plain text (.txt).
"""

import io
from pypdf import PdfReader


def extract_resume_text(uploaded_file) -> str:  # line 9
    """
    Accept a Streamlit UploadedFile object.
    Returns extracted plain text string.
    Raises ValueError on unsupported type or empty extraction.
    """
    name = uploaded_file.name.lower()
    raw_bytes = uploaded_file.read()  # line 16

    if name.endswith(".pdf"):
        text = _extract_pdf(raw_bytes)  # line 19
    elif name.endswith(".txt"):
        text = raw_bytes.decode("utf-8", errors="replace")
    else:
        raise ValueError(f"Unsupported file type: {uploaded_file.name}")

    text = text.strip()
    if not text:
        raise ValueError("Could not extract any text from the uploaded file. Try pasting your resume as text instead.")

    return text


def _extract_pdf(raw_bytes: bytes) -> str:  # line 32
    """Extract all text pages from a PDF byte blob."""
    reader = PdfReader(io.BytesIO(raw_bytes))
    pages = []
    for page in reader.pages:  # line 36
        page_text = page.extract_text() or ""
        pages.append(page_text)
    return "\n".join(pages)
