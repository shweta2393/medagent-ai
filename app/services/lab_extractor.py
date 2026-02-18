import io
import csv
import json
import logging
from typing import Optional

from app.config import GOOGLE_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """You are a medical lab report parser. Extract ALL lab test results from the following text.

Return a JSON array where each element has:
- "name": the test name (e.g., "HbA1c", "Complete Blood Count", "TSH")
- "value": the result value with units (e.g., "7.2%", "14.5 g/dL", "2.5 mIU/L")
- "when": the date or timeframe if mentioned (e.g., "2024-01-15", "Jan 2024"), or null if not found

Rules:
- Extract every distinct test result you can find
- Keep original units attached to values
- If a test has sub-components (e.g., CBC with WBC, RBC, Hemoglobin), list each as a separate entry
- If no date is found for any test, set "when" to null
- Return ONLY valid JSON array, no markdown, no explanation

Text to parse:
---
{text}
---"""

MAX_TEXT_LENGTH = 15000


def extract_from_pdf(file_bytes: bytes) -> str:
    import pdfplumber

    text_parts = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    result = "\n\n".join(text_parts)
    if not result.strip():
        raise ValueError("Could not extract text from PDF. The file may be image-based — try uploading as an image instead.")
    return result


def extract_from_image(file_bytes: bytes, content_type: str) -> str:
    """Use Gemini Vision to read text from a lab report image."""
    if not GOOGLE_API_KEY:
        raise ValueError(
            "Image OCR requires a Google API key (GOOGLE_API_KEY in .env). "
            "Please configure it or upload a PDF/text file instead."
        )

    import google.generativeai as genai

    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL)

    mime_map = {
        "image/jpeg": "image/jpeg",
        "image/jpg": "image/jpeg",
        "image/png": "image/png",
    }
    mime = mime_map.get(content_type, "image/jpeg")

    response = model.generate_content(
        [
            "Extract ALL text from this medical lab report image. "
            "Include test names, values, units, reference ranges, and dates. "
            "Return the raw text exactly as it appears.",
            {"mime_type": mime, "data": file_bytes},
        ],
        generation_config=genai.GenerationConfig(temperature=0.1, max_output_tokens=4096),
    )
    return response.text


def extract_from_text(file_bytes: bytes, content_type: str) -> str:
    text = file_bytes.decode("utf-8", errors="replace")

    if content_type == "text/csv" or text.count(",") > text.count("\t"):
        try:
            reader = csv.reader(io.StringIO(text))
            rows = list(reader)
            if rows:
                return "\n".join([", ".join(row) for row in rows])
        except csv.Error:
            pass

    return text


def extract_lab_values(raw_text: str) -> list[dict]:
    """Send extracted text to the LLM for structured lab value extraction."""
    from app.services.llm_service import get_llm_service

    if len(raw_text) > MAX_TEXT_LENGTH:
        raw_text = raw_text[:MAX_TEXT_LENGTH]
        logger.warning("Truncated extracted text to %d chars", MAX_TEXT_LENGTH)

    prompt = EXTRACTION_PROMPT.format(text=raw_text)
    llm = get_llm_service()
    raw_response = llm.generate(prompt, temperature=0.1)

    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()

    try:
        results = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.error("LLM returned invalid JSON for lab extraction: %s", cleaned[:200])
        raise ValueError("Could not parse lab results from the uploaded file. Please try a clearer file or enter values manually.")

    if not isinstance(results, list):
        results = [results]

    validated = []
    for item in results:
        if isinstance(item, dict) and "name" in item and "value" in item:
            validated.append({
                "name": str(item["name"]).strip(),
                "value": str(item["value"]).strip(),
                "when": str(item["when"]).strip() if item.get("when") else None,
            })

    if not validated:
        raise ValueError("No lab values could be extracted from the file. Please check the file content.")

    return validated


async def process_lab_file(file_bytes: bytes, content_type: str, filename: str) -> list[dict]:
    """Main entry point: detect file type, extract text, parse lab values."""
    content_type = (content_type or "").lower()
    filename_lower = (filename or "").lower()

    logger.info("Processing lab file: %s (type: %s, size: %d bytes)", filename, content_type, len(file_bytes))

    if content_type == "application/pdf" or filename_lower.endswith(".pdf"):
        raw_text = extract_from_pdf(file_bytes)
    elif content_type in ("image/jpeg", "image/jpg", "image/png") or any(
        filename_lower.endswith(ext) for ext in (".jpg", ".jpeg", ".png")
    ):
        raw_text = extract_from_image(file_bytes, content_type)
    elif content_type in ("text/plain", "text/csv") or any(
        filename_lower.endswith(ext) for ext in (".txt", ".csv")
    ):
        raw_text = extract_from_text(file_bytes, content_type)
    else:
        raise ValueError(
            f"Unsupported file type: {content_type or filename}. "
            "Supported formats: PDF, JPG, PNG, TXT, CSV"
        )

    logger.info("Extracted %d chars of text from %s", len(raw_text), filename)
    return extract_lab_values(raw_text)
