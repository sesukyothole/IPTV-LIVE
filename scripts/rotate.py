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
    'PURPLE': '\033[94m',
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
    
    async def check_only_fl1(self) -> bool:
        """Quick check if fl1 is online (for force-fl1 mode)"""
        try:
            url = "http://fl1.moveonjoy.com"
            async with self.session.head(url, allow_redirects=True, ssl=False, timeout=2) as response:
                return response.status in [200, 301, 302]
        except:
            return False

class M3URotator:
    """Rotates MoveOnJoy subdomains with intelligent fallback"""
    
    def __init__(self, m3u_path: str, online_subdomains: List[str], force_fl1: bool = False):
        self.m3u_path = Path(m3u_path)
        self.force_fl1 = force_fl1
        
        if force_fl1:
            # Force fl1 only mode
            online_subdomains = ["fl1"]
            print(f"{COLORS['PURPLE']}🔧 FORCE FL1 MODE: Using only fl1.moveonjoy.com{COLORS['ENDC']}")
        else:
            # Normal mode: always include fl1
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
        self.forced_fl1_count = 0 if force_fl1 else 0
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(ColorfulFormatter())
            self.logger.addHandler(console_handler)
    
    def _get_next_subdomain(self, mode: str = 'smart') -> str:
        """Get next subdomain based on mode"""
        if self.force_fl1:
            self.forced_fl1_count += 1
            return "fl1"
        
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
        
        # Display mode header
        if self.force_fl1:
            header = "🔧 FORCE FL1 MODE"
            color = COLORS['PURPLE']
        elif self.fallback_mode:
            header = "🆘 FALLBACK MODE"
            color = COLORS['ORANGE']
        else:
            header = "🎬 NORMAL MODE"
            color = COLORS['GREEN']
        
        self.logger.info(f"{COLORS['HEADER']}{COLORS['BOLD']}{header}{COLORS['ENDC']}")
        self.logger.info(f"{color}📁 File: {self.m3u_path}{COLORS['ENDC']}")
        
        if self.force_fl1:
            self.logger.info(f"{COLORS['PURPLE']}⚡ Using only: fl1.moveonjoy.com (forced){COLORS['ENDC']}")
        else:
            self.logger.info(f"{color}🌐 Online subdomains: {len(self.online_subdomains)}{COLORS['ENDC']}")
            if not self.fallback_mode:
                self.logger.info(f"{color}📋 Available: {', '.join(self.online_subdomains[:8])}..."
                               f"{' and more' if len(self.online_subdomains) > 8 else ''}{COLORS['ENDC']}")
        
        if not self.force_fl1:
            self.logger.info(f"{color}🔄 Rotation mode: {mode}{COLORS['ENDC']}")
        
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
                        
                        # Color-coded logging based on mode
                        if self.force_fl1:
                            color = COLORS['PURPLE']
                            icon = "🔧"
                            status = "(forced fl1)"
                        elif new_subdomain == "fl1":
                            color = COLORS['ORANGE']
                            icon = "🔄" if self.fallback_mode else "⚡"
                            status = "(fallback)" if self.fallback_mode else "(primary)"
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
            if self.force_fl1:
                status_emoji = "🔧"
                status_color = COLORS['PURPLE']
                status_text = "FORCE FL1 MODE"
            elif self.fallback_mode:
                status_emoji = "🆘"
                status_color = COLORS['ORANGE']
                status_text = "FALLBACK MODE"
            elif self.fallback_count > 0:
                status_emoji = "⚠️"
                status_color = COLORS['YELLOW']
                status_text = "MIXED MODE"
            else:
                status_emoji = "✅"
                status_color = COLORS['GREEN']
                status_text = "NORMAL MODE"
            
            self.logger.info(f"{status_color}{COLORS['BOLD']}{status_emoji} Rotation Complete! ({status_text}){COLORS['ENDC']}")
            self.logger.info(f"📊 Summary:")
            self.logger.info(f"   📝 Lines processed: {self.processed_lines}")
            self.logger.info(f"   🔄 Subdomains changed: {self.changed_lines}")
            
            if self.force_fl1:
                self.logger.info(f"   🔧 Forced fl1 changes: {self.forced_fl1_count}")
                self.logger.info(f"   ⚡ Using: fl1.moveonjoy.com only")
            else:
                self.logger.info(f"   🌐 Online subdomains: {len(self.online_subdomains)}")
                
                if self.fallback_count > 0:
                    self.logger.info(f"   🆘 Fallback to fl1 used: {self.fallback_count} times")
            
            self.logger.info(f"{COLORS['GREEN']}✅ File saved: {self.m3u_path}{COLORS['ENDC']}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error: {e}")
            return False

async def run_rotation(m3u_path: str = "PrimeVision/us.m3u", mode: str = 'smart', 
                       quick_mode: bool = False, force_fl1: bool = False) -> bool:
    """Run the complete rotation process"""
    print(f"{COLORS['HEADER']}{COLORS['BOLD']}")
    print("╔══════════════════════════════════════════════════╗")
    print("║    🔄 M3U Subdomain Rotator (scripts/rotator.py) ║")
    if force_fl1:
        print("║    🔧 FORCE FL1 MODE (fl1 only)                 ║")
    else:
        print("║    🛡️  Guaranteed fl1 fallback                    ║")
    print("╚══════════════════════════════════════════════════╝")
    print(f"{COLORS['ENDC']}")
    
    try:
        start_time = time.time()
        
        if force_fl1:
            # Force fl1 mode - skip scanning
            print(f"{COLORS['PURPLE']}🔧 FORCE FL1 MODE: Skipping subdomain scan{COLORS['ENDC']}")
            print(f"{COLORS['PURPLE']}⚡ Will use only: fl1.moveonjoy.com{COLORS['ENDC']}")
            online_subdomains = ["fl1"]
            
            # Quick check if fl1 is reachable (just for info)
            async with SubdomainChecker(timeout=2, retries=1) as checker:
                fl1_online = await checker.check_only_fl1()
                if fl1_online:
                    print(f"{COLORS['GREEN']}✅ fl1.moveonjoy.com is reachable{COLORS['ENDC']}")
                else:
                    print(f"{COLORS['ORANGE']}⚠️  fl1.moveonjoy.com may be offline (but will be used anyway){COLORS['ENDC']}")
        else:
            # Normal mode - scan subdomains
            timeout = 1 if quick_mode else 3
            retries = 1 if quick_mode else 2
            
            async with SubdomainChecker(timeout=timeout, retries=retries) as checker:
                online_subdomains = await checker.find_online_subdomains(1, 100)
        
        scan_time = time.time() - start_time
        
        if not force_fl1:
            print(f"{COLORS['CYAN']}⏱️  Scan completed in {scan_time:.1f}s{COLORS['ENDC']}")
            
            if len(online_subdomains) <= 1:
                print(f"{COLORS['ORANGE']}⚠️  Only fl1 available - Fallback mode active{COLORS['ENDC']}")
            else:
                print(f"{COLORS['GREEN']}✅ Found {len(online_subdomains)} online subdomains{COLORS['ENDC']}")
        
        # Rotate
        rotator = M3URotator(m3u_path, online_subdomains, force_fl1)
        
        # In force fl1 mode, mode is ignored (always uses fl1)
        if force_fl1:
            actual_mode = "fl1-only"
        else:
            actual_mode = mode
            
        success = await rotator.rotate(actual_mode if not force_fl1 else 'smart')
        
        total_time = time.time() - start_time
        print(f"{COLORS['CYAN']}⏱️  Total time: {total_time:.1f} seconds{COLORS['ENDC']}")
        
        return success
        
    except KeyboardInterrupt:
        print(f"\n{COLORS['YELLOW']}⚠️  Cancelled by user{COLORS['ENDC']}")
        return False
    except Exception as e:
        print(f"{COLORS['RED']}❌ Error: {e}{COLORS['ENDC']}")
        return False

def interactive_menu():
    """Interactive menu for non-command line usage"""
    print(f"{COLORS['HEADER']}{COLORS['BOLD']}")
    print("╔══════════════════════════════════════════════════╗")
    print("║        🔄 INTERACTIVE MODE MENU                  ║")
    print("╚══════════════════════════════════════════════════╝")
    print(f"{COLORS['ENDC']}")
    
    print(f"{COLORS['CYAN']}Choose an option:{COLORS['ENDC']}")
    print(f"  1️⃣  {COLORS['GREEN']}Smart rotation (recommended){COLORS['ENDC']}")
    print(f"  2️⃣  {COLORS['BLUE']}Sequential rotation{COLORS['ENDC']}")
    print(f"  3️⃣  {COLORS['MAGENTA']}Random rotation{COLORS['ENDC']}")
    print(f"  4️⃣  {COLORS['PURPLE']}🔧 FORCE fl1 only{COLORS['ENDC']}")
    print(f"  5️⃣  {COLORS['YELLOW']}Quick smart rotation{COLORS['ENDC']}")
    print(f"  6️⃣  {COLORS['RED']}Exit{COLORS['ENDC']}")
    
    choice = input(f"\n{COLORS['CYAN']}Enter choice (1-6): {COLORS['ENDC']}")
    
    if choice == '1':
        return 'smart', False, False
    elif choice == '2':
        return 'sequential', False, False
    elif choice == '3':
        return 'random', False, False
    elif choice == '4':
        return 'smart', False, True  # Force fl1
    elif choice == '5':
        return 'smart', True, False  # Quick mode
    elif choice == '6':
        print(f"{COLORS['CYAN']}👋 Goodbye!{COLORS['ENDC']}")
        sys.exit(0)
    else:
        print(f"{COLORS['RED']}❌ Invalid choice!{COLORS['ENDC']}")
        return interactive_menu()

def main():
    """Main entry point for command line usage"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Rotate MoveOnJoy subdomains in M3U playlists',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Interactive mode
  %(prog)s --quick                  # Quick rotation
  %(prog)s --mode random            # Random rotation
  %(prog)s --force-fl1              # Force fl1 only
  %(prog)s --file custom.m3u        # Custom M3U file
  %(prog)s --force-fl1 --quick      # Quick force fl1
  %(prog)s --force-fl1 --mode smart # Force fl1 (mode ignored)

Force fl1 mode:
  When --force-fl1 is used, the script will:
  • Skip scanning other subdomains
  • Use only fl1.moveonjoy.com
  • Much faster (no network checks)
  • Useful when fl1 is known to work
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
    parser.add_argument('--force-fl1', action='store_true',
                       help='Force use of fl1 only (skip scanning other subdomains)')
    parser.add_argument('--interactive', ac