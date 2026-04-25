import { useState, useEffect } from 'react';
import {
  AlertTriangle, Plus, Send, CheckCircle, XCircle,
  ClipboardList, Clock, Search, FileText
} from 'lucide-react';
import {
  getOverdueWorkorders, createWorkorder, getWorkorder,
  submitRectification, confirmRectification, exportAuditTrail
} from '../services/api';

export default function WorkorderPage() {
  const [tab, setTab] = useState('list'); // 'list' | 'create' | 'query' | 'submit' | 'confirm'
  const [overdueList, setOverdueList] = useState([]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  // Forms
  const [createForm, setCreateForm] = useState({ violationId: '', description: '', assignedOrg: 'Org1MSP', deadline: '72' });
  const [queryId, setQueryId] = useState('');
  const [queryResult, setQueryResult] = useState(null);
  const [submitForm, setSubmitForm] = useState({ orderId: '', proof: '', attachments: '' });
  const [confirmForm, setConfirmForm] = useState({ orderId: '', approved: true, comments: '' });
  const [auditBatchId, setAuditBatchId] = useState('');
  const [auditData, setAuditData] = useState(null);

  useEffect(() => {
    if (tab === 'list') {
      setLoading(true);
      getOverdueWorkorders()
        .then((d) => setOverdueList(d.workorders || d.orders || []))
        .catch(() => setOverdueList([]))
        .finally(() => setLoading(false));
    }
  }, [tab]);

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
    { id: 'list', label: '逾期工单', icon: ClipboardList },
    { id: 'create', label: '创建工单', icon: Plus },
    { id: 'query', label: '查询工单', icon: Search },
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
        {/* Overdue List */}
        {tab === 'list' && (
          <div className="tech-panel">
            <h3 style={{ marginBottom: '16px', color: 'var(--status-warn)', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Clock size={18} /> 逾期工单列表
            </h3>
            {loading ? (
              <div className="terminal-block">正在拉取逾期工单...</div>
            ) : overdueList.length === 0 ? (
              <div className="terminal-block" style={{ color: 'var(--text-muted)' }}>[空] // 暂无逾期工单</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {overdueList.map((wo, i) => (
                  <div key={i} style={{
                    padding: '12px 16px', background: 'var(--bg-pure)', border: '1px solid var(--border-subtle)',
                    display: 'flex', alignItems: 'center', gap: '12px', fontSize: '0.8rem',
                  }}>
                    <AlertTriangle size={14} color="var(--status-warn)" />
                    <span style={{ fontWeight: 700 }}>{wo.orderId || wo.order_id || `工单 ${i + 1}`}</span>
                    <span style={{ color: 'var(--text-muted)', flex: 1 }}>{wo.description || ''}</span>
                    <span className="tag tag-warn">{wo.status || '逾期'}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

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
              <button className="btn btn-primary" onClick={handleQuery}><Search size={14} /> 查询</button>
            </div>
            {queryResult && (
              <div style={{ marginTop: '16px', padding: '16px', background: 'var(--bg-pure)', border: '1px solid var(--border-subtle)' }}>
                <pre style={{ fontFamily: 'var(--font-data)', fontSize: '0.75rem', color: 'var(--text-muted)', whiteSpace: 'pre-wrap', wordBreak: 'break-all', margin: 0 }}>
                  {JSON.stringify(queryResult, null, 2)}
                </pre>
              </div>
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
