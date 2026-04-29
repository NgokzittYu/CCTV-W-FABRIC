import { useState } from 'react';
import {
  AlertTriangle, Plus, Send, CheckCircle, XCircle,
  Search, FileText, Hash, UserRound, CalendarClock,
  ClipboardCheck, Paperclip, MessageSquare
} from 'lucide-react';
import {
  createWorkorder, getWorkorder,
  submitRectification, confirmRectification, exportAuditTrail
} from '../services/api';

const statusMeta = {
  OPEN: { label: '待整改', color: 'var(--status-warn)', bg: 'var(--status-warn-dim)' },
  SUBMITTED: { label: '待确认', color: 'var(--status-info)', bg: 'var(--status-info-dim)' },
  CONFIRMED: { label: '已确认', color: 'var(--nv-green)', bg: 'var(--nv-green-dim)' },
  REJECTED: { label: '已驳回', color: 'var(--status-err)', bg: 'var(--status-err-dim)' },
};

function formatTime(value) {
  if (!value) return '—';
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric < 1000000000) return `${value}`;
  return new Date(numeric * 1000).toLocaleString('zh-CN', { hour12: false });
}

function formatDeadline(value) {
  if (!value) return '—';
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return `${value}`;
  if (numeric < 1000000000) return `${numeric} 小时`;
  return formatTime(numeric);
}

function DetailItem({ label, value, mono = false }) {
  return (
    <div style={{
      minWidth: 0,
      padding: '12px 14px',
      border: '1px solid var(--border-subtle)',
      background: 'rgba(255, 255, 255, 0.45)',
    }}>
      <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginBottom: '6px' }}>{label}</div>
      <div style={{
        color: 'var(--text-pure)',
        fontFamily: mono ? 'var(--font-data)' : 'inherit',
        fontSize: mono ? '0.78rem' : '0.86rem',
        wordBreak: 'break-all',
      }}>
        {value || '—'}
      </div>
    </div>
  );
}

function WorkorderResult({ data }) {
  if (data.error) {
    return (
      <div style={{
        marginTop: '16px',
        padding: '14px 16px',
        border: '1px solid var(--status-err)',
        background: 'var(--status-err-dim)',
        color: 'var(--status-err)',
        fontSize: '0.84rem',
      }}>
        查询失败：{data.error}
      </div>
    );
  }

  const meta = statusMeta[data.status] || { label: data.status || '未知', color: 'var(--text-muted)', bg: 'rgba(148, 163, 184, 0.12)' };
  const history = Array.isArray(data.history) ? data.history : [];
  const attachments = Array.isArray(data.attachments) ? data.attachments : [];

  return (
    <div style={{
      marginTop: '16px',
      border: '1px solid var(--border-subtle)',
      background: 'var(--bg-pure)',
    }}>
      <div style={{
        padding: '16px 18px',
        borderBottom: '1px solid var(--border-subtle)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: '14px',
        flexWrap: 'wrap',
      }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-muted)', fontSize: '0.72rem', marginBottom: '6px' }}>
            <Hash size={13} /> 工单编号
          </div>
          <div style={{ color: 'var(--text-pure)', fontFamily: 'var(--font-data)', fontSize: '1rem', wordBreak: 'break-all' }}>
            {data.id || '—'}
          </div>
        </div>
        <span style={{
          padding: '7px 12px',
          border: `1px solid ${meta.color}`,
          background: meta.bg,
          color: meta.color,
          fontSize: '0.76rem',
          fontWeight: 700,
        }}>
          {meta.label}
        </span>
      </div>

      <div style={{ padding: '18px', display: 'grid', gap: '18px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '10px' }}>
          <DetailItem label="关联批次" value={data.batchId} mono />
          <DetailItem label="创建组织" value={data.createdBy} />
          <DetailItem label="责任组织" value={data.assignedTo} />
          <DetailItem label="整改期限" value={formatDeadline(data.deadline)} />
          <DetailItem label="创建时间" value={formatTime(data.createdAt)} />
          <DetailItem label="更新时间" value={formatTime(data.updatedAt)} />
        </div>

        <section style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '16px' }}>
          <h4 style={{ display: 'flex', alignItems: 'center', gap: '8px', margin: '0 0 10px', color: 'var(--nv-green)' }}>
            <ClipboardCheck size={16} /> 工单流转
          </h4>
          {history.length === 0 ? (
            <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>暂无流转记录</div>
          ) : (
            <div style={{ display: 'grid', gap: '8px' }}>
              {history.map((item, index) => (
                <div key={`${item.at}-${index}`} style={{
                  display: 'grid',
                  gridTemplateColumns: '110px minmax(120px, 1fr) minmax(160px, 2fr)',
                  gap: '12px',
                  alignItems: 'start',
                  padding: '12px 14px',
                  border: '1px solid var(--border-subtle)',
                  background: 'rgba(255, 255, 255, 0.38)',
                  fontSize: '0.8rem',
                }}>
                  <div style={{ color: 'var(--nv-green)', fontWeight: 700 }}>{item.action || 'UPDATE'}</div>
                  <div style={{ color: 'var(--text-muted)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><UserRound size={12} /> {item.byMsp || item.byMSP || '—'}</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '4px' }}><CalendarClock size={12} /> {formatTime(item.at)}</div>
                  </div>
                  <div style={{ color: 'var(--text-pure)', wordBreak: 'break-word' }}>
                    {item.comment || '—'}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '12px' }}>
          <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '14px' }}>
            <h4 style={{ display: 'flex', alignItems: 'center', gap: '8px', margin: '0 0 10px', color: 'var(--nv-green)' }}>
              <Paperclip size={16} /> 附件
            </h4>
            {attachments.length === 0 ? (
              <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>暂无附件</div>
            ) : (
              <div style={{ display: 'grid', gap: '6px' }}>
                {attachments.map((item, index) => (
                  <div key={`${item}-${index}`} style={{ color: 'var(--status-info)', fontFamily: 'var(--font-data)', fontSize: '0.75rem', wordBreak: 'break-all' }}>
                    {item}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '14px' }}>
            <h4 style={{ display: 'flex', alignItems: 'center', gap: '8px', margin: '0 0 10px', color: 'var(--nv-green)' }}>
              <MessageSquare size={16} /> 最近备注
            </h4>
            <div style={{ color: 'var(--text-pure)', fontSize: '0.85rem', lineHeight: 1.7 }}>
              {history[history.length - 1]?.comment || '—'}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

export default function WorkorderPage() {
  const [tab, setTab] = useState('query'); // 'query' | 'create' | 'submit' | 'confirm' | 'audit'
  const [result, setResult] = useState(null);

  // Forms
  const [createForm, setCreateForm] = useState({ violationId: '', description: '', assignedOrg: 'Org1MSP', deadline: '72' });
  const [queryId, setQueryId] = useState('');
  const [queryResult, setQueryResult] = useState(null);
  const [submitForm, setSubmitForm] = useState({ orderId: '', proof: '', attachments: '' });
  const [confirmForm, setConfirmForm] = useState({ orderId: '', approved: true, comments: '' });
  const [auditBatchId, setAuditBatchId] = useState('');
  const [auditData, setAuditData] = useState(null);

  const handleCreate = async () => {
    setResult(null);
    try {
      const res = await createWorkorder(createForm);
      setResult({ type: 'success', message: `工单已创建: ${res.orderId || res.order_id || JSON.stringify(res)}` });
    } catch (e) {
      setResult({ type: 'error', message: e.message });
    }
  };

  const handleQuery = async () => {
    setQueryResult(null);
    try {
      const res = await getWorkorder(queryId);
      setQueryResult(res);
    } catch (e) {
      setQueryResult({ error: e.message });
    }
  };

  const handleSubmit = async () => {
    setResult(null);
    try {
      const data = {
        orderId: submitForm.orderId,
        proof: submitForm.proof,
        attachments: submitForm.attachments ? submitForm.attachments.split(',').map((s) => s.trim()) : [],
      };
      const res = await submitRectification(data);
      setResult({ type: 'success', message: `整改已提交: ${JSON.stringify(res)}` });
    } catch (e) {
      setResult({ type: 'error', message: e.message });
    }
  };

  const handleConfirm = async () => {
    setResult(null);
    try {
      const res = await confirmRectification(confirmForm);
      setResult({ type: 'success', message: `操作完成: ${JSON.stringify(res)}` });
    } catch (e) {
      setResult({ type: 'error', message: e.message });
    }
  };

  const handleAuditExport = async () => {
    setAuditData(null);
    try {
      const res = await exportAuditTrail(auditBatchId);
      setAuditData(res);
    } catch (e) {
      setAuditData({ error: e.message });
    }
  };

  const tabs = [
    { id: 'query', label: '查询工单', icon: Search },
    { id: 'create', label: '创建工单', icon: Plus },
    { id: 'submit', label: '提交整改', icon: Send },
    { id: 'confirm', label: '确认整改', icon: CheckCircle },
    { id: 'audit', label: '审计导出', icon: FileText },
  ];

  return (
    <div className="main-content" style={{ padding: '40px' }}>
      <div style={{ paddingBottom: '16px', borderBottom: '1px solid var(--border-subtle)' }}>
        <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--nv-green)' }}>
          <AlertTriangle size={24} /> 告警与工单
        </h2>
        <h4 style={{ color: 'var(--text-muted)' }}>整改工单管理 · 审计导出</h4>
      </div>

      {/* Sub Tabs */}
      <div style={{ display: 'flex', gap: '4px', marginTop: '24px', flexWrap: 'wrap' }}>
        {tabs.map((t) => {
          const Icon = t.icon;
          return (
            <button
              key={t.id}
              className={`btn ${tab === t.id ? 'btn-primary' : ''}`}
              onClick={() => { setTab(t.id); setResult(null); }}
              style={{ minHeight: '36px', fontSize: '0.8rem' }}
            >
              <Icon size={14} /> {t.label}
            </button>
          );
        })}
      </div>

      <div style={{ marginTop: '16px' }}>
        {/* Create Workorder */}
        {tab === 'create' && (
          <div className="tech-panel">
            <h3 style={{ marginBottom: '16px', color: 'var(--nv-green)' }}>创建整改工单</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', maxWidth: '500px' }}>
              {[
                { key: 'violationId', label: '违规 ID' },
                { key: 'description', label: '描述' },
                { key: 'assignedOrg', label: '指定组织' },
                { key: 'deadline', label: '截止时间 (小时)' },
              ].map(({ key, label }) => (
                <div key={key}>
                  <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>{label}</label>
                  <input className="input-raw" value={createForm[key]} onChange={(e) => setCreateForm((f) => ({ ...f, [key]: e.target.value }))} />
                </div>
              ))}
              <button className="btn btn-primary" onClick={handleCreate} style={{ alignSelf: 'flex-start' }}>
                <Plus size={14} /> 创建
              </button>
            </div>
          </div>
        )}

        {/* Query Workorder */}
        {tab === 'query' && (
          <div className="tech-panel">
            <h3 style={{ marginBottom: '16px', color: 'var(--nv-green)' }}>查询工单</h3>
            <div style={{ display: 'flex', gap: '8px', maxWidth: '500px' }}>
              <input className="input-raw" value={queryId} onChange={(e) => setQueryId(e.target.value)} placeholder="输入工单 ID" />
              <button
                className="btn btn-primary"
                onClick={handleQuery}
                style={{ minWidth: '96px', whiteSpace: 'nowrap', flexShrink: 0 }}
              >
                <Search size={14} /> 查询
              </button>
            </div>
            {queryResult && (
              <WorkorderResult data={queryResult} />
            )}
          </div>
        )}

        {/* Submit Rectification */}
        {tab === 'submit' && (
          <div className="tech-panel">
            <h3 style={{ marginBottom: '16px', color: 'var(--nv-green)' }}>提交整改证明</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', maxWidth: '500px' }}>
              <div>
                <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>工单 ID</label>
                <input className="input-raw" value={submitForm.orderId} onChange={(e) => setSubmitForm((f) => ({ ...f, orderId: e.target.value }))} />
              </div>
              <div>
                <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>整改证明</label>
                <textarea className="input-raw" rows={3} value={submitForm.proof} onChange={(e) => setSubmitForm((f) => ({ ...f, proof: e.target.value }))} style={{ resize: 'vertical' }} />
              </div>
              <div>
                <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>附件 (逗号分隔)</label>
                <input className="input-raw" value={submitForm.attachments} onChange={(e) => setSubmitForm((f) => ({ ...f, attachments: e.target.value }))} />
              </div>
              <button className="btn btn-primary" onClick={handleSubmit} style={{ alignSelf: 'flex-start' }}>
                <Send size={14} /> 提交
              </button>
            </div>
          </div>
        )}

        {/* Confirm Rectification */}
        {tab === 'confirm' && (
          <div className="tech-panel">
            <h3 style={{ marginBottom: '16px', color: 'var(--nv-green)' }}>确认/驳回整改</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', maxWidth: '500px' }}>
              <div>
                <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>工单 ID</label>
                <input className="input-raw" value={confirmForm.orderId} onChange={(e) => setConfirmForm((f) => ({ ...f, orderId: e.target.value }))} />
              </div>
              <div>
                <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>操作</label>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button className={`btn ${confirmForm.approved ? 'btn-primary' : ''}`} onClick={() => setConfirmForm((f) => ({ ...f, approved: true }))}>
                    <CheckCircle size={14} /> 批准
                  </button>
                  <button className={`btn ${!confirmForm.approved ? 'btn-primary' : ''}`} onClick={() => setConfirmForm((f) => ({ ...f, approved: false }))} style={!confirmForm.approved ? { background: 'var(--status-err)', borderColor: 'var(--status-err)' } : {}}>
                    <XCircle size={14} /> 驳回
                  </button>
                </div>
              </div>
              <div>
                <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>备注</label>
                <textarea className="input-raw" rows={2} value={confirmForm.comments} onChange={(e) => setConfirmForm((f) => ({ ...f, comments: e.target.value }))} style={{ resize: 'vertical' }} />
              </div>
              <button className="btn btn-primary" onClick={handleConfirm} style={{ alignSelf: 'flex-start' }}>
                <Send size={14} /> 提交
              </button>
            </div>
          </div>
        )}

        {/* Audit Export */}
        {tab === 'audit' && (
          <div className="tech-panel">
            <h3 style={{ marginBottom: '16px', color: 'var(--nv-green)' }}>审计报告导出</h3>
            <div style={{ display: 'flex', gap: '8px', maxWidth: '500px' }}>
              <input className="input-raw" value={auditBatchId} onChange={(e) => setAuditBatchId(e.target.value)} placeholder="输入 Batch ID" />
              <button className="btn btn-primary" onClick={handleAuditExport}><FileText size={14} /> 导出</button>
            </div>
            {auditData && (
              <div style={{ marginTop: '16px', padding: '16px', background: 'var(--bg-pure)', border: '1px solid var(--border-subtle)' }}>
                <pre style={{ fontFamily: 'var(--font-data)', fontSize: '0.75rem', color: 'var(--text-muted)', whiteSpace: 'pre-wrap', wordBreak: 'break-all', margin: 0 }}>
                  {JSON.stringify(auditData, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}

        {/* Result Banner */}
        {result && (
          <div style={{
            marginTop: '16px', padding: '12px 16px',
            background: result.type === 'success' ? 'var(--nv-green-dim)' : 'var(--status-err-dim)',
            border: `1px solid ${result.type === 'success' ? 'var(--nv-green)' : 'var(--status-err)'}`,
            fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '8px',
          }}>
            {result.type === 'success' ? <CheckCircle size={16} color="var(--nv-green)" /> : <XCircle size={16} color="var(--status-err)" />}
            <span style={{ color: result.type === 'success' ? 'var(--nv-green)' : 'var(--status-err)' }}>{result.message}</span>
          </div>
        )}
      </div>
    </div>
  );
}
