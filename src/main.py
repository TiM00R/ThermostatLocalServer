"""
RadioThermostat CT50 Local Server - Main Entry Point
"""

import asyncio
import signal
import sys
import logging
from pathlib import Path
import os

from services.thermostat_server import ThermostatServer

logger = logging.getLogger(__name__)

async def main():
    """Main entry point"""
    
    # Handle graceful shutdown
    server = None
    
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        if server:
            asyncio.create_task(server.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Get config file path from environment variable or use default
        config_path = os.environ.get('CONFIG_FILE', 'config/config.yaml')
        logger.info(f"Using configuration file name from environment: {config_path}")
        # Create and start server
        server = ThermostatServer(config_path=config_path)
        
        await server.start()
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Server failed: {e}")
        return 1
    finally:
        if server:
            await server.stop()
    
    return 0

if __name__ == "__main__":
    # Ensure logs directory exists
    Path("logs").mkdir(exist_ok=True)
    
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nServer stopped by user")
        sys.exit(0)
