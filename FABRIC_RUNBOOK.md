# Fabric Runbook（evidence 链码 + Merkle 批量上链）

本手册对应当前仓库实际实现：
- 链码：`chaincode/chaincode.go`（`evidence`）
- Web 流程：`web_app.py` 自动执行 Merkle 批量上链（调用 `CreateEvidenceBatch`）
- 脚本流程：`anchor_to_fabric.py` 单条证据上链（调用 `CreateEvidence`）

## 1. 启动 Fabric 网络并部署 evidence 链码

```bash
cd ~/projects/fabric-samples/test-network
./network.sh down
./network.sh up createChannel -c mychannel -ca
./network.sh deployCC -ccn evidence -ccp /ABS/PATH/TO/CCTV-W-FABRIC-main/chaincode -ccl go
```

说明：
- `-ccn` 必须是 `evidence`
- `-ccp` 必须指向本仓库的 `chaincode` 目录

## 2. 配置项目运行参数

在项目根目录创建 `.env`（可从 `.env.example` 复制）：

```bash
cd /ABS/PATH/TO/CCTV-W-FABRIC-main
cp .env.example .env
```

最少需要确认以下参数：

```dotenv
FABRIC_SAMPLES_PATH=~/projects/fabric-samples
CHANNEL_NAME=mychannel
CHAINCODE_NAME=evidence
EVIDENCE_DIR=evidences
VIDEO_SOURCE=https://cctv1.kctmc.nat.gov.tw/6e559e58/
```

## 3A. Web 模式（推荐）：自动 Merkle 批量上链

```bash
cd /ABS/PATH/TO/CCTV-W-FABRIC-main
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn web_app:app --host 0.0.0.0 --port 8000
```

运行后：
- 检测闭环会自动生成 `event_*.json/.jpg`
- 在时间窗内聚合证据哈希，构建 Merkle Tree
- 调用链码 `CreateEvidenceBatch` 上链 `merkle_root`

## 3B. 脚本模式：单条证据上链

```bash
cd /ABS/PATH/TO/CCTV-W-FABRIC-main
source venv/bin/activate
python3 anchor_to_fabric.py --dry-run --limit 5
python3 anchor_to_fabric.py --limit 20
```

说明：
- 脚本模式调用 `CreateEvidence`
- 适合对已有 `evidences/event_*.json` 批量补链

## 4. 查询链上数据

先设置 Fabric CLI 环境：

```bash
cd ~/projects/fabric-samples
export PATH=$PWD/bin:$PATH
export FABRIC_CFG_PATH=$PWD/config
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID=Org1MSP
export CORE_PEER_ADDRESS=localhost:7051
export CORE_PEER_TLS_ROOTCERT_FILE=$PWD/test-network/organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=$PWD/test-network/organizations/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp
```

查询单个事件（`ReadEvidence`）：

```bash
peer chaincode query -C mychannel -n evidence -c '{"function":"ReadEvidence","Args":["event_xxx"]}'
```

查询 batch（`ReadEvidence`）：

```bash
peer chaincode query -C mychannel -n evidence -c '{"function":"ReadEvidence","Args":["batch_xxx"]}'
```

查询历史（`GetHistoryForKey`）：

```bash
peer chaincode query -C mychannel -n evidence -c '{"function":"GetHistoryForKey","Args":["event_xxx"]}'
```

## 5. 验真

命令行验真：

```bash
python3 verify_evidence.py event_xxx
```

Web API 验真：

```bash
curl -X POST "http://127.0.0.1:8000/api/verify/event_xxx"
```

Web API 历史：

```bash
curl "http://127.0.0.1:8000/api/history/event_xxx"
```
