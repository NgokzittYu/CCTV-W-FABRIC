# Changelog

## 2026-03-04 (代码工程化重构)

### Added
- 新增 `services/` 模块目录，实现职责分离：
  - `services/merkle_utils.py` - Merkle Tree 构建和验证 (~60 行)
  - `services/crypto_utils.py` - 加密哈希和设备签名 (~120 行)
  - `services/fabric_client.py` - Fabric 链码交互封装 (~170 行)
  - `services/event_aggregator.py` - 事件聚合引擎 (~230 行)
  - `services/detection_service.py` - 检测循环和视频流 (~270 行)
  - `services/workorder_service.py` - 工单和审计业务逻辑 (~220 行)
- 新增测试目录 `tests/`：
  - `test_merkle_utils.py` - Merkle 工具测试
  - `test_crypto_utils.py` - 加密工具测试
  - `test_event_aggregator.py` - 事件聚合测试

### Changed
- `web_app.py` 重构：从 1399 行精简到 330 行
  - 移除所有重复的工具函数
  - 只保留路由定义和启动逻辑
  - 所有业务逻辑调用 services 模块
- `anchor_to_fabric.py` 重构：从 837 行精简
  - 移除 6 类重复函数（Merkle、加密、签名、Fabric 交互等）
  - 统一使用 services 模块

### Fixed
- **FastAPI 异步请求处理错误** (`web_app.py`)
  - `api_create_workorder()` 改为 `async def`，使用 `await request.json()`
  - `api_submit_rectification()` 改为 `async def`，使用 `await request.json()`
  - `api_confirm_rectification()` 改为 `async def`，使用 `await request.json()`
- **缺失导入** (`web_app.py`)
  - 添加 `from services.merkle_utils import apply_merkle_proof`
  - 添加 `from services.workorder_service import export_audit_trail`
- **语法错误** (`services/workorder_service.py:147`)
  - 修复 `.res()` → `.resolve()`
- **缺失方法** (`services/event_aggregator.py`)
  - 添加 `update(boxes, class_names)` 方法处理 YOLO 检测结果
- **未使用的导入清理** (`web_app.py`)
  - 移除 `datetime`, `time`, `Any` 等未使用导入

### Optimized
- 消除代码重复：`web_app.py` 和 `anchor_to_fabric.py` 之间的重复函数
- 代码总行数从 ~3600 行减少到 ~2000 行 (减少 44%)
- 模块职责更清晰，符合单一职责原则
- 提高代码复用性和可维护性

## 2026-03-04 (阶段四)

### Added

- 工单管理 REST API：
  - `POST /api/workorder/create` - 创建整改工单（Org2）
  - `POST /api/workorder/{order_id}/rectify` - 提交整改证明（Org1）
  - `POST /api/workorder/{order_id}/confirm` - 确认/驳回整改（Org2）
  - `GET /api/workorder/overdue` - 查询超期工单
  - `GET /api/workorder/{order_id}` - 获取工单详情
- Web UI 工单管理页面（`/workorder`）：
  - 工单列表展示（表格、筛选、搜索）
  - 工单详情模态框（完整信息、状态历史）
  - 创建工单表单（违规ID、描述、责任方、截止日期）
  - 提交整改模态框（整改证明、附件）
  - 确认整改模态框（审核意见、通过/驳回）
  - 状态可视化（颜色标识：待整改/待确认/已关闭/已驳回）
  - 超期工单自动标记
- 角色切换和权限控制：
  - 三组织角色选择器（Org1/Org2/Org3）
  - 基于角色的动态权限控制
  - 角色持久化（localStorage）
  - 角色切换通知提示
- 审计报告导出和验证（`/audit`）：
  - `GET /api/audit/export` - 导出审计报告
  - 报告预览功能（批次信息、事件列表、工单列表）
  - JSON 格式导出（可下载）
  - 报告签名生成和验证
- 违规事件自动触发工单机制：
  - 自动触发逻辑（批次事件 ≥5 自动创建工单）
  - 系统配置页面（`/config`）
  - 启用/禁用开关
  - 触发规则管理（违规等级、责任组织、截止天数）
  - `GET /api/config/auto-workorder` - 获取配置
  - `POST /api/config/auto-workorder` - 更新配置
- 新增页面路由：
  - `/workorder` - 工单管理
  - `/audit` - 审计报告
  - `/config` - 系统配置
- 文档：
  - `PHASE4_SUMMARY.md` - 阶段四完整实施总结
  - `QUICKSTART_PHASE4.md` - 快速启动指南

### Changed

- 主页导航栏添加角色选择器和页面链接
- 工单管理页面根据角色动态显示操作按钮
- 批次锚定成功后自动触发工单创建（可配置）

### Notes

- 工单操作需要 2-3 秒链码响应时间
- 前端权限控制为 UI 层，真正权限由链码强制执行
- 自动触发工单默认启用，可在配置页面关闭

## 2026-03-04 (阶段三)

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
