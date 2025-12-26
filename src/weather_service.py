"""
Weather Service Module
Fetches local weather temperature based on zip code using OpenWeatherMap API
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
import aiohttp
import json

logger = logging.getLogger(__name__)

class WeatherService:
    """Manages local weather temperature fetching for thermostat comparisons"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config['weather']
        self.site_config = config['site']
        
        # API configuration
        self.api_key = self.config['api_key']
        self.zip_code = self.site_config['zip_code']
        self.update_interval = self.config['update_interval_minutes'] * 60
        self.timeout = aiohttp.ClientTimeout(total=self.config['timeout_seconds'])
        self.retry_attempts = self.config['retry_attempts']
        self.fallback_temp = self.config['fallback_temp']
        
        # State tracking
        self.current_temp: Optional[float] = None
        self.last_update: Optional[datetime] = None
        self.last_error: Optional[str] = None
        self.update_count = 0
        self.error_count = 0
        
        # Session for HTTP requests
        self.session: Optional[aiohttp.ClientSession] = None
        self.enabled = self.config.get('enabled', True)
        
        if not self.enabled:
            logger.info("Weather service disabled in configuration")
        elif not self.api_key or self.api_key == "YOUR_API_KEY_HERE":
            logger.warning("Weather service disabled: no API key configured")
            self.enabled = False
        elif not self.zip_code:
            logger.warning("Weather service disabled: no zip code configured")
            self.enabled = False
    
    async def start(self):
        """Initialize weather service"""
        if not self.enabled:
            return
        
        logger.info(f"Starting weather service for zip code {self.zip_code}")
        
        # Create HTTP session
        self.session = aiohttp.ClientSession(timeout=self.timeout)
        
        # Fetch initial weather data
        await self.update_temperature()
        
        logger.info(f"Weather service started - updating every {self.update_interval//60} minutes")
    
    async def stop(self):
        """Stop weather service"""
        if self.session:
            await self.session.close()
        logger.info("Weather service stopped")
    
    async def get_current_temperature(self) -> Optional[float]:
        """
        Get current local temperature
        Returns cached temperature if recent, otherwise fetches new data
        """
        if not self.enabled:
            return self.fallback_temp
        
        # Check if we need to update
        now = datetime.now(timezone.utc)
        
        if (self.last_update is None or 
            (now - self.last_update).total_seconds() > self.update_interval):
            await self.update_temperature()
        
        return self.current_temp or self.fallback_temp
    
    async def update_temperature(self):
        """Fetch current temperature from OpenWeatherMap API"""
        if not self.enabled or not self.session:
            return
        
        for attempt in range(self.retry_attempts):
            try:
                # OpenWeatherMap current weather API by zip code
                url = f"https://api.openweathermap.org/data/2.5/weather"
                params = {
                    'zip': f"{self.zip_code},US",
                    'appid': self.api_key,
                    'units': 'imperial'  # Fahrenheit temperatures
                }
                
                logger.debug(f"Fetching weather data for {self.zip_code} (attempt {attempt + 1})")
                
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Extract temperature
                        temp_kelvin = data['main']['temp']
                        self.current_temp = temp_kelvin  # Already in Fahrenheit due to units=imperial
                        self.last_update = datetime.now(timezone.utc)
                        self.last_error = None
                        self.update_count += 1
                        
                        weather_desc = data['weather'][0]['description']
                        city_name = data['name']
                        
                        if attempt > 0:
                            logger.info(f"Weather update succeeded on attempt {attempt + 1}")
                        
                        logger.info(f"Local weather: {self.current_temp:.1f}°F in {city_name} ({weather_desc})")
                        return
                    
                    elif response.status == 401:
                        error_msg = "Invalid API key for weather service"
                        logger.error(error_msg)
                        self.last_error = error_msg
                        self.error_count += 1
                        return  # Don't retry on auth errors
                    
                    elif response.status == 404:
                        error_msg = f"Invalid zip code: {self.zip_code}"
                        logger.error(error_msg)
                        self.last_error = error_msg
                        self.error_count += 1
                        return  # Don't retry on invalid zip
                    
                    else:
                        error_text = await response.text()
                        logger.warning(f"Weather API error {response.status}: {error_text[:100]}")
                        
                        if attempt < self.retry_attempts - 1:
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff
            
            except aiohttp.ClientConnectorError as e:
                logger.warning(f"Weather API connection error (attempt {attempt + 1}): {e}")
                if attempt < self.retry_attempts - 1:
                    await asyncio.sleep(2 ** attempt)
            
            except Exception as e:
                logger.warning(f"Weather update attempt {attempt + 1} failed: {e}")
                if attempt < self.retry_attempts - 1:
                    await asyncio.sleep(2 ** attempt)
        
        # All attempts failed
        self.last_error = f"Failed to fetch weather data after {self.retry_attempts} attempts"
        self.error_count += 1
        logger.error(self.last_error)
        
        # Use fallback temperature if configured
        if self.fallback_temp is not None:
            logger.info(f"Using fallback temperature: {self.fallback_temp}°F")
    
    def get_status(self) -> Dict[str, Any]:
        """Get weather service status for monitoring"""
        return {
            "enabled": self.enabled,
            "zip_code": self.zip_code,
            "current_temp": self.current_temp,
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "last_error": self.last_error,
            "update_count": self.update_count,
            "error_count": self.error_count,
            "next_update": (
                (self.last_update + timedelta(seconds=self.update_interval)).isoformat() 
                if self.last_update else None
            )
        }
