# MinIO 设置指南

## 问题诊断

您的 Docker 容器一直处于 "Created" 状态无法启动。这通常是以下原因之一：

1. Docker Desktop 需要重启
2. 端口冲突
3. 资源限制

## 解决方案

### 方案 1: 重启 Docker Desktop（推荐）

1. 完全退出 Docker Desktop
2. 重新打开 Docker Desktop
3. 等待 Docker 完全启动（图标变绿）
4. 运行以下命令：

```bash
# 清理旧容器
docker rm -f $(docker ps -aq --filter "ancestor=minio/minio")

# 启动 MinIO
docker run -d \
  -p 9000:9000 \
  -p 9001:9001 \
  --name minio \
  -e "MINIO_ROOT_USER=minioadmin" \
  -e "MINIO_ROOT_PASSWORD=minioadmin" \
  minio/minio server /data --console-address ":9001"

# 验证
docker ps | grep minio
curl http://localhost:9000/minio/health/live
```

### 方案 2: 使用 Homebrew 安装本地版本

如果 Docker 持续有问题，可以直接在 macOS 上安装 MinIO：

```bash
# 安装
brew install minio/stable/minio

# 启动（在新终端窗口）
mkdir -p ~/minio-data
minio server ~/minio-data --console-address ":9001"
```

默认凭证：
- 用户名: minioadmin
- 密码: minioadmin

### 方案 3: 修改测试配置使用现有 MinIO

如果您已经有运行中的 MinIO 实例（不同端口），修改配置文件：

```python
# config.py
MINIO_ENDPOINT = "localhost:YOUR_PORT"  # 例如 localhost:9002
```

## 验证 MinIO 是否正常

运行以下命令验证：

```bash
# 检查健康状态
curl http://localhost:9000/minio/health/live

# 或者访问 Web 控制台
open http://localhost:9001
```

## 运行测试

MinIO 启动后，运行测试：

```bash
cd /Users/ngokzit/Documents/CCTV-W-FABRIC-main

# 运行 Go 单元测试
cd chaincode && go test -v -run TestVerifyAnchor

# 运行 Python 集成测试（需要 Fabric 网络）
cd .. && pytest tests/test_gop_verification_e2e.py -v -s
```

## 当前状态

- ✅ Go 单元测试已通过
- ✅ Fabric 网络运行中
- ❌ MinIO 服务需要手动启动

请选择上述方案之一启动 MinIO，然后继续测试。
