/**
 * Mock data for frontend components that don't require backend APIs.
 * (Device management, Alert center)
 */

export const MOCK_DEVICES = [
  {
    id: 'cctv-kctmc-apple-01',
    name: '主楼东门',
    status: 'online',
    ip: '192.168.1.101',
    model: 'DS-2CD2T45',
    location: '东门入口 A1',
    lastSeen: Date.now(),
  },
  {
    id: 'cctv-kctmc-apple-02',
    name: '停车场入口',
    status: 'online',
    ip: '192.168.1.102',
    model: 'DS-2CD2T45',
    location: '地下停车场 B2',
    lastSeen: Date.now(),
  },
  {
    id: 'cctv-kctmc-apple-03',
    name: '实验楼走廊',
    status: 'offline',
    ip: '192.168.1.103',
    model: 'DS-2CD2085',
    location: '实验楼 3F 走廊',
    lastSeen: Date.now() - 3600000,
  },
  {
    id: 'cctv-kctmc-apple-04',
    name: '后门通道',
    status: 'online',
    ip: '192.168.1.104',
    model: 'DS-2CD2T45',
    location: '后门安全通道',
    lastSeen: Date.now(),
  },
  {
    id: 'cctv-kctmc-apple-05',
    name: '图书馆大厅',
    status: 'online',
    ip: '192.168.1.105',
    model: 'DS-2CD2085',
    location: '图书馆 1F 大厅',
    lastSeen: Date.now(),
  },
  {
    id: 'cctv-kctmc-apple-06',
    name: '操场西侧',
    status: 'warning',
    ip: '192.168.1.106',
    model: 'DS-2CD2T45',
    location: '操场西侧围栏',
    lastSeen: Date.now() - 600000,
  },
];

export const MOCK_ALERTS = [
  {
    id: 1,
    type: 'tamper',
    msg: '设备 cctv-03 视频流异常中断，疑似线路故障',
    time: '14:32',
    level: 'high',
  },
  {
    id: 2,
    type: 'offline',
    msg: '实验楼走廊设备离线超过 10 分钟',
    time: '14:28',
    level: 'medium',
  },
  {
    id: 3,
    type: 'chain',
    msg: 'Fabric 区块高度同步延迟告警 (>5s)',
    time: '13:45',
    level: 'low',
  },
  {
    id: 4,
    type: 'storage',
    msg: 'IPFS 节点 ipfs-2 存储空间不足 (<10%)',
    time: '12:10',
    level: 'medium',
  },
];
