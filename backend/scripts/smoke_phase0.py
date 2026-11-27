"""Phase 0 exit gate (docs/19): one script that proves every external
dependency is reachable with the real credentials in .env --
Postgres (Neon), Redis, Pinecone, Cloudflare embeddings, Groq chat.

Usage (from backend/): python scripts/smoke_phase0.py
Makes exactly one tiny call to each free-tier service. Prints PASS/FAIL per
dependency and never prints a credential. Exit code 0 only if all pass.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def check_postgres():
    from app.db import connection

    with connection() as conn:
        assert conn.execute("SELECT 1 AS ok").fetchone()["ok"] == 1
        conn.execute("SELECT 1 FROM alembic_version").fetchone()  # migrations applied


def check_redis():
    from app.redis_resilience import get_redis

    assert get_redis().ping()


def check_pinecone():
    from app.providers.vector_store import ping

    assert ping()


def check_embeddings():
    from app.config import settings
    from app.providers.embeddings import embed_batch

    vectors = embed_batch(["knowmivo smoke test"])
    assert len(vectors) == 1 and len(vectors[0]) == settings().embedding_dim


def check_llm():
    import asyncio

    from app.chat import llm

    async def run():
        out = ""
        async for piece in llm.stream_completion([{"role": "user", "content": "Reply with the single word: pong"}]):
            out += piece
        return out

    assert asyncio.run(run()).strip()


CHECKS = [("postgres", check_postgres), ("redis", check_redis), ("pinecone", check_pinecone),
          ("cloudflare-embeddings", check_embeddings), ("groq-llm", check_llm)]


def main() -> int:
    failed = 0
    for name, fn in CHECKS:
        started = time.monotonic()
        try:
            fn()
            print(f"PASS  {name:<22} {time.monotonic() - started:.2f}s")
        except Exception as exc:  # noqa: BLE001 - print only the exception TYPE, messages can embed URLs/keys
            failed += 1
            print(f"FAIL  {name:<22} {type(exc).__name__}")
    print("ALL PASS" if not failed else f"{failed} FAILED")

    # One-shot CLI: close the Postgres pool ourselves. Otherwise the
    # interpreter's own shutdown GC runs ConnectionPool.__del__, which on
    # Python 3.13+ tries to join a background thread during finalization
    # and raises a harmless-but-alarming PythonFinalizationError.
    try:
        from app.postgres_resilience import reset_pg

        reset_pg()
    except Exception:  # noqa: BLE001 - never let cleanup mask the real result
        pass

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
