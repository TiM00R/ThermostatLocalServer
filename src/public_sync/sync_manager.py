"""
Enhanced Public Server Sync Manager
UPDATED: Protocol v2.0 - Uses phase_history array format with execution time tracking
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Any, Tuple
import aiohttp
import json
from dataclasses import dataclass, asdict
import time

from .command_executor import LocalCommandExecutor, DatabaseAdapter
from .upload_services import UploadServices
from database.manager import DatabaseManager
from discovery_command_handler import DiscoveryCommandHandler, DiscoveryProgress, DiscoveryStatus
from http_helper import create_thermostat_session, create_public_server_session
from config_loader import get_public_server_ssl_config

logger = logging.getLogger(__name__)

class EnhancedPublicServerSync:
    """Enhanced sync manager with discovery command progress support using phase_history format."""

    def __init__(self, config: Dict[str, Any], db: DatabaseManager, discovery_service=None):
        self.config = config
        self.db = db
        self.discovery_service = discovery_service
        self.running = False

        # Public server settings
        self.base_url = config['public_server']['base_url']
        self.site_token = config['public_server']['site_token']
        self.site_id = config['site']['site_id']

        # SSL configuration for public server connections
        self.ssl_config = get_public_server_ssl_config(config)

        # Enhanced timing settings
        self.status_interval = config['public_server']['status_upload_seconds']
        self.minute_interval = config['public_server']['minute_upload_seconds']
        self.command_interval = config['public_server']['command_poll_seconds']

        # Immediate update settings
        self.immediate_batch_size = config.get('immediate_upload', {}).get('batch_size', 10)
        self.immediate_timeout = config.get('immediate_upload', {}).get('timeout_seconds', 5)
        self.immediate_retry_attempts = config.get('immediate_upload', {}).get('retry_attempts', 2)

        # HTTP settings - use SSL-aware timeout
        timeout_seconds = self.ssl_config['timeout_seconds']
        self.timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self.retry_attempts = config['public_server']['retry_attempts']
        self.retry_delay = config['public_server']['retry_delay_seconds']

        # Session and state tracking
        self.session: Optional[aiohttp.ClientSession] = None
        self.last_immediate_upload = time.time()
        self.upload_queue = asyncio.Queue()

        # Command acknowledgment queue
        self.command_acks = []

        # Discovery command handler
        self.discovery_handler: Optional[DiscoveryCommandHandler] = None

        # set_state command executor
        self.command_executor: Optional[LocalCommandExecutor] = None

        self.stats = {
            'immediate_uploads': 0,
            'fallback_uploads': 0,
            'upload_failures': 0,
            'total_status_updates': 0,
            'command_polls': 0,
            'command_acks': 0,
            'discovery_commands': 0,
            'discovery_progress_reports': 0
        }
        self.upload_services = None
        
    async def start(self):
        """Start enhanced sync services with discovery support"""
        if not self.config['public_server']['enabled']:
            logger.info("Public server sync disabled in configuration")
            return

        logger.info("Starting enhanced public server sync with SSL support...")

        # Log SSL configuration
        ssl_enabled = self.ssl_config['ssl_enabled']
        ssl_verify = self.ssl_config['ssl_verify']
        ca_cert_path = self.ssl_config['ca_cert_path']
        
        logger.info(f"Public server SSL configuration:")
        logger.info(f"  - SSL Enabled: {ssl_enabled}")
        logger.info(f"  - SSL Verify: {ssl_verify}")
        logger.info(f"  - CA Cert Path: {ca_cert_path}")
        logger.info(f"  - Base URL: {self.base_url}")

        # Create SSL-aware HTTP session
        self.session = create_public_server_session(
            timeout_seconds=self.ssl_config['timeout_seconds'],
            ssl_enabled=ssl_enabled,
            ssl_verify=ssl_verify,
            ca_cert_path=ca_cert_path
        )

        # Add authentication headers to session
        self.session.headers.update({
            'X-Site-Token': self.site_token,
            'Content-Type': 'application/json'
        })

        # Initialize upload services with shared SSL-aware session
        self.upload_services = UploadServices(self.config, self.session, self.db, self.stats)

        # Initialize unified set_state command executor (reuse shared session)
        db_adapter = DatabaseAdapter(self.db)
        self.command_executor = LocalCommandExecutor(db_adapter, self.session)

        # Initialize discovery command handler
        if self.discovery_service:
            self.discovery_handler = DiscoveryCommandHandler(
                db=self.db,
                discovery=self.discovery_service,
                public_sync=self
            )
            # Add progress callback to send individual updates to public server
            self.discovery_handler.add_progress_callback(self._handle_discovery_progress)
            logger.info("Discovery command handler initialized with Protocol v2.0 (phase_history format)")

        self.running = True

        # Initialize sync checkpoints
        await self._initialize_checkpoints()

        protocol = "HTTPS" if ssl_enabled else "HTTP"
        logger.info(f"Enhanced sync started with {protocol} - runtime percentage upload enabled")

    async def get_sync_tasks(self):
        """Get all sync tasks using upload services"""
        if not self.running:
            return []

        # Get upload service tasks
        upload_tasks = [
            asyncio.create_task(self.upload_services.immediate_upload_processor()),
            asyncio.create_task(self.upload_services.status_upload_service()),
            asyncio.create_task(self.upload_services.minute_upload_service())
        ]
        
        # Keep other tasks
        other_tasks = [
            asyncio.create_task(self._command_polling_service()),
            asyncio.create_task(self._command_ack_service()),
            asyncio.create_task(self._stats_reporter())
        ]
        
        return upload_tasks + other_tasks

    # ==================  DISCOVERY PROGRESS METHODS ==================

    async def _handle_discovery_progress(self, progress: DiscoveryProgress):
        """
        Handle discovery progress updates with phase_history array.
        Protocol v2.0: Send phase_history array + execution_time_seconds at root.
        """
        try:
            # Extract summary for logging
            current_phase = next((p for p in progress.phase_history if p["status"] == "inprogress"), None)
            if current_phase:
                phase_name = current_phase.get('phase', 'unknown')
                action = current_phase.get('current_action', 'unknown')
                devices = current_phase.get('devices_found', 0)
                phase_time = current_phase.get('elapsed_time', 0)
                total_time = progress.execution_time_seconds
                
                logger.info(
                    f"Transmitting progress: {phase_name} - {action} "
                    f"({devices} devices, phase: {phase_time:.1f}s, total: {total_time:.1f}s)"
                )
            
            # Build progress payload in new format
            progress_data = {
                "command_id": progress.command_id,
                "site_id": self.site_id,
                "status": progress.status.value,
                "execution_time_seconds": progress.execution_time_seconds,  # Total time at root
                "phase_history": progress.phase_history  # Complete phase history array
            }

            # Send immediately
            await self._send_single_progress_update(progress_data)

        except Exception as e:
            logger.error(f"Failed to handle discovery progress: {e}")

    async def _send_single_progress_update(self, progress_data: Dict):
        """
        Send individual progress update to public server.
        Logs complete JSON payload being sent.
        """
        try:
            url = f"{self.base_url}/api/v1/sites/{self.site_id}/commands/progress"
            
            # Log complete JSON payload being sent
            logger.info("=" * 80)
            logger.info("SENDING PROGRESS TO BACKEND:")
            logger.info(json.dumps(progress_data, indent=2, default=str))
            logger.info("=" * 80)
            
            # Send request
            success = await self._post_with_retry(url, progress_data)

            # Log result
            if success:
                self.stats['discovery_progress_reports'] += 1
                total_time = progress_data.get('execution_time_seconds', 0)
                logger.info(f"✅ Progress transmitted: 200 OK (total: {total_time:.1f}s) - command {progress_data['command_id']}")
            else:
                logger.warning(f"❌ Progress transmission failed - command {progress_data['command_id']}")

        except Exception as e:
            logger.error(f"Failed to send discovery progress: {e}")
            logger.error(f"Failed payload: {json.dumps(progress_data, indent=2, default=str)}")

    async def _execute_discovery_command(self, command: Dict):
        """Execute discovery command"""
        if not self.discovery_handler:
            self._queue_ack(command.get('cmd_id'), False, "Discovery handler not available", None)
            return

        try:
            cmd_id = command['cmd_id']
            logger.info(f"[SEARCH] Executing discovery command {cmd_id}")
            self.stats['discovery_commands'] += 1

            # Execute discovery command
            result = await self.discovery_handler.execute_discovery_command(command)

            # Send final progress update and acknowledgment
            await self._send_final_discovery_progress(cmd_id, result)
            self._queue_discovery_ack(cmd_id, result)

        except Exception as e:
            logger.error(f"Discovery command execution error: {e}")
            self._queue_ack(command.get('cmd_id'), False, str(e), None)

    async def _send_final_discovery_progress(self, cmd_id: str, result):
        """
        Send final progress update when discovery completes or fails.
        Protocol v2.0: Uses phase_history format.
        """
        try:
            # Get the final phase_history from the discovery handler
            final_phase_history = []
            if self.discovery_handler and self.discovery_handler.last_progress:
                final_phase_history = self.discovery_handler.last_progress.phase_history
            
            # Send final progress update
            final_progress = {
                "command_id": cmd_id,
                "site_id": self.site_id,
                "status": result.status.value,
                "execution_time_seconds": result.execution_time_seconds,  # Total discovery time
                "phase_history": final_phase_history  # Complete phase history
            }
            
            # Send final progress update
            await self._send_single_progress_update(final_progress)

            if result.status == DiscoveryStatus.COMPLETED:
                total_devices = result.discovery_results.get('total_devices_found', 0) if result.discovery_results else 0
                logger.info(f"Discovery completed for {cmd_id}: {total_devices} devices found")
            else:
                error_msg = result.error.get('message', 'Unknown error') if result.error else 'Unknown error'
                logger.warning(f"Discovery failed for {cmd_id}: {error_msg}")

        except Exception as e:
            logger.error(f"Failed to send final discovery progress for {cmd_id}: {e}")

    def _queue_discovery_ack(self, cmd_id: str, result):
        """Queue discovery command acknowledgment with full results"""
        ack_data = {
            "cmd_id": cmd_id,
            "success": result.status == DiscoveryStatus.COMPLETED,
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "error_message": result.error.get('message') if result.error else None,
            "response_data": {
                "discovery_results": result.discovery_results,
                "execution_time_seconds": result.execution_time_seconds,
                "status": result.status.value
            }
        }
        self.command_acks.append(ack_data)
        logger.info(f"Queued discovery ACK for command {cmd_id}: {result.status.value}")

    # ================== COMMAND EXECUTION (set_state + set_away_temp + discovery) ==================

    async def _execute_command(self, command: Dict):
        """Execute a single command - unified set_state plus discovery and away temp support"""
        try:
            cmd_id = command['cmd_id']
            cmd_type = command['command']
            thermostat_id = command.get('thermostat_id')
            params = command.get('params', {})
            timeout_seconds = command.get('timeout_seconds', 300)

            logger.info(f"Executing command {cmd_id}: {cmd_type} for {thermostat_id}")

            # Handle discovery commands
            if cmd_type == "discover_devices":
                await self._execute_discovery_command(command)
                return

            # Handle supported unified commands
            if cmd_type not in ["set_state", "set_away_temp"]:
                self._queue_ack(cmd_id, False, f"Unsupported command type: {cmd_type}", None)
                return

            if not self.command_executor:
                self._queue_ack(cmd_id, False, "Command executor not available", None)
                return

            # Execute unified command (set_state or set_away_temp)
            success, error_msg, extra = await self.command_executor.execute_command(
                self.site_id, thermostat_id, cmd_type, params, timeout_seconds
            )

            # Queue acknowledgment with per-thermostat details when available
            self._queue_ack(cmd_id, success, error_msg, extra)

        except Exception as e:
            logger.error(f"Command execution error: {e}")
            self._queue_ack(command.get('cmd_id'), False, str(e), None)

    # ================== Immediate & Periodic Upload Services  ==================

    async def queue_immediate_update(self, thermostats_data: List[Dict]):
        """Queue thermostats for immediate upload via upload services"""
        if self.upload_services:
            await self.upload_services.queue_immediate_update(thermostats_data)
        else:
            logger.warning("Upload services not initialized")

    async def _command_polling_service(self):
        """Command polling service"""
        logger.info(f"Command polling service started (every {self.command_interval}s)")

        while self.running:
            try:
                await asyncio.sleep(self.command_interval)
                if not self.running:
                    break

                await self._poll_and_execute_commands()

            except Exception as e:
                logger.error(f"Command polling service error: {e}")

    async def _poll_and_execute_commands(self):
        """Poll for pending commands and execute them"""
        try:
            url = f"{self.base_url}/api/v1/sites/{self.site_id}/commands/pending"

            if not self.session:
                return

            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    commands = data.get('commands', [])

                    if commands:
                        logger.info(f"Received {len(commands)} commands from public server")
                        self.stats['command_polls'] += 1

                        # Execute commands
                        for cmd in commands:
                            await self._execute_command(cmd)

                elif response.status == 404:
                    # No pending commands - this is normal
                    pass
                else:
                    logger.warning(f"Command poll failed: {response.status}")

        except Exception as e:
            logger.error(f"Command polling error: {e}")

    async def _command_ack_service(self):
        """Batch command acknowledgment service"""
        logger.info("Command acknowledgment service started")

        while self.running:
            try:
                # Send ACKs every 2 seconds or when queue gets large
                await asyncio.sleep(2.0)

                if self.command_acks:
                    await self._send_command_acks()

            except Exception as e:
                logger.error(f"Command ACK service error: {e}")

    def _queue_ack(self, cmd_id: str, success: bool, error_msg: Optional[str], response_data: Optional[Dict[str, Any]]):
        """Queue command acknowledgment for batch sending (now supports response_data)"""
        ack_data = {
            "cmd_id": cmd_id,
            "success": success,
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "error_message": error_msg,
            "response_data": response_data
        }
        self.command_acks.append(ack_data)
        logger.debug(f"Queued ACK for command {cmd_id}: {'SUCCESS' if success else f'FAILED: {error_msg}'}")

    async def _send_command_acks(self):
        """Send batched command acknowledgments to public server"""
        if not self.command_acks:
            return

        try:
            # Prepare batch data
            batch_data = {
                "site_id": self.site_id,
                "results": self.command_acks.copy()
            }

            # Send to public server
            url = f"{self.base_url}/api/v1/sites/{self.site_id}/commands/results"
            success = await self._post_with_retry(url, batch_data)

            if success:
                logger.info(f"Successfully sent {len(self.command_acks)} command ACKs to public server")
                self.stats['command_acks'] += len(self.command_acks)
                self.command_acks.clear()
            else:
                logger.warning(f"Failed to send {len(self.command_acks)} command ACKs")
                # Keep ACKs for retry, but limit queue size
                if len(self.command_acks) > 100:
                    self.command_acks = self.command_acks[-50:]
                    logger.warning("Command ACK queue too large, discarded old ACKs")

        except Exception as e:
            logger.error(f"Failed to send command ACKs: {e}")

    async def _stats_reporter(self):
        """Report upload statistics periodically"""
        report_interval = 300  # Report every 5 minutes

        while self.running:
            try:
                await asyncio.sleep(report_interval)

                if not self.running:
                    break

                logger.info(
                    f"Sync Stats - Immediate: {self.stats['immediate_uploads']}, "
                    f"Fallback: {self.stats['fallback_uploads']}, "
                    f"Failures: {self.stats['upload_failures']}, "
                    f"Total Updates: {self.stats['total_status_updates']}, "
                    f"Command Polls: {self.stats['command_polls']}, "
                    f"Command ACKs: {self.stats['command_acks']}, "
                    f"Discovery Commands: {self.stats['discovery_commands']}, "
                    f"Discovery Progress: {self.stats['discovery_progress_reports']}"
                )

                # Reset stats for next period
                self.stats = {key: 0 for key in self.stats.keys()}

            except Exception as e:
                logger.error(f"Stats reporter error: {e}")

    async def _initialize_checkpoints(self):
        """Initialize sync checkpoint entries"""
        checkpoints = ['status_upload', 'minute_upload', 'command_poll']

        for checkpoint_name in checkpoints:
            checkpoint = await self.db.get_sync_checkpoint(checkpoint_name)
            if not checkpoint:
                await self.db.update_sync_checkpoint(checkpoint_name, datetime.now(timezone.utc))
                logger.info(f"Initialized sync checkpoint: {checkpoint_name}")

    async def _post_with_retry(self, url: str, data: Dict[str, Any]) -> bool:
        """Post data with retry logic (session already has headers and SSL configuration)"""
        if not self.session:
            return False

        for attempt in range(self.retry_attempts):
            try:
                async with self.session.post(url, json=data) as response:
                    if response.status in [200, 201]:
                        return True
                    elif response.status == 422:
                        # Unprocessable Entity - log the detailed error
                        error_text = await response.text()
                        logger.error(f"422 Validation Error on {url}: {error_text}")
                        logger.error(f"Payload that failed: {json.dumps(data, indent=2, default=str)}")
                        return False  # Don't retry validation errors
                    elif response.status == 429:  # Rate limited
                        logger.warning(f"Rate limited, attempt {attempt + 1}")
                        await asyncio.sleep(self.retry_delay * (attempt + 1))
                    else:
                        error_text = await response.text()
                        logger.warning(f"Upload failed: {response.status}, attempt {attempt + 1}")
                        logger.debug(f"Error response: {error_text[:200]}")
                        await asyncio.sleep(self.retry_delay)

            except Exception as e:
                logger.warning(f"Upload attempt {attempt + 1} failed: {e}")
                if attempt < self.retry_attempts - 1:
                    await asyncio.sleep(self.retry_delay)

        return False

    async def register_thermostats(self, thermostats: List[Any]) -> bool:
        """Register thermostats with public server - includes away_temp"""
        try:
            if not thermostats:
                return True

            # Convert database records to registration format
            thermostats_data = []
            for thermostat in thermostats:
                thermostats_data.append({
                    "thermostat_id": thermostat.thermostat_id or "unknown",
                    "name": thermostat.name or "Unknown Thermostat",
                    "model": thermostat.model or "Unknown Model",
                    "ip_address": str(thermostat.ip_address) if thermostat.ip_address else "0.0.0.0",
                    "api_version": thermostat.api_version or "1.0",
                    "fw_version": thermostat.fw_version or "Unknown",
                    "capabilities": thermostat.capabilities if thermostat.capabilities is not None else {},
                    "discovery_method": thermostat.discovery_method or "Unknown",
                    "away_temp": getattr(thermostat, 'away_temp', 50.0)
                })

            registration_data = {
                "site_id": self.site_id,
                "thermostats": thermostats_data
            }

            url = f"{self.base_url}/api/v1/sites/{self.site_id}/thermostats/register"
            success = await self._post_with_retry(url, registration_data)

            if success:
                logger.info(f"Successfully registered {len(thermostats_data)} thermostats with away temperatures")
            else:
                logger.error(f"Failed to register {len(thermostats_data)} thermostats with public server")

            return success

        except Exception as e:
            logger.error(f"Thermostat registration error: {e}")
            return False

    async def stop(self):
        """Stop enhanced sync services"""
        logger.info("Stopping enhanced public server sync...")
        self.running = False

        # Send any remaining ACKs
        if self.command_acks:
            await self._send_command_acks()

        # Close set_state executor (only if it owns the session, which it doesn't here)
        if self.command_executor:
            await self.command_executor.close()

        if self.session:
            await self.session.close()
