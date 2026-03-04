# 实施计划 - 阶段四：前端业务联动

## 概述
链码已支持整改工单 + 权限 + 审计，现在需要前端和 API 把它们串起来。

---

## 1. 工单管理 REST API

### 1.1 创建工单接口
- **路径**: `POST /api/workorder/create`
- **功能**: 创建新的整改工单
- **请求体**:
  ```json
  {
    "violationId": "string",
    "description": "string",
    "assignedOrg": "string",
    "deadline": "timestamp"
  }
  ```
- **实现要点**:
  - 调用链码 `CreateWorkOrder` 方法
  - 验证调用者权限（仅监管方可创建）
  - 返回工单 ID 和创建状态

### 1.2 提交整改接口
- **路径**: `POST /api/workorder/{id}/rectify`
- **功能**: 责任方提交整改证明
- **请求体**:
  ```json
  {
    "rectificationProof": "string",
    "attachments": ["url1", "url2"]
  }
  ```
- **实现要点**:
  - 调用链码 `SubmitRectification` 方法
  - 验证调用者为工单责任方
  - 更新工单状态为 "待确认"

### 1.3 确认关闭接口
- **路径**: `POST /api/workorder/{id}/confirm`
- **功能**: 监管方确认整改并关闭工单
- **请求体**:
  ```json
  {
    "approved": true,
    "comments": "string"
  }
  ```
- **实现要点**:
  - 调用链码 `ConfirmWorkOrder` 方法
  - 验证调用者为监管方
  - 若不通过，工单状态回退到 "待整改"

### 1.4 超期工单查询接口
- **路径**: `GET /api/workorder/overdue`
- **功能**: 查询所有超期未完成的工单
- **查询参数**:
  - `org`: 可选，按组织筛选
  - `page`: 分页参数
  - `limit`: 每页数量
- **实现要点**:
  - 调用链码 `QueryOverdueWorkOrders` 方法
  - 返回工单列表及超期天数
  - 支持分页和排序

---

## 2. Web UI 工单管理页面

### 2.1 工单列表页面
- **功能模块**:
  - 工单列表展示（表格形式）
  - 状态筛选器（全部/待整改/待确认/已关闭/已超期）
  - 搜索功能（按工单 ID、违规 ID）
  - 分页控件
- **显示字段**:
  - 工单 ID
  - 违规事件 ID
  - 责任组织
  - 当前状态
  - 创建时间
  - 截止时间
  - 操作按钮（根据角色和状态动态显示）

### 2.2 工单详情页面
- **信息展示**:
  - 基本信息（ID、描述、责任方、截止时间）
  - 关联违规事件详情
  - 状态流转历史（时间轴展示）
  - 整改证明（如已提交）
  - 审核意见（如已确认）
- **操作区域**:
  - 提交整改按钮（责任方可见）
  - 确认/驳回按钮（监管方可见）
  - 导出工单报告

### 2.3 工单创建表单
- **表单字段**:
  - 违规事件选择（下拉列表，可搜索）
  - 整改要求描述（富文本编辑器）
  - 责任组织选择
  - 截止日期选择器
- **验证规则**:
  - 必填字段校验
  - 截止日期不能早于当前时间
  - 违规事件不能重复创建工单

### 2.4 状态流转可视化
- **流程图展示**:
  ```
  创建 → 待整改 → 待确认 → 已关闭
                ↓          ↓
              超期      驳回（回到待整改）
  ```
- **状态颜色标识**:
  - 待整改：橙色
  - 待确认：蓝色
  - 已关闭：绿色
  - 已超期：红色

---

## 3. 角色切换演示

### 3.1 多角色登录支持
- **角色定义**:
  - Org1：监管方（可创建工单、确认整改）
  - Org2：责任方 A（可提交整改、查看自己的工单）
  - Org3：责任方 B（可提交整改、查看自己的工单）
- **实现方式**:
  - 登录页面提供组织选择下拉框
  - 后端根据组织生成对应的 JWT Token
  - Token 中包含组织身份和权限信息

### 3.2 权限控制展示
- **页面级权限**:
  - 监管方：可访问所有工单、创建工单、审计报告
  - 责任方：仅可访问分配给自己的工单
- **操作级权限**:
  - 创建工单按钮：仅监管方可见
  - 提交整改按钮：仅责任方且工单状态为"待整改"时可见
  - 确认/驳回按钮：仅监管方且工单状态为"待确认"时可见
- **数据级权限**:
  - 责任方查询工单时，链码自动过滤只返回本组织相关工单
  - 监管方可查看所有组织的工单

### 3.3 角色切换演示功能
- **快速切换**:
  - 页面右上角显示当前登录角色
  - 点击可弹出角色切换菜单
  - 切换后页面自动刷新，展示对应权限的界面
- **演示场景**:
  - 场景 1：以 Org1 身份创建工单
  - 场景 2：切换到 Org2，提交整改证明
  - 场景 3：切换回 Org1，确认整改并关闭工单

---

## 4. 审计报告导出 API

### 4.1 审计追踪导出接口
- **路径**: `GET /api/audit/export`
- **功能**: 导出可验证的审计报告
- **查询参数**:
  ```
  startTime: timestamp (可选)
  endTime: timestamp (可选)
  entityType: string (可选，如 "workorder", "violation")
  entityId: string (可选)
  format: string (json/csv/pdf，默认 json)
  ```
- **实现要点**:
  - 调用链码 `ExportAuditTrail` 方法
  - 返回包含区块哈希和签名的审计记录
  - 支持多种导出格式

### 4.2 审计报告内容
- **报告结构**:
  ```json
  {
    "reportId": "string",
    "generatedAt": "timestamp",
    "generatedBy": "string",
    "timeRange": {
      "start": "timestamp",
      "end": "timestamp"
    },
    "auditRecords": [
      {
        "timestamp": "timestamp",
        "actor": "string",
        "action": "string",
        "entityType": "string",
        "entityId": "string",
        "changes": {},
        "blockNumber": "number",
        "txId": "string",
        "blockHash": "string"
      }
    ],
    "signature": "string",
    "verificationInfo": {
      "chaincodeName": "string",
      "channelName": "string",
      "networkId": "string"
    }
  }
  ```

### 4.3 报告验证功能
- **验证接口**: `POST /api/audit/verify`
- **功能**: 验证审计报告的真实性
- **请求体**:
  ```json
  {
    "reportId": "string",
    "signature": "string"
  }
  ```
- **验证步骤**:
  1. 检查报告签名是否有效
  2. 验证区块哈希是否匹配链上数据
  3. 确认交易 ID 存在且未被篡改
  4. 返回验证结果和可信度评分

### 4.4 Web UI 审计报告页面
- **功能模块**:
  - 时间范围选择器
  - 实体类型筛选
  - 导出格式选择
  - 报告预览（表格形式）
  - 下载按钮
  - 报告验证工具（上传报告文件进行验证）

---

## 5. 违规事件自动触发工单

### 5.1 自动触发机制
- **触发条件**:
  - 违规事件成功上链
  - 违规严重等级达到阈值（如 "高" 或 "严重"）
  - 自动触发开关已启用
- **实现方式**:
  - 在违规事件上链成功后，后端监听链码事件
  - 根据配置规则判断是否需要自动创建工单
  - 调用 `CreateWorkOrder` 自动生成工单

### 5.2 配置管理
- **配置项**:
  ```json
  {
    "autoCreateWorkOrder": true,
    "triggerRules": [
      {
        "violationLevel": "high",
        "autoAssignOrg": "Org2",
        "defaultDeadlineDays": 7
      },
      {
        "violationLevel": "critical",
        "autoAssignOrg": "Org2",
        "defaultDeadlineDays": 3
      }
    ],
    "notificationEnabled": true,
    "notificationChannels": ["email", "webhook"]
  }
  ```
- **配置界面**:
  - 开关控件（启用/禁用自动触发）
  - 规则列表（可添加、编辑、删除）
  - 通知设置（邮件、Webhook 地址）

### 5.3 通知功能
- **通知时机**:
  - 工单自动创建时
  - 工单即将超期时（提前 1 天）
  - 工单已超期时
  - 整改提交时
  - 整改确认/驳回时
- **通知方式**:
  - 邮件通知（发送给责任方和监管方）
  - Webhook 通知（集成第三方系统）
  - Web UI 站内消息
- **通知内容**:
  - 工单基本信息
  - 当前状态
  - 操作链接（直接跳转到工单详情页）

### 5.4 事件监听服务
- **服务架构**:
  - 独立的事件监听服务（Node.js/Go）
  - 监听 Fabric 链码事件
  - 解析事件数据并触发相应操作
- **事件类型**:
  - `ViolationCreated`：违规事件创建
  - `WorkOrderCreated`：工单创建
  - `WorkOrderUpdated`：工单状态更新
  - `WorkOrderOverdue`：工单超期
- **容错机制**:
  - 事件重试机制（失败后重试 3 次）
  - 事件日志记录（便于排查问题）
  - 健康检查接口（监控服务状态）

---

## 实施顺序建议

1. **第一步**：实现工单管理 REST API（1-2 天）
2. **第二步**：开发 Web UI 工单管理页面（2-3 天）
3. **第三步**：实现角色切换和权限控制（1-2 天）
4. **第四步**：开发审计报告导出功能（1-2 天）
5. **第五步**：实现违规事件自动触发工单（2-3 天）
6. **第六步**：集成测试和演示准备（1-2 天）

**总计**: 约 10-14 天

---

## 技术栈建议

- **后端 API**: Node.js + Express / Go + Gin
- **前端**: React + TypeScript + Ant Design / Vue 3 + Element Plus
- **状态管理**: Redux / Pinia
- **HTTP 客户端**: Axios
- **Fabric SDK**: fabric-network (Node.js) / fabric-sdk-go
- **事件监听**: fabric-network EventListener
- **报告生成**: jsPDF (PDF) / json2csv (CSV)

---

## 测试要点

- [ ] API 接口测试（Postman/Jest）
- [ ] 权限控制测试（不同角色访问不同接口）
- [ ] 工单状态流转测试（完整流程）
- [ ] 超期工单告警测试
- [ ] 审计报告导出和验证测试
- [ ] 自动触发工单测试（模拟违规事件上链）
- [ ] 并发测试（多个组织同时操作）
- [ ] 前端 UI/UX 测试

---

## 交付物

- [ ] 完整的 REST API 文档（Swagger/OpenAPI）
- [ ] Web UI 用户操作手册
- [ ] 角色权限矩阵文档
- [ ] 审计报告样例和验证说明
- [ ] 自动触发配置指南
- [ ] 演示视频（展示完整业务流程）
