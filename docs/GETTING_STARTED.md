# SecureLens: Getting Started Guide

本指南详细介绍了基于边缘AI与联盟链的监控视频防篡改解决方案（SecureLens）的安装、配置、API和测试流程。

有关项目的高层架构设计、VIF 算法解析等核心理论，请参考主页的 [README](../README.md)。

---

## 🚀 快速开始

### 环境要求

- **操作系统**：Linux / macOS
- **Python**：3.10+
- **Docker**：20.10+
- **Docker Compose**：1.29+
- **硬件**：建议8GB+ RAM，支持GPU加速（可选）

### 安装步骤

#### 1. 克隆项目

```bash
git clone https://github.com/NgokzittYu/CCTV-W-FABRIC.git
cd CCTV-W-FABRIC-main
```

#### 2. 安装 Python 依赖

```bash
# 创建虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

#### 3. 启动 IPFS 存储集群

```bash
# 启动 3 节点 IPFS Kubo 集群
docker compose -f docker-compose.ipfs.yml up -d

# 验证节点状态
docker compose -f docker-compose.ipfs.yml ps

# 访问 http://localhost:5001/webui 查看节点 WebUI
```

> 更多详细配置参见 [IPFS_SETUP.md](../IPFS_SETUP.md)

#### 4. 启动 Hyperledger Fabric 网络

```bash
cd fabric-samples/test-network

# 启动网络
./network.sh up createChannel -ca -s couchdb

# 部署智能合约
./network.sh deployCC -ccn cctv -ccp ../../chaincode -ccl go

cd ../..
```

#### 5. 配置环境变量

在项目根目录创建 `.env` 文件：

```bash
# IPFS 配置
IPFS_API_URL=http://localhost:5001
IPFS_GATEWAY_URL=http://localhost:8080
IPFS_PIN_ENABLED=true

# Fabric配置
FABRIC_SAMPLES_PATH=./fabric-samples
CHANNEL_NAME=mychannel
CHAINCODE_NAME=cctv

# AI模型配置
SEMANTIC_MODEL_PATH=yolov8n.pt
SEMANTIC_CONFIDENCE=0.5

# VIF 多模态特征融合配置选项
VIF_MODE=fusion                # 'off' | 'phash_only' | 'semantic_only' | 'fusion'
PHASH_MODE=legacy              # 'legacy' | 'deep'
ANCHOR_MODE=fixed              # 'fixed' | 'mab_ucb' | 'mab_thompson'
EIS_MODE=lite                  # 'lite' | 'full'
```

#### 6. 运行 Demo 与测试

```bash
# 启动 Demo Web 服务
VIF_MODE=fusion python demo/app.py
```
> 打开浏览器访问 `http://localhost:5001` 开始体验。

```bash
# 测试特定模块
python -m pytest tests/test_adaptive_anchor.py -v
python -m pytest tests/test_hierarchical_merkle.py -v

# VIF 多模态融合指纹测试
VIF_MODE=fusion python -m pytest tests/test_vif.py -v
```

---

## 🔧 API 文档

### 网关 API (Gateway)

#### 1. 提交 SegmentRoot 上报
```http
POST /report
Content-Type: application/json

{
  "device_id": "cam_001",
  "segment_root": "abc123d4e5f6...",
  "timestamp": "2024-03-16T10:30:00Z",
  "semantic_summaries": [
    "检测到3辆车",
    "检测到2个行人"
  ],
  "gop_count": 150
}
```

#### 2. 健康检查
```http
GET /health
```

### 智能合约 API (Chaincode)

#### 1. 存储 EpochRoot
```bash
peer chaincode invoke -C mychannel -n cctv \
  -c '{"function":"StoreEpochRoot","Args":["epoch_001","root_hash","signature"]}'
```

#### 2. 验证 Merkle 路径
```bash
peer chaincode query -C mychannel -n cctv \
  -c '{"function":"VerifyMerklePath","Args":["epoch_001","gop_hash","merkle_path"]}'
```

---

## 🔍 故障排查 (Troubleshooting)

### 1. IPFS 连接失败
- 检查 IPFS 容器状态：`docker compose -f docker-compose.ipfs.yml ps`
- 查看日志：`docker compose -f docker-compose.ipfs.yml logs ipfs-node0`
- 重启集群：`docker compose -f docker-compose.ipfs.yml restart`

### 2. Fabric 网络启动失败
- 清理旧网络：进入 `fabric-samples/test-network` 执行 `./network.sh down`
- 清理 Docker 卷：`docker volume prune`
- 重新启动：`./network.sh up createChannel -ca -s couchdb`

### 3. YOLO 模型加载失败
如果国内网络环境无法自动下载，可手动下载并放入根目录：
```bash
wget https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n.pt
```

### 4. GOP 切分或 PyAV 报错
- 检查系统是否安装了 `ffmpeg` (macOS: `brew install ffmpeg`)
- 确保 `av` 库正确安装：`pip install av`
