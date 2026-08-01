import pytest
import os
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.security import (
    AES256GCMCipher,
    KeyValidationError,
    SecurityError,
    SecurityOverrideManager,
    OverrideError
)


class TestAES256GCMSecurity152FZ:
    """Test suite for AES-256-GCM encryption/decryption compliance under 152-FZ."""

    @pytest.fixture
    def valid_key_bytes(self) -> bytes:
        return AES256GCMCipher.generate_key()

    @pytest.fixture
    def valid_cipher(self, valid_key_bytes: bytes) -> AES256GCMCipher:
        return AES256GCMCipher(valid_key_bytes)

    def test_key_generation_integrity(self):
        """Verify generated key is cryptographically secure and exactly 256 bits (32 bytes)."""
        key = AES256GCMCipher.generate_key()
        assert isinstance(key, bytes)
        assert len(key) == 32
        assert AES256GCMCipher.validate_key(key) is True

    @pytest.mark.parametrize("invalid_key", [
        b"short_key_16byte",
        b"too_long_key_exceeding_32_bytes_length_limit!",
        b"",
        b"\x00" * 32,  # Weak zero key
        "not_bytes_or_hex_string",
    ])
    def test_key_validation_rejects_invalid_keys(self, invalid_key):
        """Verify that invalid or weak keys are strictly rejected by 152-FZ security validator."""
        with pytest.raises(KeyValidationError):
            AES256GCMCipher(invalid_key)

    def test_encryption_decryption_roundtrip_pii(self, valid_cipher: AES256GCMCipher):
        """Test encryption and decryption of 152-FZ Personal Identifiable Information (PII)."""
        pii_payload = '{"full_name": "Иванов Иван Иванович", "email": "ivanov@example.ru", "telegram_id": "12345678"}'
        
        encrypted = valid_cipher.encrypt(pii_payload)
        
        assert "nonce" in encrypted
        assert "ciphertext" in encrypted
        assert encrypted["nonce"] != ""
        assert encrypted["ciphertext"] != ""
        
        decrypted = valid_cipher.decrypt(encrypted)
        assert decrypted == pii_payload

    def test_encryption_decryption_with_associated_authenticated_data(self, valid_cipher: AES256GCMCipher):
        """Test GCM with Associated Authenticated Data (AAD) for telemetry integrity (UUID bound)."""
        telemetry_data = "HRV=68ms, RHR=54bpm, VO2max=52.4"
        athlete_uuid = b"user-uuid-9876-5432"

        encrypted = valid_cipher.encrypt(telemetry_data, associated_data=athlete_uuid)
        decrypted = valid_cipher.decrypt(encrypted, associated_data=athlete_uuid)
        
        assert decrypted == telemetry_data

    def test_tampered_ciphertext_detection(self, valid_cipher: AES256GCMCipher):
        """Verify GCM tag authentication detects tampered ciphertext and raises error."""
        data = "Sensitive Fitness Telemetry"
        encrypted = valid_cipher.encrypt(data)

        # Tamper ciphertext by altering base64 string
        raw_ciphertext = base64.b64decode(encrypted["ciphertext"])
        tampered_bytes = bytearray(raw_ciphertext)
        tampered_bytes[0] ^= 0xFF  # Flip bits
        encrypted["ciphertext"] = base64.b64encode(tampered_bytes).decode('utf-8')

        with pytest.raises(ValueError, match="Decryption/Integrity verification failed"):
            valid_cipher.decrypt(encrypted)

    def test_tampered_nonce_detection(self, valid_cipher: AES256GCMCipher):
        """Verify GCM authentication fails if nonce is altered."""
        data = "Sensitive Data"
        encrypted = valid_cipher.encrypt(data)

        # Tamper nonce
        tampered_nonce = base64.b64encode(os.urandom(12)).decode('utf-8')
        encrypted["nonce"] = tampered_nonce

        with pytest.raises(ValueError):
            valid_cipher.decrypt(encrypted)

    def test_decryption_with_wrong_key_fails(self, valid_cipher: AES256GCMCipher):
        """Verify decryption using a different valid key fails securely."""
        encrypted = valid_cipher.encrypt("Secret Data")

        wrong_key = AES256GCMCipher.generate_key()
        wrong_cipher = AES256GCMCipher(wrong_key)

        with pytest.raises(ValueError):
            wrong_cipher.decrypt(encrypted)


class TestSecurityOverrideManager:
    """Test suite for 152-FZ compliance DPO/Admin security overrides."""

    @pytest.fixture
    def override_manager(self) -> SecurityOverrideManager:
        return SecurityOverrideManager()

    def test_successful_dpo_override(self, override_manager: SecurityOverrideManager):
        """Verify authorized DPO role can request override with valid audit reason."""
        result = override_manager.request_override(
            user_role="DPO",
            user_id="dpo_admin_01",
            target_resource="athlete_pii_vault",
            reason="152-FZ Roskomnadzor official audit compliance inspection"
        )
        assert result["status"] == "APPROVED"
        assert "override_id" in result
        assert len(override_manager.get_audit_log()) == 1

    def test_unauthorized_role_override_rejected(self, override_manager: SecurityOverrideManager):
        """Verify non-security roles (e.g. ATHLETE or COACH) cannot request security overrides."""
        with pytest.raises(OverrideError, match="not authorized"):
            override_manager.request_override(
                user_role="ATHLETE",
                user_id="athlete_123",
                target_resource="system_keys",
                reason="Attempting unauthorized key override"
            )

    def test_missing_audit_reason_rejected(self, override_manager: SecurityOverrideManager):
        """Verify override requests without a valid detailed audit reason are denied."""
        with pytest.raises(OverrideError, match="Mandatory audit reason"):
            override_manager.request_override(
                user_role="SECURITY_ADMIN",
                user_id="sec_admin_01",
                target_resource="encryption_config",
                reason="short"
            )
