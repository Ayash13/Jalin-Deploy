# Jalin Deployment Agent

A Python-based deployment agent that automates the process of deploying frontend and backend applications to Docker.

## Features

- 🔐 GitHub private repository cloning with token authentication
- 🐍 Automatic backend virtual environment setup
- 📦 Frontend production build automation
- 🐳 Docker containerization with shared network
- ✅ Smart checks to avoid redundant installations

## Prerequisites

- Python 3.11+
- Git
- Docker and Docker Compose
- Node.js (for local frontend setup, will check automatically)

## Setup

1. **Create `.env.local` file:**

   Copy the example file and add your GitHub token:

   ```bash
   cp .env.local.example .env.local
   ```

   Edit `.env.local` and add your GitHub classic token:

   ```
   GITHUB_TOKEN=ghp_your_token_here
   ```

   Get your token from: https://github.com/settings/tokens

2. **Install Python dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Quick Start (with predefined repositories)

Simply run:

```bash
./deploy.sh
```

Or use Python directly:

```bash
python deploy_agent.py \
    --fe-repo https://github.com/Ayash13/Jalin-App-v2.git \
    --be-repo https://github.com/Ayash13/JalinApp-REN.git
```

### Custom Repositories

Run the deployment agent with your own repository URLs:

```bash
python deploy_agent.py --fe-repo https://github.com/your-org/your-fe-repo.git --be-repo https://github.com/your-org/your-be-repo.git
```

The agent will:

1. **Clone Repositories**: Pull frontend and backend code from GitHub (if not already present)
2. **Setup Backend**: Create virtual environment and install requirements.txt
3. **Setup Frontend**: Check Node.js, install dependencies, and build production version
4. **Build Docker Images**: Create Docker images for all services
5. **Deploy**: Start all services in Docker containers on the same network

## Project Structure

```
.
├── deploy_agent.py          # Main deployment agent script
├── docker-compose.yml       # Docker Compose configuration
├── Dockerfile.agent         # Dockerfile for the agent itself
├── frontend/
│   └── Dockerfile          # Frontend Docker configuration
├── backend/
│   └── Dockerfile          # Backend Docker configuration
├── .env.local              # GitHub token (create from .env.local.example)
└── requirements.txt        # Python dependencies
```

## Docker Services

All services run on the `jalin-network` Docker network:

- **Frontend**: Port 3000
- **Backend**: Port 8000
- **Agent**: Management service

## Docker Commands

- View running services:

  ```bash
  docker-compose ps
  ```

- View logs:

  ```bash
  docker-compose logs -f
  ```

- Stop services:

  ```bash
  docker-compose down
  ```

- Rebuild and restart:
  ```bash
  docker-compose up -d --build
  ```

## Notes

- The agent checks if directories exist before cloning (won't overwrite existing code)
- Virtual environments are reused if they already exist
- Node.js installation check is performed (manual installation required if missing)
- All services share the same Docker network for communication

## Cross-Platform Support

This deployment setup is designed to work on both:

- **macOS (ARM64)**: Development and testing
- **Linux (x86_64)**: Production servers

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

## Troubleshooting

- **GitHub authentication fails**: Check that your token is valid and has repo access
- **Node.js not found**: Install Node.js from https://nodejs.org/
- **Docker build fails**: Ensure Docker is running and check the specific service logs
- **Port conflicts**: Modify ports in `docker-compose.yml` if 3000 or 8000 are in use
- **SWC build errors on ARM64**: The Dockerfile automatically handles this by falling back to Babel
- **Cross-platform builds**: Use `--platform linux/amd64` when building on Mac for Linux servers
