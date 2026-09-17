"""
Distributed Redis Cache Service with In-Memory Fallback & Error Recovery
========================================================================
Provides unified caching interface (`get`, `set`, `delete`, `clear_pattern`) for RAG context, 
session data, and API responses across multi-instance production deployments.
"""

import time
import logging
from typing import Optional, Any
from app.core.config import settings

logger = logging.getLogger("khanx.cache")

class RedisCacheService:
    def __init__(self, redis_url: str = ""):
        self.redis_url = redis_url.strip() if redis_url else ""
        self.redis_client = None
        self.in_memory_fallback = {}
        self._init_redis()

    def _init_redis(self):
        if not self.redis_url:
            logger.info("REDIS_URL not configured. Using in-memory fallback cache.")
            return

        try:
            import redis
            self.redis_client = redis.Redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_timeout=2.0,
                socket_connect_timeout=2.0
            )
            # Test ping
            self.redis_client.ping()
            logger.info(f"Successfully connected to Redis cache at {self.redis_url}")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis server ({e}). Falling back to in-memory cache.")
            self.redis_client = None

    def get(self, key: str) -> Optional[str]:
        """Get cached string by key."""
        if self.redis_client:
            try:
                return self.redis_client.get(key)
            except Exception as e:
                logger.warning(f"Redis GET error for key '{key}': {e}. Falling back to in-memory cache.")

        # In-memory fallback lookup
        if key in self.in_memory_fallback:
            val, expire_at = self.in_memory_fallback[key]
            if expire_at is None or time.time() < expire_at:
                return val
            else:
                self.in_memory_fallback.pop(key, None)
        return None

    def set(self, key: str, value: str, ttl_seconds: Optional[int] = 300) -> bool:
        """Set string value in cache with optional TTL in seconds."""
        # Always update memory fallback for seamless availability
        expire_at = (time.time() + ttl_seconds) if ttl_seconds else None
        self.in_memory_fallback[key] = (value, expire_at)

        if self.redis_client:
            try:
                if ttl_seconds:
                    self.redis_client.setex(key, ttl_seconds, value)
                else:
                    self.redis_client.set(key, value)
                return True
            except Exception as e:
                logger.warning(f"Redis SET error for key '{key}': {e}")
        return True

    def delete(self, key: str) -> bool:
        """Delete specific key from cache."""
        self.in_memory_fallback.pop(key, None)
        if self.redis_client:
            try:
                self.redis_client.delete(key)
                return True
            except Exception as e:
                logger.warning(f"Redis DELETE error for key '{key}': {e}")
        return True

    def clear_pattern(self, pattern_prefix: str) -> bool:
        """Clear all keys matching pattern prefix (e.g. 'usr_123:')."""
        # Clear in-memory keys
        keys_to_del = [k for k in self.in_memory_fallback if k.startswith(pattern_prefix)]
        for k in keys_to_del:
            self.in_memory_fallback.pop(k, None)

        if self.redis_client:
            try:
                keys = self.redis_client.keys(f"{pattern_prefix}*")
                if keys:
                    self.redis_client.delete(*keys)
                return True
            except Exception as e:
                logger.warning(f"Redis clear_pattern error for prefix '{pattern_prefix}': {e}")
        return True


# Global singleton cache instance
cache_service = RedisCacheService(redis_url=getattr(settings, "REDIS_URL", ""))
