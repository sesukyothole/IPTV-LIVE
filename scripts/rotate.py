#!/usr/bin/env python3
"""
MoveOnJoy Subdomain Rotator with Smart Fallback
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

class SmartSubdomainChecker:
    """Check which subdomains are online with intelligent fallback"""
    
    def __init__(self, timeout: int = 3, retries: int = 2):
        self.timeout = timeout
        self.retries = retries
        self.session = None
        self.cache = {}  # Cache online status
        
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
        # Check cache first
        if subdomain in self.cache:
            return self.cache[subdomain]
        
        url = f"http://{subdomain}.moveonjoy.com"
        
        for attempt in range(self.retries):
            try:
                async with self.session.head(
                    url, 
                    allow_redirects=True,
                    ssl=False  # Some subdomains might have SSL issues
                ) as response:
                    is_online = response.status in [200, 201, 202, 204, 301, 302, 303, 307, 308]
                    self.cache[subdomain] = is_online
                    
                    if is_online:
                        return True
                    elif attempt < self.retries - 1:
                        await asyncio.sleep(0.5)  # Wait before retry
                        
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
                if attempt < self.retries - 1:
                    await asyncio.sleep(0.5)
        
        self.cache[subdomain] = False
        return False
    
    async def find_online_subdomains(self, start: int = 1, end: int = 100, 
                                    max_concurrent: int = 25) -> List[str]:
        """
        Find all online subdomains in range
        
        Args:
            start: Starting subdomain number
            end: Ending subdomain number
            max_concurrent: Maximum concurrent checks
        
        Returns:
            List of online subdomains (always includes fl1 at minimum)
        """
        online = []
        all_subdomains = [f"fl{i}" for i in range(start, end + 1)]
        
        # Always check fl1 first (our fallback)
        print(f"{COLORS['CYAN']}🔍 Starting subdomain scan...{COLORS['ENDC']}")
        print(f"{COLORS['YELLOW']}📡 Always checking fl1 first (fallback)...{COLORS['ENDC']}")
        
        # Check fl1 first
        fl1_online = await self.check_subdomain_with_retry("fl1")
        if fl1_online:
            online.append("fl1")
            print(f"{COLORS['GREEN']}✅ fl1.moveonjoy.com is online! (Fallback ready){COLORS['ENDC']}")
        else:
            print(f"{COLORS['YELLOW']}⚠️  fl1.moveonjoy.com is offline, but will be used as fallback anyway{COLORS['ENDC']}")
            online.append("fl1")  # Still add it as fallback
        
        # Check other subdomains
        other_subdomains = [sd for sd in all_subdomains if sd != "fl1"]
        
        print(f"{COLORS['CYAN']}📡 Scanning other subdomains...{COLORS['ENDC']}")
        
        # Process in batches
        for i in range(0, len(other_subdomains), max_concurrent):
            batch = other_subdomains[i:i + max_concurrent]
            tasks = [self.check_subdomain_with_retry(sd) for sd in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for sd, is_online in zip(batch, results):
                if isinstance(is_online, Exception):
                    print(f"{COLORS['RED']}❌ Error checking {sd}: {is_online}{COLORS['ENDC']}")
                    continue
                    
                if is_online:
                    online.append(sd)
                    print(f"{COLORS['GREEN']}✅ {sd}.moveonjoy.com is online!{COLORS['ENDC']}")
                else:
                    print(f"{COLORS['RED']}❌ {sd}.moveonjoy.com is offline{COLORS['ENDC']}")
            
            # Progress indicator
            progress = min(i + max_concurrent, len(other_subdomains))
            percent = (progress / len(other_subdomains)) * 100
            print(f"{COLORS['BLUE']}📊 Progress: {progress}/{len(other_subdomains)} ({percent:.1f}%){COLORS['ENDC']}")
            
            # Small delay between batches
            await asyncio.sleep(0.3)
        
        # Ensure fl1 is always first in the list for priority
        if "fl1" in online:
            online.remove("fl1")
            online.insert(0, "fl1")
        
        return online
    
    async def quick_check_fl1(self) -> bool:
        """Quick check if fl1 is online"""
        try:
            url = "http://fl1.moveonjoy.com"
            async with self.session.head(url, allow_redirects=True, ssl=False, timeout=2) as response:
                return response.status in [200, 301, 302]
        except:
            return False

class SmartM3URotator:
    """Rotates MoveOnJoy subdomains with intelligent fallback"""
    
    def __init__(self, m3u_path: str, online_subdomains: List[str]):
        """
        Initialize the rotator
        
        Args:
            m3u_path: Path to M3U playlist file
            online_subdomains: List of online subdomains (fl1 should be first if available)
        """
        self.m3u_path = Path(m3u_path)
        
        # Ensure we always have at least fl1
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
        
        # Setup colorful logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(ColorfulFormatter())
            self.logger.addHandler(console_handler)
    
    def _get_next_subdomain(self) -> str:
        """Get next subdomain, automatically fall back to fl1 if needed"""
        if self.fallback_mode or len(self.online_subdomains) == 1:
            # We're in fallback mode (only fl1)
            self.fallback_count += 1
            return "fl1"
        
        # Try to use other subdomains first
        subdomain = self.online_subdomains[self.rotation_index]
        self.rotation_index = (self.rotation_index + 1) % len(self.online_subdomains)
        
        # If we're back to fl1 and have other options, skip to next
        if subdomain == "fl1" and len(self.online_subdomains) > 1:
            subdomain = self.online_subdomains[self.rotation_index]
            self.rotation_index = (self.rotation_index + 1) % len(self.online_subdomains)
        
        return subdomain
    
    def _get_weighted_subdomain(self) -> str:
        """Get subdomain with weight favoring non-fl1 subdomains"""
        if len(self.online_subdomains) == 1:
            return "fl1"
        
        # Create weighted list (fl1 gets lower weight)
        weighted_list = []
        for sd in self.online_subdomains:
            if sd == "fl1":
                # fl1 gets lower weight (1)
                weighted_list.extend([sd] * 1)
            else:
                # Other subdomains get higher weight (3)
                weighted_list.extend([sd] * 3)
        
        return random.choice(weighted_list)
    
    async def _process_line(self, line: str, mode: str = 'smart') -> str:
        """Process a single line from M3U file"""
        self.processed_lines += 1
        
        # Match MoveOnJoy subdomains
        pattern = r'fl\d+\.moveonjoy\.com'
        matches = re.findall(pattern, line)
        
        if matches:
            self.changed_lines += 1
            
            # Replace each found subdomain
            for match in set(matches):  # Use set to avoid duplicates
                old_subdomain = match
                
                if mode == 'smart':
                    new_subdomain = self._get_weighted_subdomain()
                elif mode == 'sequential':
                    new_subdomain = self._get_next_subdomain()
                else:  # random
                    new_subdomain = random.choice(self.online_subdomains)
                
                line = line.replace(old_subdomain, f"{new_subdomain}.moveonjoy.com")
                
                # Determine color based on subdomain used
                if new_subdomain == "fl1":
                    color = COLORS['ORANGE']
                    icon = "🔄" if self.fallback_mode else "⚡"
                    status = "(fallback)" if self.fallback_mode else "(primary)"
                else:
                    color = COLORS['GREEN']
                    icon = "🎯"
                    status = ""
                
                self.logger.info(
                    f"{color}{icon} Changed: {old_subdomain} → {new_subdomain}.moveonjoy.com {status}{COLORS['ENDC']}"
                )
        
        return line
    
    async def rotate_subdomains(self, mode: str = 'smart') -> bool:
        """
        Rotate subdomains in the M3U playlist
        
        Args:
            mode: 'smart' (weighted), 'sequential', or 'random'
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.m3u_path.exists():
            self.logger.error(f"File not found: {self.m3u_path}")
            return False
        
        self.logger.info(f"{COLORS['HEADER']}{COLORS['BOLD']}🎬 Starting Smart M3U Subdomain Rotation{COLORS['ENDC']}")
        self.logger.info(f"📁 File: {self.m3u_path}")
        self.logger.info(f"🌐 Online subdomains: {len(self.online_subdomains)} found")
        
        if self.fallback_mode:
            self.logger.info(f"{COLORS['ORANGE']}⚠️  FALLBACK MODE: Only fl1 is available{COLORS['ENDC']}")
        else:
            self.logger.info(f"📋 Subdomains: {', '.join(self.online_subdomains[:8])}..."
                           f"{' and more' if len(self.online_subdomains) > 8 else ''}")
        
        self.logger.info(f"🔄 Rotation mode: {mode}")
        self.logger.info(f"{COLORS['YELLOW']}⏳ Processing...{COLORS['ENDC']}")
        
        try:
            # Read the file
            async with aiofiles.open(self.m3u_path, 'r', encoding='utf-8') as f:
                content = await f.read()
            
            lines = content.split('\n')
            processed_lines = []
            
            # Process lines
            for line in lines:
                processed_line = await self._process_line(line, mode)
                processed_lines.append(processed_line)
            
            # Write the processed content
            async with aiofiles.open(self.m3u_path, 'w', encoding='utf-8') as f:
                await f.write('\n'.join(processed_lines))
            
            # Summary with emoji status
            if self.fallback_mode:
                status_emoji = "🆘"
                status_color = COLORS['ORANGE']
                status_text = "FALLBACK MODE"
            elif self.fallback_count > 0:
                status_emoji = "⚠️"
                status_color = COLORS['YELLOW']
                status_text = "MIXED (with fallbacks)"
            else:
                status_emoji = "✅"
                status_color = COLORS['GREEN']
                status_text = "NORMAL"
            
            self.logger.info(f"{status_color}{COLORS['BOLD']}{status_emoji} Rotation Complete! ({status_text}){COLORS['ENDC']}")
            self.logger.info(f"📊 Summary:")
            self.logger.info(f"   📝 Total lines processed: {self.processed_lines}")
            self.logger.info(f"   🔄 Subdomains changed: {self.changed_lines}")
            self.logger.info(f"   🌐 Online subdomains available: {len(self.online_subdomains)}")
            
            if self.fallback_count > 0:
                self.logger.info(f"   🆘 Fallback to fl1 used: {self.fallback_count} times")
            
            self.logger.info(f"   📍 Next rotation index: {self.rotation_index}")
            
            # Show distribution
            if not self.fallback_mode:
                fl1_percent = (self.fallback_count / max(self.changed_lines, 1)) * 100
                self.logger.info(f"   📈 fl1 usage: {fl1_percent:.1f}% of changes")
            
            self.logger.info(f"{COLORS['GREEN']}✅ File saved successfully!{COLORS['ENDC']}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error processing file: {e}")
            return False

async def main():
    """Main function with interactive options"""
    m3u_path = "PrimeVision/us.m3u"
    
    print(f"{COLORS['HEADER']}{COLORS['BOLD']}")
    print("╔══════════════════════════════════════════════════════════╗")
    print("║    🧠 Smart MoveOnJoy Rotator with Fallback              ║")
    print("║    🆘 Always falls back to fl1 if others are offline     ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print(f"{COLORS['ENDC']}")
    
    try:
        # Step 1: Find online subdomains
        print(f"{COLORS['CYAN']}🔍 Step 1: Finding online subdomains...{COLORS['ENDC']}")
        print(f"{COLORS['YELLOW']}📡 Checking fl1 first (guaranteed fallback)...{COLORS['ENDC']}")
        
        start_time = time.time()
        
        async with SmartSubdomainChecker(timeout=2, retries=1) as checker:
            # Quick fl1 check first
            fl1_status = await checker.quick_check_fl1()
            
            if fl1_status:
                print(f"{COLORS['GREEN']}⚡ fl1 is online! (Fast check){COLORS['ENDC']}")
            else:
                print(f"{COLORS['ORANGE']}⚠️  fl1 appears offline, but will be used as fallback{COLORS['ENDC']}")
            
            # Find all online subdomains
            online_subdomains = await checker.find_online_subdomains(1, 100)
        
        scan_time = time.time() - start_time
        
        print(f"{COLORS['CYAN']}⏱️  Scan completed in {scan_time:.1f} seconds{COLORS['ENDC']}")
        
        # Step 2: Show results
        print(f"\n{COLORS['MAGENTA']}{COLORS['BOLD']}📊 Scan Results:{COLORS['ENDC']}")
        print(f"   ✅ Online subdomains: {len(online_subdomains)}")
        print(f"   ❌ Offline subdomains: {100 - len(online_subdomains)}")
        print(f"   📈 Online rate: {(len(online_subdomains)/100)*100:.1f}%")
        
        if len(online_subdomains) <= 1:
            print(f"{COLORS['ORANGE']}⚠️  Only fl1 is available - FALLBACK MODE ACTIVE{COLORS['ENDC']}")
        elif len(online_subdomains) <= 10:
            print(f"{COLORS['YELLOW']}⚠️  Limited subdomains available ({len(online_subdomains)}){COLORS['ENDC']}")
        
        # Step 3: Choose rotation mode
        print(f"\n{COLORS['YELLOW']}Choose rotation mode:{COLORS['ENDC']}")
        print(f"  1️⃣  {COLORS['GREEN']}Smart mode (favors non-fl1 subdomains){COLORS['ENDC']}")
        print(f"  2️⃣  {COLORS['BLUE']}Sequential rotation{COLORS['ENDC']}")
        print(f"  3️⃣  {COLORS['CYAN']}Random rotation{COLORS['ENDC']}")
        print(f"  4️⃣  {COLORS['RED']}Exit{COLORS['ENDC']}")
        
        choice = input(f"{COLORS['CYAN']}Enter choice (1-4): {COLORS['ENDC']}")
        
        if choice == '4':
            print(f"{COLORS['CYAN']}👋 Goodbye!{COLORS['ENDC']}")
            return
        
        mode_map = {'1': 'smart', '2': 'sequential', '3': 'random'}
        mode = mode_map.get(choice, 'smart')
        
        # Step 4: Rotate
        rotator = SmartM3URotator(m3u_path, online_subdomains)
        success = await rotator.rotate_subdomains(mode)
        
        if not success:
            print(f"{COLORS['RED']}❌ Operation failed!{COLORS['ENDC']}")
        
        # Final statistics
        print(f"\n{COLORS['MAGENTA']}{COLORS['BOLD']}🎯 Final Statistics:{COLORS['ENDC']}")
        print(f"   Total online subdomains: {len(online_subdomains)}")
        print(f"   Primary subdomains available: {max(0, len(online_subdomains) - 1)}")
        print(f"   Guaranteed fallback: fl1.moveonjoy.com")
        
        if len(online_subdomains) > 1:
            print(f"   Recommended for next time: fl{random.choice([int(sd[2:]) for sd in online_subdomains if sd != 'fl1'])}")
        
    except KeyboardInterrupt:
        print(f"\n{COLORS['YELLOW']}⚠️  Operation cancelled by user{COLORS['ENDC']}")
    except Exception as e:
        print(f"{COLORS['RED']}❌ Error: {e}{COLORS['ENDC']}")

async def quick_rotate():
    """Quick rotation for automation"""
    m3u_path = "PrimeVision/us.m3u"
    
    print(f"{COLORS['CYAN']}🚀 Quick smart rotation mode{COLORS['ENDC']}")
    
    try:
        # Fast check with shorter timeout for automation
        async with SmartSubdomainChecker(timeout=1, retries=1) as checker:
            online_subdomains = await checker.find_online_subdomains(1, 100)
        
        if not online_subdomains:
            online_subdomains = ["fl1"]  # Guaranteed fallback
        
        # Use smart mode for best results
        rotator = SmartM3URotator(m3u_path, online_subdomains)
        await rotator.rotate_subdomains('smart')
        
    except Exception as e:
        print(f"{COLORS['RED']}❌ Error in quick mode: {e}{COLORS['ENDC']}")
        # Even in error, try to fall back to fl1
        try:
            rotator = SmartM3URotator(m3u_path, ["fl1"])
            await rotator.rotate_subdomains('smart')
        except:
            print(f"{COLORS['RED']}💥 Critical failure{COLORS['ENDC']}")

if __name__ == "__main__":
    import sys
    
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    
    # Check for quick mode
    if len(sys.argv) > 1 and sys.argv[1] == '--quick':
        asyncio.run(quick_rotate())
    elif len(sys.argv) > 1 and sys.argv[1] == '--force-fl1':
        # Force fl1 only mode (for testing)
        print(f"{COLORS['ORANGE']}🔄 FORCING fl1-only mode{COLORS['ENDC']}")
        rotator = SmartM3URotator("PrimeVision/us.m3u", ["fl1"])
        asyncio.run(rotator.rotate_subdomains('smart'))
    else:
        asyncio.run(main())