from io import BytesIO
from pathlib import Path

from fastapi import HTTPException
from pypdf import PdfReader

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_PDF_PAGES = 100


def extract_document_text(filename: str, content: bytes) -> str:
    """Extract readable UTF-8 text from a TXT or PDF upload."""

    suffix = Path(filename or "").suffix.lower()

    if suffix not in {".txt", ".pdf"}:
        raise HTTPException(
            status_code=415,
            detail="Unsupported file type. Upload a .txt or .pdf file.",
        )

    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail="File is too large. Maximum upload size is 5 MB.",
        )

    if suffix == ".txt":
        if b"\x00" in content:
            raise HTTPException(
                status_code=400,
                detail="The text file contains invalid binary data.",
            )

        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=400,
                detail="Unable to read the text file. Please upload a UTF-8 encoded .txt file.",
            ) from exc

    else:
        if not content.startswith(b"%PDF-"):
            raise HTTPException(
                status_code=400,
                detail="The uploaded file does not appear to be a valid PDF.",
            )

        try:
            reader = PdfReader(BytesIO(content), strict=True)

            if reader.is_encrypted:
                raise HTTPException(
                    status_code=400,
                    detail="Password-protected PDFs are not supported.",
                )

            if len(reader.pages) > MAX_PDF_PAGES:
                raise HTTPException(
                    status_code=413,
                    detail="PDF exceeds the 100-page limit.",
                )

            extracted_pages = []
            for page in reader.pages:
                extracted_pages.append(page.extract_text() or "")

            text = "\n\n".join(extracted_pages)

        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail="Unable to read this PDF. The file may be malformed or damaged.",
            ) from exc

    text = text.strip()

    if not text:
        detail = (
            "No readable text was found in the PDF. Scanned PDFs may require OCR."
            if suffix == ".pdf"
            else "The text file contains no readable text."
        )
        raise HTTPException(status_code=422, detail=detail)

    return text
