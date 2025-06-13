# src/services/cache_service.py

import json
import redis
from typing import Any, Optional, Union, Dict, List
from datetime import datetime, timedelta
import logging
from src.config.settings import settings

logger = logging.getLogger(__name__)

class CacheService:
    """Redis-based caching service for dashboard data and other frequently accessed data."""
    
    def __init__(self):
        """Initialize Redis connection."""
        self.redis_client = None
        self._connect()
    
    def _connect(self):
        """Establish Redis connection with fallback handling."""
        try:
            if settings.REDIS_URL:
                self.redis_client = redis.from_url(
                    settings.REDIS_URL,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    retry_on_timeout=True
                )
                # Test connection
                self.redis_client.ping()
                logger.info("✅ Connected to Redis cache")
            else:
                logger.warning("⚠️  Redis URL not configured, caching disabled")
                self.redis_client = None
        except Exception as e:
            logger.warning(f"⚠️  Redis connection failed: {e}, caching disabled")
            self.redis_client = None
    
    def is_available(self) -> bool:
        """Check if Redis is available."""
        return self.redis_client is not None
    
    def _serialize_data(self, data: Any) -> str:
        """Serialize data for Redis storage."""
        return json.dumps(data, default=str, ensure_ascii=False)
    
    def _deserialize_data(self, data: str) -> Any:
        """Deserialize data from Redis."""
        return json.loads(data)
    
    def _build_key(self, key_type: str, business_id: int, *args) -> str:
        """Build standardized cache key."""
        key_parts = [key_type, str(business_id)]
        key_parts.extend(str(arg) for arg in args)
        return ":".join(key_parts)
    
    def get(self, key: str) -> Optional[Any]:
        """Get data from cache."""
        if not self.is_available():
            return None
        
        try:
            data = self.redis_client.get(key)
            if data:
                return self._deserialize_data(data)
            return None
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            return None
    
    def set(self, key: str, data: Any, ttl_seconds: int = 300) -> bool:
        """Set data in cache with TTL."""
        if not self.is_available():
            return False
        
        try:
            serialized_data = self._serialize_data(data)
            result = self.redis_client.setex(key, ttl_seconds, serialized_data)
            return result
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Delete data from cache."""
        if not self.is_available():
            return False
        
        try:
            result = self.redis_client.delete(key)
            return result > 0
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")
            return False
    
    def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern."""
        if not self.is_available():
            return 0
        
        try:
            keys = self.redis_client.keys(pattern)
            if keys:
                return self.redis_client.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Cache delete pattern error for {pattern}: {e}")
            return 0
    
    def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        if not self.is_available():
            return False
        
        try:
            return self.redis_client.exists(key) > 0
        except Exception as e:
            logger.error(f"Cache exists error for key {key}: {e}")
            return False
    
    def get_ttl(self, key: str) -> int:
        """Get remaining TTL for key."""
        if not self.is_available():
            return -1
        
        try:
            return self.redis_client.ttl(key)
        except Exception as e:
            logger.error(f"Cache TTL error for key {key}: {e}")
            return -1

    # Dashboard-specific cache methods
    def get_dashboard_data(self, business_id: int) -> Optional[Dict]:
        """Get cached dashboard data."""
        key = self._build_key("dashboard", business_id)
        return self.get(key)
    
    def set_dashboard_data(self, business_id: int, data: Dict, ttl_seconds: int = 300) -> bool:
        """Cache dashboard data."""
        key = self._build_key("dashboard", business_id)
        return self.set(key, data, ttl_seconds)
    
    def get_project_dashboard_data(self, business_id: int, project_id: str) -> Optional[Dict]:
        """Get cached project dashboard data."""
        key = self._build_key("project_dashboard", business_id, project_id)
        return self.get(key)
    
    def set_project_dashboard_data(self, business_id: int, project_id: str, data: Dict, ttl_seconds: int = 300) -> bool:
        """Cache project dashboard data."""
        key = self._build_key("project_dashboard", business_id, project_id)
        return self.set(key, data, ttl_seconds)
    
    def get_recent_comments(self, business_id: int, limit: int = 10) -> Optional[List]:
        """Get cached recent comments."""
        key = self._build_key("recent_comments", business_id, limit)
        return self.get(key)
    
    def set_recent_comments(self, business_id: int, comments: List, limit: int = 10, ttl_seconds: int = 180) -> bool:
        """Cache recent comments."""
        key = self._build_key("recent_comments", business_id, limit)
        return self.set(key, comments, ttl_seconds)
    
    def get_kpi_data(self, business_id: int, kpi_type: str) -> Optional[Any]:
        """Get cached KPI data."""
        key = self._build_key("kpi", business_id, kpi_type)
        return self.get(key)
    
    def set_kpi_data(self, business_id: int, kpi_type: str, data: Any, ttl_seconds: int = 600) -> bool:
        """Cache KPI data."""
        key = self._build_key("kpi", business_id, kpi_type)
        return self.set(key, data, ttl_seconds)
    
    # Cache invalidation methods
    def invalidate_dashboard_cache(self, business_id: int) -> int:
        """Invalidate all dashboard-related cache for a business."""
        patterns = [
            f"dashboard:{business_id}:*",
            f"project_dashboard:{business_id}:*",
            f"recent_comments:{business_id}:*",
            f"kpi:{business_id}:*"
        ]
        
        total_deleted = 0
        for pattern in patterns:
            total_deleted += self.delete_pattern(pattern)
        
        logger.info(f"Invalidated {total_deleted} dashboard cache keys for business {business_id}")
        return total_deleted
    
    def invalidate_project_cache(self, business_id: int, project_id: str) -> int:
        """Invalidate project-specific cache."""
        patterns = [
            f"project_dashboard:{business_id}:{project_id}",
            f"dashboard:{business_id}",  # Main dashboard includes project data
            f"recent_comments:{business_id}:*",  # Comments may include this project
            f"kpi:{business_id}:*"  # KPIs include project counts
        ]
        
        total_deleted = 0
        for pattern in patterns:
            if "*" in pattern:
                total_deleted += self.delete_pattern(pattern)
            else:
                if self.delete(pattern):
                    total_deleted += 1
        
        logger.info(f"Invalidated {total_deleted} cache keys for project {project_id}")
        return total_deleted
    
    def invalidate_comment_cache(self, business_id: int) -> int:
        """Invalidate comment-related cache."""
        pattern = f"recent_comments:{business_id}:*"
        deleted = self.delete_pattern(pattern)
        logger.info(f"Invalidated {deleted} comment cache keys for business {business_id}")
        return deleted
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        if not self.is_available():
            return {"status": "unavailable"}
        
        try:
            info = self.redis_client.info()
            return {
                "status": "available",
                "connected_clients": info.get("connected_clients", 0),
                "used_memory": info.get("used_memory_human", "unknown"),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "hit_rate": self._calculate_hit_rate(
                    info.get("keyspace_hits", 0),
                    info.get("keyspace_misses", 0)
                )
            }
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {"status": "error", "error": str(e)}
    
    def _calculate_hit_rate(self, hits: int, misses: int) -> float:
        """Calculate cache hit rate percentage."""
        total = hits + misses
        if total == 0:
            return 0.0
        return round((hits / total) * 100, 2)

# Global cache service instance
cache_service = CacheService() 