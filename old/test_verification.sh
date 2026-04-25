#!/bin/bash
# GOP 验证功能快速测试脚本

set -e

echo "=========================================="
echo "GOP 验证功能测试"
echo "=========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. Go 单元测试
echo -e "${YELLOW}[1/3] 运行 Go 单元测试...${NC}"
cd chaincode
if go test -v -run TestVerifyAnchor 2>&1 | grep -q "PASS"; then
    echo -e "${GREEN}✓ Go 单元测试通过${NC}"
else
    echo -e "${RED}✗ Go 单元测试失败${NC}"
    exit 1
fi
cd ..
echo ""

# 2. 检查 Fabric 网络
echo -e "${YELLOW}[2/3] 检查 Fabric 网络状态...${NC}"
if docker ps | grep -q "peer0.org1.example.com"; then
    echo -e "${GREEN}✓ Fabric 网络运行中${NC}"
else
    echo -e "${RED}✗ Fabric 网络未运行${NC}"
    echo "请先启动 Fabric 网络："
    echo "  cd ~/projects/fabric-samples/test-network"
    echo "  ./network.sh up createChannel -c mychannel"
    echo "  ./network.sh deployCC -ccn evidence -ccp $(pwd)/chaincode -ccl go"
    exit 1
fi
echo ""

# 3. 检查 MinIO
echo -e "${YELLOW}[3/3] 检查 MinIO 服务...${NC}"
if curl -s http://localhost:9000/minio/health/live > /dev/null 2>&1; then
    echo -e "${GREEN}✓ MinIO 服务运行中${NC}"
else
    echo -e "${RED}✗ MinIO 服务未运行${NC}"
    echo "请先启动 MinIO："
    echo "  docker run -d -p 9000:9000 -p 9001:9001 --name minio \\"
    echo "    -e MINIO_ROOT_USER=minioadmin -e MINIO_ROOT_PASSWORD=minioadmin \\"
    echo "    minio/minio server /data --console-address ':9001'"
    exit 1
fi
echo ""

# 4. 运行 Python 集成测试
echo -e "${YELLOW}运行 Python 集成测试...${NC}"
echo "这可能需要 15-30 秒..."
echo ""

if pytest tests/test_gop_verification_e2e.py -v -s; then
    echo ""
    echo -e "${GREEN}=========================================="
    echo "✓ 所有测试通过！"
    echo "==========================================${NC}"
else
    echo ""
    echo -e "${RED}=========================================="
    echo "✗ 测试失败"
    echo "==========================================${NC}"
    exit 1
fi
