# 阶段四快速启动指南

## 🚀 快速开始

### 1. 启动 Fabric 网络
```bash
cd ~/projects/fabric-samples/test-network
./network.sh up createChannel
```

### 2. 部署链码（如果尚未部署）
```bash
./network.sh deployCC \
  -ccn evidence \
  -ccp /Users/ngokzit/Documents/CCTV-W-FABRIC-main/chaincode \
  -ccl go \
  -ccep "AND('Org1MSP.peer','Org2MSP.peer')" \
  -cccg /Users/ngokzit/Documents/CCTV-W-FABRIC-main/chaincode/collections_config.json
```

### 3. 启动 Web 应用
```bash
cd /Users/ngokzit/Documents/CCTV-W-FABRIC-main
source venv/bin/activate
python -m uvicorn web_app:app --host 0.0.0.0 --port 8000 --reload
```

### 4. 访问系统
- 🏠 主页（视频监控）: http://127.0.0.1:8000
- 📋 工单管理: http://127.0.0.1:8000/workorder
- 📊 审计报告: http://127.0.0.1:8000/audit
- ⚙️ 系统配置: http://127.0.0.1:8000/config

## 🎭 角色演示流程

### 场景：完整工单流程演示

#### Step 1: Org2 创建工单
1. 访问 http://127.0.0.1:8000/workorder
2. 右上角切换到 **Org2 - 监管方**
3. 点击 **"+ 创建工单"**
4. 填写表单：
   - 违规批次ID: `batch_1709568000_1709568600_xyz`
   - 整改要求: `发现多起违规行为，需立即整改`
   - 责任组织: `Org1MSP`
   - 截止日期: 选择7天后
5. 点击 **"创建工单"**

#### Step 2: Org1 提交整改
1. 切换到 **Org1 - 监控方**
2. 在工单列表找到刚创建的工单
3. 点击 **"提交整改"**
4. 填写整改证明：
   ```
   已完成以下整改措施：
   1. 更新监控设备配置
   2. 加强人员培训
   3. 建立定期检查机制
   ```
5. 附件链接（可选）: `https://example.com/evidence.pdf`
6. 点击 **"提交整改"**

#### Step 3: Org2 确认整改
1. 切换回 **Org2 - 监管方**
2. 找到状态为 **"待确认"** 的工单
3. 点击 **"审核"**
4. 填写审核意见：`整改措施到位，验收通过`
5. 点击 **"✓ 通过"**

#### Step 4: Org3 导出审计报告
1. 访问 http://127.0.0.1:8000/audit
2. 切换到 **Org3 - 审计方**
3. 输入批次ID: `batch_1709568000_1709568600_xyz`
4. 点击 **"👁️ 预览"** 查看报告内容
5. 点击 **"📥 导出报告"** 下载 JSON 文件

## 🔧 配置自动触发工单

1. 访问 http://127.0.0.1:8000/config
2. 开启 **"自动触发工单"** 开关
3. 配置规则：
   - **规则1**：
     - 违规等级: 高
     - 责任组织: Org1MSP
     - 截止天数: 7
   - **规则2**：
     - 违规等级: 严重
     - 责任组织: Org1MSP
     - 截止天数: 3
4. 点击 **"保存配置"**

现在，当系统检测到批次中有 ≥5 个违规事件时，会自动创建工单！

## 📊 API 测试示例

### 创建工单
```bash
curl -X POST http://127.0.0.1:8000/api/workorder/create \
  -H "Content-Type: application/json" \
  -d '{
    "violationId": "batch_1709568000_1709568600_xyz",
    "description": "发现违规行为，需要整改",
    "assignedOrg": "Org1MSP",
    "deadline": 1710172800
  }'
```

### 提交整改
```bash
curl -X POST http://127.0.0.1:8000/api/workorder/order_1709568000000_abc123/rectify \
  -H "Content-Type: application/json" \
  -d '{
    "rectificationProof": "已完成整改措施",
    "attachments": ["https://example.com/evidence.pdf"]
  }'
```

### 确认整改
```bash
curl -X POST http://127.0.0.1:8000/api/workorder/order_1709568000000_abc123/confirm \
  -H "Content-Type: application/json" \
  -d '{
    "approved": true,
    "comments": "整改验收通过"
  }'
```

### 导出审计报告
```bash
curl "http://127.0.0.1:8000/api/audit/export?batch_id=batch_1709568000_1709568600_xyz&format=json" \
  -o audit_report.json
```

### 获取自动工单配置
```bash
curl http://127.0.0.1:8000/api/config/auto-workorder
```

### 更新自动工单配置
```bash
curl -X POST http://127.0.0.1:8000/api/config/auto-workorder \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true,
    "rules": [
      {
        "violation_level": "high",
        "auto_assign_org": "Org1MSP",
        "default_deadline_days": 7
      }
    ]
  }'
```

## 🎯 功能亮点

### 1. 工单管理
- ✅ 完整的工单生命周期管理
- ✅ 状态流转可视化
- ✅ 超期工单自动标记
- ✅ 角色权限控制

### 2. 角色切换
- ✅ 三个组织角色（Org1/Org2/Org3）
- ✅ 动态权限控制
- ✅ 本地存储持久化
- ✅ 切换通知提示

### 3. 审计报告
- ✅ 批次完整审计轨迹
- ✅ 报告预览功能
- ✅ JSON 格式导出
- ✅ 签名验证机制

### 4. 自动触发
- ✅ 智能工单创建
- ✅ 规则配置管理
- ✅ 异步处理不阻塞
- ✅ 可视化配置界面

## 🐛 故障排查

### 问题1: 工单创建失败
**原因**: Fabric 网络未启动或链码未部署
**解决**:
```bash
cd ~/projects/fabric-samples/test-network
./network.sh up createChannel
./network.sh deployCC -ccn evidence ...
```

### 问题2: 角色切换无效
**原因**: 浏览器缓存问题
**解决**: 清除浏览器缓存或使用无痕模式

### 问题3: 审计报告导出失败
**原因**: 批次ID不存在
**解决**: 确保输入的批次ID已经上链

### 问题4: 自动触发不工作
**原因**: 配置未启用或规则不匹配
**解决**: 访问 /config 检查配置是否正确

## 📝 注意事项

1. **链码调用**: 所有工单操作都会调用链码，需要 2-3 秒响应时间
2. **权限控制**: 前端仅做 UI 层权限控制，真正的权限由链码强制执行
3. **数据持久化**: 角色选择保存在浏览器 localStorage
4. **自动触发**: 仅在批次事件数 ≥5 时触发，可在代码中调整阈值

## 🎉 恭喜！

你已经成功完成了 SecureLens 阶段四的所有功能！

系统现在具备：
- ✅ 完整的工单管理流程
- ✅ 多组织角色协同
- ✅ 审计报告导出验证
- ✅ 智能自动化触发

享受你的区块链视频监控系统吧！🚀
