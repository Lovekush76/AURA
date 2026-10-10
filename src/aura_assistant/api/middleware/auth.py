"""
Aura Assistant - Enterprise Security & Auth Middleware
Enforces Epic E-07: Scoped API tokens, header authentication, SQLite ApiKey verification,
and dual append-only file + SQLite audit logging.
"""

import os
import time
import logging
from pathlib import Path
from fastapi import Request, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from aura_assistant.core.db.session import verify_api_key_in_db, persist_audit_orm

logger = logging.getLogger("aura-auth-middleware")

security = HTTPBearer(auto_error=False)
AUDIT_LOG_FILE = Path("data/logs/audit.log")

def get_expected_token() -> str:
    return os.environ.get("AURA_API_KEY", "aura_sec_default_change_me")

def is_valid_token(token: str) -> bool:
    if not token:
        return False
    if token == get_expected_token():
        return True
    return verify_api_key_in_db(token)

def log_audit_event(action: str, client_ip: str, user_identity: str, status: str, details: str = ""):
    """Appends an immutable audit event to disk and SQLite audit_logs table."""
    AUDIT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ')} | IP={client_ip} | USER={user_identity} | ACTION={action} | STATUS={status} | {details}\n"
    try:
        with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception as e:
        logger.error(f"Failed to append to audit log: {e}")

    persist_audit_orm(
        action=action,
        details={"ip": client_ip, "user": user_identity, "status": status, "info": details}
    )

async def verify_auth_token(credentials: HTTPAuthorizationCredentials = Security(security), request: Request = None) -> str:
    """Validates Bearer API token against environment variable and SQLite ApiKey table."""
    client_ip = request.client.host if request and request.client else "unknown"
    token = credentials.credentials if credentials else ""

    if not is_valid_token(token):
        log_audit_event("AUTH_ATTEMPT", client_ip, "anonymous", "DENIED", "Invalid or missing token")
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid API token")

    log_audit_event("AUTH_ATTEMPT", client_ip, "authenticated_user", "SUCCESS", "")
    return "authenticated_user"
