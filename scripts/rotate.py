#!/usr/bin/env python3
"""
MoveOnJoy Subdomain Rotator with Online Checking
Rotates through online fl1-fl100 subdomains
"""

import asyncio
import re
import aiofiles
import aiohttp
import logging
from typing import List, Set, Dict
from pathlib import Path
from datetime import datetime
import random

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
    """Check which subdomains are online"""
    
    def __init__(self):
        self.session = None
        self.timeout = aiohttp.ClientTimeout(total=5)
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=self.timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def check_subdomain(self, subdomain: str) -> bool:
        """Check if a subdomain is online"""
        url = f"http://{subdomain}.moveonjoy.com"
        try:
            async with self.session.head(url, allow_redirects=True) as response:
                return response.status in [200, 301, 302, 307]
        except:
            return False
    
    async def find_online_subdomains(self, start: int = 1, end: int = 100, 
                                    max_concurrent: int = 20) -> List[str]:
        """
        Find all online subdomains in range
        
        Args:
            start: Starting subdomain number
            end: Ending subdomain number
            max_concurrent: Maximum concurrent checks
            
        Returns:
            List of online subdomains
        """
        online = []
        subdomains = [f"fl{i}" for i in range(start, end + 1)]
        
        print(f"{COLORS['CYAN']}🔍 Scanning subdomains fl{start}-fl{end}...{COLORS['ENDC']}")
        print(f"{COLORS['YELLOW']}⏳ This may take a moment...{COLORS['ENDC']}")
        
        # Process in batches
        for i in range(0, len(subdomains), max_concurrent):
            batch = subdomains[i:i + max_concurrent]
            tasks = [self.check_subdomain(sd) for sd in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for sd, is_online in zip(batch, results):
                if is_online:
                    online.append(sd)
                    print(f"{COLORS['GREEN']}✅ {sd}.moveonjoy.com is online!{COLORS['ENDC']}")
                else:
                    print(f"{COLORS['RED']}❌ {sd}.moveonjoy.com is offline{COLORS['ENDC']}")
            
            # Small delay between batches to be nice
            await asyncio.sleep(0.5)
        
        return online

class M3USubdomainRotator:
    """Rotates MoveOnJoy subdomains in M3U playlists using only online subdomains"""
    
    def __init__(self, m3u_path: str, online_subdomains: List[str]):
        """
        Initialize the rotator
        
        Args:
            m3u_path: Path to M3U playlist file
            online_subdomains: List of online subdomains to use
        """
        self.m3u_path = Path(m3u_path)
        self.online_subdomains = online_subdomains
        self.rotation_index = 0
        self.processed_lines = 0
        self.changed_lines = 0
        
        if not online_subdomains:
            raise ValueError("No online subdomains provided!")
        
        # Setup colorful logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(ColorfulFormatter())
            self.logger.addHandler(console_handler)
    
    def _get_next_subdomain(self) -> str:
        """Get next online subdomain in rotation"""
        subdomain = self.online_subdomains[self.rotation_index]
        self.rotation_index = (self.rotation_index + 1) % len(self.online_subdomains)
        return subdomain
    
    def _get_random_subdomain(self) -> str:
        """Get a random online subdomain"""
        return random.choice(self.online_subdomains)
    
    async def _process_line(self, line: str, mode: str = 'sequential') -> str:
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
                
                if mode == 'sequential':
                    new_subdomain = self._get_next_subdomain()
                else:  # random
                    new_subdomain = self._get_random_subdomain()
                
                line = line.replace(old_subdomain, f"{new_subdomain}.moveonjoy.com")
                
                # Log each replacement with different colors
                color_index = self.changed_lines % 4
                colors = [COLORS['BLUE'], COLORS['CYAN'], COLORS['MAGENTA'], COLORS['YELLOW']]
                color = colors[color_index]
                
                self.logger.info(
                    f"{color}🔄 Changed: {old_subdomain} → {new_subdomain}.moveonjoy.com{COLORS['ENDC']}"
                )
        
        return line
    
    async def rotate_subdomains(self, mode: str = 'sequential') -> bool:
        """
        Rotate subdomains in the M3U playlist
        
        Args:
            mode: 'sequential' or 'random' rotation
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.m3u_path.exists():
            self.logger.error(f"File not found: {self.m3u_path}")
            return False
        
        self.logger.info(f"{COLORS['HEADER']}{COLORS['BOLD']}🎬 Starting M3U Subdomain Rotation{COLORS['ENDC']}")
        self.logger.info(f"📁 File: {self.m3u_path}")
        self.logger.info(f"🌐 Online subdomains: {len(self.online_subdomains)} available")
        self.logger.info(f"📋 Subdomains: {', '.join(self.online_subdomains[:10])}..."
                         f"{' and more' if len(self.online_subdomains) > 10 else ''}")
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
            
            # Summary
            self.logger.info(f"{COLORS['GREEN']}{COLORS['BOLD']}✨ Rotation Complete!{COLORS['ENDC']}")
            self.logger.info(f"📊 Summary:")
            self.logger.info(f"   📝 Total lines processed: {self.processed_lines}")
            self.logger.info(f"   🔄 Subdomains changed: {self.changed_lines}")
            self.logger.info(f"   🌐 Online subdomains used: {len(self.online_subdomains)}")
            self.logger.info(f"   📍 Next rotation starts at: {self.online_subdomains[self.rotation_index]}")
            self.logger.info(f"{COLORS['GREEN']}✅ File saved successfully!{COLORS['ENDC']}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error processing file: {e}")
            return False

async def main():
    """Main function with interactive options"""
    m3u_path = "PrimeVision/us.m3u"
    
    print(f"{COLORS['HEADER']}{COLORS['BOLD']}")
    print("╔══════════════════════════════════════════════════════╗")
    print("║    🌐 MoveOnJoy Subdomain Rotator (Online Check)     ║")
    print("║    🔍 Checks online status of fl1-fl100              ║")
    print("╚══════════════════════════════════════════════════════╝")
    print(f"{COLORS['ENDC']}")
    
    try:
        # Step 1: Find online subdomains
        print(f"{COLORS['CYAN']}🔍 Step 1: Finding online subdomains...{COLORS['ENDC']}")
        
        async with SubdomainChecker() as checker:
            online_subdomains = await checker.find_online_subdomains(1, 100)
        
        if not online_subdomains:
            print(f"{COLORS['RED']}❌ No online subdomains found! Exiting.{COLORS['ENDC']}")
            return
        
        print(f"{COLORS['GREEN']}✅ Found {len(online_subdomains)} online subdomains!{COLORS['ENDC']}")
        
        # Step 2: Choose rotation mode
        print(f"\n{COLORS['YELLOW']}Choose rotation mode:{COLORS['ENDC']}")
        print(f"  1️⃣  {COLORS['GREEN']}Sequential rotation{COLORS['ENDC']}")
        print(f"  2️⃣  {COLORS['BLUE']}Random rotation{COLORS['ENDC']}")
        print(f"  3️⃣  {COLORS['RED']}Exit{COLORS['ENDC']}")
        
        choice = input(f"{COLORS['CYAN']}Enter choice (1-3): {COLORS['ENDC']}")
        
        if choice == '3':
            print(f"{COLORS['CYAN']}👋 Goodbye!{COLORS['ENDC']}")
            return
        
        mode = 'sequential' if choice == '1' else 'random'
        
        # Step 3: Rotate
        rotator = M3USubdomainRotator(m3u_path, online_subdomains)
        success = await rotator.rotate_subdomains(mode)
        
        if not success:
            print(f"{COLORS['RED']}❌ Operation failed!{COLORS['ENDC']}")
        
        # Show statistics
        print(f"\n{COLORS['MAGENTA']}{COLORS['BOLD']}📈 Statistics:{COLORS['ENDC']}")
        print(f"   Total online: {len(online_subdomains)}")
        print(f"   Online rate: {(len(online_subdomains)/100)*100:.1f}%")
        print(f"   First 10 online: {', '.join(online_subdomains[:10])}")
        
    except KeyboardInterrupt:
        print(f"\n{COLORS['YELLOW']}⚠️  Operation cancelled by user{COLORS['ENDC']}")
    except Exception as e:
        print(f"{COLORS['RED']}❌ Error: {e}{COLORS['ENDC']}")

async def quick_rotate():
    """Quick rotation without interactive menu"""
    m3u_path = "PrimeVision/us.m3u"
    
    print(f"{COLORS['CYAN']}🚀 Quick rotation mode{COLORS['ENDC']}")
    
    try:
        # Find online subdomains
        async with SubdomainChecker() as checker:
            online_subdomains = await checker.find_online_subdomains(1, 100)
        
        if not online_subdomains:
            print(f"{COLORS['RED']}❌ No online subdomains found!{COLORS['ENDC']}")
            return
        
        # Rotate with random mode
        rotator = M3USubdomainRotator(m3u_path, online_subdomains)
        await rotator.rotate_subdomains('random')
        
    except Exception as e:
        print(f"{COLORS['RED']}❌ Error: {e}{COLORS['ENDC']}")

if __name__ == "__main__":
    import sys
    
    # Check for quick mode
    if len(sys.argv) > 1 and sys.argv[1] == '--quick':
        asyncio.run(quick_rotate())
    else:
        asyncio.run(main())