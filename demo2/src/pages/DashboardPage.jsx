import { useEffect, useMemo, useState } from 'react';
import { Activity, Blocks, Cpu, Database, RadioTower, Server } from 'lucide-react';
import { getBatchDetails, getDevices, getIpfsStats, getRecentBlocks, getSystemHealth } from '../services/api';
import BlockDetailModal from '../components/BlockDetailModal';
import RecentBlocksRail from '../components/RecentBlocksRail';
import { mergeDevicesWithCameraDefaults } from '../constants/cameras';

const STATUS_META = {
  ok: { label: '稳定', tone: 'var(--nv-green)', soft: 'rgba(118, 185, 0, 0.12)' },
  running: { label: '运行中', tone: 'var(--status-info)', soft: 'rgba(56, 189, 248, 0.14)' },
  degraded: { label: '降级', tone: 'var(--status-warn)', soft: 'rgba(251, 191, 36, 0.14)' },
  error: { label: '异常', tone: 'var(--status-err)', soft: 'rgba(255, 90, 90, 0.14)' },
  stopped: { label: '停止', tone: 'var(--status-err)', soft: 'rgba(255, 90, 90, 0.14)' },
  unknown: { label: '未知', tone: 'var(--text-muted)', soft: 'rgba(154, 165, 177, 0.12)' },
  online: { label: '在线', tone: 'var(--nv-green)', soft: 'rgba(118, 185, 0, 0.12)' },
  detecting: { label: '在线', tone: 'var(--nv-green)', soft: 'rgba(118, 185, 0, 0.12)' },
};

const VISIBLE_DEVICE_LIMIT = 5;

function getStatusMeta(status) {
  return STATUS_META[status] || STATUS_META.unknown;
}

function formatNumber(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return '—';
  return new Intl.NumberFormat('zh-CN').format(parsed);
}

function formatBytes(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let size = parsed;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${index === 0 || size >= 10 ? size.toFixed(0) : size.toFixed(1)} ${units[index]}`;
}

function formatAgo(timestamp) {
  if (!timestamp) return '未记录';
  const seconds = Math.max(0, Math.floor(Date.now() / 1000 - Number(timestamp)));
  if (seconds < 60) return `${seconds}s 前`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m 前`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h 前`;
  return `${Math.floor(seconds / 86400)}d 前`;
}

function resolveVifStatus(health) {
  const detectionRunning = health?.detection?.status === 'running';
  const anchorRunning = health?.gop_anchor?.status === 'running';
  if (detectionRunning && anchorRunning) return 'running';
  if (detectionRunning || anchorRunning) return 'degraded';
  if (health) return 'stopped';
  return 'unknown';
}

function resolveFabricStatus(health) {
  const readerStatus = health?.fabric?.status || 'unknown';
  const writerStatus = health?.fabric?.writer_status || 'unknown';
  if (readerStatus === 'error') return 'error';
  if (writerStatus === 'degraded') return 'degraded';
  if (writerStatus === 'ok') return 'ok';
  return readerStatus;
}

function resolveOverallStatus(cards) {
  const statuses = cards.map((card) => card.status);
  if (statuses.some((status) => ['error', 'stopped'].includes(status))) return 'error';
  if (statuses.some((status) => status === 'degraded')) return 'degraded';
  if (statuses.some((status) => status === 'running')) return 'running';
  if (statuses.some((status) => status === 'ok')) return 'ok';
  return 'unknown';
}

function StatusPill({ status }) {
  const meta = getStatusMeta(status);
  return (
    <span className="dashboard-status-pill" style={{ '--status-tone': meta.tone, '--status-soft': meta.soft }}>
      <span className="dashboard-status-pill__dot" />
      {meta.label}
    </span>
  );
}

function OverviewMetric({ label, value, note, tone }) {
  return (
    <div className="dashboard-overview__metric" style={{ '--metric-tone': tone }}>
      <span className="dashboard-overview__metricLabel">{label}</span>
      <strong className="dashboard-overview__metricValue">{value}</strong>
      <p className="dashboard-overview__metricNote">{note}</p>
    </div>
  );
}

function PriorityModule({ card, reads }) {
  const meta = getStatusMeta(card.status);
  const Icon = card.icon;

  return (
    <article className="dashboard-priorityModule" style={{ '--card-tone': meta.tone, '--card-soft': meta.soft }}>
      <div className="dashboard-priorityModule__head">
        <div>
          <span className="dashboard-moduleCard__eyebrow">{card.eyebrow}</span>
          <h3 className="dashboard-priorityModule__title">安全记录与防篡改保护</h3>
        </div>
        <div className="dashboard-priorityModule__icon">
          <Icon size={18} />
        </div>
      </div>

      <div className="dashboard-priorityModule__metricRow">
        <div>
          <strong className="dashboard-priorityModule__value">{card.value}</strong>
          <span className="dashboard-priorityModule__label">链上记录高度</span>
        </div>
        <StatusPill status={card.status} />
      </div>

      <p className="dashboard-priorityModule__detail">
        系统正在持续记录安全信息，并对视频内容执行 HASH 与 VIF 双重校验，
        用于后续验证证据是否发生篡改。
      </p>
      <p className="dashboard-priorityModule__subdetail">
        每次关键写入都会保留链上凭证与时间记录，便于在复核阶段快速证明内容完整性。
      </p>

      <div className="dashboard-priorityModule__reads">
        {reads.map((read) => (
          <div key={read.label} className="dashboard-priorityModule__read">
            <span>{read.label}</span>
            <strong>{read.value}</strong>
          </div>
        ))}
      </div>
    </article>
  );
}

export default function DashboardPage() {
  const [health, setHealth] = useState(null);
  const [ipfsStats, setIpfsStats] = useState(null);
  const [devices, setDevices] = useState([]);
  const [blocks, setBlocks] = useState([]);
  const [error, setError] = useState('');
  const [selectedBatchId, setSelectedBatchId] = useState(null);
  const [selectedDetail, setSelectedDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    let disposed = false;

    const refreshHealth = async () => {
      try {
        const [nextHealth, nextDevices, nextIpfsStats] = await Promise.all([
          getSystemHealth(),
          getDevices(),
          getIpfsStats().catch(() => null),
        ]);
        if (disposed) return;
        setHealth(nextHealth);
        setDevices(mergeDevicesWithCameraDefaults(nextDevices.devices || []));
        setIpfsStats(nextIpfsStats);
        setError('');
      } catch (nextError) {
        if (disposed) return;
        setError(nextError?.message || '管理端状态接口不可用');
      }
    };

    const refreshBlocks = async () => {
      try {
        const nextBlocks = await getRecentBlocks(5);
        if (disposed) return;
        setBlocks(nextBlocks.blocks || []);
      } catch {
        // Keep the last successful block snapshot if polling temporarily fails.
      }
    };

    refreshHealth();
    refreshBlocks();
    const healthTimer = setInterval(refreshHealth, 30000);
    const blockTimer = setInterval(refreshBlocks, 8000);

    return () => {
      disposed = true;
      clearInterval(healthTimer);
      clearInterval(blockTimer);
    };
  }, []);

  useEffect(() => {
    if (!selectedBatchId) return undefined;
    let disposed = false;
    getBatchDetails(selectedBatchId)
      .then((detail) => {
        if (!disposed) setSelectedDetail(detail);
      })
      .catch(() => {
        if (!disposed) setSelectedDetail(null);
      })
      .finally(() => {
        if (!disposed) setDetailLoading(false);
      });
    return () => {
      disposed = true;
    };
  }, [selectedBatchId]);

  const focusCards = useMemo(() => ([
    {
      key: 'fabric',
      eyebrow: 'Hyperledger Fabric',
      title: '区块链',
      icon: Blocks,
      status: resolveFabricStatus(health),
      value: health?.fabric?.block_height != null ? `#${formatNumber(health.fabric.block_height)}` : '—',
      metricLabel: '当前区块高度',
      detail: health?.fabric?.status === 'error'
        ? health?.fabric?.message || '联盟链读链异常'
        : `${health?.fabric?.status === 'ok' ? '读链稳定' : '读链待确认'} / ${health?.fabric?.writer_status === 'ok' ? '写链正常' : health?.fabric?.writer_status === 'degraded' ? '写链异常' : '写链未知'}`,
      subdetail: health?.fabric?.writer_hint || '暂无写链反馈',
    },
    {
      key: 'ipfs',
      eyebrow: 'Distributed Storage',
      title: 'IPFS',
      icon: Database,
      status: health?.ipfs?.status || 'unknown',
      value: formatNumber(health?.ipfs?.num_objects || 0),
      metricLabel: '存储对象',
      detail: health?.ipfs?.message || `仓库占用 ${formatBytes(health?.ipfs?.repo_size || 0)}`,
      subdetail: `节点心跳 ${formatAgo(health?.connections?.ipfs_last_success)}`,
      facts: [
        { label: '仓库占用', value: formatBytes(health?.ipfs?.repo_size || 0) },
        { label: '心跳', value: formatAgo(health?.connections?.ipfs_last_success) },
        { label: '对象总数', value: formatNumber(health?.ipfs?.num_objects || 0) },
      ],
    },
    {
      key: 'vif',
      eyebrow: 'Video Integrity Fingerprint',
      title: 'VIF 模块',
      icon: Cpu,
      status: resolveVifStatus(health),
      value: 'V4',
      metricLabel: '指纹版本',
      detail: health?.detection?.model || '检测线程未就绪',
      subdetail: `${formatNumber(health?.gop_anchor?.pending_gops || 0)} GOP 待处理 / 窗口 ${formatNumber(health?.gop_anchor?.segment_gops || 0)} GOP`,
      facts: [
        { label: '模型', value: health?.detection?.model || '未就绪' },
        { label: '待处理', value: `${formatNumber(health?.gop_anchor?.pending_gops || 0)} GOP` },
        { label: '窗口', value: `${formatNumber(health?.gop_anchor?.segment_gops || 0)} GOP` },
      ],
    },
    {
      key: 'gateway',
      eyebrow: 'Epoch Aggregation',
      title: '聚合网关',
      icon: Server,
      status: health?.gateway?.status || 'unknown',
      value: health?.gateway?.latest_epoch || '暂无',
      metricLabel: '最新 Epoch',
      detail: health?.gateway?.message || '设备上报与批次聚合正常待机',
      subdetail: `写链 ${formatNumber(health?.connections?.anchor_successes || 0)} / ${formatNumber(health?.connections?.anchor_failures || 0)}`,
    },
  ]), [health]);

  const deviceSummary = useMemo(() => {
    const total = devices.length;
    const online = devices.filter((device) => ['online', 'detecting'].includes(device.status)).length;
    return { total, online };
  }, [devices]);

  const latestBlock = useMemo(() => blocks[0] || null, [blocks]);
  const overallStatus = useMemo(() => resolveOverallStatus(focusCards), [focusCards]);
  const overallMeta = getStatusMeta(overallStatus);
  const primaryCard = focusCards[0];

  const overviewText = useMemo(() => {
    if (error) return '状态接口当前不可用，页面展示的是最近一次成功拉取的系统快照。';

    const fragments = [];

    if (deviceSummary.online > 0) {
      fragments.push(`当前 ${deviceSummary.online} 路监控探头在线`);
    } else {
      fragments.push('当前没有在线探头，系统处于待命状态');
    }

    if (health?.fabric?.block_height != null) {
      fragments.push(`链上高度位于 #${formatNumber(health.fabric.block_height)}`);
    }

    if ((health?.gop_anchor?.pending_gops || 0) > 0) {
      fragments.push(`仍有 ${formatNumber(health.gop_anchor.pending_gops)} 个 GOP 待处理`);
    } else {
      fragments.push('当前没有待处理 GOP');
    }

    return `${fragments.join('，')}。`;
  }, [deviceSummary.online, error, health]);

  const integrityStatus = resolveVifStatus(health);
  const fabricStatus = resolveFabricStatus(health);
  const ipfsNodeSummary = useMemo(() => {
    const onlineCount = Number(ipfsStats?.cluster_online_count);
    const totalCount = Number(ipfsStats?.cluster_total_count);
    if (Number.isFinite(onlineCount) && Number.isFinite(totalCount) && totalCount > 0) {
      return `${onlineCount}/${totalCount}`;
    }
    if (health?.ipfs?.status === 'ok') return '1/1';
    return '—';
  }, [health?.ipfs?.status, ipfsStats?.cluster_online_count, ipfsStats?.cluster_total_count]);

  const overviewMetrics = useMemo(() => ([
    {
      label: '系统态势',
      value: overallMeta.label,
      note: `${focusCards.filter((card) => !['error', 'stopped', 'unknown'].includes(card.status)).length}/${focusCards.length} 模块已接入 · ${deviceSummary.online} 路探头在线`,
      tone: overallMeta.tone,
    },
    {
      label: '完整性校验模块',
      value: getStatusMeta(integrityStatus).label,
      note: health?.detection?.model
        ? 'HASH / VIF 校验链路可用'
        : 'HASH / VIF 校验链路待确认',
      tone: 'var(--nv-green)',
    },
    {
      label: 'Fabric 区块链',
      value: health?.fabric?.block_height != null ? `#${formatNumber(health.fabric.block_height)}` : '—',
      note: `工作状态：${getStatusMeta(fabricStatus).label}${health?.fabric?.writer_hint ? ` · ${health.fabric.writer_hint}` : ''}`,
      tone: getStatusMeta(fabricStatus).tone,
    },
    {
      label: 'IPFS 分布式存储',
      value: ipfsNodeSummary,
      note: `在线节点 / 仓库 ${formatBytes(health?.ipfs?.repo_size || 0)}`,
      tone: getStatusMeta(health?.ipfs?.status || 'unknown').tone,
    },
  ]), [deviceSummary.online, fabricStatus, focusCards, health, integrityStatus, ipfsNodeSummary, overallMeta]);

  const visibleDevices = useMemo(() => devices.slice(0, VISIBLE_DEVICE_LIMIT), [devices]);
  const priorityReads = useMemo(() => ([
    {
      label: '安全记录',
      value: deviceSummary.online > 0 ? '持续记录中' : '等待输入',
    },
    {
      label: '完整性校验',
      value: getStatusMeta(integrityStatus).label,
    },
    {
      label: '链上凭证',
      value: getStatusMeta(fabricStatus).label,
    },
    {
      label: '在线探头',
      value: `${deviceSummary.online}/${deviceSummary.total || 0}`,
    },
  ]), [deviceSummary, fabricStatus, integrityStatus]);

  return (
    <div className="main-content dashboard-shell dashboard-shell--command" style={{ padding: '32px 36px 40px' }}>
      <section className="tech-panel dashboard-commandDeck">
        <div className="dashboard-commandDeck__lead">
          <div className="dashboard-overview__statusLine">
            <span className="dashboard-eyebrow">NVIDIA Security Stack</span>
            <StatusPill status={overallStatus} />
          </div>

          <h2 className="dashboard-title">
            <Activity size={24} />
            SECURELENS 系统控制台
          </h2>

          <p className="dashboard-subtitle dashboard-commandDeck__summary">{overviewText}</p>

          {error ? <div className="dashboard-errorHint">状态接口不可用：{error}</div> : null}

          <div className="dashboard-commandDeck__metrics">
            {overviewMetrics.map((metric) => (
              <OverviewMetric key={metric.label} {...metric} />
            ))}
          </div>
        </div>

        <PriorityModule card={primaryCard} reads={priorityReads} />
      </section>

      <section className="dashboard-focusGrid">
        <div className="tech-panel dashboard-focusPanel">
          <div className="dashboard-focusPanel__head">
            <div>
              <span className="dashboard-eyebrow">Device Presence</span>
              <h3 className="dashboard-focusPanel__title">
                <RadioTower size={18} />
                在线设备状态
              </h3>
            </div>
            <span className="dashboard-inlineStat">在线 {deviceSummary.online} / 总数 {deviceSummary.total || 0}</span>
          </div>

          <div className="dashboard-focusPanel__body">
            <div className="dashboard-focusPanel__stats">
              <div className="dashboard-focusStat">
                <span>在线设备</span>
                <strong>{deviceSummary.online} 路</strong>
              </div>
              <div className="dashboard-focusStat">
                <span>在线状态</span>
                <strong>{deviceSummary.online > 0 ? '在线' : '待命'}</strong>
              </div>
            </div>

            {visibleDevices.length > 0 ? (
              <div className="dashboard-deviceStack">
                {visibleDevices.map((device) => {
                  const meta = getStatusMeta(device.status);
                  return (
                    <article key={device.device_id} className="dashboard-deviceRow">
                      <div className="dashboard-deviceRow__main">
                        <div className="dashboard-deviceRow__top">
                          <div>
                            <strong className="dashboard-deviceRow__label">{device.label || device.device_id}</strong>
                            <span className="dashboard-deviceRow__id">{device.device_id}</span>
                          </div>
                          <StatusPill status={device.status} />
                        </div>
                        <div className="dashboard-deviceRow__meta">
                          <span style={{ color: meta.tone }}>{meta.label}</span>
                          <span>在线状态已同步</span>
                        </div>
                      </div>
                    </article>
                  );
                })}
              </div>
            ) : (
              <div className="dashboard-emptyState">暂无设备在线数据</div>
            )}

            {devices.length > visibleDevices.length ? (
              <div className="dashboard-focusPanel__foot">另有 {devices.length - visibleDevices.length} 路设备未展开</div>
            ) : null}
          </div>
        </div>

        <div className="tech-panel dashboard-focusPanel">
          <div className="dashboard-focusPanel__head">
            <div>
              <span className="dashboard-eyebrow">Latest Blocks</span>
              <h3 className="dashboard-focusPanel__title">
                <Blocks size={18} />
                最近链上区块
              </h3>
            </div>
            <span className="dashboard-inlineStat">
              {latestBlock?.block_number != null ? `最新 #${latestBlock.block_number}` : '等待新区块'}
            </span>
          </div>

          <div className="dashboard-focusPanel__body">
            <RecentBlocksRail
              blocks={blocks}
              mode="dashboard"
              onSelect={(block) => {
                setSelectedDetail(null);
                setDetailLoading(true);
                setSelectedBatchId(block.batch_id);
              }}
            />
          </div>
        </div>
      </section>

      <BlockDetailModal
        open={Boolean(selectedBatchId)}
        detail={selectedDetail}
        loading={detailLoading}
        onClose={() => {
          setSelectedBatchId(null);
          setSelectedDetail(null);
        }}
      />
    </div>
  );
}
