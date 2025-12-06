#!/usr/bin/env python3
"""
📺 MoveOnJoy M3U Subdomain Updater
🔧 Updates fl1-fl49 subdomains to fl50 and pushes to GitHub
🚀 Async version with enhanced logging
"""

import re
import os
import asyncio
import aiofiles
import tempfile
import subprocess
import shutil
from pathlib import Path
import sys
from datetime import datetime
from typing import List, Tuple, Optional
import logging
from enum import Enum

# Color codes for terminal (optional, for prettier logs)
class Colors:
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    END = '\033[0m'
    BOLD = '\033[1m'

class LogLevel(Enum):
    INFO = "ℹ️"
    SUCCESS = "✅"
    WARNING = "⚠️"
    ERROR = "❌"
    DEBUG = "🐛"
    GIT = "📦"
    NETWORK = "🌐"
    FILE = "📁"
    CONFIG = "⚙️"

class AsyncM3UUpdater:
    def __init__(self, github_token: Optional[str] = None, 
                 repo_url: Optional[str] = None,
                 local_path: Optional[str] = None):
        """
        Initialize the async updater with enhanced logging.
        
        Args:
            github_token: GitHub Personal Access Token
            repo_url: GitHub repository URL
            local_path: Local path for repository
        """
        self.github_token = github_token
        self.repo_url = repo_url
        self.local_path = local_path or tempfile.mkdtemp(prefix="m3u_async_")
        self.repo_cloned = False
        self.log_file = None
        self.setup_logging()
        
    def setup_logging(self):
        """Setup logging with emojis and timestamps."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        self.log_file = log_dir / f"m3u_update_{timestamp}.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def log(self, level: LogLevel, message: str, color: Optional[str] = None):
        """Enhanced logging with emojis and colors."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_msg = f"{level.value} [{timestamp}] {message}"
        
        if color and sys.stdout.isatty():
            log_msg = f"{color}{log_msg}{Colors.END}"
            
        print(log_msg)
        
        # Also log to file without colors
        file_msg = f"{level.value} [{timestamp}] {message}"
        if level == LogLevel.INFO:
            self.logger.info(file_msg)
        elif level == LogLevel.SUCCESS:
            self.logger.info(f"SUCCESS: {file_msg}")
        elif level == LogLevel.ERROR:
            self.logger.error(file_msg)
        elif level == LogLevel.WARNING:
            self.logger.warning(file_msg)
        else:
            self.logger.debug(file_msg)
    
    async def clone_repository_async(self) -> bool:
        """Async clone of GitHub repository."""
        if not self.repo_url:
            self.log(LogLevel.ERROR, "❓ Repository URL not provided", Colors.RED)
            return False
            
        self.log(LogLevel.NETWORK, f"📥 Cloning repository: {self.repo_url}", Colors.CYAN)
        self.log(LogLevel.INFO, f"📂 Local path: {self.local_path}", Colors.BLUE)
        
        # Prepare git command
        cmd = ['git', 'clone']
        
        if self.github_token and 'https://' in self.repo_url:
            repo_url_with_token = self.repo_url.replace(
                'https://', 
                f'https://{self.github_token}@'
            )
            cmd.append(repo_url_with_token)
            self.log(LogLevel.CONFIG, "🔐 Using GitHub token authentication", Colors.PURPLE)
        else:
            cmd.append(self.repo_url)
            self.log(LogLevel.CONFIG, "🔑 Using SSH/default authentication", Colors.PURPLE)
            
        cmd.append(self.local_path)
        
        try:
            # Run git clone in a separate process
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Show progress animation
            animation = ["⏳", "⏳", "⏳"]
            for i in range(10):
                if process.returncode is not None:
                    break
                self.log(LogLevel.INFO, f"{animation[i % 3]} Cloning...", Colors.YELLOW)
                await asyncio.sleep(0.5)
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                self.repo_cloned = True
                self.log(LogLevel.SUCCESS, "🎉 Repository cloned successfully!", Colors.GREEN)
                return True
            else:
                self.log(LogLevel.ERROR, f"💥 Clone failed: {stderr.decode()}", Colors.RED)
                return False
                
        except Exception as e:
            self.log(LogLevel.ERROR, f"💣 Clone error: {str(e)}", Colors.RED)
            return False
    
    async def read_m3u_file_async(self, file_path: Path) -> List[str]:
        """Async read M3U file."""
        self.log(LogLevel.FILE, f"📖 Reading file: {file_path}", Colors.BLUE)
        
        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                lines = content.splitlines(keepends=True)
                
            self.log(LogLevel.INFO, f"📊 Read {len(lines)} lines", Colors.BLUE)
            return lines
        except Exception as e:
            self.log(LogLevel.ERROR, f"📄 Read error: {str(e)}", Colors.RED)
            raise
    
    async def write_m3u_file_async(self, file_path: Path, lines: List[str]) -> bool:
        """Async write M3U file."""
        self.log(LogLevel.FILE, f"📝 Writing file: {file_path}", Colors.BLUE)
        
        try:
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                await f.writelines(lines)
                
            self.log(LogLevel.SUCCESS, f"💾 File saved successfully", Colors.GREEN)
            return True
        except Exception as e:
            self.log(LogLevel.ERROR, f"💾 Write error: {str(e)}", Colors.RED)
            return False
    
    async def update_subdomains_async(self, m3u_file_path: str, 
                                     offline_only: bool = True) -> Tuple[int, int, List[str]]:
        """
        Async update of subdomains from fl1-fl49 to fl50.
        
        Returns:
            Tuple of (updated_count, total_lines, updated_urls)
        """
        file_path = Path(self.local_path) / m3u_file_path
        
        if not file_path.exists():
            self.log(LogLevel.ERROR, f"📂 File not found: {file_path}", Colors.RED)
            raise FileNotFoundError(f"M3U file not found: {file_path}")
        
        # Read file async
        lines = await self.read_m3u_file_async(file_path)
        
        updated_count = 0
        updated_urls = []
        pattern = r'(fl)(\d{1,2})(?=[\.-]|$)'
        
        self.log(LogLevel.INFO, f"🔍 Searching for subdomains...", Colors.YELLOW)
        
        # Process lines (could be parallelized if needed)
        new_lines = []
        for i, line in enumerate(lines, 1):
            original_line = line
            
            # Show progress every 100 lines
            if i % 100 == 0:
                self.log(LogLevel.DEBUG, f"📈 Processed {i}/{len(lines)} lines", Colors.CYAN)
            
            # Check offline condition
            if offline_only and 'offline' not in line.lower():
                new_lines.append(line)
                continue
            
            # Replace function
            def replace_fl(match):
                prefix = match.group(1)
                number = match.group(2)
                if number.isdigit() and 1 <= int(number) <= 49:
                    return 'fl50'
                return match.group(0)
            
            # Apply replacement
            updated_line = re.sub(pattern, replace_fl, line)
            
            if updated_line != original_line:
                updated_count += 1
                # Extract URL for logging
                if 'http' in updated_line:
                    updated_urls.append(updated_line.strip())
                
                # Log first few updates
                if updated_count <= 3:
                    self.log(LogLevel.DEBUG, 
                            f"🔄 Updated: {original_line.strip()[:50]}...", 
                            Colors.PURPLE)
                    self.log(LogLevel.DEBUG,
                            f"➡️  To: {updated_line.strip()[:50]}...",
                            Colors.PURPLE)
            
            new_lines.append(updated_line)
        
        # Write updated content async
        await self.write_m3u_file_async(file_path, new_lines)
        
        return updated_count, len(lines), updated_urls
    
    async def run_git_command_async(self, *args, **kwargs) -> Tuple[str, str, int]:
        """Async wrapper for git commands."""
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **kwargs
            )
            
            stdout, stderr = await process.communicate()
            return stdout.decode(), stderr.decode(), process.returncode
            
        except Exception as e:
            self.log(LogLevel.ERROR, f"🔧 Git command error: {str(e)}", Colors.RED)
            return "", str(e), 1
    
    async def commit_and_push_async(self, m3u_file_path: str, 
                                   commit_message: Optional[str] = None) -> bool:
        """Async commit and push to GitHub."""
        if not self.repo_cloned:
            self.log(LogLevel.ERROR, "💥 Repository not cloned", Colors.RED)
            return False
        
        original_dir = os.getcwd()
        os.chdir(self.local_path)
        
        try:
            # Configure git
            self.log(LogLevel.GIT, "⚙️  Configuring git...", Colors.YELLOW)
            await self.run_git_command_async('git', 'config', 'user.email', 'm3u-bot@example.com')
            await self.run_git_command_async('git', 'config', 'user.name', 'M3U Bot 🤖')
            
            # Add file
            self.log(LogLevel.GIT, f"➕ Adding {m3u_file_path}...", Colors.YELLOW)
            await self.run_git_command_async('git', 'add', m3u_file_path)
            
            # Check status
            self.log(LogLevel.GIT, "🔍 Checking git status...", Colors.YELLOW)
            stdout, stderr, returncode = await self.run_git_command_async(
                'git', 'status', '--porcelain'
            )
            
            if not stdout.strip():
                self.log(LogLevel.WARNING, "📭 No changes to commit", Colors.YELLOW)
                return False
            
            # Commit
            commit_msg = commit_message or f"🔄 Update subdomains in {m3u_file_path}"
            self.log(LogLevel.GIT, f"💬 Committing: {commit_msg}", Colors.YELLOW)
            await self.run_git_command_async('git', 'commit', '-m', commit_msg)
            
            # Push with animated progress
            self.log(LogLevel.GIT, "🚀 Pushing to GitHub...", Colors.CYAN)
            
            # Show push animation
            push_task = asyncio.create_task(
                self.run_git_command_async('git', 'push')
            )
            
            # Animation while pushing
            push_anim = ["⏳", "🔄", "🚀"]
            for i in range(20):
                if push_task.done():
                    break
                self.log(LogLevel.INFO, f"{push_anim[i % 3]} Pushing...", Colors.CYAN)
                await asyncio.sleep(0.3)
            
            stdout, stderr, returncode = await push_task
            
            if returncode == 0:
                self.log(LogLevel.SUCCESS, "🎉 Successfully pushed to GitHub!", Colors.GREEN)
                return True
            else:
                self.log(LogLevel.ERROR, f"💥 Push failed: {stderr}", Colors.RED)
                return False
                
        except Exception as e:
            self.log(LogLevel.ERROR, f"💣 Git operation error: {str(e)}", Colors.RED)
            return False
        finally:
            os.chdir(original_dir)
    
    async def validate_changes(self, m3u_file_path: str, original_count: int) -> bool:
        """Async validation of changes."""
        self.log(LogLevel.INFO, "🔬 Validating changes...", Colors.YELLOW)
        
        file_path = Path(self.local_path) / m3u_file_path
        
        try:
            lines = await self.read_m3u_file_async(file_path)
            
            # Count fl50 occurrences
            fl50_count = sum(1 for line in lines if 'fl50' in line)
            fl_other_count = sum(1 for line in lines if re.search(r'fl[1-9]\d?', line) and 'fl50' not in line)
            
            self.log(LogLevel.INFO, f"📊 Statistics:", Colors.CYAN)
            self.log(LogLevel.INFO, f"   Total lines: {len(lines)}", Colors.CYAN)
            self.log(LogLevel.INFO, f"   fl50 occurrences: {fl50_count}", Colors.CYAN)
            self.log(LogLevel.INFO, f"   Other flX occurrences: {fl_other_count}", Colors.CYAN)
            
            if fl_other_count == 0:
                self.log(LogLevel.SUCCESS, "🎯 All flX subdomains updated to fl50!", Colors.GREEN)
            else:
                self.log(LogLevel.WARNING, 
                        f"⚠️  Still found {fl_other_count} non-fl50 subdomains", 
                        Colors.YELLOW)
            
            return fl_other_count == 0
            
        except Exception as e:
            self.log(LogLevel.ERROR, f"🔍 Validation error: {str(e)}", Colors.RED)
            return False
    
    async def cleanup_async(self):
        """Async cleanup of temporary directory."""
        if os.path.exists(self.local_path) and 'tmp' in self.local_path:
            try:
                self.log(LogLevel.INFO, f"🧹 Cleaning up: {self.local_path}", Colors.YELLOW)
                await asyncio.to_thread(shutil.rmtree, self.local_path)
                self.log(LogLevel.SUCCESS, "✅ Cleanup completed", Colors.GREEN)
            except Exception as e:
                self.log(LogLevel.ERROR, f"🧹 Cleanup error: {str(e)}", Colors.RED)
    
    async def run_async(self, m3u_file_path: str, 
                       offline_only: bool = True,
                       validate: bool = True,
                       cleanup: bool = True) -> dict:
        """
        Complete async workflow.
        
        Returns:
            Dictionary with results
        """
        results = {
            'success': False,
            'updated_count': 0,
            'total_lines': 0,
            'updated_urls': [],
            'validation_passed': False,
            'push_success': False
        }
        
        try:
            # Start banner
            self.log(LogLevel.INFO, "=" * 50, Colors.BOLD)
            self.log(LogLevel.INFO, "📺 M3U SUBDOMAIN UPDATER", Colors.BOLD + Colors.PURPLE)
            self.log(LogLevel.INFO, "=" * 50, Colors.BOLD)
            
            # Step 1: Clone repository
            self.log(LogLevel.INFO, "📋 STEP 1: Clone Repository", Colors.BOLD + Colors.CYAN)
            clone_success = await self.clone_repository_async()
            if not clone_success:
                return results
            
            # Step 2: Update subdomains
            self.log(LogLevel.INFO, "📋 STEP 2: Update Subdomains", Colors.BOLD + Colors.CYAN)
            updated_count, total_lines, updated_urls = await self.update_subdomains_async(
                m3u_file_path, offline_only
            )
            
            results['updated_count'] = updated_count
            results['total_lines'] = total_lines
            results['updated_urls'] = updated_urls
            
            self.log(LogLevel.SUCCESS, 
                    f"✨ Updated {updated_count}/{total_lines} lines", 
                    Colors.GREEN)
            
            if updated_count == 0:
                self.log(LogLevel.WARNING, "🤷 No updates needed", Colors.YELLOW)
                return results
            
            # Step 3: Validate changes (optional)
            if validate:
                self.log(LogLevel.INFO, "📋 STEP 3: Validate Changes", Colors.BOLD + Colors.CYAN)
                validation_result = await self.validate_changes(m3u_file_path, updated_count)
                results['validation_passed'] = validation_result
            
            # Step 4: Commit and push
            self.log(LogLevel.INFO, "📋 STEP 4: Commit & Push", Colors.BOLD + Colors.CYAN)
            push_success = await self.commit_and_push_async(m3u_file_path)
            results['push_success'] = push_success
            
            if push_success:
                results['success'] = True
                
                # Summary
                self.log(LogLevel.INFO, "=" * 50, Colors.BOLD)
                self.log(LogLevel.SUCCESS, "🎉 UPDATE COMPLETE!", Colors.BOLD + Colors.GREEN)
                self.log(LogLevel.INFO, "=" * 50, Colors.BOLD)
                self.log(LogLevel.INFO, f"📈 Lines updated: {updated_count}", Colors.CYAN)
                self.log(LogLevel.INFO, f"📦 Push successful: {push_success}", Colors.CYAN)
                self.log(LogLevel.INFO, f"✅ Validation passed: {validation_result}", Colors.CYAN)
            
            return results
            
        except Exception as e:
            self.log(LogLevel.ERROR, f"💥 Workflow failed: {str(e)}", Colors.RED)
            return results
        finally:
            if cleanup:
                await self.cleanup_async()


def print_banner():
    """Print fancy banner."""
    banner = """
    ╔═══════════════════════════════════════════════════╗
    ║      📺 MOVEONJOY M3U UPDATER 🚀                  ║
    ║      🔧 Async Edition with Emoji Logs 🎨         ║
    ╚═══════════════════════════════════════════════════╝
    """
    print(Colors.BOLD + Colors.PURPLE + banner + Colors.END)


async def main_async():
    """Async main function."""
    print_banner()
    
    # Configuration
    GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
    REPO_URL = os.environ.get('REPO_URL', "https://github.com/YOUR_USERNAME/PrimeVision.git")
    M3U_FILE_PATH = os.environ.get('M3U_PATH', "us.m3u")
    
    # Check environment
    self.log(LogLevel.CONFIG, "🔍 Checking configuration...", Colors.YELLOW)
    
    if not GITHUB_TOKEN and 'https://' in REPO_URL:
        self.log(LogLevel.WARNING, 
                "⚠️  GITHUB_TOKEN not set in environment", 
                Colors.YELLOW)
        self.log(LogLevel.INFO,
                "💡 Set with: export GITHUB_TOKEN='your_token_here'",
                Colors.CYAN)
        self.log(LogLevel.INFO,
                "   or use SSH URL: git@github.com:user/repo.git",
                Colors.CYAN)
    
    # Create updater
    updater = AsyncM3UUpdater(
        github_token=GITHUB_TOKEN,
        repo_url=REPO_URL
    )
    
    # Run the workflow
    self.log(LogLevel.INFO, f"🎬 Starting update workflow...", Colors.BOLD + Colors.CYAN)
    
    results = await updater.run_async(
        m3u_file_path=M3U_FILE_PATH,
        offline_only=True,
        validate=True,
        cleanup=False  # Keep files for debugging
    )
    
    # Final status
    if results['success']:
        self.log(LogLevel.SUCCESS, "🏁 All tasks completed successfully!", Colors.BOLD + Colors.GREEN)
    else:
        self.log(LogLevel.WARNING, "⚠️  Some tasks did not complete successfully", Colors.YELLOW)
    
    return results


def main(