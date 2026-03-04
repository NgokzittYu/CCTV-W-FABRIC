# Changelog

## 2026-03-04

### Added

- 阶段三链码能力：
  - Org1/Org2/Org3 方法级 ACL（`requireMSP`）
  - `CreateEvidenceBatch` 设备签名字段与验签校验
  - `RectificationOrder` 工作流（创建/提交/确认）
  - `ExportAuditTrail(batchID)` 审计导出
  - PDC 接口：`PutRawEvidencePrivate` / `GetRawEvidencePrivate` / `GetRawEvidenceHash`
- PDC 配置文件：`chaincode/collections_config.json`
- 阶段三脚本：
  - `scripts/stage3_setup_network.sh`
  - `scripts/stage3_verify.sh`
- 设备签名配置项：
  - `ORG3_*` 网络配置
  - `DEVICE_CERT_PATH` / `DEVICE_KEY_PATH` / `DEVICE_SIGN_ALGO` / `DEVICE_SIGNATURE_REQUIRED`
- 离线补链脚本增强：
  - `anchor_to_fabric.py` 新增 `--mode batch` 签名批量上链
  - 新增 `--put-private` 与 `--private-use-transient` 私有数据写入能力

### Changed

- Web 批量上链流程改为强制附带设备签名参数（默认 `DEVICE_SIGNATURE_REQUIRED=true`）
- 运行文档更新为阶段三命令（3 Org、`-ccep`、`-cccg`）
- `PutRawEvidencePrivate` 支持可选 transient 负载（当 `imageBase64` 参数为空时）

## 2026-03-03

### Added

- 事件聚合状态机（`pending -> confirmed -> closed`）
- 按 `class + IoU` 的跨帧目标聚合逻辑
- 丢失帧关闭机制（减少单帧噪声上链）
- Merkle 批量上链能力（60 秒窗口）
- Merkle proof 生成与本地持久化（每事件）
- 链码 `CreateEvidenceBatch(...)`
- 链码 `GetHistoryForKey(...)`
- Web API：`GET /api/history/{event_id}`
- 前端弹窗历史时间线展示
- 前端按 `batch_id` 去重展示卡片（避免一批事件刷出大量重复“区块”）

### Changed

- 上链策略从“单事件单交易”升级为“批量 root 上链 + 事件 proof 验真”
- 验证逻辑升级为 Merkle proof 验证
- 哈希标准化逻辑统一：排除 `_anchor`、`_merkle`、`evidence_hash`、`evidence_hash_list` 字段

### Fixed

- 修复 proof 验证 `Mismatch`：由哈希字段口径不一致导致
- 修复页面观感问题：同一批次事件不再重复新增区块卡

### Notes

- 旧事件可能因历史口径差异出现验证不一致，建议以修复后新生成事件为准。
