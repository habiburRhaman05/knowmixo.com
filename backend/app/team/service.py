"""Team members + invites (D8.6). No permission-matrix doc exists for
this sprint (confirmed absent from launch/*.md by search) -- role names
(owner/admin/agent/viewer) and the hierarchy in app.deps.require_role
are this session's from-scratch design, not a spec it implements.

V1 scope stays "one owner, one company" for OWNERS specifically
(companies.owner_user_id is still UNIQUE); invited members are the one
additive exception -- they join via membership only, never via their own
owned company. An existing user whose own email is invited to a second
company gains a second membership row, but app.auth.service.resolve_session
still prioritises their OWNED company above any invited membership, so
they will not see the invited company as their active session context
until a company-switcher ships (not in this sprint's scope).
"""
import logging

from app.email import send_invite_email
from app.security.tokens import expires_at, generate_opaque_token, hash_token

log = logging.getLogger(__name__)

INVITE_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days
INVITABLE_ROLES = {"admin", "agent", "viewer"}


class TeamError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def list_members(conn, company_id: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT u.id AS user_id, u.email, u.name, m.role, m.created_at
        FROM memberships m JOIN users u ON u.id = m.user_id
        WHERE m.company_id = %s
        ORDER BY (m.role = 'owner') DESC, m.created_at ASC
        """,
        (company_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def update_member_role(conn, company_id: str, user_id: str, new_role: str) -> dict:
    if new_role not in ("admin", "agent", "viewer"):
        raise TeamError(422, "invalid_role", "Role must be admin, agent, or viewer.")

    target = conn.execute(
        "SELECT role FROM memberships WHERE company_id = %s AND user_id = %s",
        (company_id, user_id),
    ).fetchone()
    if not target:
        raise TeamError(404, "member_not_found", "Member not found.")
    if target["role"] == "owner":
        raise TeamError(400, "cannot_change_owner_role", "The company owner's role cannot be changed here.")

    row = conn.execute(
        "UPDATE memberships SET role = %s WHERE company_id = %s AND user_id = %s RETURNING user_id, role",
        (new_role, company_id, user_id),
    ).fetchone()
    return dict(row)


def remove_member(conn, company_id: str, user_id: str) -> None:
    target = conn.execute(
        "SELECT role FROM memberships WHERE company_id = %s AND user_id = %s",
        (company_id, user_id),
    ).fetchone()
    if not target:
        raise TeamError(404, "member_not_found", "Member not found.")
    if target["role"] == "owner":
        raise TeamError(400, "cannot_remove_owner", "The company owner cannot be removed.")
    conn.execute("DELETE FROM memberships WHERE company_id = %s AND user_id = %s", (company_id, user_id))


def _check_member_quota(conn, company_id: str) -> None:
    """Billing plan-limit enforcement (K.1): `plans.limits.members` existed
    with zero enforcement. Counts existing members plus pending (not yet
    accepted/revoked/expired) invites, so a seat can't be oversold before
    the invite is even accepted."""
    from app.billing.entitlements import entitlements

    limit = entitlements(company_id).get("members")
    if limit is None:
        return
    count = conn.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM memberships WHERE company_id = %s) +
            (SELECT COUNT(*) FROM invites WHERE company_id = %s AND accepted_at IS NULL
                AND revoked_at IS NULL AND expires_at > now()) AS n
        """,
        (company_id, company_id),
    ).fetchone()["n"]
    if int(count) >= int(limit):
        raise TeamError(402, "plan_limit_members", f"Your plan allows up to {limit} team members. Upgrade to add more.")


def create_invite(conn, company_id: str, invited_by: str, email: str, role: str) -> dict:
    if role not in INVITABLE_ROLES:
        raise TeamError(422, "invalid_role", "Role must be admin, agent, or viewer.")

    _check_member_quota(conn, company_id)

    normalized = email.strip().lower()
    existing_member = conn.execute(
        """
        SELECT 1 FROM memberships m JOIN users u ON u.id = m.user_id
        WHERE m.company_id = %s AND u.normalized_email = %s
        """,
        (company_id, normalized),
    ).fetchone()
    if existing_member:
        raise TeamError(409, "already_a_member", "This person is already a member of your team.")

    token = generate_opaque_token()
    try:
        row = conn.execute(
            """
            INSERT INTO invites (company_id, email, role, token_hash, invited_by, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, email, role, expires_at, created_at
            """,
            (company_id, normalized, role, hash_token(token), invited_by, expires_at(INVITE_TTL_SECONDS)),
        ).fetchone()
    except Exception as exc:
        if "idx_invites_pending_email" in str(exc):
            raise TeamError(409, "invite_already_pending", "An invite is already pending for this email.") from exc
        raise

    company = conn.execute("SELECT name FROM companies WHERE id = %s", (company_id,)).fetchone()
    try:
        send_invite_email(normalized, token, company["name"] if company else "your team", role)
    except Exception:
        log.exception("failed to send invite email to %s", normalized)

    return dict(row)


def list_invites(conn, company_id: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, email, role, expires_at, accepted_at, revoked_at, created_at
        FROM invites WHERE company_id = %s ORDER BY created_at DESC
        """,
        (company_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def revoke_invite(conn, company_id: str, invite_id: str) -> bool:
    result = conn.execute(
        "UPDATE invites SET revoked_at = now() WHERE id = %s AND company_id = %s AND accepted_at IS NULL AND revoked_at IS NULL",
        (invite_id, company_id),
    )
    return result.rowcount > 0


def resolve_invite(conn, token: str) -> dict | None:
    row = conn.execute(
        """
        SELECT i.id, i.company_id, i.email, i.role, c.name AS company_name
        FROM invites i JOIN companies c ON c.id = i.company_id
        WHERE i.token_hash = %s AND i.accepted_at IS NULL AND i.revoked_at IS NULL AND i.expires_at > now()
        """,
        (hash_token(token),),
    ).fetchone()
    return dict(row) if row else None


def accept_invite(conn, token: str, name: str, password: str) -> str:
    """Creates a new user account (or reuses one with a matching email)
    and a membership row, then returns a fresh session token. Not wrapped
    in the caller's own transaction assumptions -- callers should run this
    inside `with connection() as conn:` so the invite consumption, user/
    membership insert and session creation commit atomically."""
    from app.auth.service import create_session
    from app.security.passwords import hash_password

    invite = resolve_invite(conn, token)
    if not invite:
        raise TeamError(410, "invite_expired", "This invite has expired, was revoked, or was already used.")

    existing_user = conn.execute(
        "SELECT id FROM users WHERE normalized_email = %s", (invite["email"],)
    ).fetchone()

    if existing_user:
        user_id = str(existing_user["id"])
    else:
        if not name or not password or len(password) < 8:
            raise TeamError(422, "account_details_required", "Name and an 8+ character password are required to accept this invite.")
        new_user = conn.execute(
            """
            INSERT INTO users (normalized_email, email, password_hash, name, email_verified_at)
            VALUES (%s, %s, %s, %s, now())
            RETURNING id
            """,
            (invite["email"], invite["email"], hash_password(password), name),
        ).fetchone()
        user_id = str(new_user["id"])

    already_member = conn.execute(
        "SELECT 1 FROM memberships WHERE company_id = %s AND user_id = %s",
        (invite["company_id"], user_id),
    ).fetchone()
    if not already_member:
        conn.execute(
            "INSERT INTO memberships (company_id, user_id, role) VALUES (%s, %s, %s)",
            (invite["company_id"], user_id, invite["role"]),
        )

    conn.execute("UPDATE invites SET accepted_at = now() WHERE id = %s", (invite["id"],))

    return create_session(conn, user_id)
