"""
Custom CORS middleware for multi-tenant subdomain support.
Validates origins against allowed domain patterns dynamically.
"""

from fastapi import Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response as FastAPIResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse
from typing import List, Optional
import re
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class DynamicCORSMiddleware(BaseHTTPMiddleware):
    """
    Custom CORS middleware that supports dynamic subdomain validation.
    Allows any subdomain of specified domain patterns.
    """
    
    def __init__(
        self,
        app,
        allowed_origins: List[str] = None,
        allowed_domain_patterns: List[str] = None,
        allow_credentials: bool = True,
        allow_methods: List[str] = None,
        allow_headers: List[str] = None,
        expose_headers: List[str] = None,
        max_age: int = 600,
    ):
        super().__init__(app)
        self.allowed_origins = allowed_origins or []
        self.allowed_domain_patterns = allowed_domain_patterns or []
        self.allow_credentials = allow_credentials
        self.allow_methods = allow_methods or ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
        self.allow_headers = allow_headers or ["*"]
        self.expose_headers = expose_headers or []
        self.max_age = max_age
        
        # Compile regex patterns for domain matching
        self.domain_regexes = []
        for pattern in self.allowed_domain_patterns:
            # Convert domain pattern to regex (e.g., "convrse.com" -> r"^.*\.convrse\.com$")
            escaped_pattern = re.escape(pattern)
            regex_pattern = f"^.*\\.{escaped_pattern}$|^{escaped_pattern}$"
            self.domain_regexes.append(re.compile(regex_pattern))
    
    def is_origin_allowed(self, origin: str) -> bool:
        """
        Check if the origin is allowed based on static list or domain patterns.
        
        Args:
            origin: The origin to validate (e.g., "http://demo-business.localhost")
        
        Returns:
            bool: True if origin is allowed, False otherwise
        """
        # Check static allowed origins first
        if origin in self.allowed_origins:
            return True
        
        # Parse the origin to get the hostname
        try:
            parsed = urlparse(origin)
            hostname = parsed.hostname
            
            if not hostname:
                return False
            
            # Check against domain patterns
            for regex in self.domain_regexes:
                if regex.match(hostname):
                    logger.debug(f"Origin {origin} allowed by domain pattern match")
                    return True
            
            return False
            
        except Exception as e:
            logger.warning(f"Failed to parse origin {origin}: {e}")
            return False
    
    async def dispatch(self, request: Request, call_next) -> StarletteResponse:
        """Handle CORS for incoming requests."""
        
        origin = request.headers.get("origin")
        method = request.method
        
        # Handle preflight requests
        if method == "OPTIONS":
            if origin and self.is_origin_allowed(origin):
                response = StarletteResponse()
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Methods"] = ", ".join(self.allow_methods)
                response.headers["Access-Control-Allow-Headers"] = ", ".join(self.allow_headers)
                if self.allow_credentials:
                    response.headers["Access-Control-Allow-Credentials"] = "true"
                response.headers["Access-Control-Max-Age"] = str(self.max_age)
                if self.expose_headers:
                    response.headers["Access-Control-Expose-Headers"] = ", ".join(self.expose_headers)
                logger.debug(f"CORS preflight approved for origin: {origin}")
                return response
            else:
                # Return 200 but without CORS headers for disallowed origins
                logger.warning(f"CORS preflight denied for origin: {origin}")
                return StarletteResponse(status_code=200)
        
        # Process the actual request
        response = await call_next(request)
        
        # Add CORS headers to the response
        if origin and self.is_origin_allowed(origin):
            response.headers["Access-Control-Allow-Origin"] = origin
            if self.allow_credentials:
                response.headers["Access-Control-Allow-Credentials"] = "true"
            if self.expose_headers:
                response.headers["Access-Control-Expose-Headers"] = ", ".join(self.expose_headers)
            logger.debug(f"CORS headers added for origin: {origin}")
        else:
            if origin:
                logger.warning(f"CORS denied for origin: {origin}")
        
        return response