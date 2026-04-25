import { useCallback, useEffect, useMemo, useState } from 'react';
import { CalendarClock, Copy, Database, Download, ExternalLink, HardDrive, PlayCircle, RadioTower, RefreshCw } from 'lucide-react';
import { getDevices, getIPFSStats, getReplayDownloadJsonURL, getReplayDownloadTsURL, getReplayPlaylistURL, listIPFSGops } from '../services/api';
import HlsPlayer from '../components/HlsPlayer';
import { pickDefaultDeviceId } from '../constants/cameras';

const REPLAY_TIMEZONE = 'Asia/Shanghai';

function formatBytes(bytes) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function formatDateTime(ts) {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleString('zh-CN', { hour12: false });
}

function formatPeerIdShort(peerId) {
  if (!peerId) return '—';
  return peerId.length <= 18 ? peerId : `${peerId.slice(0, 10)}...${peerId.slice(-6)}`;
}

function formatGatewayHost(url) {
  if (!url) return 'Gateway 未配置';
  return url.replace(/^https?:\/\//, '');
}

function formatAsiaShanghaiDateTimeLocal(date = new Date()) {
  const formatter = new Intl.DateTimeFormat('sv-SE', {
    timeZone: REPLAY_TIMEZONE,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
  const parts = Object.fromEntries(formatter.formatToParts(date).map((part) => [part.type, part.value]));
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}:${parts.second}`;
}

function toUnixFromShanghaiLocal(localValue) {
  if (!localValue) return 0;
  const iso = localValue.length === 16 ? `${localValue}:00+08:00` : `${localValue}+08:00`;
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? 0 : Math.floor(date.getTime() / 1000);
}

export default function IPFSPage() {
  const [stats, setStats] = useState(null);
  const [devices, setDevices] = useState([]);
  const [gops, setGops] = useState([]);
  const [loading, setLoading] = useState(true);
  const [replayLoading, setReplayLoading] = useState(false);
  const [error, setError] = useState('');
  const [replayError, setReplayError] = useState('');
  const [replayDeviceId, setReplayDeviceId] = useState('');
  const [replayStartLocal, setReplayStartLocal] = useState(() => {
    const end = new Date();
    return formatAsiaShanghaiDateTimeLocal(new Date(end.getTime() - 5 * 60 * 1000));
  });
  const [replayEndLocal, setReplayEndLocal] = useState(() => formatAsiaShanghaiDateTimeLocal(new Date()));
  const [replayUrl, setReplayUrl] = useState('');
  const [copiedCid, setCopiedCid] = useState('');
  const [rangeSeeded, setRangeSeeded] = useState(false);

  const applyLatestReplayWindow = useCallback((deviceId, sourceStats) => {
    const bounds = sourceStats?.latest_gop_by_device?.[deviceId];
    const latestTs = bounds?.latest_timestamp;
    if (!latestTs) return false;

    const earliestTs = bounds?.earliest_timestamp || latestTs;
    const latestMs = latestTs * 1000;
    const earliestMs = earliestTs * 1000;
    const windowStartMs = Math.max(earliestMs, latestMs - 20 * 1000);

    setReplayStartLocal(formatAsiaShanghaiDateTimeLocal(new Date(windowStartMs)));
    setReplayEndLocal(formatAsiaShanghaiDateTimeLocal(new Date(latestMs)));
    return true;
  }, []);

  const loadOverview = useCallback(async () => {
    try {
      setLoading(true);
      const [statsRes, devicesRes] = await Promise.all([getIPFSStats(), getDevices()]);
      setStats(statsRes);
      const nextDevices = devicesRes.devices || [];
      setDevices(nextDevices);
      const fallbackDeviceId =
        replayDeviceId ||
        pickDefaultDeviceId(nextDevices, statsRes?.latest_gop_device_id || '');
      setReplayDeviceId(fallbackDeviceId);
      if (!rangeSeeded && fallbackDeviceId && applyLatestReplayWindow(fallbackDeviceId, statsRes)) {
        setRangeSeeded(true);
      }
      setError('');
    } catch (nextError) {
      setError(nextError?.message || 'IPFS 状态读取失败');
    } finally {
      setLoading(false);
    }
  }, [applyLatestReplayWindow, rangeSeeded, replayDeviceId]);

  const loadRangeGops = useCallback(async (deviceId, startLocal, endLocal) => {
    if (!deviceId) {
      setGops([]);
      return;
    }
    try {
      const start = toUnixFromShanghaiLocal(startLocal);
      const end = toUnixFromShanghaiLocal(endLocal);
      const result = await listIPFSGops(deviceId, start, end);
      setGops(result.gops || []);
    } catch (nextError) {
      setError(nextError?.message || 'GOP 列表读取失败');
      setGops([]);
    }
  }, []);

  useEffect(() => {
    loadOverview();
  }, [loadOverview]);

  useEffect(() => {
    if (!replayDeviceId) return;
    loadRangeGops(replayDeviceId, replayStartLocal, replayEndLocal);
  }, [loadRangeGops, replayDeviceId, replayStartLocal, replayEndLocal]);

  const handleGenerateReplay = async () => {
    if (!replayDeviceId || !replayStartLocal || !replayEndLocal) {
      setReplayError('请先选择探头并填写完整的东八区起止时间。');
      return;
    }

    setReplayLoading(true);
    setReplayError('');
    setReplayUrl('');
    try {
      const nextUrl = getReplayPlaylistURL({
        deviceId: replayDeviceId,
        startLocal: replayStartLocal,
        endLocal: replayEndLocal,
        timezone: REPLAY_TIMEZONE,
      });
      const response = await fetch(nextUrl);
      if (!response.ok) {
        const contentType = response.headers.get('content-type') || '';
        let message = '回放生成失败';
        if (contentType.includes('application/json')) {
          const data = await response.json();
          message = data.error || message;
        } else {
          message = (await response.text()) || message;
        }
        throw new Error(message);
      }
      setReplayUrl(nextUrl);
      await loadRangeGops(replayDeviceId, replayStartLocal, replayEndLocal);
    } catch (nextError) {
      const latestTs = stats?.latest_gop_by_device?.[replayDeviceId]?.latest_timestamp;
      const latestHint = latestTs ? `当前探头最近可播数据停在 ${formatDateTime(latestTs)}。` : '';
      const nextMessage = nextError?.message || '回放生成失败';
      setReplayError(nextMessage.includes('No playable GOPs') && latestHint ? `${nextMessage} ${latestHint}` : nextMessage);
    } finally {
      setReplayLoading(false);
    }
  };

  const handleReplayDeviceChange = (nextDeviceId) => {
    setReplayDeviceId(nextDeviceId);
    setReplayUrl('');
    setReplayError('');
    applyLatestReplayWindow(nextDeviceId, stats);
  };

  const replaySummary = useMemo(() => {
    const totalSeconds = gops.reduce((sum, gop) => sum + Number(gop.duration || 0), 0);
    return {
      count: gops.length,
      totalSeconds,
    };
  }, [gops]);

  const exportSummary = useMemo(() => {
    const playable = gops
      .filter((gop) => gop.playback_segment_url)
      .map((gop) => ({
        ...gop,
        timestamp: Number(gop.timestamp || 0),
        duration: Number(gop.duration || 0),
      }))
      .sort((left, right) => left.timestamp - right.timestamp);
    if (!playable.length || !replayDeviceId) return null;

    let actualStart = playable[0].timestamp;
    let actualEnd = playable[0].timestamp + Math.max(playable[0].duration, 0);
    let previousEnd = actualEnd;
    let playableDurationSeconds = 0;
    let gapCount = 0;

    for (const gop of playable) {
      const start = gop.timestamp;
      const end = gop.timestamp + Math.max(gop.duration, 0);
      if (start - previousEnd > 0.5) gapCount += 1;
      actualStart = Math.min(actualStart, start);
      actualEnd = Math.max(actualEnd, end);
      previousEnd = Math.max(previousEnd, end);
      playableDurationSeconds += Math.max(gop.duration, 0);
    }

    return {
      playableCount: playable.length,
      actualStart,
      actualEnd,
      playableDurationSeconds,
      gapCount,
      gapFlag: gapCount > 0,
      tsUrl: getReplayDownloadTsURL({
        deviceId: replayDeviceId,
        startLocal: replayStartLocal,
        endLocal: replayEndLocal,
        timezone: REPLAY_TIMEZONE,
      }),
      jsonUrl: getReplayDownloadJsonURL({
        deviceId: replayDeviceId,
        startLocal: replayStartLocal,
        endLocal: replayEndLocal,
        timezone: REPLAY_TIMEZONE,
      }),
    };
  }, [gops, replayDeviceId, replayStartLocal, replayEndLocal]);

  const selectedReplayBounds = useMemo(
    () => stats?.latest_gop_by_device?.[replayDeviceId] || null,
    [stats, replayDeviceId],
  );

  const clusterNodes = stats?.cluster_nodes || [];
  const clusterTotalCount = stats?.cluster_total_count ?? clusterNodes.length;

  return (
    <div className="main-content" style={{ padding: '36px 40px 42px' }}>
      <section className="tech-panel ipfs-shell__hero" style={{ marginBottom: '18px' }}>
        <div className="dashboard-sectionHeader">
          <div>
            <span className="dashboard-eyebrow">IPFS / Node Runtime</span>
            <h2 className="dashboard-title" style={{ marginTop: '8px' }}>
              <Database size={24} />
              IPFS 存储
            </h2>
          </div>
          <button type="button" className="btn btn-ghost" onClick={loadOverview}>
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
            刷新
          </button>
        </div>

        {error ? <div className="dashboard-errorHint">IPFS ERROR // {error}</div> : null}

        <div className="ipfs-runtimeLayout">
          <article className="ipfs-statCard ipfs-clusterPanel">
            <div className="ipfs-statCard__head">
              <div>
                <span className="dashboard-kpi-card__eyebrow" style={{ marginBottom: 0 }}>IPFS 集群</span>
                <p className="ipfs-clusterPanel__note">主面板集中展示节点在线率、主网关入口和每个节点的索引情况。</p>
              </div>
              <div className="ipfs-statCard__icon">
                <RadioTower size={14} />
              </div>
            </div>

            <div className="ipfs-clusterTelemetry">
              <div className="ipfs-clusterTelemetry__item">
                <span className="ipfs-clusterTelemetry__label">在线节点</span>
                <strong className="ipfs-clusterTelemetry__value">{stats?.cluster_online_count ?? 0} / {clusterTotalCount}</strong>
                <p className="ipfs-clusterTelemetry__note">实时反映集群可用度与故障面。</p>
              </div>
              <div className="ipfs-clusterTelemetry__item">
                <span className="ipfs-clusterTelemetry__label">主网关</span>
                <strong className="ipfs-clusterTelemetry__value ipfs-clusterTelemetry__value--small">
                  {formatGatewayHost(stats?.gateway_url)}
                </strong>
                <p className="ipfs-clusterTelemetry__note">当前默认回放与对象读取入口。</p>
              </div>
              <div className="ipfs-clusterTelemetry__item">
                <span className="ipfs-clusterTelemetry__label">对象索引</span>
                <strong className="ipfs-clusterTelemetry__value">{stats?.num_objects ?? '—'}</strong>
                <p className="ipfs-clusterTelemetry__note">主节点已索引对象总量。</p>
              </div>
            </div>

            <div className="ipfs-clusterList">
              {clusterNodes.length ? clusterNodes.map((node) => (
                <div key={node.name} className="ipfs-clusterNode">
                  <div className="ipfs-clusterNode__topline">
                    <span className="ipfs-clusterNode__name">{node.label || node.name || '未命名节点'}</span>
                    <span className={`ipfs-clusterNode__status ipfs-clusterNode__status--${node.status === 'ok' ? 'online' : 'offline'}`}>
                      {node.status === 'ok' ? '在线' : '离线'}
                    </span>
                  </div>
                  <div className="ipfs-clusterNode__peerWrap">
                    <span className="ipfs-clusterNode__eyebrow">Peer ID</span>
                    <div className="ipfs-clusterNode__peer">{formatPeerIdShort(node.peer_id)}</div>
                  </div>
                  <div className="ipfs-clusterNode__metaList">
                    <div className="ipfs-clusterNode__metaItem">
                      <span className="ipfs-clusterNode__metaLabel">网关地址</span>
                      <span className="ipfs-clusterNode__metaValue">{formatGatewayHost(node.gateway_url)}</span>
                    </div>
                    <div className="ipfs-clusterNode__metaItem">
                      <span className="ipfs-clusterNode__metaLabel">对象数量</span>
                      <span className="ipfs-clusterNode__metaValue">{node.num_objects ?? 0} objects</span>
                    </div>
                  </div>
                </div>
              )) : (
                <div className="ipfs-clusterNode ipfs-clusterNode--empty">暂无节点状态</div>
              )}
            </div>
          </article>

          <div className="ipfs-runtimeRail">
            <article className="ipfs-statCard ipfs-statCard--spotlight">
              <div className="ipfs-statCard__head">
                <span className="dashboard-kpi-card__eyebrow" style={{ marginBottom: 0 }}>节点状态</span>
                <div className="ipfs-statCard__icon">
                  <Database size={14} />
                </div>
              </div>
              <div className="runtime-layer__metric ipfs-runtimeRail__metric">
                <span className="runtime-layer__metricValue" style={{ color: stats?.status === 'ok' ? 'var(--nv-green)' : 'var(--nv-amber)' }}>
                  {stats?.status === 'ok' ? '在线' : '离线'}
                </span>
                <span className="runtime-layer__metricLabel">Gateway Runtime</span>
              </div>
              <p className="runtime-layer__note ipfs-runtimeRail__note">
                {stats?.gateway_url || 'Gateway 未返回'}
              </p>
            </article>

            <article className="ipfs-statCard ipfs-statCard--dense">
              <div className="ipfs-statCard__head">
                <span className="dashboard-kpi-card__eyebrow" style={{ marginBottom: 0 }}>容量概览</span>
                <div className="ipfs-statCard__icon">
                  <HardDrive size={14} />
                </div>
              </div>
              <div className="ipfs-statMatrix">
                <div className="ipfs-statMatrix__item">
                  <span className="ipfs-statMatrix__label">存储对象</span>
                  <strong className="ipfs-statMatrix__value">{stats?.num_objects ?? '—'}</strong>
                  <p className="ipfs-statMatrix__note">当前主节点索引到的对象数量</p>
                </div>
                <div className="ipfs-statMatrix__item">
                  <span className="ipfs-statMatrix__label">仓库大小</span>
                  <strong className="ipfs-statMatrix__value">{stats?.repo_size ? formatBytes(stats.repo_size) : '—'}</strong>
                  <p className="ipfs-statMatrix__note">当前主节点仓库占用空间</p>
                </div>
              </div>
            </article>
          </div>
        </div>
      </section>

      <section className="tech-panel ipfs-replayPanel">
        <div className="dashboard-sectionHeader">
          <div>
            <span className="dashboard-eyebrow">Replay Builder</span>
            <h3 className="dashboard-kpi-card__state" style={{ marginTop: '8px' }}>
              <PlayCircle size={18} />
              按时间段合成 GOP 回放
            </h3>
          </div>
          <span className="dashboard-inlineStat">{REPLAY_TIMEZONE} / 最长 30 分钟</span>
        </div>

        <div className="ipfs-replayPanel__layout">
          <div className="ipfs-replayPanel__controlCard">
            <div className="ipfs-replayPanel__controls">
              <label className="ipfs-replayPanel__field">
                <span><RadioTower size={12} /> 探头选择</span>
                <select value={replayDeviceId} onChange={(event) => handleReplayDeviceChange(event.target.value)}>
                  <option value="">-- 选择探头 --</option>
                  {devices.map((device) => (
                    <option key={device.device_id} value={device.device_id}>
                      {(device.label || device.device_id)} ({device.device_id})
                    </option>
                  ))}
                </select>
              </label>

              <label className="ipfs-replayPanel__field">
                <span><CalendarClock size={12} /> 开始时间（东八区）</span>
                <input type="datetime-local" step="1" value={replayStartLocal} onChange={(event) => setReplayStartLocal(event.target.value)} />
              </label>

              <label className="ipfs-replayPanel__field">
                <span><CalendarClock size={12} /> 结束时间（东八区）</span>
                <input type="datetime-local" step="1" value={replayEndLocal} onChange={(event) => setReplayEndLocal(event.target.value)} />
              </label>

              <button type="button" className="btn btn-primary ipfs-replayPanel__submit" onClick={handleGenerateReplay} disabled={!replayDeviceId || replayLoading}>
                <PlayCircle size={16} />
                {replayLoading ? '生成中...' : '生成回放'}
              </button>
            </div>

            {selectedReplayBounds?.latest_timestamp ? (
              <div className="runtime-layer__note" style={{ minHeight: 'auto', marginTop: '4px' }}>
                当前探头最近可播范围：{formatDateTime(selectedReplayBounds.earliest_timestamp)} 至 {formatDateTime(selectedReplayBounds.latest_timestamp)}
              </div>
            ) : null}

            {replayError ? (
              <div style={{ padding: '12px 14px', borderLeft: '3px solid var(--status-err)', background: 'rgba(239,68,68,0.08)', color: 'var(--status-err)', fontSize: '0.82rem' }}>
                {replayError}
              </div>
            ) : null}

            <div className="ipfs-replayPanel__microStats">
              <div className="ipfs-replayPanel__microStat">
                <span>当前探头</span>
                <strong>{replayDeviceId || '未选择'}</strong>
              </div>
              <div className="ipfs-replayPanel__microStat">
                <span>命中 GOP</span>
                <strong>{replaySummary.count}</strong>
              </div>
              <div className="ipfs-replayPanel__microStat">
                <span>可播时长</span>
                <strong>{replaySummary.totalSeconds.toFixed(1)}s</strong>
              </div>
            </div>
          </div>

          {replayUrl ? (
            <div className="ipfs-replayPanel__stage">
              <div className="ipfs-replayPanel__stageHead">
                <div>
                  <div className="dashboard-kpi-card__eyebrow">Continuous Playback Ready</div>
                  <div className="dashboard-kpi-card__state" style={{ fontSize: '1rem', marginTop: '6px' }}>
                    {replayDeviceId}
                  </div>
                </div>
                <a href={replayUrl} target="_blank" rel="noopener noreferrer" className="ipfs-replayPanel__link">
                  打开 HLS 播放流 <ExternalLink size={14} />
                </a>
              </div>
              <div style={{ aspectRatio: '16 / 9', background: '#000' }}>
                <HlsPlayer url={replayUrl} autoPlay={false} muted={false} controls />
              </div>
              <div className="ipfs-replayPanel__summary">
                命中 GOP {replaySummary.count} 段，累计可播约 {replaySummary.totalSeconds.toFixed(1)} 秒。
                若时间段中间存在缺失 GOP，播放器会自动跳过空洞片段。
              </div>
              {exportSummary ? (
                <div style={{ padding: '14px 16px', borderTop: '1px solid var(--border-subtle)', display: 'grid', gap: '12px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', flexWrap: 'wrap', alignItems: 'flex-start' }}>
                    <div style={{ display: 'grid', gap: '6px' }}>
                      <div style={{ color: 'var(--nv-green)', fontFamily: 'var(--font-heading)', fontSize: '0.84rem' }}>
                        验证样本导出
                      </div>
                      <div style={{ color: 'var(--text-muted)', fontSize: '0.78rem', fontVariantNumeric: 'tabular-nums' }}>
                        实际时间段 {formatDateTime(exportSummary.actualStart)} 至 {formatDateTime(exportSummary.actualEnd)}
                      </div>
                      <div style={{ color: 'var(--text-muted)', fontSize: '0.78rem', fontVariantNumeric: 'tabular-nums' }}>
                        命中可导出 GOP {exportSummary.playableCount} 段，样本时长约 {exportSummary.playableDurationSeconds.toFixed(1)} 秒，缺口 {exportSummary.gapCount} 处
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                      <a href={exportSummary.tsUrl} className="btn btn-primary" style={{ textDecoration: 'none' }}>
                        <Download size={14} />
                        下载验证样本 TS
                      </a>
                      <a href={exportSummary.jsonUrl} className="btn btn-ghost" style={{ textDecoration: 'none' }}>
                        <Download size={14} />
                        下载导出清单 JSON
                      </a>
                    </div>
                  </div>
                  {exportSummary.gapFlag ? (
                    <div style={{ padding: '12px 14px', borderLeft: '3px solid var(--status-warn)', background: 'rgba(245, 158, 11, 0.08)', color: 'var(--status-warn)', fontSize: '0.8rem', textWrap: 'pretty' }}>
                      当前导出样本为非连续证据。下载得到的 TS 只包含当前可恢复 GOP，后续在验证端应按部分覆盖样本理解，不要把中间空洞误当成二次篡改。
                    </div>
                  ) : (
                    <div style={{ padding: '12px 14px', borderLeft: '3px solid var(--nv-green)', background: 'rgba(118, 185, 0, 0.08)', color: 'var(--text-muted)', fontSize: '0.8rem' }}>
                      当前导出样本为连续证据，可直接上传到验证终端进行闭环验证。
                    </div>
                  )}
                </div>
              ) : null}
            </div>
          ) : (
            <div className="ipfs-replayPanel__placeholder">
              <div>
                <div className="dashboard-kpi-card__eyebrow">Preview Stage</div>
                <div className="dashboard-kpi-card__state" style={{ marginTop: '8px' }}>等待生成回放</div>
                <p className="runtime-layer__note" style={{ minHeight: 'auto', marginTop: '12px' }}>
                  先选探头和时间段，右侧会生成连续回放预览。这里会始终作为这个页面的主舞台。
                </p>
              </div>
            </div>
          )}
        </div>
      </section>

      <section className="tech-panel" style={{ marginTop: '18px' }}>
        <div className="dashboard-sectionHeader">
          <div>
            <span className="dashboard-eyebrow">Matched GOP Evidence</span>
            <h3 className="dashboard-kpi-card__state" style={{ marginTop: '8px' }}>
              <HardDrive size={18} />
              GOP 辅助明细
            </h3>
          </div>
          <span className="dashboard-inlineStat">当前命中 {gops.length} 条记录</span>
        </div>

        {gops.length === 0 ? (
          <div className="recent-blocks__empty" style={{ minHeight: '120px' }}>当前时间范围没有命中 GOP 记录</div>
        ) : (
          <div className="ipfs-gopList">
            {gops.map((gop) => (
              <article key={`${gop.ipfs_cid}-${gop.gop_id}`} className="ipfs-gopCard">
                <div className="ipfs-gopCard__head">
                  <div>
                    <div className="dashboard-kpi-card__eyebrow">GOP #{gop.gop_id}</div>
                    <div className="dashboard-kpi-card__state" style={{ fontSize: '1rem', marginTop: '6px' }}>{gop.device_id}</div>
                  </div>
                  <div className="ipfs-gopCard__actions">
                    <button
                      type="button"
                      className="ipfs-gopTable__copy"
                      onClick={() => {
                        navigator.clipboard?.writeText(gop.ipfs_cid || '');
                        setCopiedCid(gop.ipfs_cid || '');
                      }}
                    >
                      复制 CID <Copy size={11} />
                    </button>
                  </div>
                </div>

                <div className="ipfs-gopCard__meta">
                  <div className="ipfs-gopCard__metaItem">
                    <span>时间</span>
                    <strong>{formatDateTime(gop.timestamp)}</strong>
                  </div>
                  <div className="ipfs-gopCard__metaItem">
                    <span>时长</span>
                    <strong>{Number(gop.duration || 0).toFixed(1)}s</strong>
                  </div>
                  <div className="ipfs-gopCard__metaItem">
                    <span>哈希</span>
                    <strong>{gop.sha256_hash?.slice(0, 18)}...</strong>
                  </div>
                </div>

                <div className="ipfs-gopCard__cid">
                  <span>CID</span>
                  <code>{gop.ipfs_cid}</code>
                </div>

                <div className="ipfs-gopCard__links">
                  {gop.playback_playlist_url ? (
                    <a href={gop.playback_playlist_url} target="_blank" rel="noopener noreferrer">
                      <PlayCircle size={14} />
                      播放该 GOP
                    </a>
                  ) : null}
                  {gop.gateway_url ? (
                    <a href={gop.gateway_url} target="_blank" rel="noopener noreferrer">
                      <ExternalLink size={14} />
                      打开 Gateway
                    </a>
                  ) : null}
                </div>
              </article>
            ))}
            {copiedCid ? (
              <div className="runtime-layer__note" style={{ minHeight: 'auto', marginTop: '10px' }}>
                已复制 CID：{copiedCid}
              </div>
            ) : null}
          </div>
        )}
      </section>
    </div>
  );
}
