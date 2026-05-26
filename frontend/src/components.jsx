import { useState, useEffect, createContext, useContext, useCallback } from 'react';

// ── Toast Context ─────────────────────────────────────────
const ToastCtx = createContext(null);

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const add = useCallback((msg, type = 'info') => {
    const id = Date.now();
    setToasts(t => [...t, { id, msg, type }]);
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 4000);
  }, []);
  return (
    <ToastCtx.Provider value={add}>
      {children}
      <div className="toast-container">
        {toasts.map(t => (
          <div key={t.id} className={`toast toast-${t.type}`}>
            <span>{t.type === 'success' ? '✅' : t.type === 'error' ? '❌' : 'ℹ️'}</span>
            <span>{t.msg}</span>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}
export const useToast = () => useContext(ToastCtx);

// ── Status Badge ─────────────────────────────────────────
export function StatusBadge({ status }) {
  if (!status) return null;
  const s = status.toLowerCase();
  return <span className={`badge badge-${s}`}>{status.replace('_', ' ')}</span>;
}

// ── DISC Chip ─────────────────────────────────────────────
export function DISCChip({ type }) {
  if (!type || type === 'UNKNOWN') return <span className="disc-chip disc-UNKNOWN">?</span>;
  return <span className={`disc-chip disc-${type}`}>{type}</span>;
}

// ── Spinner ───────────────────────────────────────────────
export function Spinner({ size }) {
  return <div className={`spinner${size === 'lg' ? ' spinner-lg' : ''}`} />;
}

// ── Enrich Dots ───────────────────────────────────────────
export function EnrichDots({ status }) {
  if (!status) return null;
  const sources = ['opencorporates', 'hunter', 'serper', 'company_analysis'];
  return (
    <div className="enrich-dots" title="Enrichment: OC / Hunter / Serper / Analysis">
      {sources.map(s => (
        <div
          key={s}
          className={`enrich-dot ${status[s]?.fresh ? 'fresh' : status[s]?.has_data ? 'stale' : 'empty'}`}
          title={`${s}: ${status[s]?.fresh ? 'fresh' : status[s]?.has_data ? 'cached' : 'empty'}`}
        />
      ))}
    </div>
  );
}

// ── Modal ─────────────────────────────────────────────────
export function Modal({ open, onClose, title, children, size }) {
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose(); };
    if (open) window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className={`modal${size ? ' modal-' + size : ''}`} onClick={e => e.stopPropagation()}>
        {title && (
          <div className="modal-header">
            <h3 className="modal-title">{title}</h3>
            <button className="btn btn-ghost btn-icon" onClick={onClose}>✕</button>
          </div>
        )}
        {children}
      </div>
    </div>
  );
}

// ── Empty State ───────────────────────────────────────────
export function EmptyState({ icon, title, text, action }) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">{icon || '📭'}</div>
      <div className="empty-state-title">{title || 'Nothing here yet'}</div>
      <div className="empty-state-text">{text}</div>
      {action && <div style={{ marginTop: 20 }}>{action}</div>}
    </div>
  );
}

// ── Copy Button ───────────────────────────────────────────
export function CopyButton({ text, label = 'Copy' }) {
  const [copied, setCopied] = useState(false);
  const handle = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <button className="btn btn-secondary btn-sm" onClick={handle}>
      {copied ? '✅ Copied' : `📋 ${label}`}
    </button>
  );
}

// ── Confirm Button ────────────────────────────────────────
export function ConfirmButton({ label, onConfirm, className = 'btn btn-danger btn-sm', confirmLabel = 'Sure?' }) {
  const [confirming, setConfirming] = useState(false);
  if (confirming) return (
    <span style={{ display: 'inline-flex', gap: 6 }}>
      <button className="btn btn-danger btn-sm" onClick={() => { setConfirming(false); onConfirm(); }}>{confirmLabel}</button>
      <button className="btn btn-secondary btn-sm" onClick={() => setConfirming(false)}>Cancel</button>
    </span>
  );
  return <button className={className} onClick={() => setConfirming(true)}>{label}</button>;
}

// ── useApi hook ───────────────────────────────────────────
export function useApi(apiFn, deps = [], opts = {}) {
  const [data, setData] = useState(opts.initial ?? null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await apiFn();
      setData(result);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, deps);

  useEffect(() => { load(); }, [load]);

  return { data, loading, error, reload: load, setData };
}

// ── Format helpers ────────────────────────────────────────
export function fmtDate(d) {
  if (!d) return '—';
  return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

export function fmtRelative(d) {
  if (!d) return '—';
  const diff = Date.now() - new Date(d).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

export function truncate(str, n = 60) {
  if (!str) return '—';
  return str.length > n ? str.slice(0, n) + '…' : str;
}
