# Fabric 网络清理与重建指南

## 🧹 完整清理步骤

### 方法 1: 使用官方脚本清理（推荐）

```bash
# 进入 Fabric 测试网络目录
cd ~/projects/fabric-samples/test-network

# 停止并清理所有容器、网络、卷
./network.sh down

# 如果需要更彻底的清理，添加 -v 参数删除卷
./network.sh down -v
```

### 方法 2: 手动清理（如果脚本失败）

```bash
# 1. 停止所有 Fabric 相关容器
docker stop $(docker ps -a | grep hyperledger | awk '{print $1}')

# 2. 删除所有 Fabric 相关容器
docker rm $(docker ps -a | grep hyperledger | awk '{print $1}')

# 3. 删除所有 Fabric 相关镜像（可选，会重新下载）
docker rmi $(docker images | grep hyperledger | awk '{print $3}')

# 4. 删除所有 Docker 卷
docker volume prune -f

# 5. 删除所有 Docker 网络
docker network prune -f

# 6. 清理本地生成的证书和配置文件
cd ~/projects/fabric-samples/test-network
rm -rf organizations/peerOrganizations
rm -rf organizations/ordererOrganizations
rm -rf channel-artifacts
rm -rf system-genesis-block
rm -rf log.txt
```

### 方法 3: 完全重置（最彻底）

```bash
# 停止所有 Docker 容器
docker stop $(docker ps -aq)

# 删除所有 Docker 容器
docker rm $(docker ps -aq)

# 删除所有 Docker 卷
docker volume rm $(docker volume ls -q)

# 删除所有 Docker 网络
docker network rm $(docker network ls -q)

# 清理 Docker 系统
docker system prune -a --volumes -f
```

## 🚀 重建网络步骤

### 步骤 1: 启动 3 组织网络

```bash
cd ~/projects/fabric-samples/test-network

# 启动网络并创建通道
./network.sh up createChannel -c mychannel -ca

# 如果需要指定 3 个组织（如果你的脚本支持）
# ./network.sh up createChannel -c mychannel -ca -s couchdb
```

### 步骤 2: 部署链码

```bash
# 部署 evidence 链码（带双重背书策略和私有数据集合）
./network.sh deployCC \
  -ccn evidence \
  -ccp /Users/ngokzit/Documents/CCTV-W-FABRIC-main/chaincode \
  -ccl go \
  -ccep "AND('Org1MSP.peer','Org2MSP.peer')" \
  -cccg /Users/ngokzit/Documents/CCTV-W-FABRIC-main/chaincode/collections_config.json
```

### 步骤 3: 验证网络状态

```bash
# 查看运行中的容器
docker ps

# 应该看到以下容器：
# - peer0.org1.example.com
# - peer0.org2.example.com
# - orderer.example.com
# - ca_org1
# - ca_org2
# - ca_orderer

# 测试链码调用
cd ~/projects/fabric-samples/test-network

# 设置环境变量（Org1）
export PATH=${PWD}/../bin:$PATH
export FABRIC_CFG_PATH=$PWD/../config/
export CORE_PEER_TLS_ENABLED=true
export CORE_PEER_LOCALMSPID="Org1MSP"
export CORE_PEER_TLS_ROOTCERT_FILE=${PWD}/organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt
export CORE_PEER_MSPCONFIGPATH=${PWD}/organizations/peerOrganizations/org1.example.com/users/Admin@org1.example.com/msp
export CORE_PEER_ADDRESS=localhost:7051

# 测试链码初始化
peer chaincode invoke \
  -o localhost:7050 \
  --ordererTLSHostnameOverride orderer.example.com \
  --tls \
  --cafile "${PWD}/organizations/ordererOrganizations/example.com/orderers/orderer.example.com/msp/tlscacerts/tlsca.example.com-cert.pem" \
  -C mychannel \
  -n evidence \
  --peerAddresses localhost:7051 \
  --tlsRootCertFiles "${PWD}/organizations/peerOrganizations/org1.example.com/peers/peer0.org1.example.com/tls/ca.crt" \
  --peerAddresses localhost:9051 \
  --tlsRootCertFiles "${PWD}/organizations/peerOrganizations/org2.example.com/peers/peer0.org2.example.com/tls/ca.crt" \
  -c '{"function":"InitLedger","Args":[]}'
```

## 🔍 故障排查

### 问题 1: 端口被占用

```bash
# 查看占用端口的进程
lsof -i :7051
lsof -i :9051
lsof -i :7050

# 杀死占用端口的进程
kill -9 <PID>
```

### 问题 2: Docker 容器无法启动

```bash
# 查看 Docker 日志
docker logs peer0.org1.example.com
docker logs orderer.example.com

# 重启 Docker 服务
# macOS
killall Docker && open /Applications/Docker.app

# Linux
sudo systemctl restart docker
```

### 问题 3: 链码部署失败

```bash
# 查看链码容器日志
docker logs $(docker ps -a | grep evidence | awk '{print $1}')

# 重新打包链码
cd /Users/ngokzit/Documents/CCTV-W-FABRIC-main/chaincode
go mod tidy
go mod vendor

# 重新部署
cd ~/projects/fabric-samples/test-network
./network.sh deployCC -ccn evidence -ccp /Users/ngokzit/Documents/CCTV-W-FABRIC-main/chaincode -ccl go
```

### 问题 4: 证书过期

```bash
# 删除旧证书
cd ~/projects/fabric-samples/test-network
rm -rf organizations/peerOrganizations
rm -rf organizations/ordererOrganizations

# 重新生成证书
./network.sh up createChannel -ca
```

## 📝 快速清理重建脚本

创建一个快速脚本 `reset_fabric.sh`：

```bash
#!/bin/bash

echo "🧹 清理 Fabric 网络..."
cd ~/projects/fabric-samples/test-network
./network.sh down -v

echo "🚀 启动新网络..."
./network.sh up createChannel -c mychannel -ca

echo "📦 部署链码..."
./network.sh deployCC \
  -ccn evidence \
  -ccp /Users/ngokzit/Documents/CCTV-W-FABRIC-main/chaincode \
  -ccl go \
  -ccep "AND('Org1MSP.peer','Org2MSP.peer')" \
  -cccg /Users/ngokzit/Documents/CCTV-W-FABRIC-main/chaincode/collections_config.json

echo "✅ 网络重建完成！"
docker ps
```

使用方法：

```bash
chmod +x reset_fabric.sh
./reset_fabric.sh
```

## ⚠️ 注意事项

1. **数据丢失**: 清理网络会删除所有链上数据，包括：
   - 所有证据记录
   - 所有工单记录
   - 所有审计轨迹

2. **本地文件**: 清理网络不会删除本地的证据文件（`evidences/` 目录）

3. **配置文件**: 确保 `.env` 文件配置正确

4. **端口冲突**: 确保以下端口未被占用：
   - 7050 (Orderer)
   - 7051 (Org1 Peer)
   - 9051 (Org2 Peer)
   - 7054 (Org1 CA)
   - 8054 (Org2 CA)

## 🎯 推荐清理流程

```bash
# 1. 停止 Web 应用
# Ctrl+C 停止 uvicorn

# 2. 清理 Fabric 网络
cd ~/projects/fabric-samples/test-network
./network.sh down -v

# 3. 重建网络
./network.sh up createChannel -c mychannel -ca

# 4. 部署链码
./network.sh deployCC \
  -ccn evidence \
  -ccp /Users/ngokzit/Documents/CCTV-W-FABRIC-main/chaincode \
  -ccl go \
  -ccep "AND('Org1MSP.peer','Org2MSP.peer')" \
  -cccg /Users/ngokzit/Documents/CCTV-W-FABRIC-main/chaincode/collections_config.json

# 5. 验证网络
docker ps

# 6. 重启 Web 应用
cd /Users/ngokzit/Documents/CCTV-W-FABRIC-main
source venv/bin/activate
python -m uvicorn web_app:app --host 0.0.0.0 --port 8000 --reload
```

现在你的 Fabric 网络应该已经完全清理并重建成功了！🎉
