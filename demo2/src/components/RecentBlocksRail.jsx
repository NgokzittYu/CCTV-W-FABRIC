import { motion } from 'framer-motion';
import { Blocks, Clock, Layers, Link2 } from 'lucide-react';

function formatDateTime(timestamp) {
  if (!timestamp) return '—';
  return new Date(Number(timestamp) * 1000).toLocaleString('zh-CN', {
    hour12: false,
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function formatChainDateTime(timestamp) {
  if (!timestamp) return { date: '—', time: '—' };
  const parts = formatDateTime(timestamp).split(' ');
  return {
    date: parts[0] || '—',
    time: parts[1] || '—',
  };
}

function formatRoot(value) {
  return value || '—';
}

function formatTxId(value) {
  if (!value) return '—';
  return value.length > 10 ? value.slice(0, 10) : value;
}

export default function RecentBlocksRail({ blocks = [], mode = 'compact', onSelect }) {
  const visibleBlocks = mode === 'chain' ? blocks.slice(0, 5) : blocks;

  if (!blocks.length) {
    return (
      <div className={`recent-blocks recent-blocks--${mode}`}>
        <div className="recent-blocks__empty">暂无最新区块</div>
      </div>
    );
  }

  return (
    <div className={`recent-blocks recent-blocks--${mode}`}>
      {visibleBlocks.map((block, index) => (
        <motion.button
          key={block.batch_id || `${block.block_number}-${block.tx_id}`}
          type="button"
          className={`recent-blocks__node recent-blocks__node--${mode}${mode === 'chain' && index === 0 ? ' is-latest' : ''}`}
          initial={false}
          whileHover={{ y: -2 }}
          whileTap={{ scale: 0.96 }}
          transition={{ type: 'spring', duration: 0.3, bounce: 0 }}
          onClick={() => onSelect?.(block)}
        >
          {mode === 'chain' && index < visibleBlocks.length - 1 ? <span className="recent-blocks__link" /> : null}
          <div className="recent-blocks__nodeHead">
            <div className="recent-blocks__blockBadge">
              <Blocks size={13} />
              <span>#{block.block_number ?? '—'}</span>
            </div>
            {mode === 'chain' && index === 0 ? (
              <span className="recent-blocks__latest">最新</span>
            ) : mode !== 'chain' ? (
              <span className="recent-blocks__count">{block.event_count ?? 0} GOP</span>
            ) : null}
          </div>

          {mode === 'chain' ? (
            <div className="recent-blocks__chainBody">
              <span className="recent-blocks__time">
                <Clock size={11} />
                <span className="recent-blocks__timeText">
                  <span>{formatChainDateTime(block.timestamp).date}</span>
                  <span>{formatChainDateTime(block.timestamp).time}</span>
                </span>
              </span>
              <span className="recent-blocks__gopPill">
                <Layers size={11} />
                {block.event_count ?? 0} GOP
              </span>
            </div>
          ) : (
            <>
              <div className="recent-blocks__root">
                <span>Merkle Root</span>
                <strong title={block.merkle_root || undefined}>{formatRoot(block.merkle_root)}</strong>
              </div>
              <div className="recent-blocks__meta">
                <span>
                  <Clock size={12} />
                  {formatDateTime(block.timestamp)}
                </span>
                <span>
                  <Link2 size={12} />
                  {formatTxId(block.tx_id)}
                </span>
              </div>
            </>
          )}

          {mode === 'dashboard' ? <div className="recent-blocks__action">查看批次详情</div> : null}
        </motion.button>
      ))}
    </div>
  );
}
