import smtplib
import ssl
from email.message import EmailMessage

from app.config import settings

# CAN-SPAM footer (K.15, launch punch list): every outbound email carries
# accurate sender identification and a postal address. These are
# transactional/relationship emails (account verification, password
# reset, team invites, escalation/alert notifications) tied to an action
# the recipient took or an account they hold, which CAN-SPAM treats more
# leniently than bulk commercial email -- no unsubscribe link is legally
# required for this category -- but identification + a valid address are
# required regardless of category, so both are included here centrally
# rather than left to each call site to remember.
#
# COMPANY_POSTAL_ADDRESS is a placeholder: replace with the real
# registered business address before launch. Sending bulk commercial
# email (marketing, not transactional) without a real one is a genuine
# CAN-SPAM violation, not just a formality.
COMPANY_POSTAL_ADDRESS = "Knowmivo, Inc. · [ADD REAL MAILING ADDRESS BEFORE LAUNCH]"


def _append_footer(body: str) -> str:
    return f"{body}\n\n---\nKnowmivo · {COMPANY_POSTAL_ADDRESS}\nYou're receiving this because of an action on your Knowmivo account."


def send_email(to: str, subject: str, body: str) -> None:
    s = settings()
    full_body = _append_footer(body)
    if not s.smtp_user or not s.smtp_app_password:
        # Dev fallback when SMTP isn't configured: never silently drop a
        # verification/reset email during local development.
        print(f"[email:dev-noop] to={to} subject={subject}\n{full_body}\n")
        return

    msg = EmailMessage()
    msg["From"] = s.email_from or s.smtp_user
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(full_body)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(s.smtp_user, s.smtp_app_password)
        server.send_message(msg)


def send_verification_email(to: str, token: str) -> None:
    link = f"{settings().public_app_url}/verify-email?token={token}"
    send_email(
        to=to,
        subject="Verify your Knowmivo email",
        body=f"Confirm your email to finish setting up your Knowmivo account:\n\n{link}\n\nThis link expires in 24 hours.",
    )


def send_password_reset_email(to: str, token: str) -> None:
    link = f"{settings().public_app_url}/reset-password?token={token}"
    send_email(
        to=to,
        subject="Reset your Knowmivo password",
        body=f"Reset your password using this link:\n\n{link}\n\nThis link expires in 1 hour. If you did not request this, ignore this email.",
    )


def send_email_change_confirmation(to: str, token: str) -> None:
    link = f"{settings().public_app_url}/confirm-email-change?token={token}"
    send_email(
        to=to,
        subject="Confirm your new Knowmivo email address",
        body=f"Confirm this address as your new Knowmivo login email:\n\n{link}\n\nThis link expires in 24 hours.",
    )


def send_invite_email(to: str, token: str, company_name: str, role: str) -> None:
    link = f"{settings().public_app_url}/accept-invite?token={token}"
    send_email(
        to=to,
        subject=f"You've been invited to join {company_name} on Knowmivo",
        body=f"You've been invited to join {company_name} as a {role}.\n\nAccept the invite:\n\n{link}\n\nThis link expires in 7 days.",
    )
