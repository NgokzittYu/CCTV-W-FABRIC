# 网关服务 - 多设备时段聚合

## 概述

网关服务将来自多个边缘设备的 SegmentRoot 聚合到时段级别的 Merkle 树中，每 30 秒将其锚定到区块链上。

## 架构

```
边缘设备 (cam_001, cam_002, cam_003)
    ↓ POST /report (每 10 秒)
网关服务
    ↓ 将上报聚合到时段 (每 30 秒)
EpochMerkleTree (设备 SegmentRoot 作为叶子节点)
    ↓ 将 EpochRoot 锚定到区块链
Fabric 区块链
```

## 组件

### 1. EpochMerkleTree (`services/merkle_utils.py`)
- 将多个设备的 SegmentRoot 聚合为单个 EpochRoot
- 每个设备在每个时段贡献一个叶子节点
- 支持证明生成和验证
- 可序列化为 JSON 以持久化

### 2. GatewayService (`services/gateway_service.py`)
- 管理时段生命周期（收集 → 构建 → 锚定 → 存储）
- 使用 SQLite 数据库存储历史数据
- 自动去重（每个设备采用最后写入优先策略）
- 使用 asyncio.Lock 保证线程安全

### 3. Web API 路由 (`web_app.py`)
- `POST /report` - 接收设备上报
- `GET /epochs` - 列出最近的时段
- `GET /epoch/{epoch_id}` - 获取时段详情
- `GET /proof/{epoch_id}/{device_id}` - 获取 Merkle 证明

### 4. 设备模拟器 (`gateway/simulate_devices.py`)
- 模拟 3 个边缘设备发送上报
- 随机生成哈希用于测试
- 可配置上报间隔

## 安装

```bash
pip install apscheduler httpx
```

## 使用方法

### 启动网关服务器

```bash
python web_app.py
```

服务器将：
- 在 `http://localhost:8000` 启动
- 初始化网关服务，SQLite 数据库位于 `data/gateway.db`
- 每 30 秒调度一次时段刷新

### 运行设备模拟

在另一个终端中：

```bash
python gateway/simulate_devices.py
```

这将模拟 3 个设备（`cam_001`、`cam_002`、`cam_003`）每 10 秒发送一次上报。

### 查询时段

列出最近的时段：
```bash
curl http://localhost:8000/epochs
```

获取时段详情：
```bash
curl http://localhost:8000/epoch/epoch_20260316_142500
```

获取设备证明：
```bash
curl http://localhost:8000/proof/epoch_20260316_142500/cam_001
```

### 手动发送设备上报

```bash
curl -X POST http://localhost:8000/report \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "cam_001",
    "segment_root": "a3f8c1d2e5b6...",
    "timestamp": "2026-03-16T14:25:00Z",
    "semantic_summaries": ["检测到车辆", "交通正常"],
    "gop_count": 150
  }'
```

## 数据库结构

### epochs 表
- `epoch_id` (主键) - 唯一时段标识符
- `epoch_root` - 所有设备 SegmentRoot 的 Merkle 根
- `device_count` - 此时段中的设备数量
- `tx_id` - 区块链交易 ID
- `created_at` - 时间戳
- `tree_json` - 序列化的 EpochMerkleTree

### device_reports 表
- `id` (主键) - 自增 ID
- `epoch_id` - 外键，关联到 epochs 表
- `device_id` - 设备标识符
- `segment_root` - 设备的 SegmentRoot 哈希
- `timestamp` - 上报时间戳
- `gop_count` - 片段中的 GOP 数量
- `semantic_summaries` - 语义摘要的 JSON 数组

## 测试

运行单元测试：
```bash
pytest tests/test_epoch_merkle.py -v
```

所有 11 个测试应该通过：
- 基本树构建
- 证明生成和验证
- 序列化/反序列化
- 去重逻辑
- 错误处理
- 确定性排序
- 大型树性能

## 设计决策

1. **30 秒时段窗口** - 在区块链成本和数据新鲜度之间取得平衡
2. **最后写入优先的去重策略** - 对重复上报采用简单的冲突解决方案
3. **Asyncio.Lock** - 保护 API 处理器和调度器之间的并发访问
4. **阻塞 I/O 使用线程池** - SQLite 和 Fabric 调用包装在 `asyncio.to_thread()` 中
5. **确定性排序** - 设备按 device_id 排序以获得可重现的根哈希
6. **与 MerkleBatchManager 分离** - 网关在设备-片段级别操作，MerkleBatchManager 在事件级别操作

## 与现有系统的集成

网关服务是**增量式**的，不修改现有功能：
- `MerkleBatchManager` 继续处理事件级别的批处理
- `HierarchicalMerkleTree` 继续处理设备内的 GOP 聚合
- `EpochMerkleTree` 添加跨设备的片段聚合

## 故障排除

**导入时调度器错误：**
- 通过将调度器初始化移至 `@app.on_event("startup")` 修复
- 调度器需要运行中的事件循环

**数据库锁定：**
- 确保只有一个网关实例在运行
- 检查 `data/gateway.db-journal` 是否有陈旧的锁

**缺失上报：**
- 检查设备模拟器是否在运行
- 验证到网关的网络连接
- 检查网关日志中的错误

## 未来增强

- 设备上报的身份验证
- 每个设备的速率限制
- 缺失设备的监控/告警
- 数据库连接池
- 待处理上报的优雅关闭处理
- 时段可视化的 Web UI
