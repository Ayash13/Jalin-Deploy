#!/bin/bash

# Cross-platform Docker build script
# Builds images for the platform Docker is running on
# For Linux servers, builds linux/amd64
# For Mac, builds linux/arm64 or linux/amd64 depending on architecture

set -e

echo "🔨 Building Docker images for deployment..."

# Detect the target platform
if [ -z "$DOCKER_BUILD_PLATFORM" ]; then
    # Default: build for the platform Docker is running on
    PLATFORM=""
else
    PLATFORM="--platform $DOCKER_BUILD_PLATFORM"
fi

echo "📦 Building with docker-compose..."
docker-compose build $PLATFORM

echo "✅ Build completed successfully!"
echo ""
echo "To build for a specific platform (e.g., Linux x86_64):"
echo "  DOCKER_BUILD_PLATFORM=linux/amd64 ./docker-build.sh"
echo ""
echo "Or use docker buildx for multi-platform:"
echo "  docker buildx build --platform linux/amd64,linux/arm64 -t your-image ."

