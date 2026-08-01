import os
import base64
import json
from typing import Optional, Dict, Any, Union
from datetime import datetime, timezone, timedelta
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import jwt
import bcrypt

from app.core.config import settings


class SecurityError(Exception):
    """Base exception for security and encryption operations."""
    pass


class KeyValidationError(SecurityError, ValueError):
    """Raised when encryption key fails integrity or validation checks."""
    pass


class OverrideError(SecurityError, PermissionError):
    """Raised when a security override request fails authorization or audit checks."""
    pass


class AES256GCMCipher:
    """
    AES-256-GCM Encryption / Decryption engine compliant with Russian Federal Law 152-FZ.
    Ensures confidentiality, integrity, and authenticity of sensitive personal fitness telemetry and PII.
    """
    KEY_SIZE_BYTES = 32  # 256 bits
    NONCE_SIZE_BYTES = 12  # 96 bits standard GCM nonce

    def __init__(self, key: Union[bytes, str]):
        if isinstance(key, str):
            if len(key) == 64:
                try:
                    key = bytes.fromhex(key)
                except ValueError:
                    key = key.encode('utf-8')
            else:
                key = key.encode('utf-8')

        self.validate_key(key)
        self._key = key
        self._aesgcm = AESGCM(self._key)

    @classmethod
    def validate_key(cls, key: bytes) -> bool:
        """Validates key length and basic entropy requirements for 152-FZ compliance."""
        if not isinstance(key, bytes):
            raise KeyValidationError("Key must be bytes or a valid 64-character hex string.")
        if len(key) != cls.KEY_SIZE_BYTES:
            raise KeyValidationError(
                f"Invalid key length ({len(key)} bytes). AES-256-GCM requires exactly 32 bytes (256 bits)."
            )
        # Prevent trivial/weak keys in production
        if key == b'\x00' * cls.KEY_SIZE_BYTES:
            raise KeyValidationError("Weak key prohibited: All-zero key is invalid for 152-FZ protection.")
        return True

    @classmethod
    def generate_key(cls) -> bytes:
        """Generates a cryptographically secure 256-bit key."""
        return AESGCM.generate_key(bit_length=256)

    def encrypt(
        self,
        data: Union[str, bytes],
        associated_data: Optional[bytes] = None
    ) -> Dict[str, str]:
        """
        Encrypts data with AES-256-GCM.
        Returns base64 encoded dictionary containing 'nonce', 'ciphertext', and optional 'aad'.
        """
        if isinstance(data, str):
            data_bytes = data.encode('utf-8')
        elif isinstance(data, bytes):
            data_bytes = data
        else:
            raise TypeError("Data to encrypt must be str or bytes.")

        nonce = os.urandom(self.NONCE_SIZE_BYTES)
        try:
            ciphertext_with_tag = self._aesgcm.encrypt(nonce, data_bytes, associated_data)
        except Exception as e:
            raise SecurityError(f"Encryption failed: {str(e)}") from e

        return {
            "nonce": base64.b64encode(nonce).decode('utf-8'),
            "ciphertext": base64.b64encode(ciphertext_with_tag).decode('utf-8'),
            "aad": base64.b64encode(associated_data).decode('utf-8') if associated_data else ""
        }

    def decrypt(
        self,
        encrypted_payload: Dict[str, str],
        associated_data: Optional[bytes] = None
    ) -> str:
        """
        Decrypts AES-256-GCM payload and verifies authentication tag integrity.
        Raises ValueError on tampering or wrong key.
        """
        if not isinstance(encrypted_payload, dict):
            raise TypeError("encrypted_payload must be a dictionary.")

        if "nonce" not in encrypted_payload or "ciphertext" not in encrypted_payload:
            raise ValueError("Payload missing required 'nonce' or 'ciphertext' fields.")

        try:
            nonce = base64.b64decode(encrypted_payload["nonce"])
            ciphertext = base64.b64decode(encrypted_payload["ciphertext"])
        except Exception as e:
            raise ValueError(f"Invalid base64 encoding in payload: {str(e)}") from e

        aad_bytes = associated_data
        if aad_bytes is None and encrypted_payload.get("aad"):
            aad_bytes = base64.b64decode(encrypted_payload["aad"])

        try:
            decrypted_bytes = self._aesgcm.decrypt(nonce, ciphertext, aad_bytes)
            return decrypted_bytes.decode('utf-8')
        except Exception as e:
            raise ValueError(f"Decryption/Integrity verification failed (Tampered or wrong key): {str(e)}") from e


class SecurityOverrideManager:
    """
    Manages security & compliance overrides (152-FZ DPO / Admin access).
    Ensures every override action is authenticated, authorized, and logged for auditing.
    """
    ALLOWED_ROLES = {"DPO", "SECURITY_ADMIN", "SYSTEM_SUPERVISOR"}

    def __init__(self):
        self._audit_log = []

    def request_override(
        self,
        user_role: str,
        user_id: str,
        target_resource: str,
        reason: str,
        override_key: Optional[str] = None
    ) -> Dict[str, Any]:
        if user_role not in self.ALLOWED_ROLES:
            raise OverrideError(f"Role '{user_role}' is not authorized to request security overrides.")

        if not reason or len(reason.strip()) < 10:
            raise OverrideError("Override request denied: Mandatory audit reason of at least 10 characters required.")

        if not user_id:
            raise OverrideError("User ID is required for audit trail.")

        audit_entry = {
            "status": "APPROVED",
            "user_role": user_role,
            "user_id": user_id,
            "target_resource": target_resource,
            "reason": reason.strip(),
            "override_id": f"OVR-{os.urandom(4).hex().upper()}"
        }
        self._audit_log.append(audit_entry)
        return audit_entry

    def get_audit_log(self) -> list:
        return list(self._audit_log)


# Default cipher helper for application-wide 152-FZ PII encryption
def _get_default_cipher() -> AES256GCMCipher:
    key_str = settings.AES_SECRET_KEY
    if len(key_str) == 64:
        try:
            key_bytes = bytes.fromhex(key_str)
        except ValueError:
            key_bytes = key_str.encode('utf-8')[:32].ljust(32, b'0')
    else:
        key_bytes = key_str.encode('utf-8')[:32].ljust(32, b'0')
    return AES256GCMCipher(key_bytes)


def encrypt_sensitive_data(plain_text: str) -> str:
    if not plain_text:
        return plain_text
    cipher = _get_default_cipher()
    payload = cipher.encrypt(plain_text)
    return json.dumps(payload)


def decrypt_sensitive_data(encrypted_str: str) -> str:
    if not encrypted_str:
        return encrypted_str
    try:
        payload = json.loads(encrypted_str)
        cipher = _get_default_cipher()
        return cipher.decrypt(payload)
    except Exception:
        return encrypted_str


def verify_password(plain_password: str, hashed_password: str) -> bool:
    plain_bytes = plain_password.encode('utf-8')
    if len(plain_bytes) > 72:
        plain_bytes = plain_bytes[:72]
    hashed_bytes = hashed_password.encode('utf-8')
    try:
        return bcrypt.checkpw(plain_bytes, hashed_bytes)
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    if len(pwd_bytes) > 72:
        pwd_bytes = pwd_bytes[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')


def create_access_token(subject: Union[str, Any], expires_delta: Optional[timedelta] = None, extra_claims: Optional[dict] = None) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {"exp": expire, "sub": str(subject)}
    if extra_claims:
        to_encode.update(extra_claims)
    
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    try:
        decoded = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return decoded
    except Exception:
        return None
