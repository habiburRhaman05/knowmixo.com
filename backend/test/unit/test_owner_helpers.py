"""Pure-logic tests for origin allowlisting, domain validation, cursors,
embed snippets, export allowlists, idempotency fingerprinting and the quota
arithmetic -- no database required."""
from datetime import datetime, timezone

import pytest

from app.bots import history
from app.bots.service import BotError
from app.idempotency import fingerprint
from app.public.router import origin_allowed


@pytest.mark.parametrize(
    "allowed,origin,ok",
    [
        ([], None, True),  # no restriction configured
        ([], "https://anything.com", True),
        (["example.com"], "https://example.com", True),
        (["example.com"], "https://example.com:8443", True),
        (["example.com"], "https://evil.com", False),
        (["example.com"], "https://example.com.evil.com", False),
        (["example.com"], "https://sub.example.com", False),  # exact match unless wildcard
        (["*.example.com"], "https://shop.example.com", True),
        (["*.example.com"], "https://example.com", False),
        (["*.example.com"], "https://notexample.com", False),
        (["example.com"], None, False),  # allowlist set + no Origin header = rejected
        (["example.com"], "null", False),
    ],
)
def test_origin_allowlist(allowed, origin, ok):
    assert origin_allowed(allowed, origin) is ok


def test_domain_normalisation_accepts_valid_and_dedupes():
    assert history.normalize_domains(["Example.com", "example.com", "*.shop.example.org", "localhost"]) == [
        "example.com", "*.shop.example.org", "localhost",
    ]


@pytest.mark.parametrize("bad", ["https://example.com", "example.com/path", "exa mple.com", "", "*example.com", "-a.com", "a..com"])
def test_domain_normalisation_rejects_bad_input(bad):
    with pytest.raises(BotError) as exc:
        history.normalize_domains([bad])
    assert exc.value.code == "invalid_domain"


def test_domain_cap():
    with pytest.raises(BotError) as exc:
        history.normalize_domains([f"d{i}.example.com" for i in range(history.MAX_DOMAINS + 1)])
    assert exc.value.code == "too_many_domains"


def test_cursor_round_trip_and_tamper_rejection():
    ts = datetime(2026, 11, 24, 10, 0, tzinfo=timezone.utc)
    rid = "6f1c2f0e-3b9a-4a43-9d57-0a0a0a0a0a0a"
    assert history.decode_cursor(history.encode_cursor(ts, rid)) == (ts, rid)
    for bad in ("garbage", "", history.encode_cursor(ts, "not-a-uuid")):
        with pytest.raises(BotError) as exc:
            history.decode_cursor(bad)
        assert exc.value.status_code == 400


def test_embed_snippets_expose_public_id_only(monkeypatch):
    out = history.embed_snippets("pub_abc123")
    assert set(out) == {"public_id", "script_snippet", "react_snippet", "nextjs_snippet", "hosted_chat_url"}
    blob = " ".join(out.values())
    assert "pub_abc123" in blob
    for secret_word in ("key", "token", "secret", "password"):
        assert secret_word not in blob.lower().replace("public_id", "")


def test_idempotency_fingerprint_is_order_independent_and_content_sensitive():
    assert fingerprint({"a": 1, "b": [1, 2]}) == fingerprint({"b": [1, 2], "a": 1})
    assert fingerprint(["v1"]) != fingerprint(["v2"])


def test_idempotent_runner_replays_and_rejects_key_reuse():
    from app.idempotency import run_idempotent

    class Store:
        def __init__(self):
            self.rows = {}
            self.last = None

        def execute(self, sql, params=()):
            self.last = sql
            store = self

            class R:
                def fetchone(self_inner):
                    if "FROM idempotency_keys" in sql:
                        k = (params[0], params[1], params[2])
                        return store.rows.get(k)
                    return None

            if "INSERT INTO idempotency_keys" in sql:
                company, scope, key, fp, _status, response = params
                import json

                store.rows[(company, scope, key)] = {"request_fingerprint": fp, "response": json.loads(response)}
            return R()

    conn, calls = Store(), []

    def action():
        calls.append(1)
        return {"publication_id": "p1"}

    first, replayed1 = run_idempotent(conn, "c", "bot.publish", "k1", ["v1"], action)
    second, replayed2 = run_idempotent(conn, "c", "bot.publish", "k1", ["v1"], action)
    assert (first, replayed1, second, replayed2) == ({"publication_id": "p1"}, False, {"publication_id": "p1"}, True)
    assert len(calls) == 1  # side effect ran exactly once

    with pytest.raises(BotError) as exc:
        run_idempotent(conn, "c", "bot.publish", "k1", ["DIFFERENT"], action)
    assert exc.value.status_code == 409 and exc.value.code == "idempotency_key_reuse"

    run_idempotent(conn, "c", "bot.publish", None, ["v1"], action)  # no key = always runs
    assert len(calls) == 2


def test_quota_reset_is_next_utc_midnight():
    from app.chat import quota

    reset = quota.next_reset_at()
    assert reset > datetime.now(timezone.utc) and (reset.hour, reset.minute, reset.second) == (0, 0, 0)
    assert 1 <= quota._seconds_until_reset() <= 86400  # noqa: SLF001


def test_audit_context_is_isolated_between_concurrent_requests():
    import threading
    import time

    from app.audit.service import audit_context, audit_request_context

    seen = {}

    def worker(name):
        with audit_request_context(name, "company", "owner", name):
            time.sleep(0.03)
            seen[name] = (audit_context.request_id, audit_context.actor_id)

    threads = [threading.Thread(target=worker, args=(f"req{i}",)) for i in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert all(v == (k, k) for k, v in seen.items())
