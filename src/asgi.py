"""
ASGI entry point for uvicorn
This module exposes the FastAPI app for use with uvicorn command line
"""

import asyncio
import logging
from pathlib import Path

from config_loader import load_config, setup_logging
from database.manager import DatabaseManager
from api.main_api import ThermostatAPI
from weather_service import WeatherService

# Ensure logs directory exists
Path("logs").mkdir(exist_ok=True)

# Load configuration
config = load_config()
setup_logging(config)

logger = logging.getLogger(__name__)

# Initialize components synchronously for uvicorn
logger.info("Initializing application components...")

# Create database manager
db = DatabaseManager(config)

# Create weather service
weather = WeatherService(config)

# Create API (which contains the FastAPI app)
api = ThermostatAPI(db, config, weather)

# Expose the FastAPI app for uvicorn
app = api.app

# Lifespan events for proper initialization and cleanup
@app.on_event("startup")
async def startup_event():
    """Initialize database and weather service on startup"""
    logger.info("Starting up application...")
    await db.initialize()
    logger.info("Database initialized")
    
    await weather.start()
    logger.info("Weather service initialized")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown"""
    logger.info("Shutting down application...")
    await weather.stop()
    await db.close()
    logger.info("Application shut down complete")

logger.info("ASGI app ready for uvicorn")
