# 阶段三：多组织 + 设备可信（信任架构）执行计划

目标：把“多方互不信任”的叙事落到可运行系统，完成 3 Org 网络、设备签名、链码验签、隐私数据隔离与方法级访问控制。

当前进度（2026-03-04）：
- 仓库内代码与脚本改造已基本完成（ACL/验签/PDC/整改流/审计导出/文档同步）。
- 仍需在本机 Fabric 环境执行联调（3 Org 实际拉起、deployCC、端到端验收脚本）。

---

## 0. 执行前提（编程 AI 必读）

- 当前仓库链码为 `chaincode/chaincode.go`（单链码）。
- 当前 Web 入口为 `web_app.py`，批量上链走 `CreateEvidenceBatch`。
- Fabric 运行目录在 `~/projects/fabric-samples/test-network`。

关键技术约束（必须按这个实现）：

1. Fabric lifecycle 背书策略是“链码级”，不是“函数级”。
2. 因此“EvidenceCommit / RectificationWorkflow 写操作都需 Org1+Org2 背书”应通过链码级策略实现。
3. 查询类函数（如 `VerifyEvent`、`ExportAuditTrail`）不走背书策略，Org3 独立验真通过“Org3 自己 peer 查询 + 链码内 ACL”实现。
4. 方法级权限（Org3 禁写）由链码中 `MSP` 校验实现，不依赖 channel ACL 单独完成。

---

## 1. 目标架构与验收标准

### 1.1 三组织角色

| Org | 角色 | 职责 | Fabric 组件 |
|---|---|---|---|
| Org1 | 施工方/企业 | 摄像头部署、证据采集、整改提交 | peer0.org1 + CA-Org1 |
| Org2 | 监管方/交管 | 证据审核、工单签发、整改确认 | peer0.org2 + CA-Org2 |
| Org3 | 保险/审计方 | 独立验真、审计导出、理赔依据 | peer0.org3 + CA-Org3 |

### 1.2 背书与权限目标

- 写入链上存证：`AND('Org1MSP.peer','Org2MSP.peer')`
- 整改状态写入：`AND('Org1MSP.peer','Org2MSP.peer')`
- 审计查询：Org3 可独立执行查询（不依赖 Org1/Org2）
- ACL：Org3 禁止调用写接口（`CreateEvidence*`, `CreateRectification*`, `ConfirmRectification*`）

### 1.3 验收通过定义（DoD）

1. Org1 单独发起存证交易提交失败（背书不足）。
2. Org1+Org2 双背书存证提交成功。
3. Org3 调用 `VerifyEvent`、`ExportAuditTrail` 成功。
4. Org3 调用写接口返回“permission denied”。
5. 设备签名错误时，`CreateEvidenceBatch` 明确报错并拒绝写入。
6. PDC 中原始图片只有 Org1/Org2 可读，Org3 只能看到哈希/元数据。

---

## 2. 交付物清单（必须产出）

### 2.1 仓库内新增/修改

- [x] `chaincode/chaincode.go`：新增 ACL、设备签名验签、整改流程、审计导出、PDC 接口。
- [x] `chaincode/collections_config.json`：定义 `collectionRawEvidence`。
- [x] `chaincode/chaincode_test.go`：补充阶段三测试用例。
- [x] `web_app.py`：批量上链接口增加签名字段；新增私有数据写入流程。
- [x] `anchor_to_fabric.py`：支持设备签名与（可选）transient 数据。
- [x] `config.py` + `.env.example`：增加 Org3 与设备签名配置项。
- [x] `scripts/stage3_setup_network.sh`：3 Org 网络部署脚本（调用 test-network/addOrg3）。
- [x] `scripts/stage3_verify.sh`：背书/ACL/PDC 全链路验证脚本。
- [x] `README.md` + `FABRIC_RUNBOOK.md`：同步阶段三说明与命令。

### 2.2 fabric-samples 外部改动（通过脚本驱动）

- [ ] 启动 test-network 后引入 Org3（建议走 `test-network/addOrg3` 标准流程）。
- [ ] 部署链码时带上 `-ccep` 与 `-cccg` 参数。

---

## 3. 工作包分解（按顺序执行）

## WP-A：3 Org 网络搭建

- [x] A1. 新增 `scripts/stage3_setup_network.sh`，内容包含：
1. `./network.sh down`
2. `./network.sh up createChannel -c mychannel -ca`
3. `cd addOrg3 && ./addOrg3.sh up -c mychannel -ca`
4. 返回仓库并输出 Org3 peer 健康检查命令。

- [x] A2. 脚本末尾自动验证 Org3 是否入通道：
1. `CORE_PEER_LOCALMSPID=Org3MSP` 环境下执行 `peer channel getinfo -c mychannel`
2. 成功即输出 `Org3 joined mychannel`

- [x] A3. 失败回滚策略：
1. 任何步骤失败时打印命令与 stderr
2. 给出 `./network.sh down` 清理提示

验收：
- [ ] `docker ps` 能看到 Org3 相关容器
- [ ] Org3 peer 可查询 channel info

## WP-B：链码级背书策略与部署

- [x] B1. 部署命令统一为：

```bash
./network.sh deployCC \
  -ccn evidence \
  -ccp /ABS/PATH/CCTV-W-FABRIC-main/chaincode \
  -ccl go \
  -ccep "AND('Org1MSP.peer','Org2MSP.peer')" \
  -cccg /ABS/PATH/CCTV-W-FABRIC-main/chaincode/collections_config.json
```

- [x] B2. 在 `scripts/stage3_verify.sh` 内加入“单背书失败 + 双背书成功”检查。

验收：
- [ ] Org1 单 peer 发起 invoke 提交失败（`ENDORSEMENT_POLICY_FAILURE`）
- [ ] Org1+Org2 双 peer 发起 invoke 提交成功（`status VALID`）

## WP-C：设备身份与签名链路

### C1. 设备证书发放

- [ ] C1-1. 使用 Org1 CA 为每台摄像头注册/签发身份（命名：`device-<cameraId>`）。
- [x] C1-2. 约定证书目录：`device_keys/<cameraId>/{cert.pem,key.pem}`（不提交 Git）。
- [x] C1-3. 在 `.env.example` 增加：
1. `DEVICE_CERT_PATH`
2. `DEVICE_KEY_PATH`
3. `DEVICE_SIGN_ALGO=ECDSA_SHA256`

### C2. 签名规范（必须固定）

- [x] C2-1. 定义待签名消息（canonical JSON，键排序、无空白）：
1. `batchId`
2. `cameraId`
3. `merkleRoot`
4. `windowStart`
5. `windowEnd`
6. `eventIds`
7. `eventHashes`

- [x] C2-2. Python 端签名输出：
1. `payloadHash`（hex）
2. `signature`（base64, ASN.1 DER）
3. `deviceCertPem`（PEM 字符串）

- [x] C2-3. `CreateEvidenceBatch` 扩展参数：
1. `deviceCertPEM`
2. `signatureB64`
3. `payloadHashHex`

### C3. 链码验签

- [x] C3-1. `chaincode.go` 新增 `VerifyDeviceSignature(...)`：
1. 解析 PEM 证书与 ECDSA 公钥
2. 验证 `signatureB64` 对 `payloadHash` 的签名
3. 校验证书归属 Org1（MSP/Issuer 约束）

- [x] C3-2. `CreateEvidenceBatch` 写入前强制调用验签，失败直接返回错误。

验收：
- [x] 正确签名可上链
- [x] 篡改 `eventHashes` 或签名后上链失败

## WP-D：整改流程（RectificationWorkflow）

- [x] D1. 在链码增加结构 `RectificationOrder`：
1. `orderId`
2. `batchId`
3. `createdBy`
4. `assignedTo`
5. `status`（OPEN/SUBMITTED/CONFIRMED/REJECTED）
6. `deadline`
7. `attachments`
8. `timestamps`

- [x] D2. 增加方法：
1. `CreateRectificationOrder`（监管方创建）
2. `SubmitRectification`（施工方提交）
3. `ConfirmRectification`（监管方确认）

- [x] D3. 上述写方法均受链码级 AND 背书策略保护。

验收：
- [x] 工单生命周期可完整流转
- [x] 非法状态跳转被拒绝

## WP-E：PDC 与访问控制

### E1. Private Data Collection

- [x] E1-1. 新增 `chaincode/collections_config.json`：
1. `name`: `collectionRawEvidence`
2. `policy`: `OR('Org1MSP.member','Org2MSP.member')`
3. `memberOnlyRead`: `true`
4. `memberOnlyWrite`: `true`

- [x] E1-2. 链码新增：
1. `PutRawEvidencePrivate(eventId, imageBase64, mimeType, imageSha256)`
2. `GetRawEvidencePrivate(eventId)`（仅 Org1/Org2）
3. `GetRawEvidenceHash(eventId)`（所有 org 可查）

### E2. 方法级 ACL（链码内）

- [x] E2-1. 新增 `requireMSP(ctx, allowedMSPs...)` 辅助函数。
- [x] E2-2. 方法权限表：
1. Org1/Org2：`CreateEvidence*`, `CreateRectification*`, `ConfirmRectification*`, `PutRawEvidencePrivate`
2. Org3：`VerifyEvent`, `ExportAuditTrail`, `GetRawEvidenceHash`
3. Org3 禁止写接口（返回 `permission denied for MSP`）

验收：
- [x] Org3 调用写接口被拒绝
- [x] Org3 能调用审计/验真接口
- [x] Org3 读取私有原图失败，但可读私有哈希

## WP-F：审计导出（AccessControl / Audit）

- [x] F1. 新增 `ExportAuditTrail(batchID)`：
1. 汇总 `MerkleBatch`
2. 汇总 member events
3. 汇总 rectification history（若存在）
4. 输出审计 JSON（不含私有原图）

- [x] F2. Web 或脚本侧新增审计导出入口（Org3 身份）。

验收：
- [ ] Org3 可导出完整审计报告
- [ ] 导出内容不泄露 PDC 原图

---

## 4. 测试计划（必须自动化 + 手工）

## 4.1 Go 单元测试（chaincode）

- [x] 新增/更新测试用例：
1. `TestCreateEvidenceBatch_WithValidSignature_OK`
2. `TestCreateEvidenceBatch_InvalidSignature_Fail`
3. `TestACL_Org3CannotCreateEvidenceBatch`
4. `TestACL_Org3CanVerifyEvent`
5. `TestPutRawEvidencePrivate_Org1Org2Only`
6. `TestRectificationWorkflow_StateTransition`

执行：

```bash
cd /Users/ngokzit/Documents/CCTV-W-FABRIC-main/chaincode
GOCACHE=/tmp/go-build go test -v ./...
```

## 4.2 联调测试（Fabric）

- [ ] Org1 单方 invoke 失败
- [ ] Org1+Org2 invoke 成功
- [ ] Org3 query `VerifyEvent` 成功
- [ ] Org3 invoke `CreateEvidenceBatch` 被拒绝
- [ ] PDC 可见性符合策略

---

## 5. 里程碑与执行顺序（硬性）

- [ ] M0：完成 WP-A（3 Org 网络）并截图/日志留档
- [ ] M1：完成 WP-B（背书策略部署）
- [x] M2：完成 WP-C（设备签名 + 链码验签）
- [x] M3：完成 WP-D（整改流程）
- [x] M4：完成 WP-E（PDC + ACL）
- [x] M5：完成 WP-F（审计导出）
- [x] M6：完成测试计划并更新 README/FABRIC_RUNBOOK

禁止跳步：未完成前一里程碑，不进入下一里程碑。

---

## 6. 风险与回退

- [ ] R1. 如果 Org3 加入通道失败，优先回退到 `network.sh down` 后重建。
- [x] R2. 如果签名验签影响现有流量，保留开关 `DEVICE_SIGNATURE_REQUIRED`（默认 `true`，可临时 `false` 降级）。
- [ ] R3. 如果 PDC 写入过大导致性能问题，改为“图片对象存储 + 仅密钥/引用入 PDC”。

---

## 7. 完成后文档更新清单

- [x] 更新 `README.md`：新增 3 Org、签名、PDC、ACL 的部署与验收步骤。
- [x] 更新 `FABRIC_RUNBOOK.md`：新增 Org3 环境变量模板与验证命令。
- [x] 更新 `EXECUTE_INSTRUCTIONS.md`：新增阶段三最短执行路径。
- [x] 更新 `CHANGELOG.md`：记录阶段三发布日期与破坏性变更。
