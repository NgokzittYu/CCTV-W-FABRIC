import { Shield, ShieldAlert, ShieldCheck } from 'lucide-react';

const config = {
  INTACT: {
    label: '完整',
    labelEn: 'INTACT',
    className: 'badge-intact',
    Icon: ShieldCheck,
  },
  RE_ENCODED: {
    label: '合法转码',
    labelEn: 'RE_ENCODED',
    className: 'badge-re-encoded',
    Icon: Shield,
  },
  TAMPERED: {
    label: '高危篡改',
    labelEn: 'TAMPERED',
    className: 'badge-tampered',
    Icon: ShieldAlert,
  },
};

export default function StatusBadge({ state, showIcon = true, showEn = true }) {
  const c = config[state] || config.TAMPERED;
  const { Icon } = c;

  return (
    <span className={`badge ${c.className}`}>
      {showIcon && <Icon size={14} />}
      {c.label}
      {showEn && <span style={{ opacity: 0.7, marginLeft: 2 }}>({c.labelEn})</span>}
    </span>
  );
}
