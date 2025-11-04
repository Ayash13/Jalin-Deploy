#!/usr/bin/env python3
"""
Deployment Agent for Frontend and Backend Applications
Handles GitHub cloning, environment setup, and Docker deployment
"""

import os
import subprocess
import sys
import shutil
import time
import requests
import zipfile
import tempfile
from pathlib import Path
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DeploymentAgent:
    def __init__(self):
        self.base_dir = Path(__file__).parent
        self.frontend_dir = self.base_dir / "frontend"
        self.backend_dir = self.base_dir / "backend"
        self.github_token = None
        
        # Load environment variables
        env_file = self.base_dir / ".env.local"
        if env_file.exists():
            load_dotenv(env_file)
            self.github_token = os.getenv("GITHUB_TOKEN")
        else:
            logger.warning(".env.local not found. Please create it with GITHUB_TOKEN")
        
    def check_command(self, command):
        """Check if a command is available in the system"""
        try:
            subprocess.run(
                ["which", command],
                check=True,
                capture_output=True,
                text=True
            )
            return True
        except subprocess.CalledProcessError:
            return False
    
    def verify_repo_cloned(self, target_dir, repo_name, required_files=None):
        """Verify that repository is fully downloaded and contains expected files"""
        if not target_dir.exists():
            return False
        
        # Check if it's a directory with content (either git repo or API download)
        if not target_dir.is_dir():
            return False
        
        # Check if directory has files (not empty)
        try:
            if not any(target_dir.iterdir()):
                logger.warning(f"{repo_name} directory exists but is empty")
                return False
        except Exception as e:
            logger.warning(f"Could not check {repo_name} directory contents: {e}")
            return False
        
        # Check for required files if specified
        if required_files:
            missing_files = []
            for file_name in required_files:
                file_path = target_dir / file_name
                if not file_path.exists():
                    missing_files.append(file_name)
            
            if missing_files:
                logger.warning(f"{repo_name} missing expected files: {', '.join(missing_files)}")
                return False
        
        return True
    
    def _merge_directories(self, source_dir, target_dir):
        """Merge source directory into target directory, like git pull.
        Files from source replace files in target, but files only in target are preserved.
        Special files like .env.local are preserved and not overwritten."""
        source_path = Path(source_dir)
        target_path = Path(target_dir)
        
        # List of files to preserve (don't overwrite these from source)
        preserve_files = {'.env.local', '.env.local.example', 'Dockerfile'}
        
        # Create target directory if it doesn't exist
        target_path.mkdir(parents=True, exist_ok=True)
        
        # Walk through all files in source directory
        for root, dirs, files in os.walk(source_path):
            # Calculate relative path from source root
            rel_path = os.path.relpath(root, source_path)
            
            # Create corresponding directory in target
            if rel_path == '.':
                target_subdir = target_path
            else:
                target_subdir = target_path / rel_path
                target_subdir.mkdir(parents=True, exist_ok=True)
            
            # Copy all files from source to target
            for file in files:
                source_file = Path(root) / file
                target_file = target_subdir / file
                
                # Preserve special files - don't overwrite if they exist
                if file in preserve_files and target_file.exists():
                    logger.debug(f"Preserving existing {file} - not overwriting")
                    continue
                
                # Copy file, replacing if it exists
                # Handle permission errors when writing to mounted volumes
                try:
                    shutil.copy2(source_file, target_file)
                except PermissionError as e:
                    logger.warning(f"Permission error copying {file}, trying with chmod...")
                    # Try to fix permissions and retry
                    try:
                        os.chmod(target_file.parent, 0o755)
                        shutil.copy2(source_file, target_file)
                        os.chmod(target_file, 0o644)
                    except Exception as e2:
                        logger.error(f"Failed to copy {file} even with permission fix: {e2}")
                        raise
                except Exception as e:
                    logger.error(f"Error copying {file}: {e}")
                    raise
        
        logger.info(f"✓ Merged updates into {target_dir} (preserved .env.local and Dockerfiles)")
    
    def extract_repo_info(self, repo_url):
        """Extract owner and repo name from GitHub URL"""
        repo_url = repo_url.rstrip('/')
        if repo_url.endswith('.git'):
            repo_url = repo_url[:-4]
        
        # Extract owner/repo from various URL formats
        if 'github.com' in repo_url:
            parts = repo_url.split('github.com/')[-1].split('/')
            if len(parts) >= 2:
                return parts[0], parts[1]
        
        raise ValueError(f"Invalid GitHub repository URL: {repo_url}")
    
    def clone_repository(self, repo_url, target_dir, repo_name):
        """Download GitHub repository using API, always gets latest version"""
        # Always download latest version, even if directory exists
        if target_dir.exists():
            logger.info(f"{repo_name} directory exists. Updating with latest from GitHub...")
        
        if not self.github_token:
            logger.error("GitHub token not found. Please set GITHUB_TOKEN in .env.local")
            return False
        
        try:
            # Extract owner and repo name from URL
            owner, repo = self.extract_repo_info(repo_url)
            logger.info(f"Downloading {repo_name} from GitHub API...")
            
            # Try to get default branch from API, fallback to main
            default_branch = "main"
            try:
                repo_info_url = f"https://api.github.com/repos/{owner}/{repo}"
                repo_response = requests.get(
                    repo_info_url,
                    headers={"Authorization": f"token {self.github_token}"},
                    timeout=10
                )
                if repo_response.status_code == 200:
                    repo_data = repo_response.json()
                    default_branch = repo_data.get("default_branch", "main")
                    logger.info(f"Using branch: {default_branch}")
            except Exception as e:
                logger.warning(f"Could not determine default branch, using 'main': {e}")
            
            # GitHub API endpoint for downloading repository as zipball
            api_url = f"https://api.github.com/repos/{owner}/{repo}/zipball/{default_branch}"
            
            headers = {
                "Authorization": f"token {self.github_token}",
                "Accept": "application/vnd.github.v3+json"
            }
            
            # Create a temporary file for the zip
            with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_file:
                tmp_zip_path = tmp_file.name
            
            try:
                # Download the repository
                response = requests.get(api_url, headers=headers, stream=True)
                response.raise_for_status()
                
                # Save to temporary file
                with open(tmp_zip_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                logger.info(f"Downloaded {repo_name} successfully. Extracting and merging...")
                
                # Create parent directory if needed
                target_dir.parent.mkdir(parents=True, exist_ok=True)
                
                # Extract zip file to temporary location first
                # Use a location that's not a mounted volume to avoid permission issues
                extract_temp = Path("/tmp") / f"_temp_extract_{repo_name}_{int(time.time())}"
                if extract_temp.exists():
                    shutil.rmtree(extract_temp)
                extract_temp.mkdir(parents=True, exist_ok=True)
                
                try:
                    with zipfile.ZipFile(tmp_zip_path, 'r') as zip_ref:
                        # Extract all files
                        zip_ref.extractall(extract_temp)
                        
                        # Find the root folder (GitHub adds owner-repo-hash prefix)
                        zip_members = zip_ref.namelist()
                        if not zip_members:
                            raise ValueError("Zip file appears to be empty")
                        
                        root_folder = zip_members[0].split('/')[0]
                        extracted_folder = extract_temp / root_folder
                        
                        if not extracted_folder.exists():
                            raise ValueError(f"Expected folder {root_folder} not found in extracted files")
                        
                        # Smart merge: copy files from extracted folder to target
                        # This preserves local files (like Dockerfiles) that aren't in the repo
                        if target_dir.exists():
                            logger.info(f"Merging {repo_name} updates (preserving local files like Dockerfiles)...")
                            try:
                                self._merge_directories(extracted_folder, target_dir)
                            except Exception as e:
                                logger.error(f"Error during merge: {e}")
                                raise
                        else:
                            # If target doesn't exist, just move the extracted folder
                            extracted_folder.rename(target_dir)
                            logger.info(f"Created {repo_name} directory at {target_dir}")
                        
                finally:
                    # Clean up temp extract directory
                    if extract_temp.exists():
                        try:
                            shutil.rmtree(extract_temp)
                        except Exception as e:
                            logger.warning(f"Could not clean up temp directory: {e}")
                
                logger.info(f"✓ Successfully downloaded and extracted {repo_name}")
                
                # Verify the download
                if self.verify_repo_cloned(target_dir, repo_name):
                    return True
                else:
                    logger.error(f"Download completed but verification failed for {repo_name}")
                    return False
                    
            finally:
                # Clean up temporary file
                if os.path.exists(tmp_zip_path):
                    os.unlink(tmp_zip_path)
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download {repo_name} from GitHub API: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response status: {e.response.status_code}")
                logger.error(f"Response body: {e.response.text[:200]}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error downloading {repo_name}: {e}")
            return False
    
    def is_running_in_docker(self):
        """Check if we're running inside a Docker container"""
        # Check for .dockerenv file (present in Docker containers)
        if Path("/.dockerenv").exists():
            return True
        # Check cgroup (another Docker indicator)
        try:
            with open("/proc/self/cgroup", "r") as f:
                if "docker" in f.read():
                    return True
        except:
            pass
        return False
    
    def setup_backend(self):
        """Setup backend: create venv and install requirements (only if needed)
        Skip venv setup if running in Docker (Docker will handle it during build)"""
        logger.info("Setting up backend environment...")
        
        # If running in Docker, skip venv setup - Docker will handle it
        if self.is_running_in_docker():
            logger.info("Running in Docker container - skipping venv setup (Docker will handle during build)")
            logger.info("✓ Backend setup skipped (will be handled by Docker build)")
            return True
        
        venv_path = self.backend_dir / "venv"
        requirements_file = self.backend_dir / "requirements.txt"
        
        # Check if venv already exists - if yes, skip creation
        if venv_path.exists():
            logger.info("Backend venv already exists. Skipping creation.")
        else:
            logger.info("Creating virtual environment...")
            try:
                subprocess.run(
                    [sys.executable, "-m", "venv", str(venv_path)],
                    check=True,
                    cwd=self.backend_dir
                )
                logger.info("✓ Virtual environment created")
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to create venv: {e}")
                return False
        
        # Install requirements if venv exists
        if venv_path.exists() and requirements_file.exists():
            logger.info("Installing/updating backend requirements...")
            pip_cmd = str(venv_path / "bin" / "pip")
            if sys.platform == "win32":
                pip_cmd = str(venv_path / "Scripts" / "pip.exe")
            
            try:
                # Upgrade pip first
                subprocess.run(
                    [pip_cmd, "install", "--upgrade", "pip"],
                    check=True,
                    cwd=self.backend_dir,
                    capture_output=True
                )
                # Install/update requirements
                subprocess.run(
                    [pip_cmd, "install", "-r", str(requirements_file)],
                    check=True,
                    cwd=self.backend_dir
                )
                logger.info("✓ Backend requirements installed/updated")
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to install requirements: {e}")
                return False
        elif not requirements_file.exists():
            logger.warning(f"requirements.txt not found in {self.backend_dir}")
        
        return True
    
    def check_nodejs(self):
        """Check if Node.js is installed - don't install, just verify"""
        if self.check_command("node"):
            node_version = subprocess.run(
                ["node", "--version"],
                capture_output=True,
                text=True
            ).stdout.strip()
            logger.info(f"Node.js is already installed: {node_version} - Skipping installation")
            return True
        else:
            logger.warning("Node.js not found. Please install Node.js manually.")
            logger.info("Visit https://nodejs.org/ to install Node.js")
            return False
    
    def setup_frontend(self):
        """Setup frontend: check Node.js and run production build
        Skip build if running in Docker (Docker will handle it during build)"""
        logger.info("Setting up frontend...")
        
        # If running in Docker, skip frontend build - Docker will handle it
        if self.is_running_in_docker():
            logger.info("Running in Docker container - skipping frontend build (Docker will handle during build)")
            logger.info("✓ Frontend setup skipped (will be handled by Docker build)")
            return True
        
        # Check Node.js
        if not self.check_nodejs():
            return False
        
        # Install dependencies
        package_json = self.frontend_dir / "package.json"
        if package_json.exists():
            logger.info("Installing frontend dependencies...")
            try:
                subprocess.run(
                    ["npm", "install", "--force"],
                    check=True,
                    cwd=self.frontend_dir
                )
                logger.info("✓ Frontend dependencies installed")
            except subprocess.CalledProcessError as e:
                logger.warning(f"npm install --force failed, trying with --legacy-peer-deps...")
                try:
                    subprocess.run(
                        ["npm", "install", "--legacy-peer-deps"],
                        check=True,
                        cwd=self.frontend_dir
                    )
                    logger.info("✓ Frontend dependencies installed with --legacy-peer-deps")
                except subprocess.CalledProcessError as e2:
                    logger.error(f"Failed to install frontend dependencies: {e2}")
                    return False
            
            # Build production version with Docker service URL for internal communication
            logger.info("Building frontend for production...")
            try:
                # Set environment variable for Docker internal communication
                env = os.environ.copy()
                env['NEXT_PUBLIC_API_BASE_URL'] = 'http://backend:8000/api'
                
                subprocess.run(
                    ["npm", "run", "build"],
                    check=True,
                    cwd=self.frontend_dir,
                    env=env
                )
                logger.info("✓ Frontend production build completed")
            except subprocess.CalledProcessError as e:
                logger.warning(f"Build command failed (might not have build script): {e}")
        else:
            logger.warning(f"package.json not found in {self.frontend_dir}")
        
        return True
    
    def build_docker_images(self):
        """Build Docker images for all services - optimized for speed"""
        logger.info("Building Docker images (using cache for faster builds)...")
        
        docker_compose_file = self.base_dir / "docker-compose.yml"
        if not docker_compose_file.exists():
            logger.error("docker-compose.yml not found!")
            return False
        
        # Verify repositories are cloned before building
        logger.info("Verifying repositories are ready...")
        if not self.verify_repo_cloned(self.frontend_dir, "Frontend"):
            logger.error("Frontend repository not properly cloned. Cannot build Docker image.")
            return False
        
        if not self.verify_repo_cloned(self.backend_dir, "Backend", ["requirements.txt"]):
            logger.error("Backend repository not properly cloned or missing requirements.txt. Cannot build Docker image.")
            return False
        
        logger.info("Repositories verified. Proceeding with Docker build...")
        
        try:
            # Build only frontend and backend (not the agent itself)
            # The agent shouldn't rebuild itself during updates
            # Check for docker compose (v2) vs docker-compose (v1)
            build_cmd = None
            try:
                subprocess.run(["docker", "compose", "version"], 
                             capture_output=True, check=True, timeout=5)
                # docker compose v2 uses -p flag
                build_cmd = ["docker", "compose", "-p", "jalindeploy", "build", "--parallel", "frontend", "backend"]
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                # docker-compose v1 uses --project-name flag
                build_cmd = ["docker-compose", "--project-name", "jalindeploy", "build", "--parallel", "frontend", "backend"]
            
            # When running in Docker, use the mounted project directory
            if self.is_running_in_docker():
                compose_dir = Path("/app/project")
            else:
                compose_dir = self.base_dir
            
            subprocess.run(
                build_cmd,
                check=True,
                cwd=compose_dir
            )
            logger.info("✓ Docker images built successfully")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to build Docker images: {e}")
            return False
    
    def deploy(self):
        """Deploy all services using Docker Compose"""
        logger.info("Deploying services to Docker...")
        
        try:
            # Check for docker compose (v2) vs docker-compose (v1)
            compose_cmd_base = None
            project_flag = None
            try:
                subprocess.run(["docker", "compose", "version"], 
                             capture_output=True, check=True, timeout=5)
                # docker compose v2 uses -p flag
                compose_cmd_base = ["docker", "compose"]
                project_flag = "-p"
            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
                # docker-compose v1 uses --project-name flag
                compose_cmd_base = ["docker-compose"]
                project_flag = "--project-name"
            
            # When running in Docker, use the mounted project directory
            if self.is_running_in_docker():
                compose_dir = Path("/app/project")
            else:
                compose_dir = self.base_dir
            
            # Forcefully stop and remove ONLY frontend and backend containers (agent stays running)
            # This ensures containers are removed before recreating them in the same network
            logger.info("Stopping and removing frontend and backend containers (agent will stay running)...")
            containers_to_remove = ["jalin-frontend", "jalin-backend"]
            for container_name in containers_to_remove:
                # Stop container if running
                stop_result = subprocess.run(
                    ["docker", "stop", container_name],
                    capture_output=True,
                    check=False  # Don't fail if container doesn't exist
                )
                # Force remove container (removes even if running)
                rm_result = subprocess.run(
                    ["docker", "rm", "-f", container_name],
                    capture_output=True,
                    check=False  # Don't fail if container doesn't exist
                )
                if rm_result.returncode == 0:
                    logger.info(f"✓ Removed {container_name}")
                elif stop_result.returncode != 0 and rm_result.returncode != 0:
                    logger.debug(f"Container {container_name} doesn't exist (will be created)")
            
            # Small delay to ensure containers are fully removed
            time.sleep(1)
            
            # Start ONLY frontend and backend services (agent is not touched)
            # They will be recreated in the same network (jalin-network) where agent is running
            # Use project flag to ensure we use "jalindeploy" instead of directory name
            logger.info("Recreating frontend and backend services in the same network...")
            up_cmd = compose_cmd_base + [project_flag, "jalindeploy", "up", "-d", "--no-deps", "--build", "frontend", "backend"]
            # --no-deps ensures we don't touch the agent service
            # --project-name ensures we use jalindeploy network, not "project"
            subprocess.run(
                up_cmd,
                check=True,
                cwd=compose_dir
            )
            logger.info("✓ Services deployed successfully")
            
            # Clean up old unused images (jalindeploy-frontend and jalindeploy-backend)
            # This removes the old images that are no longer in use
            logger.info("Cleaning up old unused images...")
            old_images = ["jalindeploy-frontend", "jalindeploy-backend"]
            for image_name in old_images:
                try:
                    # Remove dangling images (untagged) for this image name
                    result = subprocess.run(
                        ["docker", "image", "prune", "-f", "--filter", f"dangling=true"],
                        capture_output=True,
                        check=False
                    )
                    # Also try to remove old images with the exact name
                    subprocess.run(
                        ["docker", "rmi", "-f", image_name],
                        capture_output=True,
                        check=False  # Don't fail if image doesn't exist
                    )
                except Exception as e:
                    logger.debug(f"Could not clean up image {image_name}: {e}")
            
            logger.info("✓ Deployment and cleanup completed")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to deploy services: {e}")
            return False
    
    def run(self, fe_repo_url, be_repo_url):
        """Main deployment flow"""
        logger.info("=" * 60)
        logger.info("Starting Deployment Agent")
        logger.info("=" * 60)
        
        # Step 1: Clone repositories
        logger.info("\n[Step 1/5] Cloning repositories...")
        if not self.clone_repository(fe_repo_url, self.frontend_dir, "Frontend"):
            return False
        if not self.clone_repository(be_repo_url, self.backend_dir, "Backend"):
            return False
        
        # Step 2: Setup backend
        logger.info("\n[Step 2/5] Setting up backend...")
        if not self.setup_backend():
            return False
        
        # Step 3: Setup frontend
        logger.info("\n[Step 3/5] Setting up frontend...")
        if not self.setup_frontend():
            return False
        
        # Step 4: Build Docker images
        logger.info("\n[Step 4/5] Building Docker images...")
        if not self.build_docker_images():
            return False
        
        # Step 5: Deploy to Docker
        logger.info("\n[Step 5/5] Deploying to Docker...")
        if not self.deploy():
            return False
        
        logger.info("\n" + "=" * 60)
        logger.info("🎉 Deployment completed successfully!")
        logger.info("=" * 60)
        logger.info("\nServices are running in Docker.")
        logger.info("Use 'docker-compose ps' to check status")
        logger.info("Use 'docker-compose logs' to view logs")
        
        return True


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Deployment Agent for Frontend and Backend Applications"
    )
    parser.add_argument(
        "--fe-repo",
        required=True,
        help="Frontend GitHub repository URL"
    )
    parser.add_argument(
        "--be-repo",
        required=True,
        help="Backend GitHub repository URL"
    )
    
    args = parser.parse_args()
    
    agent = DeploymentAgent()
    success = agent.run(args.fe_repo, args.be_repo)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

