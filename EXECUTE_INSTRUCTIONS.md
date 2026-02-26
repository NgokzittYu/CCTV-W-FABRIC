# 执行指南：监控数据上链闭环

我已为您更新了代码文件。为了使新的“闭环”方案生效，您需要在 Ubuntu 终端中执行以下操作。

## 1. 初始化 Go 链码模块

新的链码位于 `projects/cv-simple/chaincode/chaincode.go`。我们需要初始化 Go 模块。

```bash
cd ~/projects/cv-simple/chaincode
go mod init chaincode
go mod tidy
```

## 2. 重新部署链码

由于我们更改了数据结构（从 `Asset` 变为 `Evidence`），我们需要部署一个新的链码（或者升级旧的）。这里建议直接部署一个新的链码，名称为 `evidence`。

假设您的 Fabric 测试网络在 `~/projects/fabric-samples/test-network`：

```bash
cd ~/projects/fabric-samples/test-network

# 1. 停止当前网络（清理旧数据）- 可选，如果想保留旧数据请跳过，但可能需要解决冲突
./network.sh down

# 2. 启动网络
./network.sh up createChannel -c mychannel -ca

# 3. 部署我们新的 'evidence' 链码
# 注意：路径指向我们刚才创建的 chaincode 文件夹
./network.sh deployCC -ccn evidence -ccp ~/projects/cv-simple/chaincode -ccl go
```

## 3. 运行上链脚本 (Anchor)

现在运行 Python 脚本，它会计算哈希并上链。

```bash
cd ~/projects/cv-simple

# 首次运行建议 dry-run 看看哈希是否生成
python3 anchor_to_fabric.py --dry-run --limit 5

# 实际上链 (limit 限制数量，防止一次太多)
python3 anchor_to_fabric.py --limit 10
```

## 4. 运行闭环验证 (Verify)

挑选一个已上链的 ID（例如 `event_0000`），运行验证脚本。脚本会从区块链拉取哈希，并与您本地的 JSON+图片 重新计算的哈希进行对比。

```bash
# 验证成功案例
python3 verify_evidence.py event_0000

# 验证篡改案例（您可以手动修改 event_0000.json 里的一个字符，再运行此命令，应该会报错）
```

## 5. 常见问题 (FAQ)

### 端口冲突无法启动链码网络

如果在执行启动网络（`./network.sh up`）时遇到 `Error response from daemon: Ports are not available: listen tcp 0.0.0.0:7054: bind: An attempt was made to access a socket in a way forbidden by its access permissions.` 的报错：

**原因：**
Windows 的 Hyper-V 或 `winnat` 网络服务意外占用了某些随机端口。

**解决方法：**
在 Windows 宿主机中（而非 WSL 内），使用**管理员身份**打开 PowerShell 或 CMD，执行以下命令重启 NAT 服务解决：
```powershell
net stop winnat
net start winnat
```
之后回到 WSL 即可正常通过该脚本拉起包含 7054 端口的 Docker 容器。
