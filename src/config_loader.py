"""
Configuration loader for RadioThermostat CT50 Server
Loads and validates configuration from YAML files
ENHANCED: Added SSL support for public server connections
"""

import yaml
import logging
from typing import Dict, Any
from pathlib import Path
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

def load_config(config_path: str = "config/config.yaml") -> Dict[str, Any]:
    """
    Load configuration from YAML file with validation
    """
    try:
        config_file = Path(config_path)
        if not config_file.exists():
            logger.error(f"Configuration file not found: {config_path}")
            raise FileNotFoundError(f"Config file not found: {config_path}")
        
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
        
        # Validate required sections
        _validate_config(config)
        
        # Apply defaults
        config = _apply_defaults(config)
        
        logger.info(f"Configuration loaded from {config_path}")
        return config
        
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        raise

def _validate_config(config: Dict) -> None:
    """Validate that required configuration sections exist"""
    required_sections = ['network', 'polling', 'database']
    
    for section in required_sections:
        if section not in config:
            raise ValueError(f"Missing required configuration section: {section}")
    
    # Validate network section
    network = config['network']
    if 'ip_ranges' not in network or not network['ip_ranges']:
        raise ValueError("network.ip_ranges is required and must not be empty")
    
    # Validate database section
    db = config['database']
    required_db_fields = ['host', 'port', 'database', 'username', 'password']
    for field in required_db_fields:
        if field not in db:
            raise ValueError(f"Missing required database field: {field}")
    
    # Validate polling section
    polling = config['polling']
    if 'status_interval_seconds' not in polling:
        raise ValueError("polling.status_interval_seconds is required")
    
    # Validate public server SSL configuration if present
    if 'public_server' in config:
        _validate_public_server_ssl(config['public_server'])

def _validate_public_server_ssl(public_server_config: Dict) -> None:
    """Validate public server SSL configuration"""
    ssl_enabled = public_server_config.get('ssl_enabled', False)
    base_url = public_server_config.get('base_url', '')
    
    # Check for SSL/URL consistency
    if ssl_enabled and not base_url.startswith('https://'):
        logger.warning("ssl_enabled is true but base_url uses http:// - this may cause connection issues")
    elif not ssl_enabled and base_url.startswith('https://'):
        logger.warning("ssl_enabled is false but base_url uses https:// - this may cause connection issues")
    
    # Validate SSL certificate path if verification is enabled
    if ssl_enabled:
        ssl_verify = public_server_config.get('ssl_verify', True)
        ca_cert_path = public_server_config.get('ca_cert_path')
        
        if ssl_verify and ca_cert_path:
            cert_path = Path(ca_cert_path)
            if not cert_path.exists():
                logger.warning(f"SSL CA certificate not found: {ca_cert_path}")
        
        logger.info(f"Public server SSL configured: enabled={ssl_enabled}, verify={ssl_verify}")

def _apply_defaults(config: Dict) -> Dict:
    """Apply default values to configuration"""
    
    # Network defaults
    network_defaults = {
        'discovery_method': 'udp_multicast',
        'discovery_timeout': 10,
        'request_timeout': 5,
        'scan_interval_minutes': 30
    }
    for key, default_value in network_defaults.items():
        if key not in config['network']:
            config['network'][key] = default_value
    
    # Polling defaults  
    polling_defaults = {
        'max_concurrent_requests': 5,
        'retry_attempts': 3,
        'retry_delay_seconds': 2,
        'error_threshold': 10
    }
    for key, default_value in polling_defaults.items():
        if key not in config['polling']:
            config['polling'][key] = default_value
    
    # API defaults
    if 'api' not in config:
        config['api'] = {}
    api_defaults = {
        'host': '0.0.0.0',
        'port': 8000,
        'cors_origins': ['*']
    }
    for key, default_value in api_defaults.items():
        if key not in config['api']:
            config['api'][key] = default_value
    
    # Public server SSL defaults
    if 'public_server' in config:
        ssl_defaults = {
            'ssl_enabled': False,              # Default: HTTP mode
            'ssl_verify': True,                # Default: Verify SSL certificates
            'ca_cert_path': 'certs/thermo-ca.crt',  # Default: Use local CA cert
            'timeout_seconds': 30              # Default: 30 second timeout for HTTPS
        }
        for key, default_value in ssl_defaults.items():
            if key not in config['public_server']:
                config['public_server'][key] = default_value
    
    # Logging defaults
    if 'logging' not in config:
        config['logging'] = {}
    logging_defaults = {
        'level': 'INFO',
        'file': 'logs/thermostat_server.log',
        'console_output': True
    }
    for key, default_value in logging_defaults.items():
        if key not in config['logging']:
            config['logging'][key] = default_value
    
    # Thermostat time sync defaults
    if 'thermostat_time_sync' not in config:
        config['thermostat_time_sync'] = {}
    sync_defaults = {
        'sync_interval_days': 7,
        'sync_after_discovery': True
    }
    for key, default_value in sync_defaults.items():
        if key not in config['thermostat_time_sync']:
            config['thermostat_time_sync'][key] = default_value
    
    # Monitoring defaults
    if 'monitoring' not in config:
        config['monitoring'] = {}
    monitoring_defaults = {
        'health_check_interval_minutes': 5,
        'device_timeout_minutes': 10
    }
    for key, default_value in monitoring_defaults.items():
        if key not in config['monitoring']:
            config['monitoring'][key] = default_value
    
    return config

def get_public_server_ssl_config(config: Dict) -> Dict[str, Any]:
    """Get SSL configuration for public server connections"""
    if 'public_server' not in config:
        return {
            'ssl_enabled': False,
            'ssl_verify': True,
            'ca_cert_path': None,
            'timeout_seconds': 30
        }
    
    public_server = config['public_server']
    return {
        'ssl_enabled': public_server.get('ssl_enabled', False),
        'ssl_verify': public_server.get('ssl_verify', True),
        'ca_cert_path': public_server.get('ca_cert_path', 'certs/thermo-ca.crt'),
        'timeout_seconds': public_server.get('timeout_seconds', 30)
    }


class EDTFormatter(logging.Formatter):
    """Custom formatter to display timestamps in Eastern Daylight Time (EDT)"""
    
    def __init__(self, fmt=None):
        super().__init__(fmt)
        # Eastern timezone (handles both EST and EDT automatically)
        self.eastern_tz = pytz.timezone('America/New_York')
    
    def formatTime(self, record, datefmt=None):
        # Convert timestamp to Eastern time
        dt = datetime.fromtimestamp(record.created, tz=self.eastern_tz)
        if datefmt:
            return dt.strftime(datefmt)
        else:
            # Default format: YYYY-MM-DD HH:MM:SS EDT
            return dt.strftime('%Y-%m-%d %H:%M:%S %Z')

def setup_logging(config: Dict) -> None:
    """Setup logging based on configuration with EDT timestamps"""
    log_config = config.get('logging', {})
    level = log_config.get('level', 'INFO')
    
    # Configure logging format with custom EDT formatter
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Create custom EDT formatter
    formatter = EDTFormatter(log_format)
    
    # Setup logging
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=log_format,
        handlers=[]
    )
    
    # Console handler with EDT timestamps
    if log_config.get('console_output', True):
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logging.getLogger().addHandler(console_handler)
    
    # File handler with EDT timestamps
    log_file = log_config.get('file')
    if log_file:
        # Create logs directory if it doesn't exist
        log_path = Path(log_file)
        log_path.parent.mkdir(exist_ok=True)
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logging.getLogger().addHandler(file_handler)
    
    logger.info(f"Logging configured with EDT timestamps: level={level}, console={log_config.get('console_output', True)}, file={log_file}")

def get_sample_config() -> Dict:
    """Return a sample configuration for reference with SSL support"""
    return {
        "site": {
            "site_id": "cape_home",
            "site_name": "Cape House",
            "timezone": "America/New_York"
        },
        "network": {
            "discovery_method": "udp_multicast",
            "ip_ranges": ["10.0.60.1-10.0.60.254"],
            "discovery_timeout": 10,
            "request_timeout": 5,
            "scan_interval_minutes": 30
        },
        "polling": {
            "status_interval_seconds": 5,
            "max_concurrent_requests": 5,
            "retry_attempts": 3,
            "retry_delay_seconds": 2,
            "error_threshold": 10
        },
        "database": {
            "host": "localhost",
            "port": 5433,  # 5433 for dev, 5432 for prod
            "database": "thermostat_db",
            "username": "postgres",
            "password": "postgres"
        },
        "api": {
            "host": "0.0.0.0",
            "port": 8000,
            "cors_origins": ["*"]
        },
        "public_server": {
            "enabled": True,
            "base_url": "https://your-server.com:8001",  # Use HTTPS for SSL mode
            "site_token": "your-site-token-here",
            "ssl_enabled": True,                         # Enable SSL
            "ssl_verify": True,                          # Verify certificates
            "ca_cert_path": "certs/thermo-ca.crt",      # CA certificate path
            "timeout_seconds": 30,                      # HTTPS timeout
            "status_upload_seconds": 30,
            "minute_upload_seconds": 60,
            "command_poll_seconds": 10,
            "retry_attempts": 3,
            "retry_delay_seconds": 2,
            "max_batch_size": 100
        },
        "logging": {
            "level": "INFO",
            "file": "logs/thermostat_server.log",
            "console_output": True
        },
        "thermostat_time_sync": {
            "sync_interval_days": 7,
            "sync_after_discovery": True
        }
    }
