"""Independent Google ID token validation.

Per docs/03-TRD.md: "The Google callback exchanges its ID token with
FastAPI, which validates it independently against the configured Google
client ID." We never trust a client-asserted email/subject -- only the
cryptographically verified claims from Google's own library.
"""
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.config import settings

_VALID_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
_request = google_requests.Request()


class GoogleTokenError(ValueError):
    pass


def verify_google_id_token(token: str) -> dict:
    """Returns verified claims (sub, email, email_verified, ...).

    Raises GoogleTokenError on any forged, expired, wrong-audience or
    wrong-issuer token, or an unverified Google email.
    """
    client_id = settings().google_client_id
    if not client_id:
        raise GoogleTokenError("Google sign-in is not configured")

    try:
        claims = google_id_token.verify_oauth2_token(token, _request, client_id)
    except Exception as exc:  # noqa: BLE001 -- library raises several distinct types
        raise GoogleTokenError("Invalid Google ID token") from exc

    if claims.get("iss") not in _VALID_ISSUERS:
        raise GoogleTokenError("Invalid token issuer")
    if not claims.get("email_verified"):
        raise GoogleTokenError("Google account email is not verified")
    if not claims.get("email") or not claims.get("sub"):
        raise GoogleTokenError("Google token missing required claims")

    return claims
