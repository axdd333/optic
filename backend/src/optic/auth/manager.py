"""API key management for Optic.

Supports key generation, storage (in-memory + file-persisted),
status tracking, and key revocation.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class KeyStatus(str, Enum):
    """Status of an API key."""

    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


@dataclass
class APIKeyInfo:
    """Information about a single API key."""

    key_id: str
    key_hash: str
    name: str
    status: KeyStatus = KeyStatus.ACTIVE
    rate_limit_per_minute: int = 100
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    last_used_at: Optional[float] = None
    metadata: dict = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        """Check if the key is currently active."""
        if self.status != KeyStatus.ACTIVE:
            return False
        if self.expires_at and time.time() > self.expires_at:
            return False
        return True

    def to_dict(self) -> dict:
        """Serialize to a dict for persistence."""
        return {
            "key_id": self.key_id,
            "key_hash": self.key_hash,
            "name": self.name,
            "status": self.status.value,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "last_used_at": self.last_used_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> APIKeyInfo:
        """Deserialize from a dict."""
        return cls(
            key_id=data["key_id"],
            key_hash=data["key_hash"],
            name=data["name"],
            status=KeyStatus(data.get("status", "active")),
            rate_limit_per_minute=data.get("rate_limit_per_minute", 100),
            created_at=data.get("created_at", 0.0),
            expires_at=data.get("expires_at"),
            last_used_at=data.get("last_used_at"),
            metadata=data.get("metadata", {}),
        )


def _hash_api_key(raw_key: str) -> str:
    """Hash an API key for secure storage."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def _generate_key_id() -> str:
    """Generate a unique, readable key ID (e.g., opt_xxxxx)."""
    return f"opt_{secrets.token_hex(8)}"


def _generate_raw_key() -> str:
    """Generate a secure raw API key."""
    return f"optic_{secrets.token_urlsafe(32)}"


class APIKeyManager:
    """Manages API key lifecycle: creation, validation, revocation, persistence."""

    def __init__(self, storage_path: Optional[str] = None) -> None:
        self._keys: dict[str, APIKeyInfo] = {}  # key_hash -> info
        self._key_id_to_hash: dict[str, str] = {}  # key_id -> key_hash
        self._storage_path = (
            Path(storage_path) if storage_path else Path.home() / ".optic" / "api_keys.json"
        )
        self._load()

    # ── CRUD ──────────────────────────────────────────────────────────────

    def create_key(
        self,
        name: str,
        rate_limit_per_minute: int = 100,
        expires_in_days: Optional[int] = None,
        metadata: Optional[dict] = None,
    ) -> tuple[str, str]:
        """Create a new API key.

        Returns:
            Tuple of (key_id, raw_api_key). The raw key is shown once and cannot
            be retrieved again — store it securely!
        """
        raw_key = _generate_raw_key()
        key_hash = _hash_api_key(raw_key)
        key_id = _generate_key_id()

        expires_at: Optional[float] = None
        if expires_in_days:
            expires_at = time.time() + (expires_in_days * 86400)

        info = APIKeyInfo(
            key_id=key_id,
            key_hash=key_hash,
            name=name,
            rate_limit_per_minute=rate_limit_per_minute,
            expires_at=expires_at,
            metadata=metadata or {},
        )

        self._keys[key_hash] = info
        self._key_id_to_hash[key_id] = key_hash
        self._save()
        return key_id, raw_key

    def validate_key(self, raw_key: str) -> Optional[APIKeyInfo]:
        """Validate a raw API key. Returns the key info if valid, None otherwise."""
        key_hash = _hash_api_key(raw_key)
        info = self._keys.get(key_hash)
        if info is None:
            return None
        if not info.is_active:
            return None
        info.last_used_at = time.time()
        self._save()
        return info

    def get_key_info(self, key_id: str) -> Optional[APIKeyInfo]:
        """Get info about a key by its ID."""
        key_hash = self._key_id_to_hash.get(key_id)
        if key_hash is None:
            return None
        return self._keys.get(key_hash)

    def list_keys(self, include_revoked: bool = False) -> list[APIKeyInfo]:
        """List all managed keys."""
        keys = list(self._keys.values())
        if not include_revoked:
            keys = [k for k in keys if k.status == KeyStatus.ACTIVE]
        return sorted(keys, key=lambda k: k.created_at, reverse=True)

    def revoke_key(self, key_id: str) -> bool:
        """Revoke an API key by its ID. Returns True if successful."""
        key_hash = self._key_id_to_hash.get(key_id)
        if key_hash is None:
            return False
        info = self._keys.get(key_hash)
        if info is None:
            return False
        info.status = KeyStatus.REVOKED
        self._save()
        return True

    def update_rate_limit(self, key_id: str, rate_limit_per_minute: int) -> bool:
        """Update the rate limit for an existing key."""
        key_hash = self._key_id_to_hash.get(key_id)
        if key_hash is None:
            return False
        info = self._keys.get(key_hash)
        if info is None:
            return False
        info.rate_limit_per_minute = rate_limit_per_minute
        self._save()
        return True

    # ── Persistence ───────────────────────────────────────────────────────

    def _save(self) -> None:
        """Persist keys to disk."""
        try:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "keys": [info.to_dict() for info in self._keys.values()],
            }
            self._storage_path.write_text(json.dumps(data, indent=2))
        except OSError as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to save API keys: {e}")

    def _load(self) -> None:
        """Load keys from disk."""
        try:
            if not self._storage_path.exists():
                return
            data = json.loads(self._storage_path.read_text())
            for entry in data.get("keys", []):
                info = APIKeyInfo.from_dict(entry)
                self._keys[info.key_hash] = info
                self._key_id_to_hash[info.key_id] = info.key_hash
        except (json.JSONDecodeError, OSError, KeyError) as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to load API keys: {e}")
            self._keys = {}
            self._key_id_to_hash = {}
