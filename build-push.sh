#!/usr/bin/env bash
# TrendRod Build & Push to Aliyun ACR
# Usage: ALIYUN_PASSWORD=your_password ./build-push.sh [tag]
# If tag omitted, uses current git tag or 'latest'.

set -euo pipefail

REGISTRY="registry.cn-hangzhou.aliyuncs.com"
NAMESPACE="docker-pusher"
IMAGE="sales_web"
FULL_IMAGE="${REGISTRY}/${NAMESPACE}/${IMAGE}"

# 1. 确定 tag
if [ $# -ge 1 ]; then
    TAG="$1"
else
    TAG=$(git describe --tags --exact-match 2>/dev/null || echo "latest")
fi

echo "=== TrendRod Build & Push ==="
echo "Registry : ${REGISTRY}"
echo "Image    : ${FULL_IMAGE}"
echo "Tag      : ${TAG}"

# 2. Build
echo ""
echo "[1/4] Building image..."
docker build -t "${FULL_IMAGE}:${TAG}" -t "${FULL_IMAGE}:latest" .

# 3. Login (password from env to avoid leaking in scripts)
echo ""
echo "[2/4] Logging into Aliyun ACR..."
if [ -z "${ALIYUN_PASSWORD:-}" ]; then
    echo "ERROR: Set ALIYUN_PASSWORD env var before running."
    echo "  Example: ALIYUN_PASSWORD=xxx ./build-push.sh"
    exit 1
fi
echo "${ALIYUN_PASSWORD}" | docker login "${REGISTRY}" -u "aliyun3174025308" --password-stdin

# 4. Push
echo ""
echo "[3/4] Pushing ${TAG}..."
docker push "${FULL_IMAGE}:${TAG}"

echo ""
echo "[4/4] Pushing latest..."
docker push "${FULL_IMAGE}:latest"

echo ""
echo "=== Done ==="
echo "Image: ${FULL_IMAGE}:${TAG}"
echo ""
echo "Deploy on server:"
echo "  docker pull ${FULL_IMAGE}:${TAG}"
echo "  docker compose up -d"
