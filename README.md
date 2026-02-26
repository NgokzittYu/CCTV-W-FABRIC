# CV-Simple 监控数据上链闭环

本系统实现了一个计算机视觉监控与区块链数据防篡改闭环。

详细的执行步骤和代码结构请参考以下文档。

## 快速入口文档

- [执行指南：监控数据上链闭环](EXECUTE_INSTRUCTIONS.md)
- [Fabric 上链快速操作手册](FABRIC_RUNBOOK.md)

---

## 常见问题与排错 (FAQ)

### Windows/WSL 环境下启动 Fabric 网络报错端口冲突被占用 (7054 等端口)

**错误现象：**
在执行 `./network.sh up createChannel -c mychannel -ca` 等相关命令启动网络时，发生类似下列的网络绑定错误：
```text
Error response from daemon: Ports are not available: exposing port TCP 0.0.0.0:7054 -> 0.0.0.0:0: listen tcp 0.0.0.0:7054: bind: An attempt was made to access a socket in a way forbidden by its access permissions.
```

**错误原因：**
Windows 系统的 NAT (`winnat`) 服务或 Hyper-V 意外保留或锁定了此类端口（如 Windows 的随机端口保留机制占用），导致 WSL2 内的 Docker 无法成功将容器内的端口映射到宿主机。

**解决方法：**
需要重启 Windows 系统的网络 NAT 服务。此操作不会切断你的本机网络连接。

1. 在 Windows 系统中，点击桌面任务栏的 **“开始菜单”**，搜索输入 `PowerShell` 或 `CMD`。
2. 找到搜索结果后，**右键点击，选择“以管理员身份运行”**。
3. 在管理终端窗口中依次输入并执行以下两条命令，以释放保留的端口：
   ```powershell
   net stop winnat
   net start winnat
   ```
4. 看到服务重启成功后，返回到 WSL (Ubuntu) 终端中，重新执行启动网络的命令，即可正常运行。
