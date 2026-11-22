"""BGE-M3-compatible tokenizer for token-aware chunking (docs/03-TRD.md:
"Use a tokenizer compatible with BGE-M3, not character-count
assumptions"). Loaded lazily and cached process-wide so it only downloads
once per machine. Tests inject a cheap fake counter instead of pulling
this down over the network, per docs/11-AGENT-RULES.md rule 6.
"""
from functools import lru_cache


@lru_cache
def _tokenizer():
    from tokenizers import Tokenizer

    return Tokenizer.from_pretrained("BAAI/bge-m3")


def count_tokens(text: str) -> int:
    return len(_tokenizer().encode(text).ids)
