#!/usr/bin/env python3
"""
MoveOnJoy Subdomain Rotator for M3U Playlists
Rotates fl1-fl100 subdomains for offline MoveOnJoy streams
"""

import asyncio
import re
import aiofiles
import logging
from typing import List, Tuple
from pathlib import Path
from datetime import datetime

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

class M3USubdomainRotator:
    """Rotates MoveOnJoy subdomains in M3U playlists"""
    
    def __init__(self, m3u_path: str, rotation_range: Tuple[int, int] = (1, 100)):
        """
        Initialize the rotator
        
        Args:
            m3u_path: Path to M3U playlist file
            rotation_range: Range of subdomains to rotate through (min, max)
        """
        self.m3u_path = Path(m3u_path)
        self.rotation_range = rotation_range
        self.current_subdomain = rotation_range[0]
        self.processed_lines = 0
        self.changed_lines = 0
        
        # Setup colorful logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(ColorfulFormatter())
            self.logger.addHandler(console_handler)
    
    def _get_next_subdomain(self) -> str:
        """Get next subdomain in rotation"""
        subdomain = f"fl{self.current_subdomain}"
        self.current_subdomain += 1
        
        # Reset if we exceed max range
        if self.current_subdomain > self.rotation_range[1]:
            self.current_subdomain = self.rotation_range[0]
            self.logger.info(f"{COLORS['CYAN']}🔄 Subdomain rotation reset to fl{self.rotation_range[0]}{COLORS['ENDC']}")
        
        return subdomain
    
    async def _process_line(self, line: str) -> str:
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
                new_subdomain = self._get_next_subdomain()
                line = line.replace(old_subdomain, f"{new_subdomain}.moveonjoy.com")
                
                # Log each replacement with different colors
                color_index = self.changed_lines % 4
                colors = [COLORS['BLUE'], COLORS['CYAN'], COLORS['GREEN'], COLORS['YELLOW']]
                color = colors[color_index]
                
                self.logger.info(
                    f"{color}🔄 Changed: {old_subdomain} → {new_subdomain}.moveonjoy.com{COLORS['ENDC']}"
                )
        
        return line
    
    async def rotate_subdomains(self) -> bool:
        """
        Rotate subdomains in the M3U playlist
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.m3u_path.exists():
            self.logger.error(f"File not found: {self.m3u_path}")
            return False
        
        self.logger.info(f"{COLORS['HEADER']}{COLORS['BOLD']}🎬 Starting M3U Subdomain Rotation{COLORS['ENDC']}")
        self.logger.info(f"📁 File: {self.m3u_path}")
        self.logger.info(f"🔄 Rotation Range: fl{self.rotation_range[0]} - fl{self.rotation_range[1]}")
        self.logger.info(f"{COLORS['YELLOW']}⏳ Processing...{COLORS['ENDC']}")
        
        try:
            # Read the file
            async with aiofiles.open(self.m3u_path, 'r', encoding='utf-8') as f:
                content = await f.read()
            
            lines = content.split('\n')
            processed_lines = []
            
            # Process lines asynchronously
            tasks = [self._process_line(line) for line in lines]
            processed_lines = await asyncio.gather(*tasks)
            
            # Write the processed content
            async with aiofiles.open(self.m3u_path, 'w', encoding='utf-8') as f:
                await f.write('\n'.join(processed_lines))
            
            # Summary
            self.logger.info(f"{COLORS['GREEN']}{COLORS['BOLD']}✨ Rotation Complete!{COLORS['ENDC']}")
            self.logger.info(f"📊 Summary:")
            self.logger.info(f"   📝 Total lines processed: {self.processed_lines}")
            self.logger.info(f"   🔄 Subdomains changed: {self.changed_lines}")
            self.logger.info(f"   📍 Next rotation starts at: fl{self.current_subdomain}")
            self.logger.info(f"{COLORS['GREEN']}✅ File saved successfully!{COLORS['ENDC']}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error processing file: {e}")
            return False
    
    async def preview_changes(self) -> None:
        """Preview changes without modifying the file"""
        if not self.m3u_path.exists():
            self.logger.error(f"File not found: {self.m3u_path}")
            return
        
        self.logger.info(f"{COLORS['HEADER']}{COLORS['BOLD']}👁️  Preview Mode - No changes will be made{COLORS['ENDC']}")
        
        try:
            async with aiofiles.open(self.m3u_path, 'r', encoding='utf-8') as f:
                content = await f.read()
            
            lines = content.split('\n')
            preview_counter = 0
            
            for i, line in enumerate(lines[:50], 1):  # Preview first 50 lines
                pattern = r'fl\d+\.moveonjoy\.com'
                matches = re.findall(pattern, line)
                
                if matches and preview_counter < 10:  # Show first 10 matches
                    preview_counter += 1
                    old_subdomain = matches[0]
                    new_subdomain = self._get_next_subdomain()
                    
                    self.logger.info(
                        f"{COLORS['CYAN']}📋 Line {i}: {old_subdomain} → {new_subdomain}.moveonjoy.com{COLORS['ENDC']}"
                    )
            
            if preview_counter == 0:
                self.logger.warning("⚠️  No MoveOnJoy subdomains found in preview")
            elif preview_counter >= 10:
                self.logger.info(f"{COLORS['YELLOW']}📋 ... and more (preview limited to 10 changes){COLORS['ENDC']}")
                
        except Exception as e:
            self.logger.error(f"Error previewing file: {e}")

async def main():
    """Main function with interactive options"""
    m3u_path = "PrimeVision/us.m3u"
    
    print(f"{COLORS['HEADER']}{COLORS['BOLD']}")
    print("╔══════════════════════════════════════════╗")
    print("║    🎬 MoveOnJoy Subdomain Rotator        ║")
    print("║    🔄 Rotation Range: fl1 - fl100        ║")
    print("╚══════════════════════════════════════════╝")
    print(f"{COLORS['ENDC']}")
    
    rotator = M3USubdomainRotator(m3u_path)
    
    # Interactive menu
    print(f"{COLORS['YELLOW']}Choose an option:{COLORS['ENDC']}")
    print(f"  1️⃣  {COLORS['GREEN']}Rotate subdomains{COLORS['ENDC']}")
    print(f"  2️⃣  {COLORS['BLUE']}Preview changes{COLORS['ENDC']}")
    print(f"  3️⃣  {COLORS['RED']}Exit{COLORS['ENDC']}")
    
    choice = input(f"{COLORS['CYAN']}Enter choice (1-3): {COLORS['ENDC']}")
    
    if choice == '1':
        success = await rotator.rotate_subdomains()
        if not success:
            print(f"{COLORS['RED']}❌ Operation failed! Check logs above.{COLORS['ENDC']}")
    elif choice == '2':
        await rotator.preview_changes()
    elif choice == '3':
        print(f"{COLORS['CYAN']}👋 Goodbye!{COLORS['ENDC']}")
        return
    else:
        print(f"{COLORS['RED']}❌ Invalid choice!{COLORS['ENDC']}")

if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())