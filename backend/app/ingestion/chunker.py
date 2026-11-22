"""Tokenizer-aware chunking (docs/03-TRD.md step 6): split
paragraphs/headings first (done by the parser layer), then build
tokenizer-aware windows with a 350-token target and 50-token overlap,
enforcing a 512-token hard max. Preserves heading/page references on
every chunk.
"""
from typing import Callable

TARGET_TOKENS = 350
OVERLAP_TOKENS = 50
MAX_TOKENS = 512


def _split_oversized(text: str, count_tokens_fn: Callable[[str], int], max_tokens: int) -> list[str]:
    """A single paragraph/block larger than max_tokens must still be
    split -- otherwise one oversized block would silently violate the
    hard cap that exists specifically to bound provider input size."""
    words = text.split()
    pieces: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join(current + [word])
        if current and count_tokens_fn(candidate) > max_tokens:
            pieces.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        pieces.append(" ".join(current))
    return pieces


def chunk_blocks(
    blocks: list[dict],
    count_tokens_fn: Callable[[str], int],
    target_tokens: int = TARGET_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
    max_tokens: int = MAX_TOKENS,
) -> list[dict]:
    """blocks: already paragraph/heading-split [{"heading", "page", "text"}].
    Returns ordered chunks: [{"ordinal", "heading", "page", "text", "token_count"}].
    Raises ValueError if blocks contain no usable text at all.
    """
    raw_chunks: list[dict] = []
    current_texts: list[str] = []
    current_tokens = 0
    current_heading = None
    current_page = None

    def flush():
        nonlocal current_texts, current_tokens, current_heading, current_page
        if current_texts:
            raw_chunks.append({"heading": current_heading, "page": current_page, "text": " ".join(current_texts).strip()})
        current_texts = []
        current_tokens = 0

    for block in blocks:
        text = (block.get("text") or "").strip()
        if not text:
            continue
        heading = block.get("heading")
        page = block.get("page")
        block_tokens = count_tokens_fn(text)

        if block_tokens > max_tokens:
            flush()
            for piece in _split_oversized(text, count_tokens_fn, max_tokens):
                raw_chunks.append({"heading": heading, "page": page, "text": piece})
            continue

        if current_texts and current_tokens + block_tokens > target_tokens:
            flush()

        current_heading = heading or current_heading
        current_page = page if page is not None else current_page
        current_texts.append(text)
        current_tokens += block_tokens

    flush()

    if not raw_chunks:
        raise ValueError("No chunks produced from the given blocks.")

    # Trailing-context overlap between consecutive chunks (word-count
    # approximation of token overlap -- close enough for a 50-token target
    # and cheap to compute without re-tokenizing the whole previous chunk).
    final_chunks = []
    previous_text = ""
    for i, raw in enumerate(raw_chunks):
        if i == 0 or overlap_tokens <= 0:
            text = raw["text"]
        else:
            overlap_words = previous_text.split()[-overlap_tokens:]
            candidate = " ".join(overlap_words) + " " + raw["text"]
            text = candidate if count_tokens_fn(candidate) <= max_tokens else raw["text"]
        final_chunks.append(
            {
                "ordinal": i,
                "heading": raw["heading"],
                "page": raw["page"],
                "text": text,
                "token_count": count_tokens_fn(text),
            }
        )
        previous_text = raw["text"]

    return final_chunks
