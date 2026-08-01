from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import encrypt_sensitive_data, decrypt_sensitive_data
from app.db.session import get_db

router = APIRouter()


@router.get("/health", response_model=Dict[str, Any])
async def health_check(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """
    System Health Check Endpoint.
    Verifies database connectivity, 152-FZ encryption integrity, and service version.
    """
    db_status = "ok"
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"error: {str(e)}"

    # Perform 152-FZ AES-256-GCM test
    test_str = "Test PII Data 152-FZ"
    encrypted = encrypt_sensitive_data(test_str)
    decrypted = decrypt_sensitive_data(encrypted)
    crypto_status = "ok" if decrypted == test_str else "error"

    return {
        "status": "online",
        "app_name": settings.PROJECT_NAME,
        "compliance_152_fz": {
            "enabled": settings.COMPLIANCE_152_FZ_ENABLED,
            "crypto_aes256_gcm": crypto_status,
        },
        "database": db_status,
    }
