"""
Upload services for status and minute data
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Any
import aiohttp
import time

logger = logging.getLogger(__name__)

class UploadServices:
    """Handles status and minute data uploads to public server"""
    
    def __init__(self, config: Dict, session: aiohttp.ClientSession, db_manager, stats: Dict):
        self.config = config
        self.session = session
        self.db = db_manager
        self.stats = stats
        self.base_url = config['public_server']['base_url']
        self.site_id = config['site']['site_id']
        self.retry_attempts = config['public_server']['retry_attempts']
        self.retry_delay = config['public_server']['retry_delay_seconds']
        
        # Immediate update settings
        self.immediate_batch_size = config.get('immediate_upload', {}).get('batch_size', 10)
        self.immediate_timeout = config.get('immediate_upload', {}).get('timeout_seconds', 5)
        self.immediate_retry_attempts = config.get('immediate_upload', {}).get('retry_attempts', 2)
        
        self.upload_queue = asyncio.Queue()
        self.last_immediate_upload = time.time()
    
    async def queue_immediate_update(self, thermostats_data: List[Dict]):
        """Queue thermostats for immediate upload due to changes"""
        try:
            timestamp = datetime.now(timezone.utc).isoformat()
            upload_data = {
                "site_id": self.site_id,
                "timestamp": timestamp,
                "thermostats": thermostats_data,
                "immediate_update": True
            }

            await self.upload_queue.put(upload_data)
            logger.debug(f"Queued immediate update for {len(thermostats_data)} thermostats")

        except Exception as e:
            logger.error(f"Failed to queue immediate update: {e}")

    async def immediate_upload_processor(self):
        """Process immediate upload queue"""
        logger.info("Immediate upload processor started")

        batch_buffer = []
        last_batch_time = time.time()

        while True:  # Will be managed by the main sync service
            try:
                # Try to get upload data with short timeout
                try:
                    upload_data = await asyncio.wait_for(self.upload_queue.get(), timeout=1.0)
                    batch_buffer.append(upload_data)
                except asyncio.TimeoutError:
                    upload_data = None

                current_time = time.time()
                batch_age = current_time - last_batch_time

                # Send batch if conditions met
                should_send_batch = (
                    batch_buffer and (
                        len(batch_buffer) >= self.immediate_batch_size or
                        batch_age >= self.immediate_timeout or
                        (upload_data is None and batch_buffer)
                    )
                )

                if should_send_batch:
                    # Merge all thermostats from batch into single upload
                    merged_thermostats = []
                    for batch_item in batch_buffer:
                        merged_thermostats.extend(batch_item['thermostats'])

                    # Create consolidated upload
                    consolidated_upload = {
                        "site_id": self.site_id,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "thermostats": merged_thermostats,
                        "immediate_update": True
                    }

                    # Send to public server
                    success = await self._send_status_upload(consolidated_upload, immediate=True)

                    if success:
                        self.stats['immediate_uploads'] += 1
                        self.stats['total_status_updates'] += len(merged_thermostats)
                        self.last_immediate_upload = current_time
                    else:
                        self.stats['upload_failures'] += 1

                    # Clear batch buffer
                    batch_buffer.clear()
                    last_batch_time = current_time

            except Exception as e:
                logger.error(f"Immediate upload processor error: {e}")
                await asyncio.sleep(1.0)

    async def status_upload_service(self):
        """Status upload service (fallback every 30s)"""
        status_interval = self.config['public_server']['status_upload_seconds']
        logger.info(f"Status upload service started (fallback every {status_interval}s)")

        while True:  # Will be managed by the main sync service
            try:
                await asyncio.sleep(status_interval)

                # Only do fallback upload if no immediate upload in the last interval
                time_since_immediate = time.time() - self.last_immediate_upload

                if time_since_immediate >= status_interval:
                    await self._upload_current_status_fallback()
                else:
                    logger.debug("Skipping fallback upload - immediate update recent")

            except Exception as e:
                logger.error(f"Status upload service error: {e}")

    async def _upload_current_status_fallback(self):
        """Fallback status upload"""
        try:
            current_status = await self.db.get_current_status()

            if not current_status:
                logger.debug("No current status data for fallback upload")
                return

            # Convert to upload format
            thermostats_data = []
            for status in current_status:
                thermostat_data = {
                    "thermostat_id": status.thermostat_id,
                    "ip_address": str(status.ip_address),
                    "temp": status.temp,
                    "t_heat": status.t_heat,
                    "tmode": status.tmode,
                    "tstate": status.tstate,
                    "hold": status.hold,
                    "override": status.override,
                    "last_poll_success": status.last_error is None,
                    "last_error": status.last_error
                }

                # Include local weather temperature if available
                if status.local_temp is not None:
                    thermostat_data["local_temp"] = status.local_temp

                thermostats_data.append(thermostat_data)

            upload_data = {
                "site_id": self.site_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "thermostats": thermostats_data,
                "fallback_upload": True
            }

            success = await self._send_status_upload(upload_data, immediate=False)

            if success:
                await self.db.update_sync_checkpoint('status_upload', datetime.now(timezone.utc))
                self.stats['fallback_uploads'] += 1
                self.stats['total_status_updates'] += len(thermostats_data)
                logger.info(f"Fallback upload successful for {len(thermostats_data)} thermostats")
            else:
                logger.warning("Fallback status upload failed after retries")
                self.stats['upload_failures'] += 1

        except Exception as e:
            logger.error(f"Fallback status upload error: {e}")
            self.stats['upload_failures'] += 1

    async def _send_status_upload(self, upload_data: Dict, immediate: bool = False) -> bool:
        """Send status upload with enhanced error handling"""
        try:
            upload_type = "immediate" if immediate else "fallback"
            logger.debug(f"Sending {upload_type} status upload for {len(upload_data['thermostats'])} thermostats")

            url = f"{self.base_url}/api/v1/sites/{self.site_id}/status"

            # Use enhanced retry logic for immediate updates
            retry_attempts = self.immediate_retry_attempts if immediate else self.retry_attempts

            for attempt in range(retry_attempts):
                try:
                    if not self.session:
                        logger.warning("No session available for upload")
                        return False

                    async with self.session.post(url, json=upload_data) as response:
                        if response.status in [200, 201]:
                            if attempt > 0:
                                logger.info(f"{upload_type.capitalize()} upload succeeded on attempt {attempt + 1}")
                            return True
                        elif response.status == 429:  # Rate limited
                            logger.warning(f"Rate limited on {upload_type} upload, attempt {attempt + 1}")
                            await asyncio.sleep(self.retry_delay * (attempt + 1))
                        else:
                            response_text = await response.text()
                            logger.warning(f"{upload_type.capitalize()} upload failed: {response.status}, attempt {attempt + 1}")
                            logger.debug(f"Response: {response_text[:200]}")
                            await asyncio.sleep(self.retry_delay)

                except aiohttp.ClientConnectorError as e:
                    logger.warning(f"Connection error on {upload_type} upload: {e}")
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                except Exception as e:
                    logger.warning(f"{upload_type.capitalize()} upload attempt {attempt + 1} failed: {e}")
                    if attempt < retry_attempts - 1:
                        await asyncio.sleep(self.retry_delay)

            logger.error(f"{upload_type.capitalize()} upload failed after {retry_attempts} attempts")
            return False

        except Exception as e:
            logger.error(f"Status upload error: {e}")
            return False

    async def minute_upload_service(self):
        """Minute data upload service"""
        minute_interval = self.config['public_server']['minute_upload_seconds']
        logger.info(f"Minute upload service started (every {minute_interval}s)")

        while True:  # Will be managed by the main sync service
            try:
                await asyncio.sleep(minute_interval)
                await self._upload_minute_data()

            except Exception as e:
                logger.error(f"Minute upload service error: {e}")


    async def _upload_minute_data(self):
        """Upload minute aggregation data - WITH DEBUG LOGGING"""
        try:
            # Get last upload checkpoint
            checkpoint = await self.db.get_sync_checkpoint('minute_upload')
            # logger.info(f"[DEBUG] Read checkpoint from DB: {checkpoint.strftime('%Y-%m-%d %H:%M:%S UTC') if checkpoint else 'None'}")
            
            if not checkpoint:
                checkpoint = datetime.now(timezone.utc) - timedelta(hours=1)
                logger.warning("No minute upload checkpoint found, using 1 hour ago")
            
            # Get minute data since last upload
            start_time = checkpoint
            end_time = datetime.now(timezone.utc)
            
            # logger.info(f"[DEBUG] Query parameters: start_time={start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}, end_time={end_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            
            logger.info(
                "minute upload window | start_time=%s | end_time=%s | duration=%s",
                start_time.strftime('%H:%M:%S'),
                end_time.strftime('%H:%M:%S'),
                str(end_time - start_time).split('.')[0],
            )

            minute_data = await self.db.get_minute_readings_since(start_time)
            
            # logger.info(f"[DEBUG] Query returned {len(minute_data)} records")
            # if minute_data:
            #     min_ts = min(r.minute_ts for r in minute_data)
            #     max_ts = max(r.minute_ts for r in minute_data)
            #     logger.info(f"[DEBUG] Data range: {min_ts.strftime('%Y-%m-%d %H:%M:%S')} to {max_ts.strftime('%Y-%m-%d %H:%M:%S')}")
            
            if not minute_data:
                logger.info(f"No minute data to upload. Exiting without updating checkpoint. Checkpoint remains: {checkpoint.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                return

            # Convert to upload format
            upload_records = []
            for record in minute_data:
                upload_record = {
                    "thermostat_id": record.thermostat_id,
                    "minute_ts": record.minute_ts.isoformat(),
                    "temp_avg": record.temp_avg,
                    "t_heat_last": record.t_heat_last,
                    "tmode_last": record.tmode_last,
                    "hvac_runtime_percent": record.hvac_runtime_percent,
                    "poll_count": record.poll_count,
                    "poll_failures": record.poll_failures
                }

                if record.local_temp_avg is not None:
                    upload_record["local_temp_avg"] = record.local_temp_avg

                upload_records.append(upload_record)

            # Batch upload
            max_batch = self.config['public_server']['max_batch_size']
            for i in range(0, len(upload_records), max_batch):
                batch = upload_records[i:i + max_batch]

                batch_data = {
                    "site_id": self.site_id,
                    "minute_readings": batch
                }

                url = f"{self.base_url}/api/v1/sites/{self.site_id}/minute"
                success = await self._post_with_retry(url, batch_data)
                # for idx, rec in enumerate(batch, start=1):
                #     ts_hms = (
                #         rec["minute_ts"][11:19]
                #         if isinstance(rec["minute_ts"], str)
                #         else rec["minute_ts"].strftime('%H:%M:%S')
                #     )
                #     logger.info(
                #         "idx=%d | thermostat_id=%s | minute_ts=%s | poll_count=%s",
                #         idx, rec["thermostat_id"], ts_hms, rec["poll_count"]
                #     )

                if not success:
                    logger.warning(f"Upload failed, checkpoint NOT updated. Remains: {checkpoint.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                    return

            # Update checkpoint on successful upload
            #logger.info(f"[DEBUG] About to calculate latest_minute_ts from {len(minute_data)} records")
            latest_minute_ts = max(record.minute_ts for record in minute_data)
            
            #logger.info(f"[DEBUG] Calculated latest_minute_ts: {latest_minute_ts.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            #logger.info(f"[DEBUG] About to update checkpoint from {checkpoint.strftime('%Y-%m-%d %H:%M:%S UTC')} to {latest_minute_ts.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            
            await self.db.update_sync_checkpoint('minute_upload', latest_minute_ts)
            #logger.info(f"[DEBUG] Checkpoint update SQL executed")

            # Verify the update
            # verify_checkpoint = await self.db.get_sync_checkpoint('minute_upload')
            # logger.info(f"[DEBUG] Verification: Read checkpoint back from DB: {verify_checkpoint.strftime('%Y-%m-%d %H:%M:%S UTC') if verify_checkpoint else 'None'}")
            # if verify_checkpoint and verify_checkpoint != latest_minute_ts:
            #     logger.error(f"[DEBUG]  CHECKPOINT MISMATCH! Expected {latest_minute_ts.strftime('%Y-%m-%d %H:%M:%S UTC')}, but DB has {verify_checkpoint.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            # elif verify_checkpoint and verify_checkpoint == latest_minute_ts:
            #     logger.info(f"[DEBUG] Checkpoint verified successfully: {verify_checkpoint.strftime('%Y-%m-%d %H:%M:%S UTC')}")

            # Log with runtime percentage info
            weather_count = sum(1 for r in upload_records if 'local_temp_avg' in r)
            runtime_avg = sum(r['hvac_runtime_percent'] for r in upload_records) / len(upload_records) if upload_records else 0
            logger.info(f"Minute upload successful: {len(upload_records)} records ({weather_count} with weather, avg runtime: {runtime_avg:.1f}%)")

        except Exception as e:
            logger.error(f"Minute data upload error: {e}")
            import traceback
            logger.error(f"[DEBUG] Traceback: {traceback.format_exc()}")







    async def _post_with_retry(self, url: str, data: Dict[str, Any]) -> bool:
        """Post data with retry logic"""
        if not self.session:
            return False

        for attempt in range(self.retry_attempts):
            try:
                async with self.session.post(url, json=data) as response:
                    if response.status in [200, 201]:
                        return True
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
