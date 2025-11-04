# Jalin Deployment Agent

An automated Python-based deployment agent that monitors GitHub repositories and automatically deploys frontend and backend applications to Docker. The agent runs continuously in Docker and automatically redeploys when new commits are detected.

## Features

- 🔐 GitHub private repository cloning with token authentication
- 🔄 **Automated redeployment** - Monitors GitHub for new commits and redeploys automatically
- 🐍 Automatic backend virtual environment setup (skipped when running in Docker)
- 📦 Frontend production build automation (skipped when running in Docker)
- 🐳 Docker containerization with shared network (`jalindeploy_jalin-network`)
- ✅ Smart checks to avoid redundant installations
- 🏗️ **Cross-platform support** - Works on macOS (ARM64) and Linux (x86_64)
- 🧹 **Automatic cleanup** - Removes old containers and images after deployment

## Prerequisites

- Python 3.11+
- Docker and Docker Compose (v1 or v2)
- GitHub Classic Token with repository access

## Setup

1. **Create `.env.local` file:**

   Create `.env.local` in the root directory and add your GitHub token:

   ```
   GITHUB_TOKEN=ghp_your_token_here
   ```

   Get your token from: https://github.com/settings/tokens

   **Note:** The token needs access to your private repositories.

2. **Install Python dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Quick Start (Automated Deployment)

The recommended way is to run everything in Docker with automatic redeployment:

```bash
# Build and start all services (agent, frontend, backend)
docker-compose up -d --build

# The agent will automatically:
# 1. Clone the repositories
# 2. Build Docker images
# 3. Start all services
# 4. Monitor for new commits every 5 minutes
```

### Manual Deployment

If you prefer to run the deployment manually:

```bash
# Using the helper script
./deploy.sh

# Or directly with Python
python deploy_agent.py \
    --fe-repo https://github.com/Ayash13/Jalin-App-v2.git \
    --be-repo https://github.com/Ayash13/JalinApp-REN.git
```

### Custom Repositories

Edit `docker-compose.yml` and update the environment variables:

```yaml
environment:
  - FE_REPO_URL=https://github.com/your-org/your-fe-repo.git
  - BE_REPO_URL=https://github.com/your-org/your-be-repo.git
  - POLL_INTERVAL=300 # Polling interval in seconds (default: 5 minutes)
```

Or set them when running:

```bash
FE_REPO_URL=https://github.com/your-org/your-fe-repo.git \
BE_REPO_URL=https://github.com/your-org/your-be-repo.git \
docker-compose up -d
```

## Project Structure

```
.
├── deploy_agent.py          # Main deployment agent script
├── deploy_watcher.py        # Automated redeployment watcher (runs in Docker)
├── docker-compose.yml       # Docker Compose configuration
├── Dockerfile.agent         # Dockerfile for the agent service
├── Dockerfile.frontend      # Dockerfile for frontend (in root)
├── Dockerfile.backend       # Dockerfile for backend (in root)
├── frontend/                # Frontend code (cloned from GitHub)
├── backend/                 # Backend code (cloned from GitHub)
├── .env.local              # GitHub token and configuration
├── requirements.txt        # Python dependencies
└── deploy.sh               # Quick deployment script
```

## Docker Services

All services run on the `jalindeploy_jalin-network` Docker network:

- **Frontend**: Port 3000 (serves static files via `serve`)
- **Backend**: Port 8000 (Flask/Python application)
- **Agent**: Monitors GitHub and triggers redeployments (runs `deploy_watcher.py`)

### Service Details

- **Agent Container (`jalin-agent`)**:

  - Runs continuously in Docker
  - Polls GitHub every 5 minutes (configurable via `POLL_INTERVAL`)
  - Automatically triggers redeployment when new commits are detected
  - Stays running during redeployments (only frontend/backend are recreated)

- **Frontend Container (`jalin-frontend`)**:

  - Built with Next.js static export
  - API URL configured for browser: `http://localhost:8000/api`
  - Serves static files on port 3000

- **Backend Container (`jalin-backend`)**:
  - Python Flask application
  - Runs on port 8000
  - Automatically detects entry point (`app.py`, `main.py`, `run.py`, or `manage.py`)

## Docker Commands

### View Running Services

```bash
# Using docker-compose v1
docker-compose ps

# Using docker compose v2
docker compose ps
```

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f agent
docker-compose logs -f frontend
docker-compose logs -f backend
```

### Stop Services

```bash
docker-compose down
```

### Rebuild and Restart

```bash
docker-compose up -d --build
```

### Manual Redeployment

If you want to trigger a redeployment manually:

```bash
# Restart the agent (it will detect changes on next poll)
docker-compose restart agent

# Or force a rebuild
docker-compose up -d --build frontend backend
```

## Automated Redeployment

The agent automatically monitors your GitHub repositories for new commits:

1. **Polling**: Checks for new commits every 5 minutes (configurable)
2. **Detection**: Compares latest commit SHA with previous deployment
3. **Redeployment**: If changes detected:
   - Pulls latest code from GitHub
   - Merges updates (preserves local files like Dockerfiles)
   - Rebuilds Docker images (frontend and backend only)
   - Stops and removes old containers
   - Creates new containers in the same network
   - Cleans up old unused images

**Important**: The agent container stays running during redeployments. Only frontend and backend containers are recreated.

## Configuration

### Environment Variables

Set in `docker-compose.yml` or `.env.local`:

- `GITHUB_TOKEN`: Your GitHub classic token (required)
- `FE_REPO_URL`: Frontend repository URL (default: `https://github.com/Ayash13/Jalin-App-v2.git`)
- `BE_REPO_URL`: Backend repository URL (default: `https://github.com/Ayash13/JalinApp-REN.git`)
- `POLL_INTERVAL`: Polling interval in seconds (default: `300` = 5 minutes)

### Frontend Configuration

The frontend is configured to use `http://localhost:8000/api` for API requests. This is set at build time via `NEXT_PUBLIC_API_BASE_URL` in `Dockerfile.frontend`.

### Backend Configuration

The backend automatically:

- Detects the entry point (`app.py`, `main.py`, `run.py`, or `manage.py`)
- Uses port 8000 (configurable via `PORT` environment variable)
- Binds to `0.0.0.0` for Docker networking

## Cross-Platform Support

This deployment setup is designed to work on both:

- **macOS (ARM64)**: Development and testing
- **Linux (x86_64)**: Production servers

### Architecture Detection

The Dockerfiles automatically detect the architecture and install appropriate dependencies:

- **ARM64**: Uses ARM64-optimized SWC packages or falls back to Babel
- **x86_64**: Uses x86_64-optimized SWC packages

### Building for Production (Linux Server)

If you're building on Mac but deploying to a Linux server:

```bash
# Build for Linux x86_64 architecture
DOCKER_BUILD_PLATFORM=linux/amd64 docker-compose build

# Or use the helper script
DOCKER_BUILD_PLATFORM=linux/amd64 ./docker-build.sh
```

### Multi-Platform Builds

For building images that work on both architectures:

```bash
docker buildx create --use
docker buildx build --platform linux/amd64,linux/arm64 -t your-image .
```

## How It Works

### Initial Deployment

1. **Clone Repositories**: Downloads frontend and backend code from GitHub using the API (not git clone)
2. **Merge Updates**: Smart merge that preserves local files (Dockerfiles, `.env.local`)
3. **Skip Setup**: When running in Docker, skips venv/Node.js setup (handled by Dockerfiles)
4. **Build Images**: Creates Docker images for frontend and backend
5. **Deploy**: Starts all services in Docker containers

### Automated Updates

1. **Monitor**: Agent polls GitHub API every 5 minutes
2. **Detect**: Compares commit SHAs
3. **Update**: If new commits found:
   - Downloads latest code
   - Merges into existing directories (preserves Dockerfiles)
   - Rebuilds Docker images
   - Stops old containers
   - Creates new containers in `jalindeploy` project
   - Cleans up old images

### Network and Project Management

- All services use the **`jalindeploy`** project name (not directory name)
- All containers join **`jalindeploy_jalin-network`** network
- Agent stays running during redeployments
- Frontend and backend are recreated in the same network

## Troubleshooting

### GitHub Authentication Fails

- Check that your token is valid and has repository access
- Verify the token is in `.env.local` as `GITHUB_TOKEN=ghp_...`
- Ensure the token hasn't expired

### Container Name Conflicts

- The agent automatically removes old containers before creating new ones
- If you see conflicts, manually remove: `docker rm -f jalin-frontend jalin-backend`

### Network Issues

- All services must use the `jalindeploy` project name
- Check network: `docker network ls | grep jalindeploy`
- Services should be on `jalindeploy_jalin-network`

### Frontend Can't Connect to Backend

- Frontend uses `http://localhost:8000/api` (browser-side)
- Backend must be accessible on host port 8000
- Check backend logs: `docker-compose logs backend`

### Build Errors

- **npm install fails**: Uses `--force` or `--legacy-peer-deps` automatically
- **SWC build errors on ARM64**: Automatically falls back to Babel
- **Permission errors**: Check Docker volume mounts and file permissions

### Docker Compose Version Issues

- The agent automatically detects Docker Compose v1 or v2
- v2 uses `-p` flag, v1 uses `--project-name` flag
- Both are handled automatically

### Port Conflicts

- Frontend: Modify port mapping in `docker-compose.yml` (currently `3000:3000`)
- Backend: Modify port mapping in `docker-compose.yml` (currently `8000:8000`)

### Redeployment Not Working

- Check agent logs: `docker-compose logs -f agent`
- Verify polling interval: Check `POLL_INTERVAL` in docker-compose.yml
- Ensure GitHub token has access to repositories
- Check network connectivity from agent container

## File Preservation

During updates, the following files are **preserved** (not overwritten):

- `Dockerfile` (frontend and backend)
- `.env.local` files
- Any files that exist locally but not in the repository

This ensures your Docker configurations and environment variables are never lost during updates.

## Notes

- The agent checks if directories exist before cloning (won't overwrite existing code)
- Virtual environments are reused if they already exist (when running locally)
- Node.js installation check is performed (when running locally)
- All services share the same Docker network for communication
- The agent container has access to Docker socket for managing other containers
- Old images are automatically cleaned up after successful deployments
