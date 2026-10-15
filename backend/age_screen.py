"""Short-lived adult self-registration proofs; no birth dates are collected."""
import hashlib
import hmac
import secrets
import time

from fastapi import HTTPException
from auth import _secret

COOKIE = "forma_age_screen"
ELIGIBLE_SECONDS = 600
BLOCKED_SECONDS = 86400


def issue_proof(eligible: bool) -> str:
    body = f"v1.{'eligible' if eligible else 'blocked'}.{int(time.time())}.{secrets.token_hex(16)}"
    signature = hmac.new(_secret(), ("age-screen:" + body).encode(), hashlib.sha256).hexdigest()
    return body + "." + signature


def proof_state(token: str | None) -> str | None:
    if not token or len(token) > 200:
        return None
    try:
        version, state, issued, nonce, signature = token.split(".")
        body = ".".join((version, state, issued, nonce))
        expected = hmac.new(_secret(), ("age-screen:" + body).encode(), hashlib.sha256).hexdigest()
        lifetime = ELIGIBLE_SECONDS if state == "eligible" else BLOCKED_SECONDS
        elapsed = int(time.time()) - int(issued)
        if version == "v1" and state in {"eligible", "blocked"} and 0 <= elapsed < lifetime and hmac.compare_digest(signature, expected):
            return state
    except (ValueError, TypeError):
        pass
    return None


def require_eligible(token: str, cookie: str | None):
    if proof_state(token) != "eligible" or proof_state(cookie) != "eligible" or not hmac.compare_digest(token, cookie or ""):
        raise HTTPException(403, "Complete the age check before registration.")
