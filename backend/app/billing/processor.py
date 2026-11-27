"""Stripe event processor (launch/09-BILLING-PAYMENTS.md §4).
Reads unprocessed rows from `stripe_events` and upserts subscriptions,
invoices, fires dunning emails, etc. Called by the job runner.
"""
import json
import logging
from datetime import datetime, timezone

from app.billing.entitlements import invalidate_entitlements
from app.db import connection

log = logging.getLogger(__name__)

_HANDLED_TYPES = {
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.paid",
    "invoice.payment_failed",
    "checkout.session.completed",
    "customer.subscription.trial_will_end",
}


def process_pending_events(batch_size: int = 50) -> int:
    processed = 0
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT event_id, type, created_at, payload
            FROM stripe_events
            WHERE processed_at IS NULL
            ORDER BY received_at ASC
            LIMIT %s
            """,
            (batch_size,),
        ).fetchall()

        for row in rows:
            event_id = row["event_id"]
            event_type = row["type"]
            try:
                payload = row["payload"] if isinstance(row["payload"], dict) else json.loads(row["payload"])
                data_obj = payload.get("data", {}).get("object", {})

                if event_type in ("customer.subscription.created", "customer.subscription.updated"):
                    _upsert_subscription(conn, data_obj, row["created_at"])
                elif event_type == "customer.subscription.deleted":
                    _cancel_subscription(conn, data_obj)
                elif event_type == "invoice.paid":
                    _record_invoice(conn, data_obj, "paid")
                elif event_type == "invoice.payment_failed":
                    _record_invoice(conn, data_obj, "payment_failed")
                    _enqueue_dunning(conn, data_obj)
                elif event_type == "checkout.session.completed":
                    _handle_checkout_completed(conn, data_obj)
                elif event_type == "customer.subscription.trial_will_end":
                    log.info("trial_will_end for %s", data_obj.get("customer"))

                conn.execute(
                    "UPDATE stripe_events SET processed_at = now() WHERE event_id = %s",
                    (event_id,),
                )
                processed += 1
            except Exception:
                log.exception("failed to process stripe event %s", event_id)

    return processed


def _resolve_company_id(conn, stripe_customer_id: str) -> str | None:
    row = conn.execute(
        "SELECT company_id FROM subscriptions WHERE stripe_customer_id = %s LIMIT 1",
        (stripe_customer_id,),
    ).fetchone()
    return str(row["company_id"]) if row else None


def _lookup_key_to_plan_id(conn, lookup_key: str) -> str | None:
    if not lookup_key:
        return None
    row = conn.execute(
        "SELECT id FROM plans WHERE stripe_lookup_key = %s", (lookup_key,)
    ).fetchone()
    return row["id"] if row else None


def _upsert_subscription(conn, sub: dict, event_created_at: datetime) -> None:
    stripe_sub_id = sub.get("id")
    stripe_customer_id = sub.get("customer")
    status = sub.get("status", "active")

    items = sub.get("items", {}).get("data", [])
    plan_id = None
    if items:
        price = items[0].get("price", {})
        plan_id = _lookup_key_to_plan_id(conn, price.get("lookup_key"))
    if not plan_id:
        plan_id = "free"

    period_start = _ts(sub.get("current_period_start"))
    period_end = _ts(sub.get("current_period_end"))
    cancel_at_period_end = sub.get("cancel_at_period_end", False)

    existing = conn.execute(
        "SELECT updated_at FROM subscriptions WHERE stripe_subscription_id = %s",
        (stripe_sub_id,),
    ).fetchone()
    if existing and existing["updated_at"] and existing["updated_at"] >= event_created_at:
        return  # out-of-order event

    conn.execute(
        """
        INSERT INTO subscriptions (stripe_customer_id, stripe_subscription_id, plan_id, status,
            current_period_start, current_period_end, cancel_at_period_end, company_id)
        SELECT %s, %s, %s, %s, %s, %s, %s, s.company_id
        FROM subscriptions s WHERE s.stripe_customer_id = %s LIMIT 1
        ON CONFLICT (stripe_subscription_id) DO UPDATE SET
            plan_id = EXCLUDED.plan_id,
            status = EXCLUDED.status,
            current_period_start = EXCLUDED.current_period_start,
            current_period_end = EXCLUDED.current_period_end,
            cancel_at_period_end = EXCLUDED.cancel_at_period_end,
            updated_at = now()
        """,
        (
            stripe_customer_id, stripe_sub_id, plan_id, status,
            period_start, period_end, cancel_at_period_end,
            stripe_customer_id,
        ),
    )

    company_id = _resolve_company_id(conn, stripe_customer_id)
    if company_id:
        invalidate_entitlements(company_id)


def _cancel_subscription(conn, sub: dict) -> None:
    stripe_sub_id = sub.get("id")
    stripe_customer_id = sub.get("customer")
    conn.execute(
        "UPDATE subscriptions SET status = 'canceled', updated_at = now() WHERE stripe_subscription_id = %s",
        (stripe_sub_id,),
    )
    company_id = _resolve_company_id(conn, stripe_customer_id)
    if company_id:
        invalidate_entitlements(company_id)


def _record_invoice(conn, inv: dict, status: str) -> None:
    stripe_invoice_id = inv.get("id")
    stripe_customer_id = inv.get("customer")
    company_id = _resolve_company_id(conn, stripe_customer_id)
    if not company_id:
        log.warning("no company for customer %s, skipping invoice %s", stripe_customer_id, stripe_invoice_id)
        return
    amount_cents = inv.get("amount_paid", inv.get("amount_due", 0))
    conn.execute(
        """
        INSERT INTO invoices (company_id, stripe_invoice_id, amount_cents, status,
            hosted_url, pdf_url, period_start, period_end)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (stripe_invoice_id) DO UPDATE SET status = EXCLUDED.status, hosted_url = EXCLUDED.hosted_url, pdf_url = EXCLUDED.pdf_url
        """,
        (
            company_id, stripe_invoice_id, amount_cents, status,
            inv.get("hosted_invoice_url"), inv.get("invoice_pdf"),
            _ts(inv.get("period_start")), _ts(inv.get("period_end")),
        ),
    )


def _enqueue_dunning(conn, inv: dict) -> None:
    from app.jobs.queue import enqueue_job
    stripe_customer_id = inv.get("customer")
    company_id = _resolve_company_id(conn, stripe_customer_id)
    if company_id:
        enqueue_job(
            conn, company_id, "send_dunning_email",
            payload={"stripe_invoice_id": inv.get("id"), "attempt": inv.get("attempt_count", 1)},
        )


def _handle_checkout_completed(conn, session: dict) -> None:
    stripe_customer_id = session.get("customer")
    stripe_sub_id = session.get("subscription")
    company_id_meta = (session.get("metadata") or {}).get("company_id")

    if company_id_meta and stripe_customer_id:
        existing = conn.execute(
            "SELECT id FROM subscriptions WHERE company_id = %s::uuid LIMIT 1",
            (company_id_meta,),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE subscriptions SET stripe_customer_id = %s, stripe_subscription_id = %s,
                    status = 'active', updated_at = now()
                WHERE id = %s
                """,
                (stripe_customer_id, stripe_sub_id, existing["id"]),
            )
        else:
            conn.execute(
                """
                INSERT INTO subscriptions (company_id, stripe_customer_id, stripe_subscription_id, plan_id, status)
                VALUES (%s::uuid, %s, %s, 'free', 'active')
                """,
                (company_id_meta, stripe_customer_id, stripe_sub_id),
            )
        invalidate_entitlements(company_id_meta)


def _ts(unix_ts) -> datetime | None:
    if unix_ts is None:
        return None
    return datetime.fromtimestamp(int(unix_ts), tz=timezone.utc)
