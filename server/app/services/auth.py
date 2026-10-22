import hashlib
import hmac
from typing import Optional
from fastapi import Header, HTTPException, Depends, status
from sqlalchemy.orm import Session
from server.app.database import get_db
from server.app.models.api_key import ApiKey
from server.app.config import settings


def hash_api_key(key: str) -> str:
    """Return SHA-256 hash of an API key."""
    return hashlib.sha256(key.strip().encode("utf-8")).hexdigest()


def seed_default_api_key(db: Session) -> ApiKey:
    """Ensure a default API key exists in the database."""
    default_hash = hash_api_key(settings.DEFAULT_API_KEY)
    key_record = db.query(ApiKey).filter(ApiKey.key_hash == default_hash).first()
    if not key_record:
        key_record = ApiKey(
            key_hash=default_hash,
            label="default-agent",
            is_active=True,
        )
        db.add(key_record)
        db.commit()
        db.refresh(key_record)
    return key_record


def verify_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> ApiKey:
    """
    Authenticate request using X-API-Key header.
    Looks up SHA-256 hash in api_keys table.
    Default dev key is only accepted/seeded when ENV is 'dev' or 'test'.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )

    # Dev key is strictly rejected in non-dev/non-test environments
    is_dev_env = getattr(settings, "ENV", "dev").lower() in ("dev", "test")
    if not is_dev_env and x_api_key == settings.DEFAULT_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or revoked API key: default dev key is disabled in non-dev environments",
        )

    key_hash = hash_api_key(x_api_key)
    api_key_record = db.query(ApiKey).filter(
        ApiKey.key_hash == key_hash,
        ApiKey.is_active == True,
    ).first()

    if not api_key_record:
        if is_dev_env and x_api_key == settings.DEFAULT_API_KEY:
            api_key_record = seed_default_api_key(db)
        else:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid or revoked API key",
            )

    return api_key_record


def verify_admin_token(
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
) -> str:
    """
    Authenticate request using X-Admin-Token header.
    Required for policy upload, rollback, and approval decisions.
    Fails with 500 if server has no ADMIN_TOKEN configured.
    """
    configured_admin_token = getattr(settings, "ADMIN_TOKEN", None)
    if not configured_admin_token or not configured_admin_token.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server administrator token is not configured",
        )

    if not x_admin_token or not hmac.compare_digest(
        x_admin_token.strip().encode("utf-8"),
        configured_admin_token.strip().encode("utf-8"),
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing X-Admin-Token",
        )
    return x_admin_token

