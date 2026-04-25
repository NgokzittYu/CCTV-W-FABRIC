#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# SecureLens 服务状态检查脚本
# ═══════════════════════════════════════════════════════════════════

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
CHANNEL=${CHANNEL_NAME:-mychannel}

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  SecureLens 服务状态检查"
echo "═══════════════════════════════════════════════════════════"
echo ""

# Check Fabric
echo -n "  Fabric Network:  "
if [ -d "$FABRIC_SAMPLES/test-network" ]; then
    cd "$FABRIC_SAMPLES/test-network"
    export PATH="$FABRIC_SAMPLES/bin:$PATH"
    export FABRIC_CFG_PATH="$FABRIC_SAMPLES/config"
    
    ORG1_DIR="$FABRIC_SAMPLES/test-network/organizations/peerOrganizations/org1.example.com"
    export CORE_PEER_TLS_ENABLED=true
    export CORE_PEER_LOCALMSPID=Org1MSP
    export CORE_PEER_ADDRESS=localhost:7051
    export CORE_PEER_TLS_ROOTCERT_FILE="$ORG1_DIR/peers/peer0.org1.example.com/tls/ca.crt"
    export CORE_PEER_MSPCONFIGPATH="$ORG1_DIR/users/Admin@org1.example.com/msp"
    
    if peer channel getinfo -c "$CHANNEL" >/dev/null 2>&1; then
        BLOCK_HEIGHT=$(peer channel getinfo -c "$CHANNEL" 2>/dev/null | grep -o '"height":[0-9]*' | grep -o '[0-9]*')
        echo -e "${GREEN}✅ 运行中${NC} (Channel=$CHANNEL, BlockHeight=$BLOCK_HEIGHT)"
    else
        echo -e "${RED}❌ 未运行${NC}"
    fi
    cd "$PROJECT_ROOT"
else
    echo -e "${YELLOW}⚠️  目录不存在${NC}"
fi

# Check IPFS
echo -n "  IPFS:            "
if curl -s http://localhost:5001/api/v0/id >/dev/null 2>&1; then
    IPFS_ID=$(curl -s http://localhost:5001/api/v0/id 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin).get('ID','unknown')[:16])" 2>/dev/null || echo "unknown")
    echo -e "${GREEN}✅ 运行中${NC} (PeerID=${IPFS_ID}...)"
else
    echo -e "${RED}❌ 未运行${NC}"
fi

# Check Backend
echo -n "  Backend:         "
if curl -s http://localhost:8000/api/config >/dev/null 2>&1; then
    echo -e "${GREEN}✅ 运行中${NC} (http://localhost:8000)"
else
    echo -e "${RED}❌ 未运行${NC}"
fi

# Check Frontend
echo -n "  Frontend:        "
if curl -s http://localhost:5173 >/dev/null 2>&1; then
    echo -e "${GREEN}✅ 运行中${NC} (http://localhost:5173)"
else
    echo -e "${RED}❌ 未运行${NC}"
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
