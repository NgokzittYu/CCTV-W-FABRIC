import { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Blocks, Hash, Link2, Search, ShieldCheck } from 'lucide-react';
import { getBatchDetails, getRecentBlocks, queryLedger } from '../services/api';
import BlockDetailModal from '../components/BlockDetailModal';
import RecentBlocksRail from '../components/RecentBlocksRail';

function QueryResultCard({ result, onOpen }) {
  if (!result) return null;

  return (
    <motion.div
      className="tech-panel ledger-queryResult"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.2, ease: [0.2, 0, 0, 1] }}
    >
      <div className="dashboard-sectionHeader" style={{ marginBottom: '14px' }}>
        <div>
          <span className="dashboard-eyebrow">Query Result</span>
          <h3 className="dashboard-kpi-card__state" style={{ marginTop: '8px' }}>
            <Blocks size={18} />
            区块 #{result.block_number ?? '—'}
          </h3>
        </div>
        <button type="button" className="btn btn-ghost" onClick={() => onOpen?.(result.batch_id)}>
          <ShieldCheck size={14} />
          查看详情
        </button>
      </div>

      <div className="block-detail-grid">
        <div className="block-detail-metric">
          <span>Batch ID</span>
          <strong>{result.batch_id || '—'}</strong>
        </div>
        <div className="block-detail-metric">
          <span>批次 GOP 数</span>
          <strong>{result.event_count ?? result.events?.length ?? 0}</strong>
        </div>
        <div className="block-detail-metric">
          <span>TX ID</span>
          <strong style={{ fontSize: '0.82rem' }}>{(result.tx_id || '—').slice(0, 18)}</strong>
        </div>
        <div className="block-detail-metric">
          <span>Merkle Root</span>
          <strong style={{ fontSize: '0.82rem' }}>{(result.merkle_root || '—').slice(0, 18)}</strong>
        </div>
      </div>
    </motion.div>
  );
}

export default function LedgerPage() {
  const [blocks, setBlocks] = useState([]);
  const [query, setQuery] = useState('');
  const [queryResult, setQueryResult] = useState(null);
  const [queryState, setQueryState] = useState('idle');
  const [queryMessage, setQueryMessage] = useState('');
  const [selectedBatchId, setSelectedBatchId] = useState(null);
  const [selectedDetail, setSelectedDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    let disposed = false;

    const refresh = async () => {
      try {
        const next = await getRecentBlocks(5);
        if (!disposed) setBlocks(next.blocks || []);
      } catch {}
    };

    refresh();
    const timer = setInterval(refresh, 8000);
    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (!selectedBatchId) return undefined;
    let disposed = false;
    setDetailLoading(true);
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

  const newestBlock = useMemo(() => blocks[0] || null, [blocks]);

  const handleQuery = async () => {
    if (!query.trim()) {
      setQueryState('error');
      setQueryMessage('请输入 block_number、batch_id 或 tx_id。');
      setQueryResult(null);
      return;
    }

    try {
      setQueryState('loading');
      setQueryMessage('');
      const result = await queryLedger(query.trim());
      setQueryResult(result);
      setQueryState('ok');
    } catch (error) {
      setQueryResult(null);
      setQueryState('error');
      setQueryMessage(error?.message || '查询失败');
    }
  };

  return (
    <div className="main-content" style={{ padding: '36px 40px 42px' }}>
      <section className="tech-panel ledger-hero">
        <div className="dashboard-sectionHeader">
          <div>
            <span className="dashboard-eyebrow">Fabric / Live Chain View</span>
            <h2 className="dashboard-title" style={{ marginTop: '8px' }}>
              <Blocks size={24} />
              区块链账本
            </h2>
          </div>
          <div className="ledger-liveBadge">
            <span>最新区块</span>
            <strong>{newestBlock?.block_number != null ? `#${newestBlock.block_number}` : '—'}</strong>
          </div>
        </div>

        <RecentBlocksRail
          blocks={blocks}
          mode="chain"
          onSelect={(block) => {
            setSelectedDetail(null);
            setSelectedBatchId(block.batch_id);
          }}
        />
      </section>

      <section className="tech-panel" style={{ marginTop: '18px' }}>
        <div className="dashboard-sectionHeader">
          <div>
            <span className="dashboard-eyebrow">Ledger Query</span>
            <h3 className="dashboard-kpi-card__state" style={{ marginTop: '8px' }}>
              <Search size={18} />
              区块查询
            </h3>
          </div>
          <span className="dashboard-inlineStat">支持 block_number / batch_id / tx_id</span>
        </div>

        <div className="ledger-queryBar">
          <div className="ledger-queryBar__inputWrap">
            <Hash size={14} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="例如：81 / batch-live-xxxx / tx1234..."
            />
          </div>
          <button type="button" className="btn" onClick={handleQuery}>
            <Search size={15} />
            查询区块
          </button>
        </div>

        {queryState === 'error' ? (
          <div className="dashboard-errorHint" style={{ marginTop: '14px' }}>QUERY ERROR // {queryMessage}</div>
        ) : null}

        {queryState === 'loading' ? (
          <div className="recent-blocks__empty" style={{ minHeight: '120px', marginTop: '14px' }}>正在查询区块...</div>
        ) : null}

        <AnimatePresence initial={false}>
          {queryState === 'ok' && queryResult ? (
            <QueryResultCard
              key={queryResult.batch_id}
              result={queryResult}
              onOpen={(batchId) => {
                setSelectedDetail(null);
                setSelectedBatchId(batchId);
              }}
            />
          ) : null}
        </AnimatePresence>

        {queryState === 'ok' && !queryResult ? (
          <div className="recent-blocks__empty" style={{ minHeight: '120px', marginTop: '14px' }}>
            没有找到匹配的区块记录
          </div>
        ) : null}

        <div className="ledger-queryHints">
          <span><Blocks size={12} /> block_number 适合按高度直达</span>
          <span><Link2 size={12} /> tx_id / batch_id 适合按证据记录定位</span>
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
