# Fabric Runbook（evidence 链码 + Merkle 批量上链）

本手册对应当前仓库实际实现：
- 链码：`chaincode/chaincode.go`（`evidence`）
- Web 流程：`web_app.py` 自动执行 Merkle 批量上链（调用 `CreateEvidenceBatch`）
- 脚本流程：`anchor_to_fabric.py` 支持单条上链（`CreateEvidence`）与批量签名上链（`CreateEvidenceBatch`）

## 1. 启动 3 Org 网络并部署 evidence 链码

推荐直接使用仓库脚本拉起 3 Org：

```bash
cd /ABS/PATH/TO/CCTV-W-FABRIC-main
./scripts/stage3_setup_network.sh
```

然后部署链码（带背书策略 + PDC）：

```bash
cd ~/projects/fabric-samples/test-network
./network.sh deployCC \
  -ccn evidence \
  -ccp /ABS/PATH/TO/CCTV-W-FABRIC-main/chaincode \
  -ccl go \
  -ccep "AND('Org1MSP.peer','Org2MSP.peer')" \
  -cccg /ABS/PATH/TO/CCTV-W-FABRIC-main/chaincode/collections_config.json
```

说明：
- `-ccn` 必须是 `evidence`
- `-ccp` 必须指向本仓库的 `chaincode` 目录
- `-ccep` 固定为阶段三写交易背书策略
- `-cccg` 指向 `collections_config.json`（PDC）

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
DEVICE_CERT_PATH=device_keys/default/cert.pem
DEVICE_KEY_PATH=device_keys/default/key.pem
DEVICE_SIGN_ALGO=ECDSA_SHA256
DEVICE_SIGNATURE_REQUIRED=true
```

## 3A. Web 模式（推荐）：自动 Merkle 批量上链

```bash
cd /ABS/PATH/TO/CCTV-W-FABRIC-main
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m uvicorn web_app:app --host 0.0.0.0 --port 8000
```

如需 WebSocket：

```bash
pip install "uvicorn[standard]"
```

运行后：
- 检测闭环会自动生成 `event_*.json/.jpg`
- 在时间窗内聚合证据哈希，构建 Merkle Tree
- 调用链码 `CreateEvidenceBatch` 上链（新签名见下）

`CreateEvidenceBatch` 当前签名：

```text
CreateEvidenceBatch(
  batchID,
  cameraId,
  merkleRoot,
  windowStart,
  windowEnd,
  eventIDsJSON,
  eventHashesJSON,
  deviceCertPEM,
  signatureB64,
  payloadHashHex
)
```

说明：
- `eventIDsJSON`：事件 ID 数组（如 `["event_a","event_b"]`）
- `eventHashesJSON`：对应顺序的 leaf hash 数组（如 `["<leafA>","<leafB>"]`）
- `deviceCertPEM`：设备证书 PEM（应为 Org1 设备证书）
- `signatureB64`：设备私钥对 canonical batch payload 的 ECDSA 签名（base64）
- `payloadHashHex`：canonical batch payload 的 SHA256 十六进制摘要
- batch 主键（`batchID`）存储为 `MerkleBatch` 结构；每个事件键的 `evidenceHash` 存储 leaf hash

## 3B. 脚本模式：离线补链（单条 / 批量签名）

```bash
cd /ABS/PATH/TO/CCTV-W-FABRIC-main
source venv/bin/activate

# 单条模式（兼容旧流程）
python3 anchor_to_fabric.py --mode single --dry-run --limit 5
python3 anchor_to_fabric.py --mode single --limit 20

# 批量签名模式（阶段三）
python3 anchor_to_fabric.py --mode batch --batch-size 20 --limit 100

# 批量签名 + PDC 写入（transient）
python3 anchor_to_fabric.py --mode batch --put-private --private-use-transient --batch-size 20 --limit 100
```

说明：
- `--mode batch` 会调用 `CreateEvidenceBatch`，并附带 `deviceCertPEM/signatureB64/payloadHashHex`
- `--put-private` 会调用 `PutRawEvidencePrivate`
- `--private-use-transient` 会通过 `--transient` 发送原图，避免超长命令行参数

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

链上 Merkle 验真（`VerifyEvent`）：

```bash
peer chaincode query -C mychannel -n evidence -c '{"function":"VerifyEvent","Args":["batch_xxx","<leaf_hash>","[{\"position\":\"right\",\"hash\":\"<sibling_hash>\"}]","<merkle_root>"]}'
```

审计导出（`ExportAuditTrail`）：

```bash
peer chaincode query -C mychannel -n evidence -c '{"function":"ExportAuditTrail","Args":["batch_xxx"]}'

# 或使用脚本入口
python3 anchor_to_fabric.py --export-audit-batch batch_xxx
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

说明：
- merkle 模式下，`/api/verify/{event_id}` 会调用链码 `VerifyEvent`
- direct 模式（非批处理）仍兼容 `VerifyEvidence` / `ReadEvidence` 对比

Web API 历史：

```bash
curl "http://127.0.0.1:8000/api/history/event_xxx"
```

## 6. 阶段三基线验收脚本

```bash
cd /ABS/PATH/TO/CCTV-W-FABRIC-main
./scripts/stage3_verify.sh
```
