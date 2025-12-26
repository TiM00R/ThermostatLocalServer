"""
Main discovery manager with progressive discovery strategies
UPDATED: Protocol v1.1 - Independent phase discovery with checkpoint-based progress
"""

import asyncio
import logging
import time
import socket
import ipaddress
import aiohttp
from typing import List, Tuple, Dict, Optional
from .models import ThermostatDevice, DiscoveryResult
from .network_discovery import NetworkDiscovery

# Import HTTP helper function

from http_helper import create_thermostat_session

logger = logging.getLogger(__name__)

class ThermostatDiscovery:
    """Main discovery service for RadioThermostat devices"""
    
    def __init__(self, config: Dict, database_manager=None):
        self.config = config
        self.db = database_manager  #  Database access for progressive discovery
        self.known_devices = {}  # uuid -> ThermostatDevice
        self.discovery_timeout = config.get('discovery_timeout', 10)
        self.request_timeout = config.get('request_timeout', 3)  # Reduced for faster startup
        self.ip_ranges = config.get('ip_ranges', ['10.0.60.1-10.0.60.254'])
        
    # ================== PROGRESSIVE DISCOVERY METHODS ==================
    
    async def discover_combined_startup(self) -> Tuple[List[ThermostatDevice], bool]:
        """
        NEW: Combined DB + UDP discovery for fast startup
        Returns: (devices_found, should_continue_to_tcp)
        """
        logger.info("[LAUNCH] Starting progressive discovery (DB + UDP)...")
        start_time = time.time()
        
        all_devices = {}
        
        # Step 1: Database-first discovery
        db_result = await self.discover_from_database()
        for device in db_result.devices:
            all_devices[device.uuid] = device
        logger.info(f" Database discovery: {len(db_result.devices)} devices in {db_result.duration_seconds:.1f}s")
        
        # === ENHANCED LOGGING: Database Discovery Phase ===
        if db_result.devices:
            db_ips = [device.ip for device in db_result.devices]
            logger.info(f"[DB DISCOVERY PHASE] Found {len(db_result.devices)} thermostats from database")
            logger.info(f"[DB DISCOVERY PHASE] IPs: {', '.join(db_ips)}")
        else:
            logger.info(f"[DB DISCOVERY PHASE] Found 0 thermostats from database")
        
        # Step 2: UDP multicast discovery
        udp_result = await self.discover_udp_only()
        new_from_udp = 0
        udp_new_ips = []
        udp_total_ips = []
        for device in udp_result.devices:
            udp_total_ips.append(device.ip)
            if device.uuid not in all_devices:
                all_devices[device.uuid] = device
                new_from_udp += 1
                udp_new_ips.append(device.ip)
        logger.info(f" UDP discovery: {new_from_udp} new devices in {udp_result.duration_seconds:.1f}s")
        
        # === ENHANCED LOGGING: UDP Discovery Phase ===
        logger.info(f"[UDP DISCOVERY PHASE] Found {len(udp_result.devices)} thermostats total, {new_from_udp} new")
        if udp_total_ips:
            logger.info(f"[UDP DISCOVERY PHASE] Total IPs: {', '.join(udp_total_ips)}")
            if udp_new_ips:
                logger.info(f"[UDP DISCOVERY PHASE] New IPs: {', '.join(udp_new_ips)}")
        else:
            logger.info(f"[UDP DISCOVERY PHASE] No thermostats found via UDP")
        
        # Update known devices registry
        self.known_devices.update(all_devices)
        
        devices_list = list(all_devices.values())
        total_time = time.time() - start_time
        
        should_continue_to_tcp = len(devices_list) == 0
        status = "ZERO devices found - will continue to TCP" if should_continue_to_tcp else f"{len(devices_list)} devices found - ready for operation"
        
        logger.info(f"[PASS] Combined startup discovery: {status} (total: {total_time:.1f}s)")
        return devices_list, should_continue_to_tcp
    
    async def discover_from_database(self) -> DiscoveryResult:
        """
        NEW: Test known devices from database first (fastest method)
        """
        start_time = time.time()
        devices = []
        devices_tested = 0
        
        if not self.db:
            logger.debug("No database available for device lookup")
            return DiscoveryResult([], "database", 0, 0, 0)
        
        try:
            # Get active thermostats from database
            db_thermostats = await self.db.get_active_thermostats()
            devices_tested = len(db_thermostats)
            
            if not db_thermostats:
                logger.debug("No known devices in database")
                return DiscoveryResult([], "database", time.time() - start_time, 0, 0)
            
            logger.info(f"Testing {len(db_thermostats)} known devices from database...")
            
            # Test each known device quickly
            semaphore = asyncio.Semaphore(5)  # Limit concurrent DB device tests
            
            async def test_known_device(thermostat_record):
                async with semaphore:
                    device = await self._get_device_details(thermostat_record.ip_address, "database")
                    if device:
                        devices.append(device)
                        logger.info(f"[OK] Database device responsive: {device.name} ({device.ip})")
                    else:
                        logger.debug(f"✗ Database device not responding: {thermostat_record.name} ({thermostat_record.ip_address})")
            
            # Test all known devices concurrently
            tasks = [test_known_device(record) for record in db_thermostats]
            await asyncio.gather(*tasks, return_exceptions=True)
            
        except Exception as e:
            logger.error(f"Database discovery failed: {e}")
        
        duration = time.time() - start_time
        return DiscoveryResult(devices, "database", duration, devices_tested, len(devices))
    
    async def discover_udp_only(self) -> DiscoveryResult:
        """
        NEW: UDP-only discovery (separated from IP scanning)
        """
        start_time = time.time()
        devices = await self.udp_multicast_discovery()
        duration = time.time() - start_time
        
        return DiscoveryResult(devices, "udp_multicast", duration, 1, len(devices))
    
    async def discover_tcp_progressive(self, callback=None) -> DiscoveryResult:
        """
        Progressive TCP discovery with checkpoint-based progress reporting
        Scans ENTIRE IP range without exclusions - each phase is independent
        
        Args:
            callback: Optional async function called every 10 IPs
                     Signature: callback(devices_since_checkpoint, ips_scanned, ips_total)
        
        Returns:
            Single DiscoveryResult with all devices found
        """
        logger.info("[SEARCH] Starting TCP discovery with checkpoint reporting...")
        start_time = time.time()
        
        # Generate ALL IPs to scan (no exclusions - phase is independent)
        all_ips = self._generate_scan_ips()
        ips_total = len(all_ips)
        ips_scanned = 0
        
        all_devices_found = []
        devices_since_checkpoint = []
        
        logger.info(f"TCP scan will check ALL {ips_total} IP addresses (no exclusions)...")
        
        semaphore = asyncio.Semaphore(5)
        
        for ip_str in all_ips:
            async with semaphore:
                device = await self._get_device_details(ip_str, "tcp_scan")
                
                if device:
                    all_devices_found.append(device)
                    devices_since_checkpoint.append(device)
                    self.known_devices[device.uuid] = device
                    logger.info(f"[OK] TCP found: {device.name} ({device.ip})")
                
                ips_scanned += 1
                
                # Checkpoint: Every 10 IPs OR final IP
                if ips_scanned % 10 == 0 or ips_scanned == ips_total:
                    if callback:
                        await callback(
                            devices_since_checkpoint.copy(),
                            ips_scanned,
                            ips_total
                        )
                    
                    # Progress logging
                    if ips_scanned % 50 == 0:
                        logger.info(f"TCP scan progress: {ips_scanned}/{ips_total} IPs, {len(all_devices_found)} devices")
                    
                    # Reset checkpoint accumulator
                    devices_since_checkpoint = []
        
        # Return single result
        duration = time.time() - start_time
        result = DiscoveryResult(
            devices=all_devices_found,
            method="tcp_scan",
            duration_seconds=duration,
            devices_tested=ips_scanned,
            success_count=len(all_devices_found)
        )
        
        logger.info(f"[PASS] TCP discovery complete: {len(all_devices_found)} devices found scanning {ips_scanned} IPs in {duration:.1f}s")
        return result
    
    def _generate_scan_ips(self) -> List[str]:
        """
        Generate list of ALL IPs to scan - NO EXCLUSIONS
        Each discovery phase is completely independent
        """
        all_ips = []
        # REMOVED: known_ips filtering - scan entire range independently
        
        for ip_range in self.ip_ranges:
            if '-' in ip_range:
                start_ip, end_ip = ip_range.split('-')
                start = ipaddress.IPv4Address(start_ip.strip())
                end = ipaddress.IPv4Address(end_ip.strip())
                
                current = start
                while current <= end:
                    all_ips.append(str(current))  # Add ALL IPs, no filtering
                    current += 1
            else:
                # Single IP or CIDR notation
                try:
                    network = ipaddress.IPv4Network(ip_range.strip(), strict=False)
                    for ip in network.hosts():
                        all_ips.append(str(ip))  # Add ALL IPs, no filtering
                except ValueError:
                    logger.warning(f"Invalid IP range format: {ip_range}")
        
        return all_ips
    
    # ================== OBSOLETE METHODS (PRESERVED FOR COMPATIBILITY) ==================
    

    async def udp_multicast_discovery(self) -> List[ThermostatDevice]:
        """
        Implements Marvell Service Discovery Protocol via UDP multicast
        """
        devices = []
        
        try:
            # Create UDP socket for multicast
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('', 0))  # Bind to any available port
            sock.settimeout(2.0)  # Short timeout for individual receives
            
            # Prepare discovery message
            discover_msg = (
                "TYPE: WM-DISCOVER\n"
                "VERSION: 1.0\n"
                "SERVICES: com.rtcoa.tstat:1.0"
            )
            
            logger.info("Sending UDP multicast discovery...")
            sock.sendto(discover_msg.encode('utf-8'), ('239.255.255.250', 1900))
            
            # Listen for responses
            start_time = time.time()
            while time.time() - start_time < self.discovery_timeout:
                try:
                    data, addr = sock.recvfrom(1024)
                    device = await self._parse_multicast_response(data, addr[0])
                    if device:
                        devices.append(device)
                        logger.info(f"Found device via multicast: {device.name} ({device.ip})")
                except socket.timeout:
                    continue
                except Exception as e:
                    logger.warning(f"Error parsing multicast response: {e}")
                    
        except Exception as e:
            logger.error(f"UDP multicast discovery failed: {e}")
        finally:
            sock.close()
            
        return devices

    async def _parse_multicast_response(self, data: bytes, sender_ip: str) -> Optional[ThermostatDevice]:
        """
        Parse WM-NOTIFY response from thermostat
        """
        try:
            response = data.decode('utf-8')
            lines = response.strip().split('\n')
            
            # Verify it's a WM-NOTIFY response
            if not response.startswith('TYPE: WM-NOTIFY'):
                return None
                
            # Extract location
            location = None
            for line in lines:
                if line.startswith('LOCATION:'):
                    location = line.split(':', 1)[1].strip()
                    break
                    
            if not location:
                logger.warning(f"No location found in multicast response from {sender_ip}")
                return None
                
            # Extract IP from location URL
            if '://' in location:
                ip_part = location.split('://')[1].split('/')[0]
                device_ip = ip_part.split(':')[0]  # Remove port if present
            else:
                device_ip = sender_ip
                
            # Get detailed device info via HTTP
            return await self._get_device_details(device_ip, "udp_multicast")
            
        except Exception as e:
            logger.error(f"Error parsing multicast response from {sender_ip}: {e}")
            return None

    async def ip_range_discovery(self) -> List[ThermostatDevice]:
        """
        Fallback discovery method - scan IP ranges for thermostats
        """
        devices = []
        
        # First, quickly check known devices
        if self.known_devices:
            logger.info("Checking known devices first...")
            known_ips = [device.ip for device in self.known_devices.values()]
            known_devices = await self._scan_ip_list(known_ips, check_known=True)
            devices.extend(known_devices)
        
        # Generate all IPs to scan
        all_ips = []
        for ip_range in self.ip_ranges:
            if '-' in ip_range:
                start_ip, end_ip = ip_range.split('-')
                start = ipaddress.IPv4Address(start_ip.strip())
                end = ipaddress.IPv4Address(end_ip.strip())
                
                current = start
                while current <= end:
                    ip_str = str(current)
                    # Skip known devices (already checked)
                    if not any(device.ip == ip_str for device in devices):
                        all_ips.append(ip_str)
                    current += 1
            else:
                # Single IP or CIDR notation
                try:
                    network = ipaddress.IPv4Network(ip_range.strip(), strict=False)
                    for ip in network.hosts():
                        ip_str = str(ip)
                        if not any(device.ip == ip_str for device in devices):
                            all_ips.append(ip_str)
                except ValueError:
                    logger.warning(f"Invalid IP range format: {ip_range}")
        
        logger.info(f"Scanning {len(all_ips)} IP addresses...")
        scan_devices = await self._scan_ip_list(all_ips)
        devices.extend(scan_devices)
        
        return devices

    async def _scan_ip_list(self, ip_list: List[str], check_known: bool = False) -> List[ThermostatDevice]:
        """
        Scan a list of IPs for thermostats using async HTTP requests
        """
        devices = []
        
        # Limit concurrent requests to avoid overwhelming network/devices
        semaphore = asyncio.Semaphore(10)
        
        async def scan_single_ip(ip: str):
            async with semaphore:
                device = await self._get_device_details(ip, "ip_scan")
                if device:
                    devices.append(device)
                    logger.info(f"Found device via IP scan: {device.name} ({device.ip})")
        
        # Create tasks for all IPs
        tasks = [scan_single_ip(ip) for ip in ip_list]
        
        # Execute with progress logging for large scans
        if len(tasks) > 20:
            completed = 0
            for i in range(0, len(tasks), 20):
                batch = tasks[i:i+20]
                await asyncio.gather(*batch, return_exceptions=True)
                completed += len(batch)
                logger.info(f"IP scan progress: {completed}/{len(tasks)} addresses checked")
        else:
            await asyncio.gather(*tasks, return_exceptions=True)
            
        return devices

    async def _get_device_details(self, ip: str, discovery_method: str) -> Optional[ThermostatDevice]:
        """
        Get detailed device information via HTTP API calls
        """
        base_url = f"http://{ip}"
        try:
            async with create_thermostat_session(self.request_timeout) as session:
                
                # Step 1: Check if it's a thermostat by calling /sys
                sys_info = await self._http_get(session, f"{base_url}/sys")
                if not sys_info or 'uuid' not in sys_info:
                    return None
                
                # Step 2: Get device name
                name_info = await self._http_get(session, f"{base_url}/sys/name")
                device_name = name_info.get('name', f"thermostat-{ip}") if name_info else f"thermostat-{ip}"
                
                # Step 3: Get model information
                model_info = await self._http_get(session, f"{base_url}/tstat/model")
                model = model_info.get('model', 'Unknown') if model_info else 'Unknown'
                
                # Create device object
                device = ThermostatDevice(
                    ip=ip,
                    uuid=sys_info['uuid'],
                    name=device_name,
                    model=model,
                    api_version=sys_info.get('api_version', 0),
                    fw_version=sys_info.get('fw_version', 'Unknown'),
                    base_url=f"{base_url}/tstat",
                    discovery_method=discovery_method,
                    last_seen=time.time()
                )
                return device
                
        except Exception as e:
            # Not a thermostat or not reachable
            logger.debug(f"Device check failed for {ip}: {e}")
            return None

    async def _http_get(self, session: aiohttp.ClientSession, url: str) -> Optional[Dict]:
        """
        Make HTTP GET request and return JSON response
        """
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.debug(f"HTTP {response.status} for {url}")
                    return None
        except Exception as e:
            logger.debug(f"HTTP GET failed for {url}: {e}")
            return None

    async def rescan_known_devices(self) -> List[ThermostatDevice]:
        """
        Quick rescan of previously discovered devices
        """
        if not self.known_devices:
            return []
            
        logger.info(f"Rescanning {len(self.known_devices)} known devices...")
        known_ips = [device.ip for device in self.known_devices.values()]
        
        updated_devices = await self._scan_ip_list(known_ips, check_known=True)
        
        # Update known devices registry
        for device in updated_devices:
            self.known_devices[device.uuid] = device
            
        # Mark missing devices as inactive (but don't remove them)
        current_time = time.time()
        active_uuids = {device.uuid for device in updated_devices}
        
        for uuid, device in self.known_devices.items():
            if uuid not in active_uuids:
                logger.warning(f"Device {device.name} ({device.ip}) not responding")
                
        return updated_devices
