# EXECUTE INSTRUCTIONS（阶段三）

本文档以当前仓库实现为准：`evidence` 链码 + 3 Org + 设备签名 + PDC。

## 1) 启动 3 Org 网络

```bash
cd /ABS/PATH/TO/CCTV-W-FABRIC-main
./scripts/stage3_setup_network.sh
```

脚本会完成：
- `network.sh down`
- `network.sh up createChannel -c mychannel -ca`
- `addOrg3.sh up -c mychannel -ca`
- Org3 `peer channel getinfo` 验证

## 2) 部署链码（带背书策略与 PDC）

```bash
cd ~/projects/fabric-samples/test-network
./network.sh deployCC \
  -ccn evidence \
  -ccp /ABS/PATH/TO/CCTV-W-FABRIC-main/chaincode \
  -ccl go \
  -ccep "AND('Org1MSP.peer','Org2MSP.peer')" \
  -cccg /ABS/PATH/TO/CCTV-W-FABRIC-main/chaincode/collections_config.json
```

## 3) 配置环境变量

```bash
cd /ABS/PATH/TO/CCTV-W-FABRIC-main
cp -n .env.example .env
```

至少确认以下项：

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

## 4) 安装依赖并启动 Web

```bash
cd /ABS/PATH/TO/CCTV-W-FABRIC-main
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m uvicorn web_app:app --host 0.0.0.0 --port 8000
```

可选（WebSocket 支持）：

```bash
python -m pip install "uvicorn[standard]"
```

浏览器访问：`http://127.0.0.1:8000`

## 5) 触发上链并验真

系统会在事件关闭后自动生成 Merkle batch 并调用：

`CreateEvidenceBatch(batchID, cameraId, merkleRoot, windowStart, windowEnd, eventIDsJSON, eventHashesJSON, deviceCertPEM, signatureB64, payloadHashHex)`

验证命令：

```bash
# 验真（Web API）
curl -X POST "http://127.0.0.1:8000/api/verify/event_xxx"

# 查询历史（Web API）
curl "http://127.0.0.1:8000/api/history/event_xxx"

# 本地脚本验真
python3 verify_evidence.py event_xxx
```

## 6) 离线补链（可选）

```bash
cd /ABS/PATH/TO/CCTV-W-FABRIC-main
source venv/bin/activate

# 单条模式（旧流程兼容）
python3 anchor_to_fabric.py --mode single --dry-run --limit 5
python3 anchor_to_fabric.py --mode single --limit 20

# 批量签名模式（阶段三）
python3 anchor_to_fabric.py --mode batch --batch-size 20 --limit 100

# 批量签名 + PDC 原图写入（transient）
python3 anchor_to_fabric.py --mode batch --put-private --private-use-transient --batch-size 20 --limit 100
```

## 7) 阶段三基线验证

```bash
cd /ABS/PATH/TO/CCTV-W-FABRIC-main
./scripts/stage3_verify.sh
```

预期：
- Org1 单背书 invoke 失败
- Org1+Org2 invoke 成功
- Org3 查询成功
