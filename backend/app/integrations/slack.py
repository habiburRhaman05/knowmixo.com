"""Slack app: OAuth install flow + alerts channel delivery (D9.5).
No live Slack app is registered yet (slack_client_id/secret blank in
dev) -- install/callback return a clear 503 rather than failing
obscurely, same no-op pattern as the other optional providers (Stripe,
WhatsApp)."""
import hashlib
import hmac
import logging
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.db import connection

log = logging.getLogger(__name__)

SLACK_OAUTH_AUTHORIZE_URL = "https://slack.com/oauth/v2/authorize"
SLACK_OAUTH_ACCESS_URL = "https://slack.com/api/oauth.v2.access"
SLACK_POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"
SLACK_SCOPES = "incoming-webhook,chat:write"


class SlackError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def _sign_state(company_id: str) -> str:
    secret = settings().auth_secret.encode()
    sig = hmac.new(secret, company_id.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{company_id}.{sig}"


def _verify_state(state: str) -> str | None:
    try:
        company_id, sig = state.rsplit(".", 1)
    except ValueError:
        return None
    expected = _sign_state(company_id).split(".", 1)[1]
    if not hmac.compare_digest(expected, sig):
        return None
    return company_id


def install_url(company_id: str) -> str:
    s = settings()
    if not s.slack_client_id:
        raise SlackError(503, "slack_not_configured", "Slack integration is not configured.")
    redirect_uri = f"{s.backend_internal_url}/api/v1/integrations/slack/callback"
    params = {
        "client_id": s.slack_client_id,
        "scope": SLACK_SCOPES,
        "redirect_uri": redirect_uri,
        "state": _sign_state(company_id),
    }
    return f"{SLACK_OAUTH_AUTHORIZE_URL}?{urlencode(params)}"


def complete_install(code: str, state: str, installed_by: str | None) -> str:
    """Returns the company_id the installation was attached to, or
    raises SlackError. Called from the public OAuth callback -- state is
    the only thing tying this request back to a company."""
    s = settings()
    if not s.slack_client_id or not s.slack_client_secret:
        raise SlackError(503, "slack_not_configured", "Slack integration is not configured.")

    company_id = _verify_state(state)
    if not company_id:
        raise SlackError(401, "invalid_state", "Invalid or tampered OAuth state.")

    redirect_uri = f"{s.backend_internal_url}/api/v1/integrations/slack/callback"
    resp = httpx.post(
        SLACK_OAUTH_ACCESS_URL,
        data={
            "client_id": s.slack_client_id,
            "client_secret": s.slack_client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        },
        timeout=10,
    )
    data = resp.json()
    if not data.get("ok"):
        raise SlackError(400, "slack_oauth_failed", data.get("error", "Slack OAuth exchange failed."))

    team = data.get("team", {})
    incoming_webhook = data.get("incoming_webhook", {})

    with connection() as conn:
        conn.execute(
            """
            INSERT INTO slack_installations (company_id, team_id, team_name, access_token, bot_user_id, incoming_webhook_url, incoming_webhook_channel, installed_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (company_id) DO UPDATE SET
                team_id = EXCLUDED.team_id, team_name = EXCLUDED.team_name,
                access_token = EXCLUDED.access_token, bot_user_id = EXCLUDED.bot_user_id,
                incoming_webhook_url = EXCLUDED.incoming_webhook_url,
                incoming_webhook_channel = EXCLUDED.incoming_webhook_channel
            """,
            (
                company_id, team.get("id"), team.get("name"), data.get("access_token"),
                data.get("bot_user_id"), incoming_webhook.get("url"), incoming_webhook.get("channel"),
                installed_by,
            ),
        )
    return company_id


def get_installation(company_id: str) -> dict | None:
    with connection() as conn:
        row = conn.execute(
            "SELECT team_name, incoming_webhook_channel, created_at FROM slack_installations WHERE company_id = %s",
            (company_id,),
        ).fetchone()
        return dict(row) if row else None


def uninstall(company_id: str) -> bool:
    with connection() as conn:
        result = conn.execute("DELETE FROM slack_installations WHERE company_id = %s", (company_id,))
        return result.rowcount > 0


def post_alert(company_id: str, text: str) -> bool:
    """Posts to the installed incoming webhook. Best-effort: a Slack
    delivery failure must never break the alert rule that triggered it
    (email already fired via app.quality.alerts._notify)."""
    with connection() as conn:
        row = conn.execute(
            "SELECT incoming_webhook_url FROM slack_installations WHERE company_id = %s",
            (company_id,),
        ).fetchone()
    if not row or not row["incoming_webhook_url"]:
        return False
    try:
        resp = httpx.post(row["incoming_webhook_url"], json={"text": text}, timeout=10)
        return resp.status_code == 200
    except Exception:
        log.exception("failed to post Slack alert for company %s", company_id)
        return False
