#!/bin/bash

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

FABRIC_SAMPLES="${FABRIC_SAMPLES_PATH:-$HOME/projects/fabric-samples}"
TEST_NETWORK="$FABRIC_SAMPLES/test-network"
CHANNEL_NAME="${CHANNEL_NAME:-mychannel}"
CHAINCODE_NAME="${CHAINCODE_NAME:-evidence}"
CHAINCODE_PATH="$ROOT/chaincode"
IPFS_COMPOSE="$ROOT/docker-compose.ipfs.yml"
VENV_PATH="$ROOT/venv"
DATA_DIR="$ROOT/data"
LOG_DIR="$DATA_DIR/logs"
BACKEND_STARTUP_RETRIES="${BACKEND_STARTUP_RETRIES:-180}"
BACKEND_STARTUP_SLEEP_SECONDS="${BACKEND_STARTUP_SLEEP_SECONDS:-2}"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[SecureLens]${NC} $1"; }
warn() { echo -e "${YELLOW}[SecureLens]${NC} $1"; }
err()  { echo -e "${RED}[SecureLens]${NC} $1"; }
info() { echo -e "${CYAN}[SecureLens]${NC} $1"; }

mkdir -p "$DATA_DIR" "$LOG_DIR"

fabric_network_running() {
    docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^peer0.org1.example.com$" &&
    docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^peer0.org2.example.com$" &&
    docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^orderer.example.com$"
}

ipfs_api_ready() {
    curl -s http://127.0.0.1:5001/api/v0/id >/dev/null 2>&1
}

ipfs_running_count() {
    docker ps --format '{{.Names}}' 2>/dev/null | awk '/^cctv-ipfs-node[0-9]+$/ {count++} END {print count+0}'
}

prepare_fabric_env() {
    export PATH="${FABRIC_SAMPLES}/bin:$PATH"
    export FABRIC_CFG_PATH="${FABRIC_SAMPLES}/config/"
    export CORE_PEER_TLS_ENABLED=true
    export CORE_PEER_LOCALMSPID="Org1MSP"
    export CORE_PEER_TLS_ROOTCERT_FILE="${TEST_NETWORK}/organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt"
    export CORE_PEER_MSPCONFIGPATH="${TEST_NETWORK}/organizations/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp"
    export CORE_PEER_ADDRESS=localhost:7051
}

fabric_channel_exists() {
    fabric_network_running || return 1
    prepare_fabric_env
    peer channel getinfo -c "$CHANNEL_NAME" >/dev/null 2>&1
}

fabric_chaincode_ready() {
    fabric_channel_exists || return 1
    prepare_fabric_env
    peer lifecycle chaincode querycommitted -C "$CHANNEL_NAME" -n "$CHAINCODE_NAME" >/dev/null 2>&1
}

require_path() {
    local path="$1"
    local label="$2"
    if [ ! -e "$path" ]; then
        err "$label 不存在: $path"
        exit 1
    fi
}

tail_log() {
    local logfile="$1"
    if [ -f "$logfile" ]; then
        warn "最近日志 ($logfile):"
        tail -20 "$logfile" | sed 's/^/    /'
    fi
}

run_with_timeout() {
    local timeout_seconds="$1"
    local logfile="$2"
    shift 2

    "$@" >"$logfile" 2>&1 &
    local pid=$!
    local elapsed=0

    while kill -0 "$pid" 2>/dev/null; do
        if [ "$elapsed" -ge "$timeout_seconds" ]; then
            warn "步骤超时 (${timeout_seconds}s)"
            kill "$pid" 2>/dev/null || true
            wait "$pid" 2>/dev/null || true
            return 124
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done

    wait "$pid"
}

wait_for_http() {
    local url="$1"
    local retries="$2"
    local sleep_seconds="$3"

    local attempt=0
    while [ "$attempt" -lt "$retries" ]; do
        if curl -s "$url" >/dev/null 2>&1; then
            return 0
        fi
        attempt=$((attempt + 1))
        sleep "$sleep_seconds"
    done
    return 1
}

stop_apps() {
    log "停止前后端服务..."

    if [ -f "$DATA_DIR/backend.pid" ]; then
        local pid
        pid="$(cat "$DATA_DIR/backend.pid")"
        kill "$pid" 2>/dev/null || true
        rm -f "$DATA_DIR/backend.pid"
    fi

    if [ -f "$DATA_DIR/frontend.pid" ]; then
        local pid
        pid="$(cat "$DATA_DIR/frontend.pid")"
        kill "$pid" 2>/dev/null || true
        rm -f "$DATA_DIR/frontend.pid"
    fi

    lsof -ti:8000 2>/dev/null | xargs kill -9 2>/dev/null || true
    lsof -ti:5173 2>/dev/null | xargs kill -9 2>/dev/null || true
}

show_status() {
    echo ""
    info "═══ SecureLens 状态 ═══"

    if fabric_network_running; then
        log "Fabric:   ✅ 运行中"
    else
        warn "Fabric:   ⚠️ 未运行"
    fi

    if [ "$(ipfs_running_count)" -ge 3 ] && ipfs_api_ready; then
        log "IPFS:     ✅ 运行中"
    else
        warn "IPFS:     ⚠️ 未运行"
    fi

    if lsof -ti:8000 >/dev/null 2>&1; then
        log "Backend:  ✅ http://127.0.0.1:8000"
    else
        warn "Backend:  ⚠️ 未运行"
    fi

    if lsof -ti:5173 >/dev/null 2>&1; then
        log "Frontend: ✅ http://127.0.0.1:5173"
    else
        warn "Frontend: ⚠️ 未运行"
    fi

    echo ""
}

ensure_prerequisites() {
    require_path "$TEST_NETWORK" "fabric-samples test-network"
    require_path "$FABRIC_SAMPLES/bin/peer" "Fabric peer 二进制"
    require_path "$FABRIC_SAMPLES/bin/orderer" "Fabric orderer 二进制"
    require_path "$IPFS_COMPOSE" "IPFS docker compose 文件"
    require_path "$CHAINCODE_PATH/chaincode.go" "链码源码"
}

ensure_fabric_network() {
    if fabric_network_running; then
        log "Fabric 网络已存在，直接复用"
        return 0
    fi

    local logfile="$LOG_DIR/fabric_up.log"
    log "启动 Fabric 网络..."
    if ! run_with_timeout 300 "$logfile" /bin/bash -lc "cd \"$TEST_NETWORK\" && ./network.sh up -ca"; then
        err "Fabric 网络启动失败"
        tail_log "$logfile"
        exit 1
    fi

    if ! fabric_network_running; then
        err "Fabric 网络没有成功起来"
        tail_log "$logfile"
        exit 1
    fi

    log "Fabric 网络已启动"
}

ensure_fabric_channel() {
    if fabric_channel_exists; then
        log "Fabric 通道 $CHANNEL_NAME 已存在"
        return 0
    fi

    local logfile="$LOG_DIR/fabric_channel.log"
    log "创建 Fabric 通道 $CHANNEL_NAME..."
    if ! run_with_timeout 180 "$logfile" /bin/bash -lc "cd \"$TEST_NETWORK\" && ./network.sh createChannel -c \"$CHANNEL_NAME\""; then
        err "Fabric 通道创建失败"
        tail_log "$logfile"
        exit 1
    fi

    if ! fabric_channel_exists; then
        err "Fabric 通道没有创建成功"
        tail_log "$logfile"
        exit 1
    fi

    log "Fabric 通道已就绪"
}

ensure_chaincode() {
    if fabric_chaincode_ready; then
        log "链码 $CHAINCODE_NAME 已部署"
        return 0
    fi

    local deploy_log="$LOG_DIR/fabric_chaincode.log"
    log "部署链码 $CHAINCODE_NAME..."
    if ! run_with_timeout 300 "$deploy_log" /bin/bash -lc "cd \"$TEST_NETWORK\" && ./network.sh deployCC -ccn \"$CHAINCODE_NAME\" -ccp \"$CHAINCODE_PATH\" -ccl go -c \"$CHANNEL_NAME\""; then
        err "链码部署失败"
        tail_log "$deploy_log"
        exit 1
    fi

    if ! fabric_chaincode_ready; then
        err "链码未成功提交到通道"
        tail_log "$deploy_log"
        exit 1
    fi

    local init_log="$LOG_DIR/fabric_init.log"
    log "初始化链码账本..."
    prepare_fabric_env
    if ! run_with_timeout 120 "$init_log" /bin/bash -lc "
        export PATH=\"$FABRIC_SAMPLES/bin:\$PATH\"
        export FABRIC_CFG_PATH=\"$FABRIC_SAMPLES/config/\"
        export CORE_PEER_TLS_ENABLED=true
        export CORE_PEER_LOCALMSPID=\"Org1MSP\"
        export CORE_PEER_TLS_ROOTCERT_FILE=\"$TEST_NETWORK/organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt\"
        export CORE_PEER_MSPCONFIGPATH=\"$TEST_NETWORK/organizations/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp\"
        export CORE_PEER_ADDRESS=localhost:7051
        peer chaincode invoke \
            -o localhost:7050 \
            --ordererTLSHostnameOverride orderer.example.com \
            --tls \
            --cafile \"$TEST_NETWORK/organizations/ordererOrganizations/example.com/orderers/orderer.example.com/msp/tlscacerts/tlsca.example.com-cert.pem\" \
            -C \"$CHANNEL_NAME\" \
            -n \"$CHAINCODE_NAME\" \
            --peerAddresses localhost:7051 \
            --tlsRootCertFiles \"$TEST_NETWORK/organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt\" \
            --peerAddresses localhost:9051 \
            --tlsRootCertFiles \"$TEST_NETWORK/organizations/peerOrganizations/org2.example.com/peers/peer0.org2.example.com/tls/ca.crt\" \
            -c '{\"function\":\"InitLedger\",\"Args\":[]}'
    "; then
        warn "链码初始化可能已执行过，继续启动"
        tail_log "$init_log"
    else
        log "链码初始化完成"
    fi
}

ensure_ipfs() {
    if [ "$(ipfs_running_count)" -ge 3 ] && ipfs_api_ready; then
        log "IPFS 集群已存在，直接复用"
        return 0
    fi

    local logfile="$LOG_DIR/ipfs_up.log"
    log "启动 IPFS 三节点集群..."
    if ! run_with_timeout 120 "$logfile" docker compose -f "$IPFS_COMPOSE" up -d; then
        err "IPFS 集群启动失败"
        tail_log "$logfile"
        exit 1
    fi

    log "等待 IPFS API 就绪..."
    if ! wait_for_http "http://127.0.0.1:5001/api/v0/id" 30 2; then
        err "IPFS API 启动超时"
        tail_log "$logfile"
        exit 1
    fi

    local node0_id
    node0_id="$(curl -s http://127.0.0.1:5001/api/v0/id 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin).get("ID",""))' 2>/dev/null || true)"
    if [ -n "$node0_id" ]; then
        curl -s -X POST "http://127.0.0.1:5002/api/v0/swarm/connect?arg=/ip4/$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' cctv-ipfs-node0)/tcp/4001/p2p/$node0_id" >/dev/null 2>&1 || true
        curl -s -X POST "http://127.0.0.1:5003/api/v0/swarm/connect?arg=/ip4/$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' cctv-ipfs-node0)/tcp/4001/p2p/$node0_id" >/dev/null 2>&1 || true
    fi

    log "IPFS 集群已启动"
}

start_backend() {
    local logfile="$DATA_DIR/backend.log"
    log "启动后端..."

    lsof -ti:8000 2>/dev/null | xargs kill -9 2>/dev/null || true
    rm -f "$logfile"

    if [ -d "$VENV_PATH" ]; then
        # shellcheck disable=SC1090
        source "$VENV_PATH/bin/activate"
    fi

    python -m demo2.server >"$logfile" 2>&1 &
    local pid=$!
    echo "$pid" > "$DATA_DIR/backend.pid"

    if ! wait_for_http "http://127.0.0.1:8000/api/health" "$BACKEND_STARTUP_RETRIES" "$BACKEND_STARTUP_SLEEP_SECONDS"; then
        err "后端启动失败"
        warn "后端可能仍在执行启动初始化，可通过 BACKEND_STARTUP_RETRIES/BACKEND_STARTUP_SLEEP_SECONDS 调整等待时长"
        tail_log "$logfile"
        exit 1
    fi

    log "后端已就绪"
}

start_frontend() {
    local logfile="$DATA_DIR/frontend.log"
    log "启动前端..."

    lsof -ti:5173 2>/dev/null | xargs kill -9 2>/dev/null || true
    rm -f "$logfile"

    cd "$ROOT/demo2"
    if [ ! -d node_modules ]; then
        log "安装前端依赖..."
        npm install >"$LOG_DIR/npm_install.log" 2>&1
    fi

    npm run dev >"$logfile" 2>&1 &
    local pid=$!
    echo "$pid" > "$DATA_DIR/frontend.pid"
    cd "$ROOT"

    if ! wait_for_http "http://127.0.0.1:5173" 30 2; then
        err "前端启动失败"
        tail_log "$logfile"
        exit 1
    fi

    log "前端已就绪"
}

start_full() {
    ensure_prerequisites
    stop_apps
    ensure_fabric_network
    ensure_fabric_channel
    ensure_chaincode
    ensure_ipfs
    start_backend
    start_frontend
    echo ""
    log "启动完成"
    log "前端: http://127.0.0.1:5173"
    log "后端: http://127.0.0.1:8000"
    log "日志目录: $LOG_DIR"
}

start_quick() {
    stop_apps
    start_backend
    start_frontend
    echo ""
    log "快速启动完成"
    log "前端: http://127.0.0.1:5173"
    log "后端: http://127.0.0.1:8000"
}

case "${1:-full}" in
    full|"")
        start_full
        ;;
    quick)
        start_quick
        ;;
    stop)
        stop_apps
        ;;
    status)
        show_status
        ;;
    *)
        echo "用法: $0 [full|quick|stop|status]"
        echo "  full   完整启动（Fabric + IPFS + Backend + Frontend）"
        echo "  quick  仅启动 Backend + Frontend"
        echo "  stop   停止前后端"
        echo "  status 查看状态"
        exit 1
        ;;
esac
