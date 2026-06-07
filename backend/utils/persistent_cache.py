import json
import logging
import time
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


class PersistentCache:
    def __init__(self, cache_dir: str, ttl_seconds: int) -> None:
        self.cache_dir = Path(cache_dir)
        self.ttl_seconds = ttl_seconds
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, key: str, allow_expired: bool = False) -> dict[str, Any] | None:
        path = self._path_for_key(key)
        if not path.exists():
            return None

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("Ignoring unreadable cache file: %s", path)
            return None

        if not allow_expired and payload.get("expires_at", 0) <= time.time():
            return None

        data = payload.get("data")
        return data if isinstance(data, dict) else None

    def set(self, key: str, data: dict[str, Any]) -> None:
        path = self._path_for_key(key)
        payload = {
            "expires_at": time.time() + self.ttl_seconds,
            "data": data,
        }
        try:
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError:
            logger.warning("Unable to write cache file: %s", path)

    def _path_for_key(self, key: str) -> Path:
        safe_key = "".join(character if character.isalnum() or character in "-_" else "-" for character in key)
        return self.cache_dir / f"{safe_key}.json"
