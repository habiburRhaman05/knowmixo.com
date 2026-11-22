"""Chunker unit tests using a fake word-count tokenizer -- no network
call to download the real BGE-M3 tokenizer (docs/11-AGENT-RULES.md rule
6). Word count is a reasonable 1:1 stand-in for token count at this
granularity of test."""
import pytest

from app.ingestion.chunker import chunk_blocks


def _word_count(text: str) -> int:
    return len(text.split())


def test_small_input_produces_one_chunk():
    blocks = [{"heading": "Intro", "page": 1, "text": "A short paragraph."}]
    chunks = chunk_blocks(blocks, count_tokens_fn=_word_count, target_tokens=350, overlap_tokens=50, max_tokens=512)
    assert len(chunks) == 1
    assert chunks[0]["ordinal"] == 0
    assert chunks[0]["heading"] == "Intro"
    assert chunks[0]["page"] == 1


def test_accumulates_blocks_until_target_then_splits():
    blocks = [{"heading": None, "page": None, "text": " ".join(["word"] * 100)} for _ in range(5)]
    chunks = chunk_blocks(blocks, count_tokens_fn=_word_count, target_tokens=150, overlap_tokens=0, max_tokens=512)
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk["token_count"] <= 512


def test_oversized_single_block_is_split_to_respect_max_tokens():
    huge_block = [{"heading": None, "page": None, "text": " ".join(["word"] * 1000)}]
    chunks = chunk_blocks(huge_block, count_tokens_fn=_word_count, target_tokens=350, overlap_tokens=0, max_tokens=512)
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk["token_count"] <= 512


def test_overlap_is_applied_between_consecutive_chunks():
    blocks = [{"heading": None, "page": None, "text": " ".join([f"w{i}" for i in range(j * 100, j * 100 + 100)])} for j in range(3)]
    chunks = chunk_blocks(blocks, count_tokens_fn=_word_count, target_tokens=100, overlap_tokens=20, max_tokens=512)
    assert len(chunks) >= 2
    # Chunk 1 should start with some trailing words from chunk 0.
    chunk0_last_words = chunks[0]["text"].split()[-20:]
    chunk1_first_words = chunks[1]["text"].split()[:20]
    assert any(w in chunk1_first_words for w in chunk0_last_words)


def test_ordinals_are_sequential_and_zero_indexed():
    blocks = [{"heading": None, "page": None, "text": f"paragraph {i}"} for i in range(10)]
    chunks = chunk_blocks(blocks, count_tokens_fn=_word_count, target_tokens=2, overlap_tokens=0, max_tokens=512)
    assert [c["ordinal"] for c in chunks] == list(range(len(chunks)))


def test_empty_blocks_raise_value_error():
    with pytest.raises(ValueError):
        chunk_blocks([{"heading": None, "page": None, "text": "   "}], count_tokens_fn=_word_count)


def test_heading_carries_forward_to_following_unheaded_blocks():
    blocks = [
        {"heading": "Section A", "page": None, "text": "first line"},
        {"heading": None, "page": None, "text": "second line, no new heading"},
    ]
    chunks = chunk_blocks(blocks, count_tokens_fn=_word_count, target_tokens=350, overlap_tokens=0, max_tokens=512)
    assert chunks[0]["heading"] == "Section A"
