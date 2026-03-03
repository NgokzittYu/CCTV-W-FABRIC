# SecureLens CCTV -> Fabric 闭环系统

本项目实现了一个“视频检测 -> 证据哈希 -> 区块链锚定 -> 验真与追溯”的闭环，核心目标是让监控事件具备可验证、可追踪、可审计能力。

## 当前版本核心能力

- 事件聚合（降噪）
  - 连续 `N` 帧命中同一目标（`class + IoU`）后才确认事件
  - 事件状态机：`pending -> confirmed -> closed`
  - 目标丢失 `M` 帧后关闭事件
- Merkle 批量上链（降本）
  - 60 秒窗口内收集所有事件 `evidence_hash`
  - 构建 Merkle Tree，只上链 `merkle_root`（1 笔交易覆盖 N 个事件）
  - 本地保存每个事件的 Merkle proof（用于后续验真）
- 链上历史追溯（可审计）
  - 链码提供 `GetHistoryForKey(eventID)`，可查看 key 的所有历史版本
- Web 可视化
  - 实时画面（原始/检测）
  - 区块卡片流（已按 batch 去重展示）
  - 弹窗内直接查看验真结果与链上历史

## 主要文件

- Web 应用与实时流程：`web_app.py`
- Fabric 调用工具：`anchor_to_fabric.py`
- 本地验真脚本：`verify_evidence.py`
- 链码：`chaincode/chaincode.go`
- 前端模板：`templates/index.html`
- 证据目录：`evidences/`

## 快速开始

### 1. 部署/升级链码（必须）

```bash
cd ~/projects/fabric-samples/test-network
./network.sh deployCC -ccn evidence -ccp /Users/ngokzit/Documents/GeminiAntigravity/CCTV-W-FABRIC-main/chaincode -ccl go
```

如果是全新环境，可先执行：

```bash
./network.sh down
./network.sh up createChannel -c mychannel -ca
```

### 2. 启动 Web 服务

```bash
cd /Users/ngokzit/Documents/GeminiAntigravity/CCTV-W-FABRIC-main
source venv/bin/activate
uvicorn web_app:app --host 0.0.0.0 --port 8000
```

打开：`http://127.0.0.1:8000`

## 如何验证

### 页面内验证（推荐）

1. 点击任意事件卡片
2. 在弹窗查看：
   - `LOCAL FILE HASH`
   - `MERKLE ROOT FROM PROOF`
   - `ON-CHAIN IMMUTABLE HASH`
3. 显示 `Proof Verified · Match` 即验真通过
4. 在 `ON-CHAIN HISTORY` 查看历史版本

### API 验证

```bash
curl -X POST "http://127.0.0.1:8000/api/verify/<event_id>"
curl "http://127.0.0.1:8000/api/history/<event_id>"
```

## 文档

- 执行指南：[`EXECUTE_INSTRUCTIONS.md`](EXECUTE_INSTRUCTIONS.md)
- Fabric 操作手册：[`FABRIC_RUNBOOK.md`](FABRIC_RUNBOOK.md)
- 更新日志：[`CHANGELOG.md`](CHANGELOG.md)

## FAQ（保留）

### Windows/WSL 启动 Fabric 时端口冲突（如 7054）

如果报错类似：

```text
Ports are not available: exposing port TCP 0.0.0.0:7054 ...
```

可在 Windows 管理员终端执行：

```powershell
net stop winnat
net start winnat
```

然后回到 WSL 重新拉起网络。
