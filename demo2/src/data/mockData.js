/**
 * SecureLens Demo — Mock Data
 * 所有模块的模拟数据，无需后端即可驱动完整的演示流程
 */

// ═══════════════════════════════════════════════════════════════
// 系统概览 — 核心指标
// ═══════════════════════════════════════════════════════════════
export const systemStats = {
  costReduction: 95,
  localizationPrecision: '1-2',
  gopProcessingSpeed: 23,
  vifComputeTime: 8.5,
  fabricTPS: 120,
  ipfsNodes: 3,
};

export const techStack = [
  { name: 'YOLOv11', category: '目标检测', desc: 'Ultralytics 最新一代实时目标检测', color: '#06B6D4' },
  { name: 'MobileNetV3', category: '特征提取', desc: 'VIF v4 视觉指纹 CNN 骨干网络', color: '#8B5CF6' },
  { name: 'Hyperledger Fabric', category: '联盟链', desc: '企业级许可链，3 Org × 2 Peer', color: '#F59E0B' },
  { name: 'IPFS Kubo', category: '去中心化存储', desc: '3 节点集群，CIDv1 内容寻址', color: '#3B82F6' },
  { name: 'Python + PyAV', category: '边缘计算', desc: 'GOP 切分、哈希计算、VIF 管线', color: '#22C55E' },
  { name: 'MAB (UCB1)', category: '强化学习', desc: '自适应锚定频率，Explore & Exploit', color: '#EF4444' },
];

export const architectureLayers = [
  {
    id: 'edge',
    name: '边缘智能层',
    nameEn: 'Edge Intelligence',
    icon: 'Brain',
    color: '#8B5CF6',
    desc: '视频分析与指纹提取',
    details: ['GOP 切分与帧解码', 'VIF v4 视觉指纹', 'YOLOv11 语义提取', 'MAB 自适应锚定', '三级 Merkle 树构建'],
  },
  {
    id: 'gateway',
    name: '聚合网关层',
    nameEn: 'Aggregation Gateway',
    icon: 'Network',
    color: '#22C55E',
    desc: '多节点协调与批处理',
    details: ['多设备 SegmentRoot 聚合', 'Epoch Merkle 树 (30s)', 'ECDSA 设备签名验证', 'SQLite 历史索引'],
  },
  {
    id: 'storage',
    name: '去中心化存储层',
    nameEn: 'IPFS Storage',
    icon: 'HardDrive',
    color: '#3B82F6',
    desc: 'IPFS 内容寻址保存原始证据',
    details: ['视频 GOP 分片 (CID 寻址)', '语义 JSON & Merkle 结构', 'Pinning 持久化', 'CIDv1 SHA-256 multihash'],
  },
  {
    id: 'chain',
    name: '联盟链层',
    nameEn: 'Hyperledger Fabric',
    icon: 'Link',
    color: '#F59E0B',
    desc: '哈希上链存证',
    details: ['智能合约 (Anchor)', 'EpochRoot 上链', 'Merkle 路径验证', 'ECDSA 签名校验'],
  },
];

// ═══════════════════════════════════════════════════════════════
// 边缘智能 — GOP 数据
// ═══════════════════════════════════════════════════════════════
export const gopList = Array.from({ length: 12 }, (_, i) => ({
  gop_id: i,
  frame_count: 24 + Math.floor(Math.random() * 12),
  start_time: (i * 1.2).toFixed(1),
  end_time: ((i + 1) * 1.2).toFixed(1),
  byte_size: 45000 + Math.floor(Math.random() * 30000),
  sha256: Array.from({ length: 64 }, () => '0123456789abcdef'[Math.floor(Math.random() * 16)]).join(''),
  phash: Array.from({ length: 16 }, () => '0123456789abcdef'[Math.floor(Math.random() * 16)]).join(''),
  vif: Array.from({ length: 64 }, () => '0123456789abcdef'[Math.floor(Math.random() * 16)]).join(''),
  detections: [
    { class: 'person', count: Math.floor(Math.random() * 6) },
    { class: 'car', count: Math.floor(Math.random() * 3) },
    { class: 'bicycle', count: Math.floor(Math.random() * 2) },
  ],
  eis_score: +(0.1 + Math.random() * 0.85).toFixed(2),
  should_anchor: Math.random() > 0.4,
}));

// VIF v4 对比数据
export const vifComparison = {
  columns: ['维度', '初代方案 (密码学哈希)', 'VIF v4 (纯视觉 Mean Pooling)'],
  rows: [
    ['容忍合法操作', '极差 — 任何转码导致哈希雪崩', '极高 — Hamming 距离 + 阈值 0.35'],
    ['计算负担', '低（仅 SHA-256）但无鲁棒性', '轻量 — MobileNetV3 + Mean Pooling'],
    ['架构纯粹性', '单点依赖，易被掩盖', '纯视觉聚焦，去除多模态耦合'],
    ['输出位宽', '256-bit SHA-256', '256-bit (64 Hex) LSH 投影'],
    ['三态支持', '仅 INTACT / TAMPERED', 'INTACT / RE_ENCODED / TAMPERED_SUSPECT'],
  ],
};

// VIF 流水线步骤
export const vifPipeline = [
  { step: 1, label: 'GOP 多帧采样', desc: 'I帧 + 确定性采样帧 (total//2)', icon: 'Film', color: '#3B82F6' },
  { step: 2, label: 'CNN 特征提取', desc: 'MobileNetV3-Small → 576维', icon: 'Cpu', color: '#8B5CF6' },
  { step: 3, label: 'Mean Pooling', desc: '多帧特征均值聚合 + L2归一化', icon: 'Layers', color: '#22C55E' },
  { step: 4, label: 'LSH 投影', desc: '256×576 高斯矩阵 → 256-bit', icon: 'Key', color: '#F59E0B' },
];

// ═══════════════════════════════════════════════════════════════
// 聚合网关 — MAB 数据
// ═══════════════════════════════════════════════════════════════
export const mabArms = [
  { arm: 0, interval: 1, label: '每 1 GOP', desc: '最激进 — 最低延迟', color: '#EF4444' },
  { arm: 1, interval: 2, label: '每 2 GOP', desc: '高频 — 平衡策略', color: '#F59E0B' },
  { arm: 2, interval: 5, label: '每 5 GOP', desc: '中频 — 常规场景', color: '#3B82F6' },
  { arm: 3, interval: 10, label: '每 10 GOP', desc: '最保守 — 最低成本', color: '#22C55E' },
];

// 生成 MAB 模拟数据（100步）
export function generateMABSimulation(steps = 100) {
  const counts = [0, 0, 0, 0];
  const values = [0, 0, 0, 0];
  const history = [];
  let totalCount = 0;

  for (let t = 0; t < steps; t++) {
    // 模拟场景变化：前30步活跃，中间40步平静，最后30步再次活跃
    const isActive = t < 30 || t >= 70;

    // UCB1 选择
    let selectedArm = 0;
    if (totalCount < 4) {
      selectedArm = totalCount;
    } else {
      let bestUCB = -Infinity;
      for (let a = 0; a < 4; a++) {
        const avg = values[a] / counts[a];
        const exploration = 1.414 * Math.sqrt(Math.log(totalCount) / counts[a]);
        const ucb = avg + exploration;
        if (ucb > bestUCB) {
          bestUCB = ucb;
          selectedArm = a;
        }
      }
    }

    // 模拟 reward
    const interval = [1, 2, 5, 10][selectedArm];
    const costPenalty = 1 / interval;
    const latencyPenalty = isActive ? 0.4 : 0.1;
    const success = Math.random() > 0.05 ? 1 : 0;
    const reward = 0.6 * success - 0.2 * costPenalty - 0.2 * latencyPenalty;

    counts[selectedArm]++;
    values[selectedArm] += reward;
    totalCount++;

    history.push({
      step: t,
      arm: selectedArm,
      reward: +reward.toFixed(3),
      cumulativeReward: +(history.length > 0 ? history[history.length - 1].cumulativeReward + reward : reward).toFixed(3),
      isActive,
      armCounts: [...counts],
    });
  }

  return history;
}

// Merkle 树模拟数据
export const merkleTreeData = {
  segmentRoot: 'a3f1c9e8...7d2b',
  chunks: [
    {
      chunkRoot: '8b4e2f1a...9c3d',
      timeRange: '0s - 30s',
      gops: gopList.slice(0, 6).map((g, i) => ({
        leafHash: g.sha256.slice(0, 12) + '...',
        gopId: i,
      })),
    },
    {
      chunkRoot: 'd7f3a2b5...1e8c',
      timeRange: '30s - 60s',
      gops: gopList.slice(6, 12).map((g, i) => ({
        leafHash: g.sha256.slice(0, 12) + '...',
        gopId: i + 6,
      })),
    },
  ],
};

// ═══════════════════════════════════════════════════════════════
// IPFS 存储层
// ═══════════════════════════════════════════════════════════════
export const ipfsNodes = [
  { id: 'node-0', peerId: 'QmYwAPJ...kBCHT', port: 5001, status: 'online', objects: 247, repoSize: '156 MB' },
  { id: 'node-1', peerId: 'QmPNCI8...xTR2M', port: 5002, status: 'online', objects: 245, repoSize: '154 MB' },
  { id: 'node-2', peerId: 'QmRfpw1...LhPNw', port: 5003, status: 'online', objects: 243, repoSize: '152 MB' },
];

export const ipfsCIDExamples = [
  { type: 'GOP 视频分片', cid: 'bafkreig5xdj...qmzpw', size: '67.2 KB', sha256: 'a3e1f2...', pinned: true },
  { type: '语义 JSON', cid: 'bafkreih8yjk...rnvtq', size: '1.4 KB', sha256: 'b7c2d4...', pinned: true },
  { type: 'Merkle 结构', cid: 'bafkreim3wnp...xhsfy', size: '3.8 KB', sha256: 'c9d5e6...', pinned: true },
];

export const storageComparison = [
  { feature: '数据完整性', minio: '需额外 SHA-256 校验', ipfs: 'CID = SHA-256 multihash，协议层保证' },
  { feature: '去中心化', minio: '单点存储，存在 SPOF', ipfs: '多节点复制，抗单点故障' },
  { feature: '内容寻址', minio: '路径寻址 (bucket/key)', ipfs: '内容寻址 (CID)，天然去重' },
  { feature: '持久化', minio: '依赖服务器运行', ipfs: 'Pinning 机制 + GC 保护' },
  { feature: '验证成本', minio: '需下载 + 重算 SHA-256', ipfs: 'CID 即证明，零额外成本' },
];

// ═══════════════════════════════════════════════════════════════
// 联盟链层
// ═══════════════════════════════════════════════════════════════
export const fabricNetwork = {
  orgs: [
    { name: 'Org1MSP', role: '边缘设备 + 数据写入', peers: ['peer0.org1', 'peer1.org1'], color: '#8B5CF6' },
    { name: 'Org2MSP', role: '网关聚合 + 验证', peers: ['peer0.org2', 'peer1.org2'], color: '#3B82F6' },
    { name: 'Org3MSP', role: '审计监督 + 只读', peers: ['peer0.org3', 'peer1.org3'], color: '#22C55E' },
  ],
  orderer: 'orderer.example.com (Raft)',
  channel: 'evidence-channel',
};

export const smartContractFunctions = [
  { name: 'Anchor', desc: '锚定 EpochRoot 到链上', params: ['epochId', 'merkleRoot', 'deviceCount'], access: 'Org1, Org2' },
  { name: 'VerifyAnchor', desc: '验证 GOP 哈希的 Merkle Proof', params: ['epochId', 'leafHash', 'merkleProof'], access: 'Org1, Org2, Org3' },
  { name: 'CreateEvidenceBatch', desc: '批量存证 + 签名验证', params: ['batchId', 'merkleRoot', 'signature', '...'], access: 'Org1, Org2' },
  { name: 'QueryAnchorHistory', desc: '查询锚定历史记录', params: ['startTime', 'endTime'], access: 'All Orgs' },
];

export const blockchainTransactions = Array.from({ length: 8 }, (_, i) => ({
  txId: Array.from({ length: 64 }, () => '0123456789abcdef'[Math.floor(Math.random() * 16)]).join(''),
  function: ['Anchor', 'VerifyAnchor', 'CreateEvidenceBatch'][i % 3],
  timestamp: new Date(2026, 2, 30, 10, i * 5, 0).toISOString(),
  signerMSP: ['Org1MSP', 'Org2MSP', 'Org1MSP'][i % 3],
  status: 'VALID',
  epochRoot: Array.from({ length: 16 }, () => '0123456789abcdef'[Math.floor(Math.random() * 16)]).join('') + '...',
}));

// ═══════════════════════════════════════════════════════════════
// 审计验证
// ═══════════════════════════════════════════════════════════════
export const verificationScenarios = [
  {
    name: '完整未修改',
    nameEn: 'INTACT',
    state: 'INTACT',
    risk: 0.0,
    shaMatch: true,
    hammingDist: 0,
    desc: '原始 GOP 字节 SHA-256 完全一致，VIF 指纹无需比对。',
    color: '#22C55E',
  },
  {
    name: '合法转码',
    nameEn: 'RE_ENCODED',
    state: 'RE_ENCODED',
    risk: 0.18,
    shaMatch: false,
    hammingDist: 46,
    desc: 'CRF 变化 / H.264→H.265 转码，VIF 距离 0.18 < 阈值 0.35，判定合法。',
    color: '#F59E0B',
  },
  {
    name: '高危篡改嫌疑',
    nameEn: 'TAMPERED_SUSPECT',
    state: 'TAMPERED',
    risk: 0.62,
    shaMatch: false,
    hammingDist: 159,
    desc: 'VIF 距离 0.62 ≥ 阈值 0.35，触发高危告警，交由 MAB 管线深检。',
    color: '#EF4444',
  },
];

export const tamperTypes = [
  { id: 'frame_replace', name: '帧替换攻击', desc: '替换关键帧为其他场景', vifDist: 0.72, severity: 'high' },
  { id: 'noise_inject', name: '噪声注入', desc: '在 P/B 帧注入随机噪声', vifDist: 0.45, severity: 'medium' },
  { id: 're_encode', name: '重编码', desc: '合法 CRF 转码（非攻击）', vifDist: 0.12, severity: 'low' },
  { id: 'object_removal', name: '目标遮挡', desc: '使用马赛克遮挡特定目标', vifDist: 0.58, severity: 'high' },
];

// ═══════════════════════════════════════════════════════════════
// 对比实验 / Benchmark
// ═══════════════════════════════════════════════════════════════
export const benchmarkMAB = {
  labels: Array.from({ length: 20 }, (_, i) => `${(i + 1) * 5}`),
  ucb1: [0.32, 0.38, 0.41, 0.45, 0.51, 0.55, 0.58, 0.62, 0.65, 0.68, 0.70, 0.72, 0.73, 0.74, 0.75, 0.76, 0.76, 0.77, 0.77, 0.78],
  thompson: [0.28, 0.35, 0.42, 0.48, 0.53, 0.57, 0.61, 0.64, 0.67, 0.69, 0.71, 0.73, 0.74, 0.75, 0.76, 0.77, 0.77, 0.78, 0.78, 0.79],
  fixed: [0.30, 0.30, 0.30, 0.30, 0.30, 0.30, 0.30, 0.30, 0.30, 0.30, 0.30, 0.30, 0.30, 0.30, 0.30, 0.30, 0.30, 0.30, 0.30, 0.30],
};

export const benchmarkVIF = {
  versions: ['SHA-256 Only', 'VIF v1 (Multi-Modal)', 'VIF v4 (Pure Visual)'],
  falsePositive: [0.0, 3.2, 0.0],
  falseNegative: [45.8, 2.1, 4.5],
  computeTimeMs: [0.1, 85.0, 8.5],
  tolerateReencode: [false, true, true],
};

export const benchmarkCost = {
  frequency: ['每1 GOP', '每2 GOP', '每5 GOP', '每10 GOP', 'MAB 自适应'],
  txPerHour: [3600, 1800, 720, 360, 450],
  costIndex: [100, 50, 20, 10, 12.5],
  securityScore: [100, 95, 82, 65, 93],
};

export const performanceMetrics = [
  { metric: 'GOP 切分速度', value: '23 GOP/s', detail: 'PyAV GOP 切分（含帧解码）' },
  { metric: 'VIF 计算延迟', value: '8.5 ms', detail: 'MobileNetV3 推理 + Mean Pooling + LSH' },
  { metric: 'Merkle 树构建', value: '< 1 ms', detail: '12 叶子 → 4 层 SHA-256' },
  { metric: 'IPFS 上传延迟', value: '~120 ms', detail: '单 GOP (~60KB) 上传到本地节点' },
  { metric: 'Fabric 锚定延迟', value: '~800 ms', detail: 'EpochRoot 上链（含共识）' },
  { metric: '端到端延迟', value: '< 2s', detail: 'GOP 产生 → 链上确认' },
];
