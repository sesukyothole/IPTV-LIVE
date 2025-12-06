#!/usr/bin/env python3
"""
MoveOnJoy Subdomain Rotator with Smart Fallback
Located at: scripts/rotator.py
Rotates through online fl1-fl100 subdomains, falls back to fl1 if all offline
"""

import asyncio
import re
import aiofiles
import aiohttp
import logging
from typing import List, Set, Dict, Optional
from pathlib import Path
from datetime import datetime
import random
import time
import sys

# Color codes for colorful logs
COLORS = {
    'HEADER': '\033[95m',
    'BLUE': '\033[94m',
    'CYAN': '\033[96m',
    'GREEN': '\033[92m',
    'YELLOW': '\033[93m',
    'RED': '\033[91m',
    'ENDC': '\033[0m',
    'BOLD': '\033[1m',
    'MAGENTA': '\033[35m',
    'ORANGE': '\033[33m',
}

class ColorfulFormatter(logging.Formatter):
    """Custom formatter with colors and emojis"""
    
    FORMATS = {
        logging.DEBUG: f"{COLORS['CYAN']}🐛 %(message)s{COLORS['ENDC']}",
        logging.INFO: f"{COLORS['GREEN']}✅ %(message)s{COLORS['ENDC']}",
        logging.WARNING: f"{COLORS['YELLOW']}⚠️  %(message)s{COLORS['ENDC']}",
        logging.ERROR: f"{COLORS['RED']}❌ %(message)s{COLORS['ENDC']}",
        logging.CRITICAL: f"{COLORS['RED']}{COLORS['BOLD']}💥 %(message)s{COLORS['ENDC']}"
    }
    
    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)

class SubdomainChecker:
    """Check which subdomains are online with intelligent fallback"""
    
    def __init__(self, timeout: int = 3, retries: int = 2):
        self.timeout = timeout
        self.retries = retries
        self.session = None
        self.cache = {}
        
    async def __aenter__(self):
        connector = aiohttp.TCPConnector(limit=30, ttl_dns_cache=300)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=self.timeout)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def check_subdomain_with_retry(self, subdomain: str) -> bool:
        """Check if a subdomain is online with retries"""
        if subdomain in self.cache:
            return self.cache[subdomain]
        
        url = f"http://{subdomain}.moveonjoy.com"
        
        for attempt in range(self.retries):
            try:
                async with self.session.head(
                    url, 
                    allow_redirects=True,
                    ssl=False
                ) as response:
                    is_online = response.status in [200, 201, 202, 204, 301, 302, 303, 307, 308]
                    self.cache[subdomain] = is_online
                    
                    if is_online:
                        return True
                    elif attempt < self.retries - 1:
                        await asyncio.sleep(0.5)
                        
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
                if attempt < self.retries - 1:
                    await asyncio.sleep(0.5)
        
        self.cache[subdomain] = False
        return False
    
    async def find_online_subdomains(self, start: int = 1, end: int = 100, 
                                    max_concurrent: int = 25) -> List[str]:
        """Find all online subdomains in range"""
        online = []
        all_subdomains = [f"fl{i}" for i in range(start, end + 1)]
        
        print(f"{COLORS['CYAN']}🔍 Scanning subdomains fl{start}-fl{end}...{COLORS['ENDC']}")
        print(f"{COLORS['YELLOW']}📡 Checking fl1 first (fallback guaranteed)...{COLORS['ENDC']}")
        
        # Always include fl1 (even if it appears offline)
        fl1_online = await self.check_subdomain_with_retry("fl1")
        if fl1_online:
            online.append("fl1")
            print(f"{COLORS['GREEN']}✅ fl1.moveonjoy.com is online!{COLORS['ENDC']}")
        else:
            online.append("fl1")  # Still include as fallback
            print(f"{COLORS['ORANGE']}⚠️  fl1 appears offline, keeping as fallback{COLORS['ENDC']}")
        
        # Check other subdomains
        other_subdomains = [sd for sd in all_subdomains if sd != "fl1"]
        
        for i in range(0, len(other_subdomains), max_concurrent):
            batch = other_subdomains[i:i + max_concurrent]
            tasks = [self.check_subdomain_with_retry(sd) for sd in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for sd, is_online in zip(batch, results):
                if isinstance(is_online, Exception):
                    continue
                    
                if is_online:
                    online.append(sd)
                    print(f"{COLORS['GREEN']}✅ {sd}.moveonjoy.com is online!{COLORS['ENDC']}")
                else:
                    print(f"{COLORS['RED']}❌ {sd}.moveonjoy.com is offline{COLORS['ENDC']}")
            
            # Progress
            progress = min(i + max_concurrent, len(other_subdomains))
            percent = (progress / len(other_subdomains)) * 100
            print(f"{COLORS['BLUE']}📊 Progress: {progress}/{len(other_subdomains)} ({percent:.1f}%){COLORS['ENDC']}")
            
            await asyncio.sleep(0.3)
        
        # Ensure fl1 is first
        if "fl1" in online:
            online.remove("fl1")
            online.insert(0, "fl1")
        
        return online

class M3URotator:
    """Rotates MoveOnJoy subdomains with intelligent fallback"""
    
    def __init__(self, m3u_path: str, online_subdomains: List[str]):
        self.m3u_path = Path(m3u_path)
        
        # Always include fl1
        if not online_subdomains:
            online_subdomains = ["fl1"]
        elif "fl1" not in online_subdomains:
            online_subdomains.insert(0, "fl1")
        
        self.online_subdomains = online_subdomains
        self.fallback_mode = len([sd for sd in online_subdomains if sd != "fl1"]) == 0
        self.rotation_index = 0
        self.processed_lines = 0
        self.changed_lines = 0
        self.fallback_count = 0
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(ColorfulFormatter())
            self.logger.addHandler(console_handler)
    
    def _get_next_subdomain(self, mode: str = 'smart') -> str:
        """Get next subdomain based on mode"""
        if self.fallback_mode or len(self.online_subdomains) == 1:
            self.fallback_count += 1
            return "fl1"
        
        if mode == 'sequential':
            subdomain = self.online_subdomains[self.rotation_index]
            self.rotation_index = (self.rotation_index + 1) % len(self.online_subdomains)
            
            # Skip fl1 if we have other options
            if subdomain == "fl1" and len(self.online_subdomains) > 1:
                subdomain = self.online_subdomains[self.rotation_index]
                self.rotation_index = (self.rotation_index + 1) % len(self.online_subdomains)
            
            return subdomain
        
        elif mode == 'random':
            return random.choice(self.online_subdomains)
        
        else:  # smart mode (weighted)
            # Weighted list (fl1 gets lower weight)
            weighted_list = []
            for sd in self.online_subdomains:
                if sd == "fl1":
                    weighted_list.extend([sd] * 1)  # Lower weight
                else:
                    weighted_list.extend([sd] * 3)  # Higher weight
            
            return random.choice(weighted_list)
    
    async def rotate(self, mode: str = 'smart') -> bool:
        """Rotate subdomains in the M3U playlist"""
        if not self.m3u_path.exists():
            self.logger.error(f"❌ File not found: {self.m3u_path}")
            return False
        
        self.logger.info(f"{COLORS['HEADER']}{COLORS['BOLD']}🎬 Starting M3U Subdomain Rotation{COLORS['ENDC']}")
        self.logger.info(f"📁 File: {self.m3u_path}")
        self.logger.info(f"🌐 Online subdomains: {len(self.online_subdomains)}")
        
        if self.fallback_mode:
            self.logger.info(f"{COLORS['ORANGE']}⚠️  FALLBACK MODE: Only fl1 available{COLORS['ENDC']}")
        else:
            self.logger.info(f"📋 Available: {', '.join(self.online_subdomains[:8])}..."
                           f"{' and more' if len(self.online_subdomains) > 8 else ''}")
        
        self.logger.info(f"🔄 Mode: {mode}")
        self.logger.info(f"{COLORS['YELLOW']}⏳ Processing...{COLORS['ENDC']}")
        
        try:
            # Read file
            async with aiofiles.open(self.m3u_path, 'r', encoding='utf-8') as f:
                content = await f.read()
            
            lines = content.split('\n')
            processed_lines = []
            
            for line in lines:
                self.processed_lines += 1
                pattern = r'fl\d+\.moveonjoy\.com'
                matches = re.findall(pattern, line)
                
                if matches:
                    self.changed_lines += 1
                    for match in set(matches):
                        old_subdomain = match
                        new_subdomain = self._get_next_subdomain(mode)
                        line = line.replace(old_subdomain, f"{new_subdomain}.moveonjoy.com")
                        
                        # Color-coded logging
                        if new_subdomain == "fl1":
                            color = COLORS['ORANGE']
                            icon = "🔄" if self.fallback_mode else "⚡"
                            status = "(fallback)" if self.fallback_mode else ""
                        else:
                            color = COLORS['GREEN']
                            icon = "🎯"
                            status = ""
                        
                        self.logger.info(f"{color}{icon} {old_subdomain} → {new_subdomain}.moveonjoy.com {status}{COLORS['ENDC']}")
                
                processed_lines.append(line)
            
            # Write file
            async with aiofiles.open(self.m3u_path, 'w', encoding='utf-8') as f:
                await f.write('\n'.join(processed_lines))
            
            # Summary
            if self.fallback_mode:
                status_emoji = "🆘"
                status_color = COLORS['ORANGE']
            elif self.fallback_count > 0:
                status_emoji = "⚠️"
                status_color = COLORS['YELLOW']
            else:
                status_emoji = "✅"
                status_color = COLORS['GREEN']
            
            self.logger.info(f"{status_color}{COLORS['BOLD']}{status_emoji} Rotation Complete!{COLORS['ENDC']}")
            self.logger.info(f"📊 Summary:")
            self.logger.info(f"   📝 Lines processed: {self.processed_lines}")
            self.logger.info(f"   🔄 Subdomains changed: {self.changed_lines}")
            self.logger.info(f"   🌐 Online subdomains: {len(self.online_subdomains)}")
            
            if self.fallback_count > 0:
                self.logger.info(f"   🆘 fl1 fallbacks used: {self.fallback_count}")
            
            self.logger.info(f"{COLORS['GREEN']}✅ File saved: {self.m3u_path}{COLORS['ENDC']}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error: {e}")
            return False

async def run_rotation(m3u_path: str = "PrimeVision/us.m3u", mode: str = 'smart', 
                       quick_mode: bool = False) -> bool:
    """Run the complete rotation process"""
    print(f"{COLORS['HEADER']}{COLORS['BOLD']}")
    print("╔══════════════════════════════════════════════════╗")
    print("║    🔄 M3U Subdomain Rotator (scripts/rotator.py) ║")
    print("║    🛡️  Guaranteed fl1 fallback                    ║")
    print("╚══════════════════════════════════════════════════╝")
    print(f"{COLORS['ENDC']}")
    
    try:
        start_time = time.time()
        
        # Find online subdomains
        timeout = 1 if quick_mode else 3
        retries = 1 if quick_mode else 2
        
        async with SubdomainChecker(timeout=timeout, retries=retries) as checker:
            online_subdomains = await checker.find_online_subdomains(1, 100)
        
        scan_time = time.time() - start_time
        print(f"{COLORS['CYAN']}⏱️  Scan completed in {scan_time:.1f}s{COLORS['ENDC']}")
        
        if len(online_subdomains) <= 1:
            print(f"{COLORS['ORANGE']}⚠️  Only fl1 available - Fallback mode active{COLORS['ENDC']}")
        else:
            print(f"{COLORS['GREEN']}✅ Found {len(online_subdomains)} online subdomains{COLORS['ENDC']}")
        
        # Rotate
        rotator = M3URotator(m3u_path, online_subdomains)
        success = await rotator.rotate(mode)
        
        total_time = time.time() - start_time
        print(f"{COLORS['CYAN']}⏱️  Total time: {total_time:.1f} seconds{COLORS['ENDC']}")
        
        return success
        
    except KeyboardInterrupt:
        print(f"\n{COLORS['YELLOW']}⚠️  Cancelled by user{COLORS['ENDC']}")
        return False
    except Exception as e:
        print(f"{COLORS['RED']}❌ Error: {e}{COLORS['ENDC']}")
        return False

def main():
    """Main entry point for command line usage"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Rotate MoveOnJoy subdomains in M3U playlists',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                    # Interactive mode
  %(prog)s --quick            # Quick rotation (for automation)
  %(prog)s --mode random      # Random rotation
  %(prog)s --mode sequential  # Sequential rotation
  %(prog)s --file custom.m3u  # Custom M3U file
        """
    )
    
    parser.add_argument('--quick', action='store_true',
                       help='Quick mode (faster, less checking)')
    parser.add_argument('--mode', choices=['smart', 'sequential', 'random'],
                       default='smart', help='Rotation mode (default: smart)')
    parser.add_argument('--file', default='PrimeVision/us.m3u',
                       help='Path to M3U file (default: PrimeVision/us.m3u)')
    parser.add_argument('--silent', action='store_true',
                       help='Minimal output (no colors/emojis)')
    
    args = parser.parse_args()
    
    # Configure logging
    if args.silent:
        logging.basicConfig(level=logging.WARNING, format='%(message)s')
    else:
        logging.basicConfig(level=logging.INFO)
    
    # Run rotation
    success = asyncio.run(run_rotation(args.file, args.mode, args.quick))
    
    if success:
        print(f"{COLORS['GREEN']}✨ Rotation completed successfully!{COLORS['ENDC']}")
        sys.exit(0)
    else:
        print(f"{COLORS['RED']}💥 Rotation failed!{COLORS['ENDC']}")
        sys.exit(1)

if __name__ == "__main__":
    main()