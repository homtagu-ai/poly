"""
PolyHunter Bot -- AES-256-GCM Credential Encryption
Encrypts / decrypts Polymarket API credentials at rest using a master key.
"""
from __future__ import annotations

import base64
import json
import logging
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

# 96-bit (12-byte) IV per NIST recommendation for GCM
_IV_BYTES = 12


def _get_master_key() -> bytes:
    """Load and validate the 32-byte master key from environment."""
    from bot.config import ENCRYPTION_MASTER_KEY

    if not ENCRYPTION_MASTER_KEY:
        raise ValueError(
            'ENCRYPTION_MASTER_KEY is not set. '
            'Generate one with: python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"'
        )

    key = base64.b64decode(ENCRYPTION_MASTER_KEY)
    if len(key) != 32:
        raise ValueError(
            f'ENCRYPTION_MASTER_KEY must decode to exactly 32 bytes '
            f'(got {len(key)})'
        )
    return key


def encrypt_credentials(
    api_key: str,
    api_secret: str,
    api_passphrase: str,
) -> tuple[bytes, bytes, bytes]:
    """Encrypt Polymarket API credentials with AES-256-GCM.

    Args:
        api_key:        Polymarket CLOB API key.
        api_secret:     Polymarket CLOB API secret.
        api_passphrase: Polymarket CLOB API passphrase.

    Returns:
        Tuple of ``(ciphertext, iv, auth_tag)`` as raw bytes.
        - *ciphertext*: the encrypted credential JSON (without the 16-byte tag).
        - *iv*:         the 12-byte initialisation vector.
        - *auth_tag*:   the 16-byte GCM authentication tag.
    """
    key = _get_master_key()
    aesgcm = AESGCM(key)

    plaintext = json.dumps({
        'api_key': api_key,
        'api_secret': api_secret,
        'api_passphrase': api_passphrase,
    }).encode('utf-8')

    iv = os.urandom(_IV_BYTES)

    # AESGCM.encrypt returns ciphertext || tag (last 16 bytes are the tag)
    ct_with_tag = aesgcm.encrypt(iv, plaintext, associated_data=None)

    ciphertext = ct_with_tag[:-16]
    auth_tag = ct_with_tag[-16:]

    logger.debug('Credentials encrypted (%d bytes ciphertext)', len(ciphertext))
    return ciphertext, iv, auth_tag


def decrypt_credentials(
    encrypted_blob: bytes,
    iv: bytes,
    auth_tag: bytes,
) -> dict:
    """Decrypt credentials previously encrypted with ``encrypt_credentials``.

    Args:
        encrypted_blob: The ciphertext bytes (without tag).
        iv:             The 12-byte initialisation vector.
        auth_tag:       The 16-byte GCM authentication tag.

    Returns:
        Dict with keys ``api_key``, ``api_secret``, ``api_passphrase``.

    Raises:
        cryptography.exceptions.InvalidTag: If tampered or wrong key.
        ValueError: If decrypted JSON is malformed.
    """
    key = _get_master_key()
    aesgcm = AESGCM(key)

    # Reconstruct the combined ciphertext || tag expected by AESGCM.decrypt
    ct_with_tag = encrypted_blob + auth_tag

    plaintext = aesgcm.decrypt(iv, ct_with_tag, associated_data=None)
    credentials = json.loads(plaintext.decode('utf-8'))

    required = {'api_key', 'api_secret', 'api_passphrase'}
    if not required.issubset(credentials.keys()):
        raise ValueError(
            f'Decrypted credentials missing keys: '
            f'{required - credentials.keys()}'
        )

    logger.debug('Credentials decrypted successfully')
    return credentials
