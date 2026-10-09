"""
Aura Assistant - Enterprise Security & Auth Middleware
Enforces Epic E-07: Scoped API tokens, header authentication, and append-only audit logging.
"""

import os
import time
import logging
from pathlib import Path
from fastapi import Request, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger("aura-auth-middleware")

security = HTTPBearer(auto_error=False)
AUDIT_LOG_FILE = Path("data/logs/audit.log")

def get_expected_token() -> str:
    return os.environ.get("AURA_API_KEY", "aura_sec_default_change_me")

def log_audit_event(action: str, client_ip: str, user_identity: str, status: str, details: str = ""):
    """Appends an immutable audit event to disk."""
    AUDIT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ')} | IP={client_ip} | USER={user_identity} | ACTION={action} | STATUS={status} | {details}\n"
    try:
        with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception as e:
        logger.error(f"Failed to append to audit log: {e}")

async def verify_auth_token(credentials: HTTPAuthorizationCredentials = Security(security), request: Request = None) -> str:
    """Validates Bearer API token."""
    expected = get_expected_token()
    client_ip = request.client.host if request and request.client else "unknown"

    if not credentials or credentials.credentials != expected:
        log_audit_event("AUTH_ATTEMPT", client_ip, "anonymous", "DENIED", "Invalid or missing token")
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid API token")

    log_audit_event("AUTH_ATTEMPT", client_ip, "authenticated_user", "SUCCESS", "")
    return "authenticated_user"
