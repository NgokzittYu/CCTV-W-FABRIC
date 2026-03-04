# EXECUTE INSTRUCTIONS（与当前代码一致）

本文档以当前仓库实现为准：`evidence` 链码 + Web 端 Merkle 批量上链。

## 1) 部署/重部署链码

```bash
cd ~/projects/fabric-samples/test-network
./network.sh down
./network.sh up createChannel -c mychannel -ca
./network.sh deployCC -ccn evidence -ccp /ABS/PATH/TO/CCTV-W-FABRIC-main/chaincode -ccl go
```

注意：
- 本仓库 `chaincode` 目录已包含 `go.mod`/`go.sum`，不需要再执行 `go mod init`。

## 2) 配置环境变量

```bash
cd /ABS/PATH/TO/CCTV-W-FABRIC-main
cp .env.example .env
```

至少确认以下键值正确：

```dotenv
FABRIC_SAMPLES_PATH=~/projects/fabric-samples
CHANNEL_NAME=mychannel
CHAINCODE_NAME=evidence
EVIDENCE_DIR=evidences
VIDEO_SOURCE=https://cctv1.kctmc.nat.gov.tw/6e559e58/
```

## 3) 安装依赖并启动 Web 服务

```bash
cd /ABS/PATH/TO/CCTV-W-FABRIC-main
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn web_app:app --host 0.0.0.0 --port 8000
```

浏览器访问：`http://127.0.0.1:8000`

## 4) 触发上链并验真

系统会在事件关闭后自动写入本地证据并进入 Merkle 批次，随后调用 `CreateEvidenceBatch` 上链。

你可以使用以下命令验证：

```bash
# 验真（Web API）
curl -X POST "http://127.0.0.1:8000/api/verify/event_xxx"

# 查询历史（Web API）
curl "http://127.0.0.1:8000/api/history/event_xxx"

# 本地脚本验真
python3 verify_evidence.py event_xxx
```

## 5) 可选：离线脚本单条上链

```bash
python3 anchor_to_fabric.py --dry-run --limit 5
python3 anchor_to_fabric.py --limit 10
```

该模式调用链码 `CreateEvidence`，不会进行 Merkle 批处理。
