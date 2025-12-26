# HTTP Helper for Thermostat Connections
# SSL-aware session configuration for both local thermostats and public server connections

import aiohttp
import ssl
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def create_thermostat_session(timeout_seconds: float = 5) -> aiohttp.ClientSession:
    """
    Create properly configured aiohttp session for local thermostat connections (always HTTP)
    Prevents connection leaks with proper cleanup and limits
    """
    connector = aiohttp.TCPConnector(
        limit_per_host=2,           # Max 2 connections per thermostat IP
        ssl=False,                  # Local thermostats use HTTP only
        force_close=True,           # Force connection cleanup
        enable_cleanup_closed=True  # Additional cleanup
    )
    
    return aiohttp.ClientSession(
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=timeout_seconds)
    )

def create_public_server_session(
    timeout_seconds: float = 30, 
    ssl_enabled: bool = False,
    ssl_verify: bool = True,
    ca_cert_path: str = None
) -> aiohttp.ClientSession:
    """
    Create properly configured aiohttp session for public server connections
    Supports both HTTP and HTTPS based on configuration
    """
    
    if ssl_enabled:
        logger.info(f"Creating SSL-enabled session (verify={ssl_verify})")
        
        # Create SSL context
        ssl_context = ssl.create_default_context()
        
        if not ssl_verify:
            # Disable SSL verification (for development/self-signed certs)
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            logger.warning("SSL verification disabled")
        else:
            # Enable SSL verification
            ssl_context.check_hostname = True
            ssl_context.verify_mode = ssl.CERT_REQUIRED
            
            # Load custom CA certificate if provided
            if ca_cert_path:
                ca_path = Path(ca_cert_path)
                if ca_path.exists():
                    ssl_context.load_verify_locations(ca_path)
                    logger.info(f"Loaded custom CA certificate: {ca_path}")
                else:
                    logger.warning(f"CA certificate not found: {ca_path}")
        
        connector = aiohttp.TCPConnector(
            ssl=ssl_context,
            limit=20,                   # Total connection pool limit
            limit_per_host=5,           # Max connections per host
            force_close=False,          # Keep connections alive for efficiency
            enable_cleanup_closed=True
        )
    else:
        logger.info("Creating HTTP-only session")
        connector = aiohttp.TCPConnector(
            ssl=False,                  # HTTP only
            limit=20,
            limit_per_host=5,
            force_close=False,
            enable_cleanup_closed=True
        )
    
    return aiohttp.ClientSession(
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=timeout_seconds)
    )
