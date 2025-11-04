#!/usr/bin/env python3
"""
Auto-deploy Watcher - Monitors GitHub for new commits and redeploys automatically
Runs continuously in Docker container
"""

import os
import subprocess
import sys
import time
import requests
from pathlib import Path
from dotenv import load_dotenv
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DeployWatcher:
    def __init__(self):
        self.base_dir = Path(__file__).parent
        self.github_token = None
        
        # Load environment variables
        env_file = self.base_dir / ".env.local"
        if env_file.exists():
            load_dotenv(env_file)
            self.github_token = os.getenv("GITHUB_TOKEN")
        
        self.fe_repo_url = os.getenv("FE_REPO_URL", "https://github.com/Ayash13/Jalin-App-v2.git")
        self.be_repo_url = os.getenv("BE_REPO_URL", "https://github.com/Ayash13/JalinApp-REN.git")
        
        self.fe_last_sha = None
        self.be_last_sha = None
        
        # Polling interval in seconds (5 minutes)
        self.poll_interval = int(os.getenv("POLL_INTERVAL", "300"))
    
    def get_latest_commit_sha(self, owner, repo, branch="main"):
        """Get the latest commit SHA from GitHub API"""
        api_url = f"https://api.github.com/repos/{owner}/{repo}/commits/{branch}"
        headers = {"Authorization": f"token {self.github_token}"} if self.github_token else {}
        
        try:
            response = requests.get(api_url, headers=headers, timeout=10)
            if response.status_code == 200:
                return response.json().get("sha")
            else:
                logger.error(f"Failed to get commit SHA: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Error checking for updates: {e}")
            return None
    
    def extract_repo_info(self, repo_url):
        """Extract owner and repo name from GitHub URL"""
        repo_url = repo_url.rstrip('/')
        if repo_url.endswith('.git'):
            repo_url = repo_url[:-4]
        
        if 'github.com' in repo_url:
            parts = repo_url.split('github.com/')[-1].split('/')
            if len(parts) >= 2:
                return parts[0], parts[1]
        raise ValueError(f"Invalid GitHub repository URL: {repo_url}")
    
    def check_for_updates(self):
        """Check if there are new commits in either repository"""
        try:
            fe_owner, fe_repo = self.extract_repo_info(self.fe_repo_url)
            be_owner, be_repo = self.extract_repo_info(self.be_repo_url)
            
            fe_sha = self.get_latest_commit_sha(fe_owner, fe_repo)
            be_sha = self.get_latest_commit_sha(be_owner, be_repo)
            
            fe_updated = fe_sha and fe_sha != self.fe_last_sha
            be_updated = be_sha and be_sha != self.be_last_sha
            
            if fe_updated or be_updated:
                logger.info(f"🔔 New commits detected!")
                if fe_updated:
                    logger.info(f"  Frontend: {fe_sha[:8]} (was {self.fe_last_sha[:8] if self.fe_last_sha else 'none'})")
                if be_updated:
                    logger.info(f"  Backend: {be_sha[:8]} (was {self.be_last_sha[:8] if self.be_last_sha else 'none'})")
                
                return True, fe_sha, be_sha
            else:
                return False, fe_sha, be_sha
        except Exception as e:
            logger.error(f"Error checking for updates: {e}")
            return False, None, None
    
    def trigger_redeploy(self):
        """Trigger a redeploy - optimized for speed"""
        logger.info("🚀 Triggering redeployment...")
        
        try:
            # Run the deployment agent to pull latest code
            # Set a timeout to prevent hanging
            result = subprocess.run(
                [sys.executable, str(self.base_dir / "deploy_agent.py"),
                 "--fe-repo", self.fe_repo_url,
                 "--be-repo", self.be_repo_url],
                cwd=self.base_dir,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )
            
            if result.returncode == 0:
                logger.info("✅ Code updated. Rebuilding and restarting services...")
                
                # Check if we're inside Docker - if so, we need to use docker CLI from host
                # First try docker compose (v2), then docker-compose (v1)
                compose_commands = [
                    (["docker", "compose"], "-p"),  # v2 uses -p
                    (["docker-compose"], "--project-name")  # v1 uses --project-name
                ]
                
                rebuild_result = None
                for cmd_base, project_flag in compose_commands:
                    try:
                        # Test if command is available
                        test_result = subprocess.run(
                            cmd_base + ["version"],
                            capture_output=True,
                            check=False,
                            timeout=5
                        )
                        if test_result.returncode == 0:
                            logger.info(f"Using {' '.join(cmd_base)} for rebuild...")
                            # Only rebuild and restart frontend and backend, not the agent itself
                            # When running in Docker, use the mounted project directory
                            if Path("/.dockerenv").exists():
                                compose_dir = Path("/app/project")
                            else:
                                compose_dir = self.base_dir
                            
                            rebuild_cmd = cmd_base + [project_flag, "jalindeploy", "up", "-d", "--build", "--force-recreate", "frontend", "backend"]
                            rebuild_result = subprocess.run(
                                rebuild_cmd,
                                cwd=compose_dir,
                                capture_output=True,
                                text=True,
                                timeout=1800  # 30 minute timeout for builds
                            )
                            break
                    except (FileNotFoundError, subprocess.TimeoutExpired):
                        continue
                
                if rebuild_result is None:
                    logger.error("❌ Neither 'docker compose' nor 'docker-compose' found!")
                    return False
                
                if rebuild_result.returncode == 0:
                    logger.info("✅ Redeployment successful! Services restarted.")
                    return True
                else:
                    logger.error(f"❌ Failed to restart services")
                    logger.error(f"stdout: {rebuild_result.stdout}")
                    logger.error(f"stderr: {rebuild_result.stderr}")
                    return False
            else:
                logger.error(f"❌ Failed to update code (exit code: {result.returncode})")
                if result.stdout:
                    logger.error(f"stdout: {result.stdout[-1000:]}")  # Last 1000 chars
                if result.stderr:
                    logger.error(f"stderr: {result.stderr[-1000:]}")  # Last 1000 chars
                return False
        except Exception as e:
            logger.error(f"Error triggering redeploy: {e}")
            return False
    
    def run(self):
        """Main monitoring loop"""
        logger.info("=" * 60)
        logger.info("🔄 Auto-Deploy Watcher Started")
        logger.info("=" * 60)
        logger.info(f"Frontend: {self.fe_repo_url}")
        logger.info(f"Backend: {self.be_repo_url}")
        logger.info(f"Polling interval: {self.poll_interval} seconds")
        logger.info("=" * 60)
        
        # Get initial commit SHAs
        try:
            fe_owner, fe_repo = self.extract_repo_info(self.fe_repo_url)
            be_owner, be_repo = self.extract_repo_info(self.be_repo_url)
            
            self.fe_last_sha = self.get_latest_commit_sha(fe_owner, fe_repo)
            self.be_last_sha = self.get_latest_commit_sha(be_owner, be_repo)
            
            logger.info(f"Initial commit SHAs:")
            logger.info(f"  Frontend: {self.fe_last_sha[:8] if self.fe_last_sha else 'unknown'}")
            logger.info(f"  Backend: {self.be_last_sha[:8] if self.be_last_sha else 'unknown'}")
        except Exception as e:
            logger.error(f"Failed to get initial commits: {e}")
        
        # Main loop
        while True:
            try:
                logger.info(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Checking for updates...")
                
                has_updates, fe_sha, be_sha = self.check_for_updates()
                
                if has_updates:
                    if self.trigger_redeploy():
                        # Update last known SHAs
                        if fe_sha:
                            self.fe_last_sha = fe_sha
                        if be_sha:
                            self.be_last_sha = be_sha
                else:
                    logger.info("No updates detected. Waiting...")
                
            except KeyboardInterrupt:
                logger.info("\n👋 Watcher stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
            
            # Wait before next check
            time.sleep(self.poll_interval)


def main():
    watcher = DeployWatcher()
    watcher.run()


if __name__ == "__main__":
    main()

