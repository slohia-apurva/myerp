"""Checks a "Sign in with Google" credential (an ID token) on the server."""

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


def verify_credential(credential: str, client_id: str) -> dict:
    """Returns the token's claims, or raises ValueError if it is not a valid,
    unexpired token that Google issued for our client id."""
    claims = id_token.verify_oauth2_token(credential, google_requests.Request(), client_id)
    if claims.get("iss") not in ISSUERS:
        raise ValueError("Wrong issuer")
    return claims
