import base64
import binascii
import secrets
from typing import Optional, Dict

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding

from app.integrations.aiosell.exceptions import AiosellAuthError, AiosellDecryptionError


def generate_basic_auth_header(username: str, password: str) -> str:
    """Generate HTTP Basic Auth header value."""
    if not username:
        raise AiosellAuthError("Aiosell API username is required for authentication.")
    raw_credentials = f"{username}:{password or ''}"
    encoded = base64.b64encode(raw_credentials.encode("utf-8")).decode("utf-8")
    return f"Basic {encoded}"


def verify_basic_auth(
    authorization_header: Optional[str],
    expected_username: str,
    expected_password: str,
) -> bool:
    """
    Verify incoming Basic Auth header for webhook security.
    Uses constant-time comparison to prevent timing attacks.
    """
    if not authorization_header or not authorization_header.startswith("Basic "):
        return False

    try:
        encoded = authorization_header[6:].strip()
        decoded = base64.b64decode(encoded).decode("utf-8")
        if ":" not in decoded:
            return False
        username, password = decoded.split(":", 1)
        user_matches = secrets.compare_digest(username, expected_username)
        pass_matches = secrets.compare_digest(password, expected_password)
        return user_matches and pass_matches
    except Exception:
        return False


def decrypt_card_field(hex_value: Optional[str], key: str) -> Optional[str]:
    """
    Decrypts a hex-encoded string encrypted with AES-128-ECB.
    Key must be 16 characters (128-bit).
    Handles PKCS#7 padding if present, otherwise strips trailing nulls/whitespaces.
    """
    if not hex_value:
        return None

    if not key or len(key.encode("utf-8")) != 16:
        raise AiosellDecryptionError(
            f"Invalid key length: AES-128 requires a 16-character key (got {len(key) if key else 0})."
        )

    try:
        ciphertext = bytes.fromhex(hex_value.strip())
        cipher = Cipher(algorithms.AES(key.encode("utf-8")), modes.ECB())
        decryptor = cipher.decryptor()
        decrypted_padded = decryptor.update(ciphertext) + decryptor.finalize()

        # Try PKCS7 unpadding first
        try:
            unpadder = padding.PKCS7(128).unpadder()
            decrypted = unpadder.update(decrypted_padded) + unpadder.finalize()
            return decrypted.decode("utf-8")
        except Exception:
            # Fallback to stripping trailing null / padding bytes
            return decrypted_padded.rstrip(b"\x00").decode("utf-8", errors="replace").strip()
    except binascii.Error as e:
        raise AiosellDecryptionError(f"Invalid hex encoding in card payload: {e}") from e
    except Exception as e:
        raise AiosellDecryptionError(f"Failed to decrypt credit card field: {e}") from e


def decrypt_credit_card_payload(
    card_dict: Optional[Dict[str, Optional[str]]],
    key: Optional[str],
) -> Optional[Dict[str, Optional[str]]]:
    """
    Decrypts all fields within the Aiosell creditCard object:
    - cardNumber, cvv, expiry, cardHolderName, cardType, activationDate
    """
    if not card_dict or not key:
        return card_dict

    decrypted: Dict[str, Optional[str]] = {}
    for field, hex_val in card_dict.items():
        if hex_val and isinstance(hex_val, str):
            decrypted[field] = decrypt_card_field(hex_val, key)
        else:
            decrypted[field] = None
    return decrypted
