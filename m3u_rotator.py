#!/usr/bin/env python3
"""
MoveOnJoy Subdomain Rotator for M3U Playlists
GitHub Actions Version
"""

import asyncio
import re
import aiofiles
import os
from pathlib import Path

class M3USubdomainRotator:
    def __init__(self, m3u_path: str, rotation_range: tuple = (1, 100)):
        self.m3u_path = Path(m3u_path)
        self.rotation_range = rotation_range
        self.current_subdomain = rotation_range[0]
        self.processed_lines = 0
        self.changed_lines = 0
    
    def _get_next_subdomain(self):
        subdomain = f"fl{self.current_subdomain}"
        self.current_subdomain += 1
        if self.current_subdomain > self.rotation_range[1]:
            self.current_subdomain = self.rotation_range[0]
        return subdomain
    
    async def rotate_subdomains(self):
        if not self.m3u_path.exists():
            print(f"❌ File not found: {self.m3u_path}")
            return False
        
        print(f"🎬 Starting M3U Subdomain Rotation")
        print(f"📁 File: {self.m3u_path}")
        print(f"🔄 Rotation Range: fl{self.rotation_range[0]} - fl{self.rotation_range[1]}")
        
        try:
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
                        new_subdomain = self._get_next_subdomain()
                        line = line.replace(old_subdomain, f"{new_subdomain}.moveonjoy.com")
                        print(f"🔄 Changed: {old_subdomain} → {new_subdomain}.moveonjoy.com")
                
                processed_lines.append(line)
            
            async with aiofiles.open(self.m3u_path, 'w', encoding='utf-8') as f:
                await f.write('\n'.join(processed_lines))
            
            print(f"✅ Rotation Complete!")
            print(f"📊 Summary:")
            print(f"   📝 Total lines processed: {self.processed_lines}")
            print(f"   🔄 Subdomains changed: {self.changed_lines}")
            print(f"   📍 Next rotation starts at: fl{self.current_subdomain}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error processing file: {e}")
            return False

async def main():
    rotator = M3USubdomainRotator("PrimeVision/us.m3u")
    success = await rotator.rotate_subdomains()
    if not success:
        raise Exception("Rotation failed!")

if __name__ == "__main__":
    asyncio.run(main())
