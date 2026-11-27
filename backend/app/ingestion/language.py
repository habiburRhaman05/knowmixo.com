"""Document-level language detection (D3.3: populates `chunks.language`,
used by the retrieval language filter per launch/05-RAG-V2-SPEC.md §3.4
-- "metadata filters ... language optional"). Detected once per document
from its full extracted text, not per chunk: a single source document is
overwhelmingly one language, and detecting per-chunk risks inconsistent
tags on short chunks (a 4-word heading-only chunk has too little signal
to classify reliably)."""
from langdetect import LangDetectException, detect

_FALLBACK = "en"


def detect_language(text: str) -> str:
    """Returns an ISO 639-1 code, falling back to 'en' when the text is
    too short/ambiguous for langdetect to classify at all."""
    sample = text.strip()
    if not sample:
        return _FALLBACK
    try:
        return detect(sample)
    except LangDetectException:
        return _FALLBACK
