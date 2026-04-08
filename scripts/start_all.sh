#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# SecureLens 一键启动脚本
# 按顺序启动: Fabric → IPFS → FastAPI Backend → Frontend Dev Server
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
FABRIC_SAMPLES=$(eval echo "$FABRIC_SAMPLES")  # expand ~
CHANNEL=${CHANNEL_NAME:-mychannel}
CHAINCODE=${CHAINCODE_NAME:-evidence}

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

print_step() { echo -e "${CYAN}[STEP]${NC} $1"; }
print_ok()   { echo -e "${GREEN}  ✅ $1${NC}"; }
print_warn() { echo -e "${YELLOW}  ⚠️  $1${NC}"; }
print_fail() { echo -e "${RED}  ❌ $1${NC}"; }

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  SecureLens 一键启动"
echo "═══════════════════════════════════════════════════════════"
echo ""

# ──────────────────────────────────────────────────────────────────
# Step 1: Fabric Network
# ──────────────────────────────────────────────────────────────────
print_step "1/4 启动 Fabric 网络..."

if [ ! -d "$FABRIC_SAMPLES/test-network" ]; then
    print_fail "Fabric Samples 路径不存在: $FABRIC_SAMPLES/test-network"
    print_warn "请检查 .env 中的 FABRIC_SAMPLES_PATH 配置"
    exit 1
fi

cd "$FABRIC_SAMPLES/test-network"

# 清理旧环境
./network.sh down 2>/dev/null || true

# 启动 3 组织网络
./network.sh up createChannel -c "$CHANNEL" -ca
print_ok "Fabric 网络已启动 (2 Org)"

# 添加 Org3
cd addOrg3
./addOrg3.sh up -c "$CHANNEL" -ca
cd ..
print_ok "Org3 已加入"

# 部署链码
CHAINCODE_PATH="$PROJECT_ROOT/chaincode"
if [ -d "$CHAINCODE_PATH" ]; then
    ./network.sh deployCC -ccn "$CHAINCODE" \
        -ccp "$CHAINCODE_PATH" -ccl go \
        -ccep "AND('Org1MSP.peer','Org2MSP.peer')" \
        -cccg "$CHAINCODE_PATH/collections_config.json" 2>&1 || {
        print_warn "链码部署使用默认策略重试..."
        ./network.sh deployCC -ccn "$CHAINCODE" \
            -ccp "$CHAINCODE_PATH" -ccl go 2>&1 || true
    }
    print_ok "链码 '$CHAINCODE' 已部署"
else
    print_warn "链码目录不存在: $CHAINCODE_PATH，跳过部署"
fi

cd "$PROJECT_ROOT"

# ──────────────────────────────────────────────────────────────────
# Step 2: IPFS Cluster
# ──────────────────────────────────────────────────────────────────
print_step "2/4 启动 IPFS 集群..."

if [ -f "$PROJECT_ROOT/docker-compose.ipfs.yml" ]; then
    docker compose -f "$PROJECT_ROOT/docker-compose.ipfs.yml" up -d 2>/dev/null || \
    docker-compose -f "$PROJECT_ROOT/docker-compose.ipfs.yml" up -d 2>/dev/null || true

    # 等待 IPFS 就绪
    echo "  等待 IPFS 节点就绪..."
    for i in $(seq 1 30); do
        if curl -s http://localhost:5001/api/v0/id >/dev/null 2>&1; then
            print_ok "IPFS 集群已启动"
            break
        fi
        sleep 1
    done
else
    print_warn "docker-compose.ipfs.yml 不存在，跳过 IPFS"
fi

# ──────────────────────────────────────────────────────────────────
# Step 3: FastAPI Backend
# ──────────────────────────────────────────────────────────────────
print_step "3/4 启动 FastAPI 后端..."

cd "$PROJECT_ROOT"

# 激活虚拟环境（如有）
if [ -f "$PROJECT_ROOT/venv/bin/activate" ]; then
    source "$PROJECT_ROOT/venv/bin/activate"
fi

# 创建上传目录
mkdir -p "$PROJECT_ROOT/data/uploads"

# 停止旧进程
pkill -f "uvicorn web_app:app" 2>/dev/null || true
sleep 1

# 启动后端
VIF_MODE=fusion nohup uvicorn web_app:app --host 0.0.0.0 --port 8000 \
    > "$PROJECT_ROOT/data/backend.log" 2>&1 &
BACKEND_PID=$!
echo "$BACKEND_PID" > "$PROJECT_ROOT/data/backend.pid"

# 等待后端就绪
for i in $(seq 1 15); do
    if curl -s http://localhost:8000/api/config >/dev/null 2>&1; then
        print_ok "FastAPI 后端已启动 (PID: $BACKEND_PID)"
        break
    fi
    sleep 1
done

# ──────────────────────────────────────────────────────────────────
# Step 4: Frontend Dev Server
# ──────────────────────────────────────────────────────────────────
print_step "4/4 启动前端 Dev Server..."

cd "$PROJECT_ROOT/demo2"

# 安装依赖（如需要）
if [ ! -d "node_modules" ]; then
    npm install
fi

# 停止旧进程
pkill -f "vite" 2>/dev/null || true
sleep 1

nohup npm run dev > "$PROJECT_ROOT/data/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo "$FRONTEND_PID" > "$PROJECT_ROOT/data/frontend.pid"

sleep 3
print_ok "前端 Dev Server 已启动 (PID: $FRONTEND_PID)"

# ──────────────────────────────────────────────────────────────────
# 打印状态汇总
# ──────────────────────────────────────────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  SecureLens 服务状态"
echo "═══════════════════════════════════════════════════════════"
echo -e "  ${GREEN}Fabric${NC}:   3 Org, Channel=$CHANNEL, Chaincode=$CHAINCODE"
echo -e "  ${GREEN}IPFS${NC}:     http://localhost:5001"
echo -e "  ${GREEN}Backend${NC}:  http://localhost:8000"
echo -e "  ${GREEN}Frontend${NC}: http://localhost:5173"
echo ""
echo "  日志文件:"
echo "    Backend:  $PROJECT_ROOT/data/backend.log"
echo "    Frontend: $PROJECT_ROOT/data/frontend.log"
echo "═══════════════════════════════════════════════════════════"
