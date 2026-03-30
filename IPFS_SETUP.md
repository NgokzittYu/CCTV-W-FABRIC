# IPFS 去中心化存储 — 安装与启动指南

本项目使用 IPFS (InterPlanetary File System) 作为 GOP 视频分片的去中心化内容寻址存储层。

## 快速启动（Docker Compose 三节点集群）

### 前置条件
- Docker Desktop 已安装并运行
- docker compose v2+ 可用

### 1. 启动集群

```bash
docker compose -f docker-compose.ipfs.yml up -d
```

### 2. 验证节点状态

```bash
# 检查三个节点是否运行
docker compose -f docker-compose.ipfs.yml ps

# 查看 node0 的 Peer ID
docker exec cctv-ipfs-node0 ipfs id

# 测试上传和下载
echo "hello CCTV-W-FABRIC" | docker exec -i cctv-ipfs-node0 ipfs add
# 输出类似: added QmXXX hello-cctv

# 从 node1 下载 node0 上传的内容（验证去中心化）
docker exec cctv-ipfs-node1 ipfs cat <上一步输出的CID>
```

### 3. 互联节点（可选，本地 Docker 网络通常自动发现）

如果节点间未自动发现，手动互联：

```bash
# 获取 node0 的地址
NODE0_ADDR=$(docker exec cctv-ipfs-node0 ipfs id -f '<addrs>' | head -1)

# 让 node1 和 node2 连接 node0
docker exec cctv-ipfs-node1 ipfs swarm connect $NODE0_ADDR
docker exec cctv-ipfs-node2 ipfs swarm connect $NODE0_ADDR
```

## 端口映射

| 节点 | Swarm (P2P) | API (应用连接) | Gateway (HTTP) |
|------|-------------|---------------|----------------|
| node0 | 4001 | **5001** | 8080 |
| node1 | 4002 | 5002 | 8081 |
| node2 | 4003 | 5003 | 8082 |

- **API 端口**：应用通过 `http://localhost:5001` 连接主节点
- **Gateway 端口**：浏览器通过 `http://localhost:8080/ipfs/<CID>` 访问内容
- **WebUI**：访问 `http://localhost:5001/webui` 查看节点状态

## 环境变量配置

在 `.env` 文件中设置：

```bash
# IPFS 配置
IPFS_API_URL=http://localhost:5001
IPFS_GATEWAY_URL=http://localhost:8080
IPFS_PIN_ENABLED=true
```

## 常用操作

### 查看存储使用情况

```bash
docker exec cctv-ipfs-node0 ipfs repo stat
```

### 列出已 Pin 的内容

```bash
docker exec cctv-ipfs-node0 ipfs pin ls --type=recursive
```

### 手动 GC（清理未 Pin 的内容）

```bash
docker exec cctv-ipfs-node0 ipfs repo gc
```

### 停止集群

```bash
docker compose -f docker-compose.ipfs.yml down
```

### 完全清除数据（谨慎）

```bash
docker compose -f docker-compose.ipfs.yml down -v
```

## 故障排查

### 1. 节点启动失败
```bash
# 查看日志
docker compose -f docker-compose.ipfs.yml logs ipfs-node0
```

### 2. API 连接被拒
- 确认容器正在运行：`docker ps | grep ipfs`
- 检查端口占用：`lsof -i :5001`
- Kubo 默认只允许本地 API 访问，Docker 端口映射已处理

### 3. 跨节点内容获取失败
- 确认节点间已互联：`docker exec cctv-ipfs-node0 ipfs swarm peers`
- 确认内容已 Pin：`docker exec cctv-ipfs-node0 ipfs pin ls | grep <CID>`

### 4. 磁盘空间不足
```bash
# 检查各节点存储
docker exec cctv-ipfs-node0 ipfs repo stat
# 清理未 Pin 内容
docker exec cctv-ipfs-node0 ipfs repo gc
```
