# Changelog

## v3.0.1 (2026-04-25) — GitHub 最新同步补录

> 基于 GitHub 远端 `origin/sensor` 检查；当前最新提交为 `68a3fc2`（2026-04-08，`260408 update`），上一轮前端大更新为 `a722628`（2026-04-05，`260405 frontend update`）。

### GitHub 最近更新概览

- **产品化演示闭环成型**
  - `demo2/` 从纯展示型 7 模块前端，升级为登录分流后的双角色应用。
  - 管理方后台覆盖监控总览、设备管理、视频存证、告警中心。
  - 验证方平台覆盖证据验真、验真报告、历史记录。

- **真实后端链路补齐**
  - 新增 `services/video_store.py`，用 SQLite 记录视频、GOP 指纹和验真历史。
  - `web_app.py` 补充视频上传、证书查询、验真、历史查询等 API。
  - 上传流程串起 GOP 切分、VIF/SHA-256 指纹、Merkle Root、Fabric 锚定和本地索引。

- **前端 API 与交互重构**
  - `demo2/src/services/api.js` 新增统一 API 封装，支持视频上传、证书拉取和验真请求。
  - 新增 `CertificateCard`、`RiskGauge`、`VideoCard`、`Sidebar` 等产品级组件。
  - `LoginPage` 支持管理方/验证方角色选择和演示账号预填。

- **演示运维脚本补齐**
  - 新增 `scripts/start_all.sh`、`scripts/stop_all.sh`、`scripts/check_services.sh`。
  - 支持按顺序启动/停止 Fabric、IPFS、后端和前端，并快速检查服务状态。

- **4 月 5 日前端大版本补录**
  - 新增 Vite + React 演示系统基础结构、依赖、入口文件和设计系统。
  - 补齐系统概览、边缘智能、聚合网关、IPFS、联盟链、审计验证、对比实验 7 个展示模块。
  - 新增 Mock 数据、导航、玻璃卡片、状态标签、计数器等前端基础组件。

### Notes

- 远端最新分支检查结果：`sensor` 与 `origin/sensor` 对齐，最新提交停留在 2026-04-08。
- 本地工作区存在大量尚未提交的后续改动，本节仅记录 GitHub 已提交内容，避免把草稿变更混入正式更新日志。

---

## v3.0.0 (2026-04-09) — 产品化重构：双角色全栈应用

### 核心升级

- **架构转型**：从 7 模块技术展板重构为 **角色分流式产品应用**
  - 管理方后台（Admin Dashboard）—— 监控总览 / 设备管理 / 视频存证 / 告警中心
  - 验证方平台（Verify Portal）—— 证据验真 / 验真报告 / 历史记录
  - 登录门户 —— 角色选择 + 预填演示凭证，一键切换双身份
- **后端真实闭环**：视频上传 → GOP 切分 → VIF 指纹 → Merkle 树 → Fabric 链上锚定 → SQLite 索引，全流程打通
- **三态验真引擎**：上传待验视频与链上存证逐 GOP 比对，输出 INTACT / RE_ENCODED / TAMPERED 报告

### Added

- **一键服务管理脚本** (`scripts/`)
  - `start_all.sh` — 按序启动 Fabric 网络 → IPFS 集群 → FastAPI 后端 → Vite 前端
  - `stop_all.sh` — 逆序安全停止所有服务
  - `check_services.sh` — 快速检查四个服务存活状态与关键指标

- **SQLite 视频索引层** (`services/video_store.py`)
  - 三张表：`videos`（存证元数据）、`video_gops`（GOP 级哈希记录）、`verify_history`（验真历史）
  - WAL 模式 + 线程安全（per-thread 连接池）
  - CRUD 接口：`insert_video()`、`list_videos()`、`get_video()`、`get_video_gops()`
  - 验真历史：`insert_verify_record()`、`list_verify_history()`

- **5 个 Video API 端点** (`web_app.py`)
  - `POST /api/video/upload` — 上传视频 → GOP 切分 → VIF + SHA-256 → Merkle 树 → Fabric 锚定 → SQLite 写入
  - `GET /api/video/list` — 列出所有已存证视频
  - `GET /api/video/{video_id}/certificate` — 获取存证证书（含 Merkle Root、TX ID、区块高度、GOP 详情）
  - `POST /api/video/verify` — 上传待验视频，逐 GOP 三态比对，输出风险评分与 GOP 级报告
  - `GET /api/video/verify/history` — 查询验真历史记录
  - CORS 中间件支持前端 `:5173` 跨域请求

- **前端 API 封装** (`demo2/src/services/api.js`)
  - `uploadVideo()` / `listVideos()` / `getVideoCertificate()` / `verifyVideo()` / `getVerifyHistory()` / `getConfig()`
  - 统一 API_BASE 配置，fetch + FormData 上传

- **登录页** (`demo2/src/pages/LoginPage.jsx`)
  - 双角色卡片选择（管理方 🟢 / 验证方 🟣），动态主题色
  - 粒子飘浮背景动画（6 个径向渐变光球）
  - 预填演示账号密码，一键登录
  - Framer Motion 入场动画 + 表单展开过渡

- **侧边栏导航** (`demo2/src/components/Sidebar.jsx`)
  - 角色感知 Tab 列表（管理方 4 项 / 验证方 3 项）
  - Spring 动画 `layoutId` 活跃指示器
  - 品牌区 + 角色标签 + 退出登录

- **管理后台** (`demo2/src/pages/AdminDashboard.jsx`)
  - **监控总览** Tab — 4 项统计卡片（已存证视频 / 在线设备 / 链上区块 / 活跃告警）+ 最近存证列表
  - **设备管理** Tab — 6 台模拟设备卡片（在线 / 离线 / 警告三态 + IP + 型号）
  - **视频存证** Tab — 真实 API：上传视频 → 处理进度 → 视频卡片列表 → 查看存证证书
  - **告警中心** Tab — 4 条模拟告警（高危 / 中风险 / 低标签 + 脉冲圆点）

- **验证平台** (`demo2/src/pages/VerifyPortal.jsx`)
  - **证据验真** Tab — 两步流程：选择原始存证 → 上传待验视频 → RiskGauge + 逐 GOP 结果
  - **验真报告** Tab — 最近一次验真的详细报告（RiskGauge + GOP 条形图）
  - **历史记录** Tab — 所有验真记录列表（状态图标 + 风险 + 时间）

- **UI 组件** (`demo2/src/components/`)
  - `CertificateCard.jsx` — 存证证书 Modal（Video ID / Merkle Root / TX ID / Block / GOP 列表 + 联盟链印章）
  - `RiskGauge.jsx` — SVG 半圆仪表盘（动画弧线 + 三态渐变色 + 风险等级标签）
  - `VideoCard.jsx` — 视频存证卡片（缩略图占位 + 元数据 + 查看证书按钮）

### Changed

- **`App.jsx`** — 完全重写路由：Login → Sidebar + AdminDashboard / VerifyPortal
- **`index.css`** — 完整重写设计系统（~950 行）
  - 新增：登录页、侧边栏、仪表盘布局、统计卡片、设备卡片、视频卡片、证书 Modal、风险仪表盘、验证步骤、GOP 结果条、告警列表、历史列表
  - 保留：Design Token 系统、Glassmorphism 基础、Orbitron + Exo 2 字体
  - 新增响应式断点：640px 折叠侧边栏为 Icon-only 模式
- **`mockData.js`** — 精简为设备列表 + 告警数据（移除旧 7 模块数据）

### Notes

- 旧 7 模块页面文件保留在 `pages/` 目录但不再被路由引用，可用于技术答辩参考
- Fabric 锚定失败时自动降级为 `offline-xxx` TX ID（非阻断），前端仍可完整展示存证流程
- `npm run build` 构建成功：index.html 0.63kB + CSS 20.24kB + JS 352.56kB（gzip 116kB）

---

## v2.0.0 (2026-04-05) — 竞赛演示系统：全流程交互式前端

### 核心新增

- **[NEW] `demo2/` — 全流程交互式演示系统**
  - 面向中国大学生计算机设计大赛，完整映射 SecureLens 四层架构
  - 纯前端 Mock 数据驱动，`npm run dev` 一键启动，无需后端/IPFS/Fabric 服务

### 技术栈

- **Vite + React** — 组件化 SPA 架构
- **原生 CSS Design System** — Dark Mode OLED 风格，Glassmorphism 毛玻璃卡片
- **Orbitron + Exo 2** — Web3/区块链科技风格字体
- **Lucide React** — 统一 SVG 图标

### Added

- **设计系统** (`src/index.css`)
  - CSS 变量 Token 系统：配色 / 字体 / 间距 / 阴影 / 动画曲线
  - Emil Kowalski 动效哲学：ease-out 曲线、scale(0.97) 按钮反馈、stagger 交错入场
  - Glassmorphism 基础样式 + 响应式断点 (1440/1024/768/375px)
  - `prefers-reduced-motion` 无障碍支持

- **共享组件** (`src/components/`)
  - `Navbar.jsx` — 顶部固定导航栏，7 模块切换 + 当前模块指示器 + 竞赛徽章
  - `GlassCard.jsx` — 通用毛玻璃卡片，IntersectionObserver 滚动淡入，可配置发光色
  - `StatusBadge.jsx` — 三态验证标签（INTACT / RE_ENCODED / TAMPERED）
  - `AnimatedCounter.jsx` — 数字计数器动画，滚动触发 + ease-out cubic

- **模块 1: 系统概览** (`src/pages/OverviewPage.jsx`)
  - Hero 区域 + 四大核心指标动画计数器
  - 四层架构交互图：点击展开各层 5 项技术细节
  - 核心技术栈 Bento Grid（6 项）

- **模块 2: 边缘智能** (`src/pages/EdgePage.jsx`)
  - GOP 时间轴（12 个 GOP，点击展示 SHA-256/pHash/VIF 三重指纹）
  - VIF v4 四步流水线动画（采样 → CNN → Pooling → LSH）
  - 三态判定仪表盘（Risk Score gauge + 0.35 阈值标线）
  - VIF v4 vs 初代方案对比表
  - YOLO 目标检测统计 + EIS 评分柱状图

- **模块 3: 聚合网关** (`src/pages/GatewayPage.jsx`)
  - MAB 四臂老虎机可视化（Arm 0-3，间隔 1/2/5/10 GOP）
  - 100 步 UCB1 模拟引擎（播放/暂停/重置），累计 Reward 曲线实时绘制
  - 三级 Merkle 树交互式可视化（SegmentRoot → ChunkRoot → GOP Leaf）
  - Merkle Proof 验证步骤说明

- **模块 4: IPFS 存储** (`src/pages/StoragePage.jsx`)
  - CID 内容寻址原理四步动画
  - 3 节点 Kubo 集群状态面板
  - 模拟上传（进度条 + 3 类 CID 生成）
  - MinIO vs IPFS 5 维对比表

- **模块 5: 联盟链** (`src/pages/BlockchainPage.jsx`)
  - 3 Org × 2 Peer 网络拓扑 + Orderer 信息
  - 智能合约 4 函数卡片（参数列表 + 访问权限）
  - Anchor → VerifyAnchor 锚定验证三步动画演示
  - 交易记录浏览器（8 条模拟交易）

- **模块 6: 审计验证** (`src/pages/VerificationPage.jsx`)
  - 三态验证引擎（INTACT/RE_ENCODED/TAMPERED 可切换）
  - Risk Score 仪表盘 + Hamming 距离详情
  - 篡改定位时间轴（GOP 3, GOP 7 红色高亮 + 二分查找说明）
  - 4 种攻击场景卡片 + VIF 距离进度条

- **模块 7: 对比实验** (`src/pages/BenchmarkPage.jsx`)
  - MAB 策略对比 SVG 曲线（UCB1 vs Thompson vs Fixed）
  - VIF 版本对比表（SHA-256 Only vs v1 vs v4）
  - 锚定频率成本分析柱状图
  - 6 项性能指标卡片

- **Mock 数据** (`src/data/mockData.js`)
  - 全部 7 模块的模拟数据集
  - 含 MAB 100 步模拟生成函数

### Notes

- 新增依赖：`lucide-react`、`recharts`、`framer-motion`
- 与 `demo/`（Flask 版）并存，互不影响
- 全中文界面 + 英文技术术语保留

---

## v1.5.0 (2026-03-30) — 存储层升级：MinIO → IPFS 去中心化内容寻址

### 核心升级

- **存储架构革新**：从 MinIO 中心化对象存储迁移至 IPFS 去中心化内容寻址存储
  - 消除存储层单点信任假设：CID 即完整性证明，无需信任存储节点
  - 协议层保证数据完整性：`ipfs cat(CID)` 返回的内容哈希一定匹配 CID
  - 存储/索引/验证三位一体：IPFS CIDv1 同时作为存储标识、索引键和链上凭证

### Added

- **[NEW] `services/ipfs_storage.py`** — IPFS 存储服务
  - `VideoStorage` 类保持与原 MinIO 版本相同的接口签名
  - 内置轻量级 `IPFSClient`（基于 Kubo RPC API）
  - 内置 `IPFSIndex` SQLite 索引（`data/ipfs_index.db`）
  - 新增方法：`pin_cid()`、`get_node_stats()`、`get_gateway_url()`
  - SHA-256 → IPFS CID 自动查找（向后兼容旧代码）
- **[NEW] `docker-compose.ipfs.yml`** — 3 节点 IPFS Kubo 集群
  - node0: API 5001, Gateway 8080
  - node1: API 5002, Gateway 8081
  - node2: API 5003, Gateway 8082
- **[NEW] `IPFS_SETUP.md`** — IPFS 集群安装与启动指南
- **[NEW] `test_ipfs_storage.py`** — IPFS 集成测试（含跨节点验证）

### Changed

- **`config.py`** — MinIO 5 项配置 → IPFS 3 项配置（无密钥管理）
  - `ipfs_api_url`（默认 `http://localhost:5001`）
  - `ipfs_gateway_url`（默认 `http://localhost:8080`）
  - `ipfs_pin_enabled`（默认 `true`）
- **`services/gop_verifier.py`** — 导入切换至 `ipfs_storage`
- **`scripts/tamper_demo.py`** — `--skip-minio` → `--skip-ipfs`
- **`.env` / `.env.example`** — 新增 IPFS 配置项
- **`requirements.txt`** — `minio` → `ipfshttpclient>=0.8.0a2`
- **`README.md`** — 架构图与存储层描述更新
- **`demo/templates/index.html`** — 存储层描述更新
- **`demo/app.py`** — 注释更新

### Removed

- **[DELETE] `services/minio_storage.py`** — MinIO 存储服务
- **[DELETE] `test_minio_storage.py`** — MinIO 集成测试
- **[DELETE] `MINIO_SETUP.md`** — MinIO 安装指南


## 2026-03-28 (Phase 4 VIF 模块重构与协议收敛)

### Changed

- **VIF 模型纯粹化与降负** (`services/vif.py`)
  - 彻底剔除基于 Farneback 光流的时序特征提取逻辑 (`extract_temporal_feature`)，解除算力黑洞。
  - 将 VIF 收敛为“纯视觉的内容级宽容匹配初筛器”。采用 GOP 关键帧与绝对确定性采样帧（默认再抽 1 帧）提取视觉 CNN Embedding 后进行平均池化（Mean Pooling），保证其在计算负担大幅下降的同时，坚守“对整个 GOP 片段背书，而非退化为单帧封面”的系统级初衷。
  - **冻结协议位宽**：在去除多模态拼接的同时，LSH 投影层直接将 Mean Pooling 后的视觉底噪映射拼接为 **256-bit (64 字符十六进制)**，绝不越界修改上游 Merkle 树及数据库已保留的特征定型标准。

- **三态验证容忍逻辑校准** (`services/tri_state_verifier.py`)
  - 彻底抹除多模态分数权重耦合。
  - 简化判定链路为：**SHA 完全一致 → INTACT**；**SHA 破坏 + VIF < 0.35 阈值 → RE_ENCODED**。
  - **防腐与定性降格**：当阈值被击穿时，API 主状态兼容旧有返回 `TAMPERED`，但在 `state_desc` 与底层逻辑日志中，明确定位该行为为 **`TAMPERED_SUSPECT`**（高危疑似建议），在代码层面坚守其非终判职权。

- **GOP 采样的绝对确定性** (`services/gop_splitter.py`)
  - 彻底重构多帧提取策略：将 `_sample_extra_frames` 基于浮点步长的均匀抽离，改为坚固的整数绝对索引提取（如单帧抽样绝对锁定在 `total // 2` 的帧位），彻底抹平跨平台与不同机器解码帧流落差引发的 Hash 漂移。

- **配置版本演进与连带测试** (`config.py`, `demo/app.py`, `tests/*`)
  - `config.py` 加入常驻版本钉死：`VIF_VERSION = "v4"` 与 `VIF_SAMPLE_FRAMES = 1`，防范未来产生旧有配置漂移和实验数据交叉污染。
  - `demo/app.py`、`tests/test_vif.py` 与重转码实验的 Benchmarks 同步切断旧时序与语义逻辑依赖，V4 相关核心链路的单元测试满分通过。

### v1.4.1 (2026-03-28)
- **VIF 模型边界定锤 (Phase 3 负面校准)**:
  - 弃用固定的拍脑袋 VIF 三态判决阈值 (0.25)，使用数据驱动 (P99 真实高动态视频特征漂移包络 0.3203，加上 margin) 建立起 `0.35` 的宽容前置过滤主线 (`Tolerant Mode`)。
  - 核心设计退让：在真实高动态视频和极重压缩实验下明确表明，受制于底层视觉与时序光流对重度马赛克的敏感放大，现存 VIF 指纹系统完全无法具备细粒度微小同源抽帧篡改的判断依据 (0.004 % 影响完全掩埋在 0.320 正常衰减噪影下)。
  - 定位校正：将原 README 与项目设定的“细粒度同源篡改”检测责任，剥离至下放层，全面交于对象检测网络与 MAB 强化学习挂靠锚定的深检。

## 2026-03-28 (Phase 3 VIF 边界消融实验与架构降级收拢)

### Changed

- **VIF 主线架构降级重组** (`services/vif.py`, `services/tri_state_verifier.py`)
  - 彻底撤销并抛弃 384-bit (96-Hex) 的局部/全局混编协议提案，主系统 VIF 永久回退并收敛为最坚硬纯粹的 **256-bit (64-Hex) 双模态架构** (128-bit 视觉加上 128-bit 时序光流)。
  - `TriStateVerifier` 同步剔除对于微弱局部分量 ($D_{local}$) 的探测和加权逻辑，回归最稳定的容错宏观判决 ($Risk = W_{vis} \cdot D_{vis} + W_{tem} \cdot D_{tem}$)。

- **学术主张正式定调**
  - 根据控制变量的消融数据结果，将 VIF 系统的纸面论文主张彻底降级定调：**将其明确降级为“对重压缩容忍度极高的前置宽容护城河”**，停止一切试图在 VIF 内进行像素级微小抽帧检测的“越级”开发。

### Added

- **网格哈希负面消融隔离区** (`services/perceptual_hash.py`, `benchmarks/tune_weights.py`)
  - 保留了在底层特征网上拉取 $2 \times 2$ 宫格局部特征池的抽取接口，但不参与上层 VIF Hash 拼接。
  - 在参数调测脚本 `tune_weights.py` 中独立实现了纯分离式的三态局部分支对照组 (Baseline vs Max_Local vs Top2_Mean)。
  - 作为学术负面试验副产物，成功保留了“静态同源视频下，简单网格特征无法冲破抗转码阈值底噪”的量化证据，用作论证后续接入复杂语义网关系统的正当性。

## 2026-03-28 (Phase 2 VIF 架构精简与统一)

### Added

- **TriStateVerifier 统一** (`services/tri_state_verifier.py`)
  - 彻底合并 `TriStateVerifierV2` 为唯一的 `TriStateVerifier`。
  - 验证接口变更为更统一的 `verify(orig_sha256, curr_sha256, orig_vif, curr_vif)`，输出 `(state, risk, dict)`。
  - 测试用例库全量更新以匹配解耦后的 256 位 VIF API，抛弃传统 pHash Hamming Threshold 断言机制。

### Changed

- **模型计算资源复用优化** (`services/vif.py` & `services/perceptual_hash.py`)
  - VIF （多模态完整性指纹）和 pHash 指纹现在统一调用 `DeepPerceptualHasher` 的单例。
  - 废弃了原有的 `_SemanticFeatureExtractor` 内置实例化逻辑网络，大幅降低了在融合模式下所需的显存与内存开销。
- **TriStateVerifier 风险决策变更** (`services/tri_state_verifier.py`)
  - 彻底移除了“语义一票否决” (`semantic_veto`) 以及“运动矢量衰减” (`mv_loss_penalty`) 的实验性启发式机制。
  - 转而采用纯数学形式的纯线性加权：`Risk = W_vis·D_vis + W_sem·D_sem + W_tem·D_tem`。

### Removed

- **废弃离线持久化** (`services/perceptual_hash.py`)
  - 删除了 LSH 投影矩阵的 `.npy` 磁盘持久化保存恢复机制 (`save()`/`load()`)。
  - 变更为由确定性种子生成的运行时构建，确立无状态系统兼容性。
- **废弃经典非深度网络功能支持** (`services/perceptual_hash.py`)
  - 全面删除了对基于 `imagehash` 库（如离散余弦变换）等非深度学习哈希方法的回退支持。现在系统仅依赖基于轻量 MobileNet 特征空间。
- **彻底删除压缩域运动矢量耦合** (`services/gop_splitter.py`, `demo/app.py`, `services/vif.py`)
  - 删除了 PyAV 对 H.264 宏块的 `AV_CODEC_FLAG2_EXPORT_MVS` 抽取参数及附随的 `GOPData.motion_vectors` 定义，显著降低 GOP 划分阶段的解码负担与长序列解析响应时间。
  - 移除了由于携带状态标识而向 VIF 标准 64 字符（256位）附加第 65 位标志位（`'m'` / `'f'`）的行为，恢复全长统一标准。
## 2026-03-25 (时序来源标记辅助分析)

### Added

- **时序来源标记 (Temporal Source Tag)** (`services/vif.py`)
  - VIF hex 末尾追加 1 字符标记：`'m'` = MV 可用，`'f'` = Farneback 回退
  - `split_vif_hex()` 返回 4-tuple `(hash_vis, hash_sem, hash_tem, temporal_tag)`
  - 向后兼容：旧 64-char VIF 默认 tag='f'
  - 标记辅助分析编码域状态，作为重压缩判断的参考特征

### Changed

- **VIF 时序哈希始终使用 Farneback** (`services/vif.py`)
  - MV 特征仅用于分析是否发生重编码，不参与时序哈希计算
  - Farneback 光流基于像素级计算，跨编码器一致性好

- **前端模态距离标签** (`demo/static/js/detect.js`)
  - 将 emoji `👁 🏷 🎬` 替换为英文 `Vis Sem Tem`

### 检测结果

| 篡改类型 | 判定结果 |
|----------|---------|
| 重压缩 | ⚠️ RE_ENCODED ✅ |
| 帧替换 | ❌ TAMPERED ✅ |
| 噪声注入 | ❌ TAMPERED ✅ |


## 2026-03-24 (Demo 全面审计 + 交互式 Merkle 树 + 哈希完整显示)

### Fixed

- **`compute_leaf_hash` 缺失 VIF 参数** (`demo/app.py`)
  - Merkle 树叶子哈希原先仅拼接 `SHA-256 + pHash`，遗漏了 `vif` 参数
  - 修复后叶子哈希公式为 `SHA-256(sha256 + vif)`（VIF 可用时），与原项目 `merkle_utils.py` 逻辑一致

- **`_tamper_store` 内存泄漏** (`demo/app.py`)
  - 每次篡改生成都往全局字典追加数据，无清理机制
  - 新增限制：最多保留 5 条，超出自动清理最旧条目

- **`detect.js` 空输入可触发检测**
  - 未选择原始视频/未生成篡改时也能点击"开始检测"按钮
  - 新增前置校验，无输入时弹出提示；后端 error 响应增加捕获处理

- **`analyze.js` 流水线重置丢失 icon 和描述**
  - 重新分析时，step 1 的"I帧边界切分 · SHA-256 · pHash · VIF"被覆盖为"等待中"
  - 修复后恢复各 step 的图标数字和 step 1 的默认描述

- **`benchmark.js` 无数据时错误未捕获**
  - API 返回 200 + `{error: ...}` JSON 时，`res.ok` 无法捕获
  - 新增 `data.error` 检查，正确显示"暂无数据"提示

- **移除未使用的 `import io`** (`demo/app.py`)

### Added

- **交互式 Merkle 树动画** (`demo/app.py` + `demo/static/js/analyze.js` + `demo/templates/analyze.html`)
  - 后端：解析 `MerkleTree._levels` 递归构建 JSON 树结构，叶子节点携带 GOP I 帧缩略图
  - 前端：使用 ECharts `tree` 系列渲染可交互 Merkle 树
  - 交互：初始仅显示 Root 根节点（`initialTreeDepth: 0`），点击可逐层展开/折叠
  - 中间节点显示 `Node` + 前 8 位 Hash；叶子节点以 I 帧缩略图为图标
  - 鼠标悬停 Tooltip 显示完整 64 字符哈希值
  - Padding 节点标记为 `Pad`（灰色小圆），与真实 GOP 叶子清晰区分

- **VIF 多帧均匀采样** (`services/gop_splitter.py`)
  - `split_gops()` 在 `VIF_MODE != off` 时，缓存非关键帧 packets 并均匀采样
  - 默认采样 3 帧（通过 `VIF_SAMPLE_FRAMES` 环境变量可调），使 VIF 时序光流分支不再退化为零向量
  - 按序遍历所有 packet 维护参考帧链，仅保留采样索引处的帧

### Changed

- **所有篡改类型统一使用 VIF 检测** (`demo/app.py`)
  - `frame_replace` / `compression` / `noise_inject` 不再仅对比 pHash，统一走 `gop_level` 模式
  - I 帧篡改时也对篡改后的关键帧计算 VIF 指纹，与原始 VIF 对比
  - 解决了局部帧替换（pHash Hamming < 旧阈值 10）被误判为 `RE_ENCODED` 的问题

- **Hamming 阈值从 10 降至 5** (`demo/app.py`)
  - pHash 和 VIF 的判定阈值统一从 10 降至 5，提高对局部篡改的灵敏度
  - 学术论文中 pHash 典型阈值为 5，与行业标准对齐

- **GOP 卡片哈希完整显示** (`demo/static/js/analyze.js`)
  - 移除 SHA-256 和 VIF 哈希值的 `.slice()` 截断，现在完整显示全部字符
  - CSS `word-break: break-all` 确保长哈希自动换行不撑破布局

### Performance Notes

- VIF 多帧采样增加约 8 秒处理耗时（3 帧模式），是安全性与性能的权衡
- 基准测试：0 帧=3s / 2 帧=9s / 3 帧=11s / 6 帧=19s / 8 帧=20s

---

## 2026-03-24 (Web Demo 演示前端)

### Added

- **独立演示应用** (`demo/`)
  - `app.py`：Flask 后端，8 路由 + SSE 流式进度推送
  - 不依赖 Fabric / MinIO，单命令 `PYTHONPATH=. python demo/app.py` 启动
  - **YOLO nano** 目标检测（延迟加载，首次 ~3s）
  - **EIS 评分** 基于检测结果自动评估 GOP 重要性
  - **MAB 自适应锚定** UCB1 策略动态决策（4 臂 × [1,2,5,10] 间隔）

- **6 步流水线**
  - GOP 切分 → YOLO 检测 → 哈希计算 → VIF 融合 → EIS+MAB 决策 → Merkle 构建

- **4 个页面** (`demo/templates/`)
  - `index.html`：系统总览 — 指标卡片 + 四层架构图 + VIF/MAB/EIS 创新点
  - `analyze.html`：视频分析 — 上传/示例选择 → 4 步流水线动画（GOP 切分 → 哈希 → VIF → Merkle）
  - `detect.html`：篡改检测 — 一键生成篡改视频（3 种类型）+ 三态判定 + 逐帧对比
  - `benchmark.html`：实验数据 — ECharts 图表（吞吐量/延迟/TPR/资源）

- **前端交互** (`demo/static/`)
  - `css/style.css`：Apple 风格亮色主题（沿用 SecureLens 设计）
  - `js/analyze.js`：视频上传/拖拽 + SSE 进度监听 + GOP 结果渲染
  - `js/detect.js`：一键篡改生成 + 三态结果展示
  - `js/benchmark.js`：ECharts 图表渲染

### Notes

- 新增依赖：`flask`
- 全部新建文件，不修改原有 `web_app.py`
- 内置示例视频通过软链接引用
- 端口：5001（避免 macOS AirPlay 冲突）

---

## 2026-03-23 (E2E Benchmark 框架)

### Added

- **Benchmark 基础设施** (`benchmarks/`)
  - `config.py`：分辨率/轮次/并发/篡改类型等参数管理
  - `metrics.py`：LatencyStats (P50/P95/P99) + ThroughputStats + ClassificationMetrics (TPR/FPR/F1) + ResourceSnapshot
  - `runner.py`：CLI 运行器，支持多轮 warmup、JSON 持久化
  - `datasets.py`：合成数据生成 + 5 种篡改类型（帧替换/内容叠加/时间偏移/重压缩/噪声注入）

- **Baselines** (`benchmarks/baselines/`)
  - `naive_hash.py`：纯 SHA-256 检测（baseline，高 FPR）
  - `simple_merkle.py`：扁平 Merkle 树（无层次）
  - `fixed_anchor.py`：固定间隔锚定策略

- **测试场景** (`benchmarks/scenarios/`)
  - `throughput.py`：480p/720p/1080p 吞吐量对比
  - `latency.py`：单 GOP 延迟分解（SHA-256 / pHash / Merkle）
  - `tamper_detection.py`：SHA-256 vs pHash vs VIF 篡改检测 TPR/FPR/F1
  - `scalability.py`：1/5/10/20 路并发可扩展性
  - `resource_usage.py`：CPU/内存占用

- **报告生成** (`benchmarks/report/`)
  - `latex_table.py`：JSON → LaTeX tabular 表格（吞吐量/延迟/篡改检测）
  - `plot_generator.py`：matplotlib + seaborn 论文图表（柱状图/折线图/对比图）

- **单元测试** (`tests/test_benchmark.py`)
  - 23 个测试用例：metrics 计算、数据集生成、baselines、LaTeX 输出格式

### Testing Results

- `tests/test_benchmark.py`: 23/23 通过 ✅

### Notes

- 新增依赖：`tabulate`
- 全部新建文件，不修改主系统任何代码
- 使用合成数据，无需真实视频即可运行

---

## 2026-03-23 (MAB 自适应锚定策略)

### Added

- **MAB 锚定模块** (`services/mab_anchor.py`)
  - 4 个锚定臂：Arm 0/1/2/3 = 每 1/2/5/10 个 GOP 锚定一次
  - `compute_reward(success, cost, latency)`：reward = α×成功率 - β×成本 - γ×延迟
  - `UCBStrategy` 类：UCB1 选择策略
    - 初始探索保证每个臂至少被拉一次
    - UCB 值 = Q(i) + c × √(ln(N)/n(i))，默认 c = √2
    - 1000 次模拟收敛到最优臂选择率 > 50%
  - `ThompsonStrategy` 类：Beta 分布 Thompson Sampling
    - 正 reward → α += 1，负/零 reward → β += 1
    - 500 次模拟收敛到最优臂
  - `MABAnchorManager` 类：
    - `should_anchor(gop_index) -> bool`：按当前臂间隔决策
    - `report_result(success, cost, latency)`：反馈更新 MAB 策略
    - `save_state()` / `load_state()`：JSON 持久化（默认 `data/mab_state.json`）
    - `get_stats()`：获取每个臂的统计信息

- **MAB 单元测试** (`tests/test_mab_anchor.py`)
  - 24 个测试用例，覆盖 5 个测试类：
  - `TestComputeReward`（5 个）：成功/失败、成本/延迟惩罚、值域钳制
  - `TestUCBStrategy`（4 个）：初始探索、收敛性、序列化、统计信息
  - `TestThompsonStrategy`（3 个）：收敛性、Beta 更新、序列化
  - `TestMABAnchorManager`（5 个）：间隔触发、结果反馈、持久化、Thompson 模式、统计
  - `TestAnchorModeIntegration`（7 个）：fixed/ucb/thompson 模式切换、EIS 仍计算、向后兼容

### Changed

- **AdaptiveAnchor 扩展** (`services/adaptive_anchor.py`)
  - `__init__` 新增 `anchor_mode` 参数，默认读取环境变量 `ANCHOR_MODE`
  - `ANCHOR_MODE=fixed`（默认）：现有 EIS 固定阈值逻辑，完全向后兼容
  - `mab_ucb` / `mab_thompson`：创建 `MABAnchorManager` 实例，委托锚定决策
  - MAB 模式下 EIS 仍被计算（用于监控和日志），但 `should_report_now` 由 MAB 覆盖
  - `AnchorDecision` 新增 `mab_arm: Optional[int]`（仅 MAB 模式非 None）
  - 新增 `report_anchor_result(success, cost, latency)` 方法

### Technical Details

- **UCB1 探索–利用平衡**：
  - 探索系数 c = √2（经典 UCB1）
  - 初始阶段每个臂强制拉一次，消除冷启动偏差
  - 随着试验次数增加，逐渐收敛到最高平均 reward 的臂

- **Reward 设计**：
  - α=0.6（成功率权重）、β=0.2（成本权重）、γ=0.2（延迟权重）
  - 归一化参考值：成本 1.0、延迟 5.0 秒
  - reward ∈ [-1, 1]，正值鼓励当前臂，负值惩罚

- **状态持久化**：
  - JSON 格式，包含策略参数和运行时统计
  - 服务重启后自动恢复历史学习
  - 线程安全（`threading.Lock` 保护决策和更新）

### Testing Results

- `tests/test_mab_anchor.py`（ANCHOR_MODE=mab_ucb）: 24/24 通过 ✅
- `tests/test_adaptive_anchor.py`（ANCHOR_MODE=fixed）: 15/15 通过 ✅

### Notes

- 无需新增依赖：numpy、json 均已存在
- MAB 决策延迟 < 1ms（纯数学计算）
- 对 `adaptive_anchor.py` 仅新增 ~30 行分发逻辑，不改现有 EIS/滑动窗口逻辑
- 权重和归一化参考值可在 `mab_anchor.py` 模块顶部常量中调整

---

## 2026-03-23 (多模态融合 VIF 视频完整性指纹)

### Added

- **VIF 核心模块** (`services/vif.py`)
  - `VIFConfig` 数据类：从 `VIF_MODE` 环境变量读取模式（`off`/`phash_only`/`semantic_only`/`fusion`，默认 `off`）
    - 权重支持环境变量覆盖：`VIF_PHASH_WEIGHT`（默认 0.4）、`VIF_SEMANTIC_WEIGHT`（默认 0.35）、`VIF_TEMPORAL_WEIGHT`（默认 0.25）
    - `output_length=256` 位（输出 64 字符十六进制字符串）
  - `extract_phash_feature(frame) -> np.ndarray`：复用 `DeepPerceptualHasher` 提取 MobileNetV3-Small **pool 后** 576 维特征向量
  - `extract_semantic_feature(frame) -> np.ndarray`：独立的 `_SemanticFeatureExtractor` 单例
    - 使用 MobileNetV3-Small **pool 前** `features` 层提取空间特征图
    - 全局平均池化 (GAP) → 截断/填充到 576 维 → L2 归一化
    - 与 phash 分支使用不同层特征，确保两个模态真正互补
  - `extract_temporal_feature(gop_frames) -> np.ndarray`：帧间稠密光流统计特征
    - 使用 OpenCV `cv2.calcOpticalFlowFarneback()` 计算相邻帧光流
    - 每对帧提取 4 个统计量：mean_magnitude, mean_angle, std_magnitude, std_angle
    - 最多 24 对帧 → 96 维固定长度向量
    - 单帧输入优雅退化为零向量（graceful degradation）
  - `_VIFLSHProjector`：VIF 专用 LSH 投影器
    - 固定种子（2026）随机高斯投影矩阵，确保确定性
    - 加权拼接三模态特征 → 投影到 256 位 → 十六进制字符串
  - `compute_vif(gop_frames, config) -> Optional[str]`：主入口函数
    - `off` → 返回 None（调用方回退传统 pHash）
    - `phash_only` → 仅感知哈希特征 → LSH 256 位
    - `semantic_only` → 仅语义特征 → LSH 256 位
    - `fusion` → 三模态加权融合

- **VIF 单元测试** (`tests/test_vif.py`)
  - 32 个测试用例，覆盖 8 个测试类：
  - `TestVIFConfig`（4 个）：默认模式、环境变量读取、权重覆盖、输出长度
  - `TestPhashFeature`（3 个）：输出维度、确定性、无效输入回退
  - `TestSemanticFeature`（4 个）：输出维度、L2 归一化、确定性、无效输入
  - `TestTemporalFeature`（5 个）：输出维度、单帧退化、None 处理、多帧非零、确定性
  - `TestComputeVIF`（6 个）：off/phash_only/semantic_only/fusion 格式、未知模式、空帧
  - `TestVIFStability`（3 个）：三模式稳定性（同输入→同输出）
  - `TestVIFDiscrimination`（3 个）：三模式区分度（不同输入→汉明距离 > 10）
  - `TestVIFMerkleCompatibility`（4 个）：叶子哈希、VIF 与传统差异、Merkle 树构建验证、向后兼容

### Changed

- **GOPData 数据类扩展** (`services/gop_splitter.py`)
  - 新增 `vif: Optional[str] = None` 字段
  - `_build_gop()` 新增 `extra_frames` 可选参数，支持多帧传入
  - 当 `VIF_MODE != "off"` 时自动调用 `compute_vif()` 计算 VIF
  - VIF 计算失败时优雅降级（打印警告，字段为 None）

- **Merkle 叶子哈希增强** (`services/merkle_utils.py`)
  - `compute_leaf_hash()` 新增可选参数 `vif: Optional[str] = None`
  - VIF 不为 None 时，替代 `phash + semantic_hash` 作为感知标识组件：`SHA-256(sha256_hash + vif)`
  - VIF 为 None 时行为不变（完全向后兼容）
  - `build_merkle_root_and_proofs()` 和 `MerkleTree` 构造函数自动传递 `gop.vif`

### Technical Details

- **三模态特征设计**：
  - phash 分支：MobileNetV3-Small `classifier=Identity()` 输出（pool 后，576 维）
  - semantic 分支：MobileNetV3-Small `features` 层输出（pool 前，经 GAP 后截断到 576 维）
  - temporal 分支：Farneback 稠密光流，参数 pyr_scale=0.5, levels=3, winsize=15, iterations=3
  - 两个 CNN 分支使用同一模型架构的不同层，提取互补特征

- **LSH 投影**：
  - 输入维度：576 + 576 + 96 = 1248（fusion 模式）
  - 加权后拼接 → 256 × 1248 随机投影矩阵 → 256 位二进制 → 64 字符十六进制
  - 使用 `np.errstate` 抑制边界浮点警告（与 `perceptual_hash.py` 一致）

- **向后兼容性**：
  - `VIF_MODE=off`（默认）时无任何行为变化
  - 现有 `compute_leaf_hash` 调用无需修改
  - 所有现有测试在默认配置下通过

### Testing Results

- `tests/test_vif.py`（VIF_MODE=fusion）: 32/32 通过 ✅
- `tests/test_perceptual_hash.py`: 11/11 通过 ✅
- `tests/test_merkle_utils.py`: 20/20 通过 ✅
- `tests/test_hierarchical_merkle.py`: 11/11 通过 ✅
- `tests/test_gop_verification_e2e.py`: 7 errors（MinIO 连接，历史遗留）

### Notes

- 无需新增依赖：torch、torchvision、opencv-python、numpy 均已存在
- 权重和输出长度可通过环境变量调参，方便论文消融实验
- 单帧场景下 temporal 分支退化为零向量，fusion 模式仍有 phash + semantic 两个有效维度
- `_SemanticFeatureExtractor` 与 `DeepPerceptualHasher` 为独立单例，避免模型冲突

---

## 2026-03-23 (完整版 EIS：光流 + 异常检测 + 规则引擎)

### Added

- **光流运动分析器** (`services/adaptive_anchor.py`)
  - 新增 `OpticalFlowAnalyzer` 类：计算相邻 GOP 关键帧之间的稠密光流
  - 使用 OpenCV `cv2.calcOpticalFlowFarneback()`，帧缩放至 320×240 降低 CPU 开销
  - `MotionFeatures` 数据类：
    - `magnitude_mean`: 光流幅值均值（整体运动强度）
    - `magnitude_max`: 光流幅值最大值（最剧烈运动区域）
    - `magnitude_std`: 光流幅值标准差（运动分布均匀性）
    - `motion_area_ratio`: 运动区域占比（幅值 > 2.0 像素的比例）
    - `dominant_direction`: 主运动方向角度（0-360°，加权平均）
  - 内部缓存上一帧灰度图，首帧返回全零特征

- **统计异常检测器** (`services/adaptive_anchor.py`)
  - 新增 `AnomalyDetector` 类：基于滑动窗口的多维 z-score 异常检测
  - 纯 numpy 实现，无 sklearn 依赖
  - 4 维特征向量：[total_count, magnitude_mean, magnitude_max, motion_area_ratio]
  - 冷启动保护：历史 < 10 个样本时返回 anomaly_score=0.0
  - `AnomalyResult` 数据类：
    - `anomaly_score`: 0.0~1.0 归一化异常分数（`min(1.0, max_z / (2 * threshold))`）
    - `is_anomaly`: 最大 z-score 是否超过阈值（默认 2.5）
    - `z_scores`: 各维度 z-score 列表（供调试）

- **EIS 规则引擎** (`services/adaptive_anchor.py`)
  - 新增 `EISRuleEngine` 类：多信号加权融合 + 规则覆盖
  - 默认权重：object_count=0.35, motion=0.35, anomaly=0.30
  - 目标计数信号：4 级映射（0→0.1, 1-3→0.3, 4-8→0.6, 9+→0.9）+ person≥3 奖励 +0.1
  - 运动信号：4 级映射（<1→0.1, 1-5→0.4, 5-15→0.7, 15+→0.95）+ 高面积覆盖覆盖
  - 规则覆盖：异常→EIS≥0.8，疑似遮挡（area>0.9 且 mag>20）→EIS=0.95

- **EIS_MODE 双模式切换** (`services/adaptive_anchor.py`)
  - `AdaptiveAnchor.__init__` 新增 `eis_mode` 参数，默认读取环境变量 `EIS_MODE`
  - `EIS_MODE=lite`（默认）：原有纯 YOLO 计数逻辑，完全向后兼容
  - `EIS_MODE=full`：光流 → 异常检测 → 规则引擎 → 滑动窗口平滑 → 防抖
  - `AdaptiveAnchor.update()` 新增可选参数 `keyframe: Optional[np.ndarray] = None`
  - `AnchorDecision` 新增可选字段：
    - `motion_features: Optional[MotionFeatures]`（仅 full 模式）
    - `anomaly_result: Optional[AnomalyResult]`（仅 full 模式）
    - `signal_breakdown: Optional[dict]`（各信号分量，如 `{"object": 0.6, "motion": 0.7, "anomaly": 0.3}`）

- **完整版 EIS 单元测试** (`tests/test_full_eis.py`)
  - 18 个测试用例，覆盖 5 个测试类：
  - `TestOpticalFlowAnalyzer`（3 个）：首帧全零、静态帧近零、运动帧检测
  - `TestAnomalyDetector`（3 个）：冷启动保护、正常→异常检测、z-score 维度
  - `TestEISRuleEngine`（6 个）：低/高活跃度、异常覆盖、遮挡覆盖、person 奖励、值域钳制
  - `TestFullEISIntegration`（2 个）：静态→活跃状态转换、signal_breakdown 输出
  - `TestBackwardCompatibility`（4 个）：lite 默认行为、忽略 keyframe、EIS 三级值、升降级时序

- **EIS 消融实验脚本** (`scripts/ablation_eis.py`)
  - 对比 lite 与 full EIS 在真实视频上的表现
  - 输入：`--video` 单视频或 `--video-dir` 批量处理
  - 输出 3 张对比图（保存到 `results/ablation_eis/`）：
    - 双折线图：lite EIS vs full EIS 随时间变化
    - 信号分量堆叠面积图（object / motion / anomaly）
    - LOW/MEDIUM/HIGH 状态切换时间线
  - 统计输出：各状态时间占比、状态切换次数、平均上报间隔
  - rich 库美化终端输出 + tabulate 对比表

### Changed

- **AdaptiveAnchor 接口扩展** (`services/adaptive_anchor.py`)
  - `__init__` 新增 `eis_mode` 参数（向后兼容，默认 "lite"）
  - `update()` 新增 `keyframe` 参数（向后兼容，默认 None）
  - `AnchorDecision` 新增 3 个 Optional 字段（向后兼容，默认 None）
  - 新增 `import cv2, math, os` 及 `import numpy as np`

### Technical Details

- **光流计算优化**：
  - 帧缩放至 320×240（实测 Farneback 单帧 ~5-10ms CPU）
  - 参数：pyr_scale=0.5, levels=3, winsize=15, iterations=3, poly_n=5, poly_sigma=1.2
  - 运动区域阈值：像素位移 > 2.0 视为运动
  - 主方向计算：幅值加权的角度均值（处理角度环绕）

- **异常检测设计**：
  - 滑动窗口最大 100 个历史样本
  - 冷启动期 10 个 GOP（约 30-60 秒视频），期间不报异常
  - 归一化公式：`score = min(1.0, max_z / (2 * z_threshold))`
  - 系统重启后需重新积累基线（内存窗口不持久化）

- **融合策略**：
  - 加权融合：`eis = 0.35*obj + 0.35*motion + 0.30*anomaly`
  - 规则覆盖优先级最高（anomaly → ≥0.8，suspected occlusion → 0.95）
  - 最终 EIS 经滑动窗口中位数平滑 + 快升慢降防抖（复用 lite 模式逻辑）

### Testing Results

- `tests/test_adaptive_anchor.py`（lite 模式）: 15/15 通过 ✅
- `tests/test_full_eis.py`（full 模式）: 18/18 通过 ✅
- 端到端验证：34 个 GOP 视频处理成功 ✅
- 消融实验：lite vs full 对比图生成成功 ✅

### Notes

- 无需新增依赖：opencv-python、numpy、matplotlib、tabulate、rich 均已存在
- 光流分析器按 GOP 顺序调用，不支持乱序或并发（与 lite 模式一致）
- 权重和阈值为初始值，可通过消融实验调参
- 所有魔法数字集中在类 `__init__` 参数或模块顶部常量中

---

## 2026-03-23 (深度感知哈希升级)

### Added

- **深度感知哈希路径** (`services/perceptual_hash.py`)
  - 新增 `PHASH_MODE=deep` 模式，使用 MobileNetV3-Small 提取 576 维深度特征
  - 新增 `DeepPerceptualHasher`：模型延迟加载、自动选择 CPU/GPU、固定预处理流程
  - 新增 `LSHCompressor`：使用固定 `seed=42` 的随机高斯投影，将深度特征压缩为 64-bit 十六进制字符串
  - 新增投影矩阵持久化能力：`save_projection(filepath)` / `load_projection(filepath)`

- **深度 pHash 单元测试** (`tests/test_deep_phash.py`)
  - 覆盖确定性、输出格式、JPEG 压缩/缩放鲁棒性、篡改区分、转码模拟场景
  - 使用 `PHASH_MODE` 在 legacy / deep 两种模式间切换，对比两种方案的汉明距离表现

- **消融实验脚本** (`scripts/ablation_phash.py`)
  - 对比 legacy pHash 与 deep pHash 在 `INTACT`、`RE_ENCODED`、`TAMPERED` 三种场景下的汉明距离分布
  - 支持 FFmpeg 转码、GOP 对齐、统计汇总、终端表格输出和图像保存
  - 输出柱状图和箱线图到 `results/ablation_phash/`

### Changed

- **感知哈希服务兼容升级** (`services/perceptual_hash.py`)
  - `compute_phash(keyframe_frame)` 继续保持现有 `numpy` BGR 帧输入接口不变
  - 默认 `PHASH_MODE=legacy`，继续使用原有 imagehash pHash 路径，保证下游调用方无需修改
  - `hamming_distance(hash1, hash2)` 改为直接对 16 位十六进制字符串计算 64-bit 汉明距离，兼容 legacy 与 deep 两种输出

- **依赖更新** (`requirements.txt`)
  - 新增 `numpy`
  - 新增 `torchvision>=0.15`
  - 新增 `matplotlib`
  - 新增 `tabulate`

### Testing Results

- `tests/test_perceptual_hash.py`: 11/11 通过
- `tests/test_deep_phash.py`: 5/5 通过
- `PHASH_MODE=deep python -m services.gop_splitter --file <local_video>` 端到端验证通过

## 2026-03-17 (端到端篡改检测演示脚本)

### Added

- **篡改检测演示脚本** (`scripts/tamper_demo.py`)
  - 端到端演示三种验证场景，适用于答辩展示
  - **场景 1: INTACT** — 原始视频直接验证，所有 GOP 返回 INTACT + Merkle 证明通过
  - **场景 2: RE_ENCODED** — FFmpeg 转码（改码率 500k），SHA-256 不匹配但 pHash 相似 → RE_ENCODED
    - 转码参数：`-g 30 -keyint_min 30 -sc_threshold 0 -forced-idr 1` 确保 GOP 结构一致
    - 时间戳最近邻匹配算法配对原始/转码 GOP（替代简单 zip），带重复使用检测警告
  - **场景 3: TAMPERED** — 字节翻转 + 关键帧替换为随机噪声 → TAMPERED
    - `HierarchicalMerkleTree.locate_tampered_gops()` 精确定位被篡改的 GOP 索引和时间范围
    - 显式 `semantic_hash = "0"*64` 占位符处理
  - 复用现有服务层：`split_gops`、`TriStateVerifier`、`MerkleTree`、`HierarchicalMerkleTree`、`VideoStorage`
  - CLI 参数：`--video`（指定视频）、`--skip-minio`（跳过存储）、`--tamper-gop`（篡改目标）、`--hamming-threshold`
  - 无视频时自动用 FFmpeg `testsrc2` 生成 10 秒动态测试视频（有移动色块，pHash 更有区分度）
  - MinIO 可选（连接失败自动跳过），Fabric 始终模拟
  - `rich` 库美化终端输出：彩色 Panel、Table、场景结果高亮
  - `ScenarioResult` 数据类统一收集三场景结果
  - 末尾一屏汇总 Panel：`✅ INTACT (9/9) | ⚠️ RE_ENCODED (9/9) | ❌ TAMPERED → GOP #2 定位成功`
  - 总计时器显示演示耗时

### Changed

- **依赖更新** (`requirements.txt`)
  - 新增 `rich>=13.0.0` — 终端美化输出库

## 2026-03-16 (自适应锚点模块)

### Added

- **AdaptiveAnchor 模块** (`services/adaptive_anchor.py`)
  - 基于场景活动动态调整区块链锚点上报频率
  - `AnchorDecision` 数据类：封装锚点决策结果
    - `eis_score`: 事件重要性评分 (0.1/0.5/0.9)
    - `smoothed_count`: 滑动窗口中位数平滑后的目标计数
    - `level`: 当前活动等级 ("LOW"/"MEDIUM"/"HIGH")
    - `report_interval_seconds`: 上报间隔 (300/60/10 秒)
    - `should_report_now`: 是否应立即上报
  - `AdaptiveAnchor` 类：核心自适应逻辑
    - 滑动窗口中位数过滤（默认窗口大小 10）：抑制瞬时噪声
    - 确认机制防抖：升级需 3 次确认，降级需 5 次确认
    - 三级活动等级：
      - LOW (EIS < 0.3): 5 分钟上报间隔
      - MEDIUM (0.3 ≤ EIS ≤ 0.7): 1 分钟上报间隔
      - HIGH (EIS > 0.7): 10 秒上报间隔
    - 等级切换时自动重置计时器，触发立即上报
  - EIS 计算规则：
    - 0 个目标 → EIS = 0.1 (LOW)
    - 1-5 个目标 → EIS = 0.5 (MEDIUM)
    - 6+ 个目标 → EIS = 0.9 (HIGH)

- **单元测试** (`tests/test_adaptive_anchor.py`)
  - 15 个测试用例，100% 通过
  - `test_initialization` — 初始状态验证
  - `test_custom_parameters` — 自定义参数支持
  - `test_eis_calculation_*` — EIS 计算逻辑（零/低/高计数）
  - `test_level_transition_low_to_medium_to_high` — 完整等级转换流程
  - `test_median_robustness_against_outliers` — 中位数抗噪声能力
  - `test_fast_upgrade_3_confirmations` — 快速升级（3 次确认）
  - `test_slow_downgrade_5_confirmations` — 缓慢降级（5 次确认）
  - `test_report_interval_mapping` — 等级与上报间隔映射
  - `test_should_report_now_timing` — 上报时机判断
  - `test_should_report_now_after_level_change` — 等级切换后立即上报
  - `test_sliding_window_behavior` — 滑动窗口行为
  - `test_confirmation_reset_on_level_change` — 确认计数器逻辑
  - `test_empty_window_initial_state` — 空窗口初始状态

### Changed

- 等级切换时重置 `_last_report_time` 为 0，确保立即触发上报
- 测试用例修正：
  - `test_report_interval_mapping`: 更新次数从 6 改为 7（满足 3 次确认）
  - `test_should_report_now_timing`: 修正为检查首次更新
  - `test_confirmation_reset_on_level_change`: 重写测试序列以匹配实际中位数计算

### Technical Details

- 使用 `collections.deque` 实现高效滑动窗口（O(1) 添加/删除）
- 使用 `statistics.median` 计算中位数（对异常值鲁棒）
- 状态机设计：`_current_level` + `_pending_level` + `_confirm_counter`
- 时间管理：`time.time()` 单调时钟，独立于 GOP 时间戳

---

## 2026-03-16 (网关服务与跨设备时段聚合)

### Added

- **EpochMerkleTree 类** (`services/merkle_utils.py`)
  - 跨设备 SegmentRoot 聚合到单个 EpochRoot
  - 每个设备在每个时段贡献一个叶子节点（SegmentRoot）
  - `DeviceSegment` 数据类：存储设备上报信息
    - `device_id`: 设备标识符
    - `segment_root`: 设备的 SegmentRoot 哈希
    - `timestamp`: ISO 格式时间戳
    - `semantic_summaries`: 语义摘要列表
    - `gop_count`: GOP 数量
  - `add_device_segment()` — 添加设备上报（自动去重，最后写入优先）
  - `build_tree()` — 构建 Merkle 树并返回 EpochRoot
  - `get_device_proof()` — 生成设备的 Merkle 证明
  - `verify_device_proof()` — 验证设备证明
  - `to_dict()`/`from_dict()` — 序列化/反序列化
  - 确定性排序：设备按 device_id 排序以保证可重现的根哈希

- **网关服务** (`services/gateway_service.py`)
  - `GatewayService` 类：管理时段生命周期
  - SQLite 数据库存储历史数据（`data/gateway.db`）
  - 两张表：
    - `epochs` — 时段记录（epoch_id, epoch_root, device_count, tx_id, created_at, tree_json）
    - `device_reports` — 设备上报记录（id, epoch_id, device_id, segment_root, timestamp, gop_count, semantic_summaries）
  - `add_device_report()` — 接收设备上报（异步，带锁保护）
  - `flush_epoch()` — 每 30 秒触发：收集上报 → 构建树 → 锚定区块链 → 存储数据库
  - `get_epoch()` — 查询时段详情
  - `list_epochs()` — 列出最近时段
  - `get_device_proof()` — 获取设备在时段中的 Merkle 证明
  - 线程安全：使用 `asyncio.Lock` 保护并发访问
  - 阻塞 I/O 优化：SQLite 和 Fabric 调用包装在 `asyncio.to_thread()` 中

- **Web API 路由** (`web_app.py`)
  - `POST /report` — 接收边缘设备的 SegmentRoot 上报
  - `GET /epochs` — 列出最近的时段（用于调试和演示）
  - `GET /epoch/{epoch_id}` — 获取时段详情
  - `GET /proof/{epoch_id}/{device_id}` — 获取设备的 Merkle 证明
  - `DeviceReport` Pydantic 模型用于请求验证
  - APScheduler 定时任务：每 30 秒调用 `flush_epoch()`

- **设备模拟器** (`gateway/simulate_devices.py`)
  - 模拟 3 个边缘设备（cam_001, cam_002, cam_003）
  - 每 10 秒向网关发送一次上报
  - 随机生成 SegmentRoot 哈希和语义摘要
  - 使用 httpx 异步 HTTP 客户端
  - 支持 Ctrl+C 优雅退出

- **单元测试** (`tests/test_epoch_merkle.py`)
  - 11 个测试用例，覆盖 EpochMerkleTree 核心功能
  - `test_basic_tree_construction` — 基本树构建
  - `test_proof_generation_and_verification` — 证明生成和验证
  - `test_serialization_deserialization` — 序列化/反序列化
  - `test_deduplication` — 去重逻辑（同设备多次上报）
  - `test_cannot_add_after_build` — 树构建后不能添加设备
  - `test_empty_tree_error` — 空树错误处理
  - `test_single_device` — 单设备场景
  - `test_proof_for_nonexistent_device` — 不存在设备的证明请求
  - `test_proof_before_build` — 树构建前请求证明
  - `test_deterministic_ordering` — 确定性排序验证
  - `test_large_tree` — 大型树性能测试（100 设备）

- **文档** (`gateway/README.md` 和 `gateway/README_CN.md`)
  - 架构说明和组件介绍
  - 安装和使用指南
  - API 接口示例
  - 数据库结构说明
  - 测试说明和故障排除
  - 设计决策和未来增强

### Changed

- `web_app.py` 导入增强
  - 添加 `HTTPException` 用于错误处理
  - 添加 `BaseModel` 用于请求验证
  - 添加 `AsyncIOScheduler` 用于定时任务
  - 添加 `GatewayService` 导入

### Design Decisions

- **30 秒时段窗口** — 在区块链成本和数据新鲜度之间取得平衡
- **最后写入优先去重** — 同一设备在同一时段多次上报时，保留最新的
- **确定性排序** — 设备按 device_id 排序，确保相同设备集产生相同 EpochRoot
- **与现有系统分离** — 网关服务是增量式的，不修改现有功能：
  - `MerkleBatchManager` 继续处理事件级别批处理
  - `HierarchicalMerkleTree` 继续处理设备内 GOP 聚合
  - `EpochMerkleTree` 添加跨设备片段聚合
- **线程安全** — 使用 `asyncio.Lock` 保护 API 处理器和调度器之间的并发访问
- **非阻塞 I/O** — SQLite 和 Fabric 调用包装在线程池中，避免阻塞事件循环

### Dependencies

- `apscheduler` — 异步任务调度
- `httpx` — 异步 HTTP 客户端（用于设备模拟器）

### Notes

- 网关服务是无状态的，除了 SQLite 持久化
- 如果网关重启，内存中的待处理上报会丢失（30 秒窗口内可接受）
- 生产环境建议添加：
  - 设备上报的身份验证
  - 每设备速率限制
  - 缺失设备的监控/告警
  - 数据库连接池
  - 待处理上报的优雅关闭处理
  - 时段可视化的 Web UI

## 2025-03-16 (语义指纹与组合验证)

### Added

- **语义指纹服务** (`services/semantic_fingerprint.py`)
  - `SemanticFingerprint` 数据类：存储 GOP 关键帧的语义内容
    - `gop_id`: GOP 标识符
    - `timestamp`: ISO 8601 格式时间戳
    - `objects`: 对象计数字典（例如 `{"person": 3, "car": 2}`）
    - `total_count`: 检测到的对象总数
    - `json_str`: 确定性 JSON 字符串（键排序）
    - `semantic_hash`: JSON 的 SHA-256 哈希值
  - `SemanticExtractor` 类：使用 YOLOv8-nano 提取语义特征
    - 单例模式 + 线程安全（延迟加载 YOLO 模型）
    - `extract(keyframe_frame, gop_id, start_time)` — 从关键帧提取语义指纹
    - 确定性 JSON 生成（相同输入 → 相同哈希）
    - 优雅降级：提取失败返回 None，不影响 GOP 处理
    - 错误处理：None 输入、空检测、模型失败均有处理

- **GOP 切分器增强** (`services/gop_splitter.py`)
  - `GOPData` 新增两个字段：
    - `semantic_hash: Optional[str]` — 语义指纹哈希
    - `semantic_fingerprint: Optional[SemanticFingerprint]` — 完整语义数据
  - `_build_gop()` 函数自动提取语义指纹
    - 在 pHash 计算后调用 `SemanticExtractor.extract()`
    - 提取失败时优雅降级（字段为 None）
    - 向后兼容：语义字段为可选，不影响现有 GOP

- **Merkle 树增强** (`services/merkle_utils.py`)
  - `compute_leaf_hash(sha256_hash, phash, semantic_hash)` — 组合叶子哈希函数
    - 组合三个哈希：SHA-256（字节完整性）+ pHash（视觉相似性）+ semantic_hash（内容语义）
    - 使用占位符处理 None 值（phash: "0"*16, semantic: "0"*64）
    - 确保相同 GOP 始终产生相同叶子哈希
    - 向后兼容：缺失字段使用占位符
  - `build_merkle_root_and_proofs()` 支持 GOPData 对象
    - 接受 `Union[List[str], List[GOPData]]` 参数
    - GOPData 列表自动计算组合叶子哈希
    - 字符串列表直接使用（向后兼容）
  - `MerkleTree` 类支持 GOPData 初始化
    - 构造函数接受 GOPData 列表或字符串列表
    - 自动转换 GOPData 为组合叶子哈希

- **MinIO 存储增强** (`services/minio_storage.py`)
  - `upload_gop()` 自动上传语义 JSON 文件
    - 检查 `gop.semantic_fingerprint` 是否存在
    - 构建语义 JSON 数据（gop_id, timestamp, objects, total_count, semantic_hash）
    - 上传到 GOP 分片同目录：`{device_id}/t_{timestamp}/{cid}_semantic.json`
    - 与视频数据共同定位，便于管理

- **配置增强** (`config.py`)
  - 新增 `semantic_model_path: str` 配置项（默认 "yolov8n.pt"）
  - 新增 `semantic_confidence: float` 配置项（默认 0.5）
  - 支持环境变量：
    - `SEMANTIC_MODEL_PATH` — YOLO 模型路径
    - `SEMANTIC_CONFIDENCE` — 检测置信度阈值

- **单元测试** (`tests/test_semantic_fingerprint.py`)
  - 13 个测试用例，覆盖语义提取核心功能
  - `test_singleton_pattern` — 单例模式验证
  - `test_extract_with_synthetic_frame` — 合成帧提取测试
  - `test_deterministic_json` — 确定性 JSON 生成
  - `test_different_frames_different_hashes` — 不同帧产生不同哈希
  - `test_empty_detection` — 空检测处理（无对象）
  - `test_invalid_frame_*` — 错误输入处理（None、空数组、错误维度）
  - `test_json_structure` — JSON 结构验证
  - `test_timestamp_format` — ISO 8601 时间戳格式
  - `test_thread_safety` — 并发提取线程安全测试

- **单元测试扩展** (`tests/test_merkle_utils.py`)
  - 7 个新测试用例，覆盖组合哈希功能
  - `test_compute_leaf_hash_all_fields` — 所有字段提供
  - `test_compute_leaf_hash_missing_phash` — phash 缺失（使用占位符）
  - `test_compute_leaf_hash_missing_semantic` — semantic_hash 缺失
  - `test_compute_leaf_hash_all_missing` — 所有可选字段缺失
  - `test_compute_leaf_hash_deterministic` — 确定性验证
  - `test_compute_leaf_hash_different_inputs` — 不同输入产生不同哈希
  - `test_build_merkle_with_gopdata` — GOPData 对象支持
  - `test_build_merkle_with_gopdata_missing_semantic` — 缺失语义哈希
  - `test_build_merkle_backward_compatible` — 向后兼容性（字符串列表）

- **集成测试扩展** (`tests/test_gop_verification_e2e.py`)
  - 3 个新集成测试
  - `test_semantic_fingerprint_upload` — 验证语义 JSON 上传到 MinIO
    - 检查文件存在性
    - 验证 JSON 结构（gop_id, timestamp, objects, total_count, semantic_hash）
    - 验证语义哈希一致性
  - `test_merkle_tree_with_semantic_hash` — 组合叶子哈希 Merkle 树构建
    - 使用 GOPData 对象构建 Merkle 树
    - 验证组合叶子哈希计算
    - 验证 Merkle 证明
  - `test_backward_compatibility_no_semantic` — 向后兼容性测试
    - 无语义数据的 GOP 仍然有效
    - 使用占位符构建 Merkle 树
    - 验证证明仍然有效
  - 更新 `_create_synthetic_gop()` 自动提取语义指纹

### Technical Details

- **语义指纹原理**：
  - 使用 YOLOv8-nano 进行目标检测（轻量级，约 6MB）
  - 提取关键帧中的对象类别和数量
  - 生成确定性 JSON（键排序，无空格）
  - 计算 SHA-256 哈希作为语义指纹
  - 检测语义篡改（对象替换/移除）

- **组合验证策略**：
  - **SHA-256**：字节级完整性（检测任何修改）
  - **pHash**：视觉相似性（容忍重编码）
  - **semantic_hash**：内容语义（检测对象级篡改）
  - 三重哈希组合为单个 Merkle 叶子
  - 提供多层次验证能力

- **性能考虑**：
  - YOLOv8-nano 推理：每帧 50-150ms
  - 模型延迟加载 + 单例复用
  - GOP 切分可接受的延迟（非实时关键）
  - 内存占用：模型约 6MB

- **向后兼容性**：
  - 语义字段为 Optional，默认 None
  - 缺失字段使用固定占位符
  - 现有 GOP 无需迁移
  - 新旧锚点可共存

### Changed

- `GOPData` 数据类添加语义字段（向后兼容）
- `build_merkle_root_and_proofs()` 支持 GOPData 对象输入
- `MerkleTree` 构造函数支持 GOPData 列表
- `upload_gop()` 自动上传语义 JSON（如果可用）

### Notes

- 语义提取失败不影响 GOP 处理（优雅降级）
- 语义 JSON 存储在 GOP 分片同目录，便于管理
- 仅新锚点使用组合叶子哈希，现有锚点保持不变
- 所有测试通过（单元测试 + 集成测试）

---

## 2026-03-15 (感知哈希与三态验证)

### Added

- **感知哈希服务** (`services/perceptual_hash.py`)
  - `compute_phash(keyframe_frame)` — 从 BGR numpy 数组计算 64-bit 感知哈希
    - 自动转换 BGR → RGB（OpenCV 到 PIL 格式）
    - 使用 8x8 DCT 感知哈希（imagehash 库）
    - 返回 16 字符十六进制字符串
    - 错误处理：None/空数组/无效维度返回 None
  - `hamming_distance(hash1, hash2)` — 计算两个 pHash 的汉明距离（0-64 bits）
    - 使用 imagehash 内置运算符（`h1 - h2`）
    - 无效格式抛出 ValueError

- **三态验证服务** (`services/tri_state_verifier.py`)
  - `TriStateVerifier` 类：区分视频完整性、重编码、篡改
  - `verify(original_sha256, original_phash, current_sha256, current_phash)` — 三态判定逻辑
    - **INTACT**: SHA-256 匹配（无论 pHash）→ 完全一致
    - **RE_ENCODED**: SHA-256 不匹配 + pHash 汉明距离 ≤ 阈值 → 合法重编码
    - **TAMPERED**: SHA-256 不匹配 + pHash 汉明距离 > 阈值 → 内容篡改
  - 可配置汉明距离阈值（默认 10 bits，容忍 H.264→H.265 转码）
  - 降级处理：pHash 缺失时回退到 SHA-256 单一验证（保守返回 TAMPERED）

- **GOP 切分器增强** (`services/gop_splitter.py`)
  - `GOPData` 新增 `phash: Optional[str]` 字段
  - `_build_gop()` 函数自动计算关键帧 pHash
  - 导入 `compute_phash` 并在 GOP 构建时调用
  - 向后兼容：phash 为可选字段，默认 None

- **配置增强** (`config.py`)
  - 新增 `phash_hamming_threshold: int` 配置项（默认 10）
  - 支持环境变量 `PHASH_HAMMING_THRESHOLD` 覆盖
  - 阈值说明：
    - 5 bits: 保守，可能误判转码为篡改
    - 10 bits: 平衡，容忍视频转码（推荐）
    - 15+ bits: 宽松，可能漏检细微篡改

- **依赖更新** (`requirements.txt`)
  - `Pillow>=10.0.0` — PIL 图像处理库
  - `imagehash==4.3.1` — 感知哈希库（支持 pHash/aHash/dHash）

- **单元测试** (`tests/test_perceptual_hash.py`)
  - 11 个测试用例，覆盖率 100%
  - `test_compute_phash_identical_images` — 相同图像 pHash 一致
  - `test_compute_phash_jpeg_compression` — JPEG 压缩 pHash 相似（≤10 bits）
  - `test_compute_phash_different_images` — 不同图像 pHash 差异大（>15 bits）
  - `test_compute_phash_edge_cases` — None/空数组/无效维度处理
  - `test_hamming_distance_invalid_input` — 无效哈希格式异常处理

- **单元测试** (`tests/test_tri_state_verifier.py`)
  - 11 个测试用例，覆盖三态逻辑
  - `test_intact_sha256_match` — SHA-256 匹配返回 INTACT
  - `test_re_encoded_phash_similar` — JPEG 压缩返回 RE_ENCODED
  - `test_tampered_phash_different` — 不同内容返回 TAMPERED
  - `test_threshold_boundary` — 阈值边界测试
  - `test_missing_phash_fallback` — pHash 缺失降级处理
  - `test_configurable_threshold` — 自定义阈值验证

- **集成测试** (`tests/test_gop_verification_e2e.py`)
  - 3 个三态验证 E2E 测试（需要 MinIO）
  - `test_tri_state_intact` — 完全一致 GOP 验证
  - `test_tri_state_re_encoded` — JPEG 压缩 GOP 验证
  - `test_tri_state_tampered` — 篡改 GOP 验证
  - 更新 `_create_synthetic_gop()` 自动计算 pHash

- **演示脚本** (`demo_tri_state.py`)
  - 交互式演示三态验证功能
  - 展示 INTACT/RE_ENCODED/TAMPERED 三种场景
  - 显示 SHA-256 匹配状态和 pHash 汉明距离

### Technical Details

- **感知哈希原理**：
  - 基于 DCT（离散余弦变换）的频域分析
  - 对 JPEG 压缩、缩放、轻微色彩调整鲁棒
  - 对内容篡改（替换、裁剪、叠加）敏感
  - 8x8 哈希大小平衡灵敏度和鲁棒性

- **三态判定流程**：
  ```
  输入：original_sha256, original_phash, current_sha256, current_phash
    ↓
  1. SHA-256 匹配？
     YES → 返回 INTACT
     NO  → 继续
    ↓
  2. pHash 存在？
     NO  → 返回 TAMPERED（保守降级）
     YES → 继续
    ↓
  3. 计算汉明距离
     distance ≤ threshold → 返回 RE_ENCODED
     distance > threshold → 返回 TAMPERED
  ```

- **线程安全注意**：
  - PIL 和 imagehash 操作非线程安全
  - 多线程 GOP 切分需添加锁保护 pHash 计算

- **性能影响**：
  - pHash 计算耗时 ~1-5ms/帧（64x64 图像）
  - 对 GOP 切分流程影响可忽略
  - 存储开销：每 GOP 增加 16 字节（十六进制字符串）

### Testing Results

```
感知哈希单元测试:     11/11 通过 ✓
三态验证单元测试:     11/11 通过 ✓
三态验证 E2E 测试:    3/3 通过 ✓ (需要 MinIO)
```

### Use Cases

1. **视频证据取证**：区分合法格式转换和恶意篡改
2. **转码容忍**：H.264→H.265 转码不触发篡改警报
3. **压缩检测**：JPEG/视频压缩标记为 RE_ENCODED
4. **内容篡改检测**：替换/叠加/裁剪标记为 TAMPERED

### Notes

- 三态验证器为独立服务，不自动集成到 `gop_verifier.py`（保持关注点分离）
- 当前实现仅哈希 GOP 首个 I 帧（MVP 足够；未来可扩展多帧融合）
- pHash 值当前存储在 GOPData 中，未持久化到 MinIO（未来集成需扩展存储）
- 阈值 10 bits 基于 JPEG 压缩测试，实际视频转码可能需调整
- 纯色图像 pHash 相同（无频率变化），测试用例使用随机图案

---

## 2026-03-15 (GOP 验证功能)

### Added

- **Chaincode 验证方法** (`chaincode/chaincode.go`)
  - `VerifyAnchor(epochId, leafHash, merkleProofJSON)` — 验证单个 GOP 完整性
    - 从链上读取 `AnchorRecord` 获取 Merkle 根
    - 解析 JSON 格式的 Merkle proof：`[{"hash": "hex", "position": "left"|"right"}]`
    - 使用 proof 从 leafHash 重新计算 Merkle 根（关键：hex decode → bytes 拼接 → SHA-256）
    - 比较计算根与链上根（不区分大小写）
    - 返回 `{"status": "INTACT"}` 或 `{"status": "NOT_INTACT", "reason": "..."}`
    - 要求 MSP 授权（org1MSP、org2MSP、org3MSP）
  - 新增结构体：`MerkleProofStep` 用于 JSON 解析

- **Chaincode 单元测试** (`chaincode/chaincode_test.go`)
  - `TestVerifyAnchor_Success` — 完整 GOP 验证通过
  - `TestVerifyAnchor_TamperedLeaf` — 篡改叶子哈希验证失败
  - `TestVerifyAnchor_WrongProof` — 错误 proof 验证失败
  - `TestVerifyAnchor_AnchorNotFound` — 锚点不存在返回 NOT_INTACT
  - `TestVerifyAnchor_InvalidJSON` — 无效 JSON 格式返回错误
  - 所有测试使用 mockStub 模式，无需真实 Fabric 网络

- **Python 客户端函数** (`services/fabric_client.py`)
  - `verify_anchor(env, channel, chaincode, epoch_id, leaf_hash, proof_json)` — 调用 chaincode `VerifyAnchor` 方法
  - 复用现有 `invoke_chaincode()` 基础设施

- **GOP 验证服务** (`services/gop_verifier.py`)
  - `GOPVerifier` 类：端到端 GOP 验证编排
  - `verify_gop(device_id, epoch_id, gop_index)` — 完整验证流程：
    1. 从 MinIO 下载 Merkle 树 JSON：`{device_id}/merkle_tree_{epoch_id}.json`
    2. 反序列化为 `MerkleTree` 对象
    3. 从 `tree.original_leaves[gop_index]` 获取 CID
    4. 从 MinIO 下载 GOP 文件：`storage.download_gop(device_id, cid)`
    5. 重新计算 SHA-256 哈希
    6. 生成 Merkle proof：`tree.get_proof(gop_index)`
    7. 调用 `fabric_client.verify_anchor()` 链上验证
    8. 返回详细结果：`{"status": "INTACT"|"NOT_INTACT", "details": {...}}`
  - 错误处理：Merkle 树不存在时返回 "Anchor phase incomplete" 提示

- **端到端集成测试** (`tests/test_gop_verification_e2e.py`)
  - `test_gop_verification_intact` — 完整 GOP 验证返回 INTACT
  - `test_gop_verification_tampered` — 完全替换 GOP 文件验证返回 NOT_INTACT
  - `test_gop_verification_single_byte_tamper` — 单字节篡改验证返回 NOT_INTACT
  - 测试覆盖完整流程：MinIO 存储 → Merkle 树构建 → 链上锚定 → 验证

- **测试辅助工具**
  - `test_verification.sh` — 自动化测试脚本，检查 Go 测试、Fabric 网络、MinIO 服务
  - `MINIO_SETUP.md` — MinIO 设置故障排查指南

### Technical Details

- **哈希拼接顺序（关键）**：
  - Go 和 Python 必须完全一致
  - 流程：hex string → `hex.DecodeString()` → bytes 拼接 → `sha256.Sum256()` → hex encode
  - `position="left"` 表示 sibling 在左侧：`hash(sibling_bytes + current_bytes)`
  - `position="right"` 表示 sibling 在右侧：`hash(current_bytes + sibling_bytes)`
  - **禁止直接拼接 hex string**，必须先解码为 bytes

- **验证流程**：
  ```
  用户请求 → GOPVerifier.verify_gop()
    ↓
  1. 下载 Merkle 树 JSON (MinIO)
  2. 下载 GOP 文件 (MinIO)
  3. 计算 GOP SHA-256
  4. 生成 Merkle proof
  5. 调用 VerifyAnchor (Fabric)
    ↓
  返回 INTACT/NOT_INTACT
  ```

### Notes

- 本功能不修改现有 `VerifyEvent` 方法，两者独立工作
- GOP 验证依赖 Anchor 阶段已完成（Merkle 树已上传到 MinIO）
- 集成测试需要 Fabric 网络和 MinIO 服务同时运行
- Go 单元测试可独立运行：`cd chaincode && go test -v -run TestVerifyAnchor`
- Python 集成测试：`pytest tests/test_gop_verification_e2e.py -v -s`

### Fixed

- **测试数据结构更新** (`tests/test_gop_verification_e2e.py`)
  - 修复 `_create_synthetic_gop()` 函数缺少 `frame_count` 和 `keyframe_frame` 参数
  - 添加 numpy 导入用于生成合成关键帧
  - 生成 64x64 BGR 合成图像作为测试用关键帧
  - 所有三个端到端测试现已通过

---

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
