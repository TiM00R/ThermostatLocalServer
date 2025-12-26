"""
Network discovery methods for thermostat devices
"""

import socket
import asyncio
import aiohttp
import ipaddress
import time
import logging
from typing import List, Optional
from .models import ThermostatDevice, DiscoveryResult

# Import HTTP helper function with fallback
try:
    from ..http_helper import create_thermostat_session
except ImportError:
    from http_helper import create_thermostat_session
    

logger = logging.getLogger(__name__)

class NetworkDiscovery:
    """Handles UDP multicast and TCP network discovery"""
    
    def __init__(self, config: dict):
        self.config = config
        self.discovery_timeout = config.get('discovery_timeout', 20)
        self.request_timeout = config.get('request_timeout', 3)
        self.ip_ranges = config.get('ip_ranges', ['10.0.60.1-10.0.60.254'])
    
    async def udp_multicast_discovery(self) -> List[ThermostatDevice]:
        """UDP multicast discovery implementation"""
        devices = []
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('', 0))
            sock.settimeout(2.0)
            
            discover_msg = (
                "TYPE: WM-DISCOVER\n"
                "VERSION: 1.0\n"
                "SERVICES: com.rtcoa.tstat:1.0"
            )
            
            logger.info("Sending UDP multicast discovery...")
            sock.sendto(discover_msg.encode('utf-8'), ('239.255.255.250', 1900))
            
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
        """Parse WM-NOTIFY response"""
        try:
            response = data.decode('utf-8')
            lines = response.strip().split('\n')
            
            if not response.startswith('TYPE: WM-NOTIFY'):
                return None
                
            location = None
            for line in lines:
                if line.startswith('LOCATION:'):
                    location = line.split(':', 1)[1].strip()
                    break
                    
            if not location:
                return None
                
            if '://' in location:
                device_ip = location.split('://')[1].split('/')[0].split(':')[0]
            else:
                device_ip = sender_ip
                
            return await self._get_device_details(device_ip, "udp_multicast")
            
        except Exception as e:
            logger.error(f"Error parsing multicast response: {e}")
            return None

    async def tcp_scan_range(self, ip_list: List[str]) -> List[ThermostatDevice]:
        """TCP scan implementation"""
        devices = []
        semaphore = asyncio.Semaphore(10)
        
        async def scan_single_ip(ip: str):
            async with semaphore:
                device = await self._get_device_details(ip, "tcp_scan")
                if device:
                    devices.append(device)
                    logger.info(f"Found device via TCP: {device.name} ({device.ip})")
        
        tasks = [scan_single_ip(ip) for ip in ip_list]
        await asyncio.gather(*tasks, return_exceptions=True)
        return devices

    async def _get_device_details(self, ip: str, discovery_method: str) -> Optional[ThermostatDevice]:
        """Get device details via HTTP"""
        try:
            async with create_thermostat_session(self.request_timeout) as session:
                sys_info = await self._http_get(session, f"http://{ip}/sys")
                if not sys_info or 'uuid' not in sys_info:
                    return None
                
                name_info = await self._http_get(session, f"http://{ip}/sys/name")
                device_name = name_info.get('name', f"thermostat-{ip}") if name_info else f"thermostat-{ip}"
                
                model_info = await self._http_get(session, f"http://{ip}/tstat/model")
                model = model_info.get('model', 'Unknown') if model_info else 'Unknown'
                
                return ThermostatDevice(
                    ip=ip,
                    uuid=sys_info['uuid'],
                    name=device_name,
                    model=model,
                    api_version=sys_info.get('api_version', 0),
                    fw_version=sys_info.get('fw_version', 'Unknown'),
                    base_url=f"http://{ip}/tstat",
                    discovery_method=discovery_method,
                    last_seen=time.time()
                )
                
        except Exception:
            return None

    async def _http_get(self, session, url: str) -> Optional[dict]:
        """Make HTTP GET request"""
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                return None
        except Exception:
            return None

    def generate_ip_range(self) -> List[str]:
        """Generate IP range from config"""
        all_ips = []
        for ip_range in self.ip_ranges:
            if '-' in ip_range:
                start_ip, end_ip = ip_range.split('-')
                start = ipaddress.IPv4Address(start_ip.strip())
                end = ipaddress.IPv4Address(end_ip.strip())
                current = start
                while current <= end:
                    all_ips.append(str(current))
                    current += 1
            else:
                try:
                    network = ipaddress.IPv4Network(ip_range.strip(), strict=False)
                    all_ips.extend(str(ip) for ip in network.hosts())
                except ValueError:
                    logger.warning(f"Invalid IP range: {ip_range}")
        return all_ips
