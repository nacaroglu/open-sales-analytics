"""Small, process-local cache for successful module response bodies."""

from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Lock

from fastapi import Depends

from app.config import Settings, get_settings

CacheKey = tuple[object, ...]


@dataclass(frozen=True)
class _Entry:
    body: bytes
    expires_at: datetime


class ResponseCache:
    """A bounded, thread-safe LRU cache whose values are serialized response bodies."""

    def __init__(self, max_entries: int = 256, ttl_seconds: int = 300) -> None:
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self._entries: OrderedDict[CacheKey, _Entry] = OrderedDict()
        self._lock = Lock()

    def get(self, key: CacheKey, now: datetime) -> bytes | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if now >= entry.expires_at:
                del self._entries[key]
                return None
            self._entries.move_to_end(key)
            return entry.body

    def put(
        self,
        key: CacheKey,
        body: bytes,
        now: datetime,
        dataset_expires_at: datetime,
    ) -> None:
        if self.max_entries == 0:
            return
        expires_at = min(now + timedelta(seconds=self.ttl_seconds), dataset_expires_at)
        if now >= expires_at:
            return
        with self._lock:
            self._entries[key] = _Entry(body, expires_at)
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)

    def invalidate_dataset(self, dataset_id: str) -> None:
        with self._lock:
            for key in tuple(self._entries):
                if key and key[0] == dataset_id:
                    del self._entries[key]

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def keys(self) -> tuple[CacheKey, ...]:
        with self._lock:
            return tuple(self._entries)

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


_default_lock = Lock()
_default_cache: ResponseCache | None = None
_default_config: tuple[int, int] | None = None


def response_cache_for_settings(settings: Settings) -> ResponseCache:
    global _default_cache, _default_config
    config = (settings.response_cache_max_entries, settings.response_cache_ttl_seconds)
    with _default_lock:
        if _default_cache is None or _default_config != config:
            _default_cache = ResponseCache(*config)
            _default_config = config
        return _default_cache


def get_response_cache(settings: Settings = Depends(get_settings)) -> ResponseCache:
    """Dependency used by module routes; tests can replace it per client."""
    return response_cache_for_settings(settings)
