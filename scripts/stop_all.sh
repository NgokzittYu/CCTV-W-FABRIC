#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# SecureLens 一键停止脚本
# 按逆序停止: Frontend → Backend → IPFS → Fabric
# ═══════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load .env
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi

FABRIC_SAMPLES=${FABRIC_SAMPLES_PATH:-~/projects/fabric-samples}
FABRIC_SAMPLES=$(eval echo "$FABRIC_SAMPLES")

GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

print_step() { echo -e "${CYAN}[STEP]${NC} $1"; }
print_ok()   { echo -e "${GREEN}  ✅ $1${NC}"; }

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  SecureLens 一键停止"
echo "═══════════════════════════════════════════════════════════"
echo ""

# Step 1: 停止前端
print_step "1/4 停止前端 Dev Server..."
if [ -f "$PROJECT_ROOT/data/frontend.pid" ]; then
    kill "$(cat "$PROJECT_ROOT/data/frontend.pid")" 2>/dev/null || true
    rm -f "$PROJECT_ROOT/data/frontend.pid"
fi
pkill -f "vite" 2>/dev/null || true
print_ok "前端已停止"

# Step 2: 停止后端
print_step "2/4 停止 FastAPI 后端..."
if [ -f "$PROJECT_ROOT/data/backend.pid" ]; then
    kill "$(cat "$PROJECT_ROOT/data/backend.pid")" 2>/dev/null || true
    rm -f "$PROJECT_ROOT/data/backend.pid"
fi
pkill -f "uvicorn web_app:app" 2>/dev/null || true
print_ok "后端已停止"

# Step 3: 停止 IPFS
print_step "3/4 停止 IPFS 集群..."
if [ -f "$PROJECT_ROOT/docker-compose.ipfs.yml" ]; then
    docker compose -f "$PROJECT_ROOT/docker-compose.ipfs.yml" down 2>/dev/null || \
    docker-compose -f "$PROJECT_ROOT/docker-compose.ipfs.yml" down 2>/dev/null || true
fi
print_ok "IPFS 已停止"

# Step 4: 停止 Fabric
print_step "4/4 停止 Fabric 网络..."
if [ -d "$FABRIC_SAMPLES/test-network" ]; then
    cd "$FABRIC_SAMPLES/test-network"
    ./network.sh down 2>/dev/null || true
fi
print_ok "Fabric 已停止"

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  所有服务已停止"
echo "═══════════════════════════════════════════════════════════"
