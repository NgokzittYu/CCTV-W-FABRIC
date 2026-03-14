# Changelog

## 2026-03-14 (GOP 级别 Merkle 锚点上链)

### Added

- **Chaincode 锚点方法** (`chaincode/chaincode.go`)
  - `AnchorRecord` 结构体：链上精简存储 `{EpochId, MerkleRoot, Timestamp, DeviceCount, GatewayId}`，不存 GOP 哈希列表
  - `Anchor(epochId, merkleRoot, timestamp, deviceCount)` — 提交 GOP 级别 Merkle 根锚点
    - GatewayId 从 `ctx.GetClientIdentity().GetID()` 的 SHA-256 截断前 8 字节派生（16 字符十六进制），防止客户端冒充身份
    - 验证 MerkleRoot 为 64 字符合法十六进制
    - 拒绝重复 epoch 提交
    - 按 gateway 强制时间戳单调递增（防回退攻击）
    - 触发 `AnchorEvent` 链上事件
  - `QueryAnchor(epochId)` — 按 epoch ID 查询单条锚点
  - `QueryAnchorsByRange(startKey, endKey)` — 范围查询，利用 `anchor:{epoch_id}` 键的字典序
  - 新增常量：`anchorPrefix`、`anchorLastTsPrefix`
  - 新增辅助函数：`deriveGatewayId()`、`anchorKey()`、`anchorLastTsKey()`

- **Python 客户端函数** (`services/fabric_client.py`)
  - `submit_anchor()` — 调用 chaincode `Anchor` 方法，复用现有 `invoke_chaincode()`
  - `query_anchor()` — 调用 chaincode `QueryAnchor` 方法，复用现有 `query_chaincode()`
  - `query_anchors_by_range()` — 调用 chaincode `QueryAnchorsByRange` 方法

- **集成测试** (`tests/test_anchor_integration.py`)
  - 提交+查询端到端验证（Merkle 根一致性）
  - 重复 epoch 提交拒绝测试
  - 时间戳回退拒绝测试
  - 范围查询测试

### Notes

- 链上只存 MerkleRoot，GOP 哈希列表和完整 Merkle 树 JSON 存 MinIO，保持链上存储精简
- GatewayId 不由客户端传入，从调用者 x509 证书身份派生
- 键设计：`anchor:{epoch_id}` 直接作为存储 key，无需解析重建组���键
- AnchorService（epoch 窗口管理、后台线程 flush）留到 Step 9 实现
- 集成测试需要 Fabric test-network 运行：`python -m pytest tests/test_anchor_integration.py -v`

---

## 2026-03-14 (Merkle Tree 类封装 + 序列化)

### Added

- **MerkleTree 类** (`services/merkle_utils.py`)
  - `MerkleTree(leaves: List[str])`：从十六进制哈希列表构建完整 Merkle 树
  - **Power-of-2 填充**：叶子数量不足 2 的幂次时，用最后一个叶子重复 padding
  - `root: str`：根哈希（hex 字符串）
  - `get_proof(leaf_index) -> List[dict]`：生成指定叶子的 Merkle Proof
  - `verify_proof(leaf_hash, proof, root) -> bool`：静态方法，验证 proof 是否与 root 匹配
  - `to_json() -> str`：序列化完整树结构为 JSON（含所有层级）
  - `from_json(json_str) -> MerkleTree`：从 JSON 反序列化，无需重建树
  - Proof 格式与现有 `apply_merkle_proof` 完全一致：`{"hash": hex, "position": "left"|"right"}`，position 表示 sibling 位置
  - 纯标准库实现（hashlib + json），无第三方依赖

- **MerkleTree 单元测试** (`tests/test_merkle_utils.py`)
  - `test_merkle_tree_single_leaf` — 单叶子边界：root == 叶子，proof 为空
  - `test_merkle_tree_two_leaves` — 双叶子：最简非平凡树
  - `test_merkle_tree_four_leaves` — 4 叶子（2 的幂次），所有 proof 验证通过
  - `test_merkle_tree_five_leaves_padding` — 5 叶子，验证 padding 到 8 + 所有 proof
  - `test_merkle_tree_tampered_leaf` — 篡改叶子后验证失败
  - `test_merkle_tree_json_roundtrip` — 6 叶子，序列化/反序列化往返一致

- **集成测试** (`test_merkle_tree_integration.py`)
  - 合成 7 个 GOP SHA-256 哈希构建 Merkle 树
  - 逐 GOP 生成并验证 proof
  - JSON 往返测试
  - 篡改检测测试

### Notes

- 现有三个函数（`sha256_digest`、`build_merkle_root_and_proofs`、`apply_merkle_proof`）未做任何修改，下游调用方不受影响
- `MerkleTree` 与现有函数的区别：预填充叶子到 2 的幂次（现有函数是逐层处理奇数节点），适用于需要完整树结构序列化的场景

---

## 2026-03-13 (MinIO 分布式对象存储集成)

### Added

- **MinIO 存储服务** (`services/minio_storage.py`)
  - `VideoStorage` 类：GOP 分片的分布式对象存储管理
  - **性能优化设计**：
    - 内存 CID 索引（`self._cid_index`）：O(1) 查找，避免遍历所有对象
    - 时间戳路径编码（`{device_id}/t_{timestamp}/{cid}.h264`）：零额外网络请求的时间范围筛选
    - 可选索引持久化（`save_cid_index` / `load_cid_index`）：进程重启后恢复索引
  - 核心方法：
    - `upload_gop(device_id, gop)` → CID：上传 GOP 分片，返回 SHA-256 CID
    - `download_gop(device_id, cid)` → bytes：通过 CID 快速下载
    - `list_gops(device_id, start_time, end_time)` → List[dict]：按时间范围列出 GOP
    - `upload_json` / `download_json`：JSON 文件上传下载
  - 自动创建 bucket（默认 `video-evidence`）
  - 元数据存储：gop_id、timestamp、sha256_hash

- **MinIO 配置** (`config.py`)
  - 新增配置项：`minio_endpoint`、`minio_access_key`、`minio_secret_key`、`minio_bucket_name`、`minio_secure`
  - 默认值：`localhost:9000`、`minioadmin/minioadmin`、bucket `video-evidence`
  - 支持环境变量覆盖

- **测试脚本** (`test_minio_storage.py`)
  - 完整的上传/下载/验证流程
  - SHA-256 一致性验证
  - 内存索引性能测试
  - 时间范围查询测试
  - JSON 上传下载测试
  - 索引持久化测试
  - 性能指标统计（上传/下载时间）

- **新增依赖** (`requirements.txt`)
  - 添加 `minio`（MinIO Python SDK）

### Technical Details

- **对象路径格式**：`{device_id}/t_{timestamp_int}/{cid}.h264`
  - 时间戳编码进路径，支持高效的时间范围筛选
  - CID 使用 GOP 的 SHA-256 hash（由 `gop_splitter.py` 预计算）
- **索引机制**：内存 dict 映射 CID → object_name，fallback 到遍历查找（兼容外部上传）
- **并行存储**：与现有本地文件系统（`evidences/` 目录）并存，不影响现有逻辑

### Notes

- MinIO 需通过 Docker 启动：`docker run -p 9000:9000 -p 9001:9001 minio/minio server /data --console-address ":9001"`
- 测试前需安装依赖：`pip install minio`
- 运行测试：`python test_minio_storage.py --file <视频文件路径>`

---

## 2026-03-13 (GOP 级别视频流切分模块)

### Added

- **GOP 切分模块** (`services/gop_splitter.py`)
  - `GOPData` 数据类：包含 `gop_id`、`raw_bytes`、`sha256_hash`、时间戳、`frame_count`、`byte_size`、`keyframe_frame`（BGR numpy array）
  - `GOPSplitter` 类：后台守护线程持续从实时 CCTV 流读取 packet，按 GOP 边界切分，通过 `on_gop` 回调传出
    - `start()` / `stop()` 控制生命周期
    - 断线自动重连（3 秒间隔），`gop_id` 重连后接续不重置
    - 根据 URL 协议动态设置 `av.open` options（RTSP 传 `rtsp_transport: tcp`，HTTP/HLS 不传）
  - `split_gops()` 离线函数：用于本地 MP4 文件分析（调试/测试）
  - **MJPEG intra-only 编码自动检测**：对 MJPEG 等每帧皆为关键帧的编码，按 `mjpeg_gop_size`（默认 25 帧 ≈ 1 秒）分组为逻辑 GOP；H.264/H.265 保持原有 keyframe 边界检测
  - **关键帧归属机制**：遇到新 keyframe 时先 decode 存为 `pending_keyframe`，再用上一次的 `pending_keyframe` 封闭上一个 GOP，确保每个 GOP 的 `keyframe_frame` 是自己的 I 帧
  - CLI 入口：`python -m services.gop_splitter [--stream URL | --file PATH] [--mjpeg-gop-size N]`
  - PTS 为 None 的防御处理

- **新增依赖** (`requirements.txt`)
  - 添加 `av`（PyAV）用于 packet 级别视频流访问

### Notes

- 该模块与现有 `detection_service.py` 完全并行，不修改现有检测流程
- `keyframe_frame` 输出为 BGR numpy array，下游可直接用于 pHash / YOLO，无需 JPEG 中转
- SHA-256 可复现仅适用于离线 MP4 模式；HLS 流因服务器端重新封装，两次拉取同一段的哈希可能不同，属预期行为

---

## 2026-03-05 (批次文件保存与恢复机制修复)

### Fixed

- **批次文件保存缺失** (`services/detection_service.py`)
  - `_anchor_batch` 方法新增批次文件保存逻辑
  - 批次文件保存到 `evidences/batches/{date}/{batch_id}.json`
  - 包含完整批次元数据：batch_id、merkle_root、tx_id、block_number、events 列表
  - 每个事件包含：event_id、evidence_hash、leaf_index、proof

- **批次列表排序错误** (`web_app.py`)
  - `/api/ledger/recent` 端点从按文件修改时间排序改为按区块号排序
  - 修复恢复的批次文件因创建时间新而显示在前的问题
  - 添加 `block_number is None` 检查，跳过无效批次文件

- **验证 API 增强** (`web_app.py`)
  - `/api/verify/{event_id}` 支持从批次文件获取 Merkle 证明
  - 当本地事件文件不存在时，自动搜索批次文件
  - 从批次文件重建 merkle_info 和 evidence_hash

- **批次详情 API 增强** (`web_app.py`)
  - `/api/batch/{batch_id}` 支持从区块链查询事件详情
  - 当本地事件文件缺失时，调用 `ReadEvidence` 链码查询
  - 正确提取事件类型（支持 top_class、event_type、type 字段）
  - 修复旧批次事件显示为 "UNKNOWN" 的问题

### Added

- **批次恢复工具** (`recover_batches.py`)
  - 从现有事件文件的 `_merkle` 和 `_anchor` 信息重建批次文件
  - 自动按 batch_id 分组事件
  - 按 leaf_index 排序事件
  - 恢复了 118 个丢失的批次文件

### Changed

- **网络重置**
  - 清理所有旧的证据文件和批次文件
  - 重建 Fabric 网络（3 个组织）
  - 重新部署 evidence 链码
  - 从区块 #8 开始记录新的证据批次

### Notes

- 批次文件现在会在每次批次上链后自动保存
- 验证功能支持本地事件文件缺失的场景
- 批次列表按区块号降序正确排序
- 系统从全新状态开始运行

---

## 2026-03-05 (报告签名验证：VerifyEvent 链上实现)

### Added

- **后端 API `POST /api/audit/verify`**（`web_app.py`）
  - 接收参数：`batchId`、`eventHash`（叶节点 hash）、`merkleProofJSON`（JSON 数组）、`merkleRoot`
  - 调用链码 `VerifyEvent`，在区块链上对 Merkle Proof 进行真实性验证
  - 返回 `{ verified: bool, batchId, message }`

- **前端验证区域重构**（`templates/audit.html`）
  - 验证表单从"报告ID + 签名"改为四字段（批次ID、事件Hash、Merkle Proof、Merkle Root），与链码 `VerifyEvent` 入参完全对齐
  - `verifyReport()` 删除 mock 逻辑（原 `signature.length > 32`），改为真实调用 `POST /api/audit/verify`
  - 验证按钮标注"链上验证"，明确区分本地和链上两种验证路径
  - `renderReportPreview()` 新增自动填充逻辑：预览报告时若首个事件含 `merkleProof` 字段，自动填入验证表单，方便一键验证

### Fixed

- **文档与代码不一致风险**：`PHASE4_COMPLETION_REPORT.md` 中标注为待办的"实现真实的报告签名验证"现已完成，前后端均调用链码而非 mock

---

## 2026-03-05 (功能修复：QueryOverdueOrders)

### Fixed

- **链码层 `QueryOverdueOrders` 功能缺口**（`chaincode/chaincode.go`）
  - 新增 `QueryOverdueOrders` 方法，遍历所有 `rectify:` 前缀的工单
  - 筛选条件：`Status == "OPEN"` 且 `Deadline > 0` 且 `now > Deadline`
  - 结果按截止日期升序排列（最紧迫的超期工单排最前）
  - ACL：Org1/Org2/Org3 均可查询（只读操作）
- **Python 服务层空壳实现**（`services/workorder_service.py`）
  - `query_overdue_workorders()` 从返回空列表改为调用链码 `QueryOverdueOrders`
  - 支持按 `org` 参数过滤（按 `assignedTo` 或 `createdBy` 筛选）
  - 支持分页（`page` / `limit` 参数）

### Added

- **链码单元测试**（`chaincode/chaincode_test.go`）
  - 新增 `mockStateIterator`：实现 `shim.StateQueryIteratorInterface`，支持 `GetStateByRange` 范围查询
  - 新增 `mockStub.GetStateByRange`：同时修复 `ExportAuditTrail` 测试的 stub 缺失问题
  - 新增 `TestQueryOverdueOrders`：覆盖 3 种边界情况
    - 已超期且 OPEN → 应出现在结果中
    - 未超期且 OPEN → 不应出现
    - 已超期但已 CONFIRMED → 不应出现



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
