# 人工智能实践赛作品报告大纲初稿

## 0. 作品定位

**建议作品名称**：SecureLens：基于哈希校验与 AI 视觉指纹的监控视频篡改检测及可信取证系统

**参赛小类**：人工智能应用类 / 人工智能实践赛

**核心叙事**：

本作品面向智能城市监控视频在传输、存储和取证过程中可能发生的篡改、替换、重压缩和格式转换问题，提出一套“密码学哈希优先、AI 视觉指纹补充判定”的分层视频完整性验证方案。系统首先使用 SHA-256 对视频 GOP 片段进行字节级精确校验；只有当哈希不一致时，才进入基于 VIF v4 的内容级宽容验证，区分合法转码与高危疑似篡改。随后通过 Merkle 树、IPFS 内容寻址存储和 Hyperledger Fabric 联盟链锚定，形成可追溯、可验证、可审计的视频证据链。

**必须坚持的表达口径**：

- 不说“VIF 替代哈希”，而说“哈希负责精确一致性，VIF 负责哈希失配后的内容级解释”。
- 不把 `TAMPERED_SUSPECT` 写成司法终判，而写成“高危疑似篡改，需要进入后续审计或人工复核”。
- 不把项目包装成硬件物联网系统，而包装为“智能城市视频 AI 取证软件系统”。
- 不把区块链作为 AI 之外的噱头，而写成“AI 验证结果可信留痕与证据链管理基础设施”。

## 1. 项目结构分析

### 1.1 AI 视频分析与完整性验证层

对应目录与文件：

- `services/gop_splitter.py`：视频 GOP 切分，构造 GOP 级证据单元，支持关键帧和采样帧提取。
- `services/vif.py`：VIF v4 视觉完整性指纹，使用 CNN 视觉特征、Mean Pooling 和 LSH 输出 256-bit 指纹。
- `services/perceptual_hash.py`：深度感知哈希和视觉特征提取，作为 VIF 的底层视觉特征来源。
- `services/tri_state_verifier.py`：三态验证逻辑，先比较 SHA-256，再在哈希不一致时比较 VIF。
- `services/semantic_fingerprint.py`：YOLO 语义信息提取，生成对象统计与语义哈希。
- `services/detection_service.py`：实时检测、视频流处理、GOP 锚定管理。
- `services/adaptive_anchor.py`：事件重要性评分 EIS，结合目标数量、运动特征、异常程度生成锚定策略输入。
- `services/mab_anchor.py`：UCB1 / Thompson Sampling 多臂老虎机自适应锚定策略。

报告写法：这一层是第 3 章“技术方案”的主体，重点讲 AI 如何参与视频完整性验证、事件识别和自适应决策。

### 1.2 可信存证与审计层

对应目录与文件：

- `services/merkle_utils.py`：Merkle Tree、三级 Merkle 结构、Epoch Merkle 树、Merkle Proof 验证。
- `services/ipfs_storage.py`：IPFS 内容寻址存储，保存 GOP 分片、语义 JSON、Merkle 结构和回放索引。
- `services/fabric_client.py`：调用 Hyperledger Fabric 链码，提交 Anchor、查询 Anchor、验证 Anchor。
- `chaincode/chaincode.go`：Fabric 智能合约，包含证据创建、批量存证、Merkle 证明验证、整改工单、审计导出等能力。
- `services/crypto_utils.py`：证据哈希规范化、设备签名材料构造、ECDSA 签名。
- `services/gateway_service.py`：多设备 SegmentRoot 聚合，构建 Epoch Merkle Tree。
- `services/workorder_service.py`：整改工单、审计导出和多组织协作流程。

报告写法：这一层放在第 3 章后半部分和第 4 章系统实现中，说明 AI 识别出的证据如何被可信存储、上链和验证。

### 1.3 后端服务与 API 层

对应目录与文件：

- `demo2/server.py`：FastAPI 后端，提供健康检查、视频上传、证据验证、导出样本验证、IPFS 回放、锚定统计、工单与审计 API。
- `config.py`：统一配置，包括 Fabric、IPFS、YOLO 模型、VIF 版本、GOP 队列、摄像头源等。
- `services/video_store.py`：SQLite 视频证据索引、GOP 记录、验证历史。

可写入报告的主要 API：

- `POST /api/video/upload`：上传视频并生成证据。
- `POST /api/video/verify`：上传待验视频并进行逐 GOP 三态验证。
- `POST /api/video/verify/export`：验证导出的证据样本。
- `GET /api/video/{video_id}/certificate`：获取视频存证证书。
- `GET /api/ipfs/replay/playlist.m3u8`：按时间范围生成 HLS 回放。
- `GET /api/anchor/stats`：获取自适应锚定状态。
- `POST /api/gop/verify`：GOP 级证据验证。

### 1.4 前端展示与交互层

对应目录与文件：

- `demo2/src/pages/DashboardPage.jsx`：系统总览，展示健康状态、设备、IPFS、链上区块。
- `demo2/src/pages/LiveMonitorPage.jsx`：实时监控画面展示。
- `demo2/src/pages/VideoEvidencePage.jsx`：视频归档、证据验证、篡改样本生成、验证历史。
- `demo2/src/pages/IPFSPage.jsx`：IPFS 存储状态、GOP 查询和回放。
- `demo2/src/pages/LedgerPage.jsx`：账本查询、区块详情、Anchor 查询。
- `demo2/src/pages/AnchorPage.jsx`：EIS/MAB 自适应锚定策略可视化。
- `demo2/src/pages/WorkorderPage.jsx`：整改工单与审计导出。
- `demo2/src/components/RiskGauge.jsx`、`GopResultsTable.jsx`、`CertificateCard.jsx`：三态风险展示、GOP 级结果表、存证证书。

报告写法：第 4 章展示系统界面和功能闭环。建议配 4-6 张截图：总览页、视频证据页、三态验证结果、IPFS 回放页、账本页、MAB 锚定页。

### 1.5 测试与实验材料

已有测试文件：

- `tests/test_tri_state_verifier.py`：三态验证规则。
- `tests/test_vif.py`：VIF 输出格式、稳定性、区分度、Merkle 兼容性。
- `tests/test_merkle_utils.py`：Merkle Root、Proof、叶子哈希、兼容性。
- `tests/test_mab_anchor.py`：UCB1、Thompson Sampling、奖励函数、状态持久化。
- `tests/test_full_eis.py`：完整 EIS、光流、异常检测、规则引擎。
- `tests/test_gop_verification_e2e.py`：GOP + IPFS + Fabric 端到端验证场景，需完整服务环境。
- `chaincode/chaincode_test.go`：链码层证据、批次、权限、整改、Anchor 验证测试。

本次已实际运行的快速测试：

```text
python -m pytest tests/test_tri_state_verifier.py tests/test_vif.py tests/test_merkle_utils.py tests/test_mab_anchor.py -q
59 passed in 15.35s
```

写入报告时要注意：这只能证明核心算法单元测试通过；Fabric/IPFS 端到端测试需要在完整服务启动后补充运行结果。

## 2. 正式报告大纲

## 第1章 作品概述

建议控制在 1 页左右，写成一段完整介绍，不要太像技术文档。

### 1.1 作品背景与主题来源

要点：

- 城市监控视频已广泛用于交通治理、安防巡查、事故追责和证据留存。
- 传统视频证据存在“可看见但难证明可信”的问题：视频可能被重编码、剪辑、替换或局部篡改。
- 单纯 SHA-256 哈希虽然能精确证明字节未变，但无法解释合法转码后哈希失配的问题。
- 因此作品选择“AI 视频完整性验证 + 可信证据链”作为主题。

建议写法：

本作品来源于智能城市监控视频取证中的真实性验证需求，目标是解决监控视频在传输、存储、导出和审计过程中“是否被改过、改在哪里、是否只是合法转码”的问题。

### 1.2 用户群体与应用场景

用户群体：

- 城市交通与安防监管人员。
- 园区、校园、物业等监控管理人员。
- 审计人员、取证人员、第三方验证人员。
- 需要保存视频证据的企业或公共机构。

应用场景：

- 交通事故视频取证。
- 公共区域监控证据审计。
- 园区或校园异常事件留痕。
- 跨部门视频证据共享与验证。

### 1.3 主要功能

功能列表：

- 视频上传或视频流接入。
- GOP 级视频切分。
- SHA-256 精确哈希校验。
- VIF v4 AI 视觉完整性指纹生成。
- `INTACT / RE_ENCODED / TAMPERED_SUSPECT` 三态验证。
- Merkle 树批量存证与篡改定位。
- IPFS 内容寻址存储。
- Hyperledger Fabric 链上锚定。
- AI 语义检测与 EIS/MAB 自适应锚定。
- Web 端证据查看、验证报告、IPFS 回放、账本查询、工单审计。

### 1.4 特色与应用价值

核心特色：

- 分层验证：哈希优先，VIF 只在哈希不一致时启用。
- 宽容验证：能区分合法转码与高危疑似篡改。
- 可追溯：Merkle Proof + Fabric Anchor 支持证据链验证。
- 成本优化：MAB 根据场景动态调整上链频率。
- 工程闭环：从视频处理到前端演示形成完整系统。

## 第2章 问题分析

### 2.1 问题来源

写作重点：

- 监控视频在城市治理中越来越重要，但其可信性并不天然成立。
- 视频文件可能经历格式转换、压缩、剪辑、传输丢包、导出重编码等过程。
- 合法转码会导致密码学哈希完全变化，容易被传统方案误判。
- 真正恶意篡改又可能被人工审查遗漏，尤其是大规模多路视频场景。

建议图表：

- 图 1：监控视频证据生命周期及风险点。

### 2.2 现有解决方案

建议比较四类方案：

| 方案 | 代表方法 | 优点 | 局限 |
| --- | --- | --- | --- |
| 人工审查 | 人工查看监控录像 | 实施简单 | 成本高、主观性强、难以规模化 |
| 密码学哈希 | SHA-256 / 文件摘要 | 字节级精确、可信度高 | 对合法转码过敏，无法解释哈希失配 |
| AI 视频分析 | YOLO、目标检测、异常检测 | 可自动识别内容和事件 | 结果本身缺少证据链背书 |
| 区块链存证 | 哈希上链、时间戳存证 | 不可篡改、可追溯 | 全量上链成本高，无法独立判断视频内容变化 |

这一节需要引用参考文献，建议覆盖 SHA-256、Merkle Tree、YOLO、IPFS、Hyperledger Fabric、感知哈希/视频指纹等。

### 2.3 本作品要解决的痛点问题

建议总结为 5 个痛点：

1. 字节级哈希与合法转码之间的冲突：哈希不同不一定代表恶意篡改。
2. 视频篡改定位困难：只知道文件变了，不知道具体哪段 GOP 出问题。
3. 证据链可信度不足：本地存储容易被覆盖或删除，缺少跨组织审计依据。
4. 全量上链成本过高：多路监控视频持续产生数据，直接上链不可行。
5. 人工审查效率不足：大量视频片段需要自动化筛查和风险提示。

### 2.4 解决问题的思路

功能需求：

- 支持视频上传、视频流处理和 GOP 级证据生成。
- 支持 SHA-256 与 VIF 双层验证。
- 支持三态验证输出和 GOP 级结果表。
- 支持证据上链、IPFS 存储、账本查询和审计导出。

性能与验证需求：

- VIF 输出稳定、定长，协议位宽为 256-bit。
- 相同输入多次计算结果一致。
- 不同内容输入具有可区分性。
- Merkle Proof 能验证 GOP 是否属于某个证据批次。
- MAB 策略能根据奖励反馈完成臂选择和状态持久化。
- 系统应提供端到端验证结果和可视化报告。

数据来源：

- 用户上传视频文件。
- 可配置 RTSP/HTTP 视频流。
- 合成 GOP/合成帧单元测试数据。
- 历史 benchmark 数据集：包含完整视频、合法重编码视频和帧替换篡改视频，可作为后续正式实验素材。

注意：正式报告中若使用历史 benchmark 的具体数值，需要用当前代码重新跑一遍，避免引用旧版本实验结果。

## 第3章 技术方案

### 3.1 总体技术路线

建议总图：

视频输入 → GOP 切分 → SHA-256 计算 → VIF v4 提取 → 三态验证 → Merkle 树 → IPFS 存储 → Fabric Anchor → Web 审计验证。

建议图表：

- 图 2：SecureLens 总体架构图。
- 图 3：分层视频完整性验证流程图。

### 3.2 GOP 级证据单元构建

技术要点：

- 使用 PyAV 按 GOP 解析视频流。
- 每个 GOP 保存原始编码字节、时间范围、帧数量、关键帧、采样帧。
- 对 GOP 原始字节计算 SHA-256。
- GOP 作为最小验证单元，便于定位篡改时间点。

对应代码：

- `services/gop_splitter.py`
- `services/gop_timing.py`

### 3.3 哈希优先的分层三态验证机制

这是全文核心方法，建议详细写。

判定规则：

1. 若 `orig_sha256 == curr_sha256`，说明 GOP 字节级完全一致，输出 `INTACT`。
2. 若 SHA-256 不一致，则不立即判定篡改，因为可能是合法转码。
3. 若原始 VIF 或当前 VIF 缺失，输出高危疑似篡改。
4. 若 VIF 均存在，则计算归一化汉明距离：

```text
Risk = HammingDistance(VIF_orig, VIF_curr) / 256
```

5. 若 `Risk < 0.35`，输出 `RE_ENCODED`。
6. 若 `Risk >= 0.35`，输出 `TAMPERED`，并在描述中标记为 `TAMPERED_SUSPECT`。

对应代码：

- `services/tri_state_verifier.py`

建议强调：

- SHA-256 是第一道严格校验，不被替代。
- VIF 是哈希失配后的 AI 宽容解释层。
- 三态结果避免把合法压缩误判为恶意篡改。

### 3.4 VIF v4 AI 视觉完整性指纹

技术流程：

1. GOP 关键帧和确定性采样帧输入。
2. 使用 MobileNetV3-Small 提取 576 维全局视觉特征。
3. 对 GOP 内多帧特征进行 Mean Pooling。
4. L2 归一化。
5. 使用固定随机种子 LSH 投影成 256-bit 指纹。
6. 输出 64 字符十六进制字符串。

对应代码：

- `services/vif.py`
- `services/perceptual_hash.py`

建议图表：

- 图 4：VIF v4 视觉指纹生成流程。

### 3.5 YOLO 语义检测与事件重要性评分

技术要点：

- 使用 YOLO 模型识别人、车等监控目标。
- 统计 GOP 或时间窗口内的目标类别、数量和事件活跃程度。
- 生成语义 JSON 与语义哈希。
- EIS 综合目标数量、运动特征、异常检测结果，为自适应锚定提供输入。

对应代码：

- `services/semantic_fingerprint.py`
- `services/detection_service.py`
- `services/adaptive_anchor.py`

### 3.6 Merkle 树与篡改定位

技术要点：

- GOP Leaf 可由 SHA-256、VIF、语义哈希等证据要素组合。
- 多个 GOP 构成 Merkle Tree，Root 作为批次摘要。
- 通过 Merkle Proof 验证单个 GOP 是否属于原始证据批次。
- 三级结构支持 GOP → Chunk → Segment 的层级验证。
- Epoch Merkle Tree 支持多设备聚合。

对应代码：

- `services/merkle_utils.py`

建议图表：

- 图 5：GOP/Chunk/Segment 三级 Merkle 结构。

### 3.7 IPFS 内容寻址存储

技术要点：

- GOP 分片、语义 JSON、Merkle 结构上传到 IPFS。
- CID 与内容哈希绑定，支持内容寻址和完整性验证。
- SQLite 索引保存设备、时间、GOP、CID、播放元数据。
- 前端支持按设备和时间范围回放。

对应代码：

- `services/ipfs_storage.py`
- `demo2/server.py`
- `demo2/src/pages/IPFSPage.jsx`

### 3.8 Fabric 联盟链锚定

技术要点：

- 不将大视频文件上链，只上链 Merkle Root / Epoch Root / 元数据。
- Chaincode 提供 Anchor、QueryAnchor、VerifyAnchor 等接口。
- 支持多组织角色、整改工单、审计导出。
- ECDSA 设备签名保证数据来源可信。

对应代码：

- `chaincode/chaincode.go`
- `services/fabric_client.py`
- `services/crypto_utils.py`

### 3.9 MAB 自适应锚定策略

技术要点：

- 全量高频上链成本高，低频上链又可能降低关键事件审计及时性。
- 将锚定间隔建模为多臂老虎机选择问题，臂对应不同 GOP 间隔。
- UCB1 和 Thompson Sampling 根据成功率、成本、延迟奖励动态选择。
- 在高风险或高活跃场景提高锚定频率，在低活跃场景降低锚定频率。

对应代码：

- `services/mab_anchor.py`
- `services/adaptive_anchor.py`
- `demo2/src/pages/AnchorPage.jsx`

## 第4章 系统实现

### 4.1 软件架构与技术栈

建议表格：

| 层次 | 技术 | 作用 |
| --- | --- | --- |
| 前端 | React + Vite | 系统展示、证据验证、审计操作 |
| 后端 | FastAPI | 视频处理 API、验证 API、状态查询 |
| AI | PyTorch、Ultralytics YOLO、MobileNetV3 | 目标检测、视觉指纹 |
| 视频处理 | OpenCV、PyAV、FFmpeg | 视频流读取、GOP 切分、HLS 回放 |
| 存储 | SQLite、IPFS | 元数据索引、内容寻址存储 |
| 区块链 | Hyperledger Fabric、Go Chaincode | Root 锚定、审计验证 |
| 测试 | Pytest、Go test | 算法与链码测试 |

### 4.2 后端实现

写作内容：

- FastAPI 服务启动和模块初始化。
- 视频上传处理流程。
- 三态验证 API。
- IPFS 回放与导出样本验证。
- Fabric 查询与 Anchor 提交。
- MAB 锚定统计 API。

对应代码：

- `demo2/server.py`

### 4.3 前端实现

写作内容：

- 登录与角色分流。
- 管理总览页。
- 视频证据页：上传、证书、验证、篡改演示、历史。
- IPFS 页：GOP 查询、回放、CID 展示。
- 账本页：区块和 Anchor 查询。
- MAB 页：策略状态可视化。
- 工单页：整改和审计。

对应代码：

- `demo2/src/pages/*.jsx`
- `demo2/src/components/*.jsx`
- `demo2/src/services/api.js`

### 4.4 数据处理与证据生成流程

建议按步骤写：

1. 用户上传视频或系统接入视频流。
2. 后端进行 GOP 切分。
3. 为每个 GOP 计算 SHA-256、VIF、语义哈希。
4. 将 GOP 分片和 JSON 上传 IPFS。
5. 构造 Merkle Tree 并得到 Root。
6. Root 和元数据提交 Fabric。
7. 前端生成证据证书。
8. 验证时逐 GOP 重新计算并输出三态结果。

### 4.5 部署与运行方式

可写：

- Python 依赖通过 `requirements.txt` 安装。
- 前端通过 `demo2/package.json` 安装依赖并运行。
- IPFS 通过 `docker-compose.ipfs.yml` 启动 3 节点 Kubo 集群。
- Fabric 依赖本地 `fabric-samples/test-network`。
- 配置项集中在 `.env` 与 `config.py`。

### 4.6 开发中的问题与解决

建议写 4 个问题：

1. 合法转码导致 SHA-256 哈希失配：通过 SHA 优先 + VIF 宽容判定解决。
2. VIF 阈值难以设定：使用合法重编码样本风险分布校准，将默认阈值设为 0.35。
3. 多路视频上链成本高：引入 Merkle 批量锚定和 MAB 自适应锚定。
4. 证据文件大且不适合直接上链：采用 IPFS 存储原始分片，链上仅保存 Root 和元数据。

## 第5章 测试分析

### 5.1 测试目标

验证内容：

- 三态验证规则是否符合设计。
- VIF 输出是否稳定、定长、可区分。
- Merkle Proof 是否能正确验证证据归属。
- MAB 策略是否能完成选择、更新、保存与加载。
- 端到端系统是否能完成上传、存证、验证和审计。

### 5.2 单元测试结果

当前可直接写入的结果：

| 测试模块 | 覆盖内容 | 本次结果 |
| --- | --- | --- |
| `test_tri_state_verifier.py` | `INTACT / RE_ENCODED / TAMPERED` 判定 | 已随组合测试通过 |
| `test_vif.py` | VIF 输出格式、稳定性、区分度、Merkle 兼容性 | 已随组合测试通过 |
| `test_merkle_utils.py` | Root 构建、Proof 验证、叶子哈希 | 已随组合测试通过 |
| `test_mab_anchor.py` | UCB1、Thompson、奖励函数、状态持久化 | 已随组合测试通过 |

组合命令结果：

```text
59 passed in 15.35s
```

注意：正式报告可以写“核心算法单元测试通过 59 个用例”，不要写“全系统所有测试通过”，除非后续补跑完整测试。

### 5.3 端到端测试设计

已有测试场景：

- 正常 GOP 上传 IPFS、提交 Anchor、验证结果为 `INTACT`。
- IPFS 索引被替换为篡改内容，验证结果为 `NOT_INTACT`。
- 单字节修改导致重算哈希与原 CID 不一致。
- 三态验证分别覆盖 `INTACT`、`RE_ENCODED`、`TAMPERED`。
- 语义 JSON 上传并通过 IPFS 取回验证。
- 带语义哈希的 Merkle Tree Proof 验证。

对应代码：

- `tests/test_gop_verification_e2e.py`

需要补充：

- 启动 IPFS 和 Fabric 后重新运行端到端测试，记录真实通过率、耗时和失败原因。

### 5.4 建议正式实验数据集

建议构造三组：

| 数据类别 | 处理方式 | 预期结果 |
| --- | --- | --- |
| 原始完整视频 | 不做修改 | `INTACT` |
| 合法转码视频 | H.264/H.265、不同 CRF、不同分辨率 | `RE_ENCODED` |
| 篡改视频 | 帧替换、内容遮挡、插帧/删帧、噪声注入 | `TAMPERED_SUSPECT` |

建议规模：

- 至少 3-5 段不同场景视频。
- 每段生成 5-10 个合法转码版本。
- 每段生成 5-10 个篡改版本。
- 每个样本统计 GOP 级结果和视频级结果。

### 5.5 指标设计

分类指标：

- 准确率 Accuracy。
- 宏平均 F1 Macro-F1。
- 合法转码误判率：`RE_ENCODED` 被误判为篡改的比例。
- 篡改召回率：篡改样本被识别为高危的比例。
- GOP 定位准确率：被篡改 GOP 是否被正确定位。

效率指标：

- 单 GOP VIF 计算耗时。
- 单视频验证耗时。
- IPFS 上传与下载耗时。
- Fabric Anchor 提交耗时。
- MAB 相比固定高频锚定的上链次数减少比例。

### 5.6 测试结论写法

建议结论结构：

- 单元测试证明核心算法链路的确定性和正确性。
- 端到端测试证明系统能够完成“视频处理 → IPFS → Fabric → 验证”的闭环。
- 合法转码实验用于证明 VIF 能缓解单纯哈希的误判问题。
- 篡改实验用于证明系统能够将高风险片段提示给审计人员。
- MAB 实验用于证明系统具备成本自适应能力。

## 第6章 作品总结

### 6.1 作品特色与创新点

建议写 5 点：

1. 哈希优先的 AI 分层验证机制：保留密码学哈希的严格性，同时利用 VIF 解释合法转码。
2. 面向 GOP 的视频完整性指纹：将验证粒度从整文件细化到片段，便于定位问题。
3. 可信证据链闭环：Merkle Tree、IPFS 和 Fabric 共同支撑可追溯审计。
4. AI 自适应锚定策略：基于 EIS/MAB 在可信性和成本之间动态权衡。
5. 完整工程实现：包含后端 API、前端演示、链码、存储、测试和文档。

### 6.2 应用推广

适用场景：

- 智慧城市交通监管。
- 公共安全视频审计。
- 校园、园区、物业监控证据管理。
- 企业安全生产视频留痕。
- 司法取证前的证据完整性初筛。

推广价值：

- 不依赖专用硬件，可部署在已有监控平台旁路。
- 支持本地视频上传、网络视频流和后续摄像头接入。
- 可与现有安防系统、审计系统、工单系统集成。

### 6.3 作品展望

后续优化：

- 建立更大规模的视频篡改与合法转码测试集。
- 引入更细粒度的时序一致性和目标轨迹验证。
- 接入真实摄像头、边缘计算盒或手机摄像头 RTSP 演示。
- 优化 VIF 模型推理速度，支持轻量化部署。
- 完善权限认证、加密传输和隐私保护机制。
- 将 `TAMPERED_SUSPECT` 与人工复核、审计工单形成更完整闭环。

## 3. 图表清单建议

| 编号 | 图表名称 | 放置章节 | 来源 |
| --- | --- | --- | --- |
| 图 1 | 监控视频证据生命周期风险点 | 第2章 | 可新画 |
| 图 2 | SecureLens 系统总体架构图 | 第3章 | README 架构图改绘 |
| 图 3 | SHA-256 + VIF 分层三态验证流程 | 第3章 | 根据 `tri_state_verifier.py` 新画 |
| 图 4 | VIF v4 指纹生成流程 | 第3章 | 根据 `vif.py` 新画 |
| 图 5 | GOP/Chunk/Segment 三级 Merkle 结构 | 第3章 | 根据 `merkle_utils.py` 新画 |
| 图 6 | 视频证据上传与验证界面 | 第4章 | 前端截图 |
| 图 7 | 三态验证结果与 GOP 风险表 | 第4/5章 | 前端截图 |
| 图 8 | MAB 自适应锚定状态页面 | 第4/5章 | 前端截图 |
| 表 1 | 现有方案对比表 | 第2章 | 本大纲提供 |
| 表 2 | 技术栈表 | 第4章 | 本大纲提供 |
| 表 3 | 单元测试结果表 | 第5章 | 当前测试结果 |
| 表 4 | 正式实验数据集设计表 | 第5章 | 后续补充 |
| 表 5 | 作品创新点总结表 | 第6章 | 后续补充 |

## 4. 参考文献候选

正式写作时建议补充并核对格式：

1. SHA-256 / Secure Hash Standard：用于密码学哈希背景。
2. Merkle Tree 原始论文或教材资料：用于 Merkle Proof 依据。
3. YOLO / Ultralytics YOLO 相关论文或官方文档：用于目标检测模型依据。
4. MobileNetV3 论文：用于 VIF 视觉特征提取网络依据。
5. Locality-Sensitive Hashing 相关论文：用于 LSH 降维指纹依据。
6. Hyperledger Fabric 论文或官方文档：用于联盟链架构依据。
7. IPFS 论文或白皮书：用于内容寻址存储依据。
8. Multi-Armed Bandit / UCB1 / Thompson Sampling 经典文献：用于自适应锚定策略依据。
9. 视频篡改检测、视频取证、感知哈希相关论文：用于现有方案分析。

## 5. 下一步撰写建议

建议按以下顺序扩写：

1. 先写第 1 章和第 2 章，确定故事线和痛点。
2. 再写第 3 章，重点打磨“SHA-256 优先 + VIF 补充”的核心方法。
3. 然后写第 4 章，补系统截图和模块说明。
4. 最后写第 5 章，补正式实验数据和测试表格。
5. 第 6 章在前面内容稳定后总结，避免创新点和实验结果脱节。

当前最需要补齐的素材：

- 正式作品编号、作品名称、填写日期。
- 4-6 张高质量系统截图。
- 当前代码的端到端 Fabric/IPFS 测试结果。
- 当前 VIF v4 在合法转码/篡改样本上的正式实验表。
- 参考文献的最终格式。
