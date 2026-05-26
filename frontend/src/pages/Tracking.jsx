import { useState } from 'react';
import api from '../api';
import { useToast, StatusBadge, Spinner, EmptyState, Modal, ConfirmButton, useApi, fmtDate, fmtRelative } from '../components';

// ════════════════════════════════════════════════════════════
//  Tracking Page
// ════════════════════════════════════════════════════════════
export function Tracking() {
  const toast = useToast();
  const [campaignId, setCampaignId] = useState('');
  const [processingFollowUps, setProcessingFollowUps] = useState(false);

  const { data: dashboard, loading, reload } = useApi(
    () => api.getDashboard(campaignId || undefined),
    [campaignId]
  );
  const { data: dueFollowUps, reload: reloadDue } = useApi(
    () => api.getDueFollowUps(campaignId || undefined),
    [campaignId]
  );
  const { data: campaigns } = useApi(() => api.getCampaigns());
  const { data: gmailStatus } = useApi(() => api.gmailStatus());

  const processFollowUps = async () => {
    setProcessingFollowUps(true);
    try {
      const r = await api.processFollowUps(campaignId || undefined);
      toast(`Follow-ups: ${r.generated} generated, ${r.errors} errors`, r.errors ? 'error' : 'success');
      reloadDue();
      reload();
    } catch (e) { toast(e.message, 'error'); }
    finally { setProcessingFollowUps(false); }
  };

  const pollGmail = async () => {
    try {
      const r = await api.pollGmail(campaignId || undefined);
      toast(`Gmail poll: ${r.new_replies_matched} new replies found`, 'info');
      reload();
    } catch (e) { toast(e.message, 'error'); }
  };

  const totals = dashboard?.totals || {};
  const metrics = dashboard?.metrics || {};

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">📊 Tracking</h1>
          <p className="page-subtitle">Monitor replies, follow-ups, and campaign performance</p>
        </div>
        <div className="flex gap-2 items-center">
          <select className="form-select" style={{ width: 'auto' }} value={campaignId} onChange={e => setCampaignId(e.target.value)}>
            <option value="">All Campaigns</option>
            {campaigns?.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <button className="btn btn-secondary btn-sm" onClick={reload}>🔄</button>
        </div>
      </div>

      {loading ? <div className="loading-overlay"><Spinner size="lg" /></div> : (
        <>
          {/* Stats */}
          <div className="stats-grid">
            <div className="stat-card">
              <div className="stat-label">Reply Rate</div>
              <div className="stat-value">{metrics.reply_rate_pct ?? 0}%</div>
              <div className="stat-sub">{totals.replied ?? 0} of {totals.sent ?? 0} sent</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Follow-ups Due</div>
              <div className="stat-value" style={{ color: (metrics.follow_ups_due_now ?? 0) > 0 ? 'var(--status-ignored)' : undefined }}>
                {metrics.follow_ups_due_now ?? 0}
              </div>
              <div className="stat-sub">need follow-up now</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Replied</div>
              <div className="stat-value">{totals.replied ?? 0}</div>
              <div className="stat-sub">contacts responded</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Ignored</div>
              <div className="stat-value">{totals.ignored ?? 0}</div>
              <div className="stat-sub">no reply yet</div>
            </div>
          </div>

          {/* Actions + Gmail */}
          <div className="grid-2" style={{ gap: 20, marginBottom: 24 }}>
            <div className="card">
              <div className="card-header">
                <span className="card-title">⚡ Follow-up Processor</span>
              </div>
              <p className="text-sm text-secondary" style={{ marginBottom: 16 }}>
                Automatically generate LLM follow-up drafts for all emails that are overdue.
                Processes up to 50 at once.
              </p>
              <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                <button className="btn btn-primary" disabled={processingFollowUps} onClick={processFollowUps}>
                  {processingFollowUps ? <><Spinner /> Processing…</> : `🔄 Process ${dueFollowUps?.count ?? 0} Due`}
                </button>
                <span className="text-xs text-muted">
                  {dueFollowUps?.count > 0 ? `${dueFollowUps.count} follow-up${dueFollowUps.count > 1 ? 's' : ''} pending` : 'No follow-ups due'}
                </span>
              </div>
            </div>

            <div className="card">
              <div className="card-header">
                <span className="card-title">📧 Gmail Integration</span>
                <span className={`badge ${gmailStatus?.authenticated ? 'badge-replied' : 'badge-ignored'}`}>
                  {gmailStatus?.authenticated ? '✓ Connected' : 'Not connected'}
                </span>
              </div>
              <p className="text-sm text-secondary" style={{ marginBottom: 16 }}>
                {gmailStatus?.message || 'Connect Gmail to push drafts and auto-detect replies.'}
              </p>
              <div className="flex gap-2">
                {!gmailStatus?.authenticated ? (
                  <button className="btn btn-secondary btn-sm" onClick={async () => {
                    const r = await api.gmailAuthorize();
                    if (r.url) window.open(r.url, '_blank');
                    else toast(r.message || 'Gmail not configured', 'error');
                  }}>🔗 Connect Gmail</button>
                ) : (
                  <button className="btn btn-secondary btn-sm" onClick={pollGmail}>📥 Poll Inbox</button>
                )}
              </div>
            </div>
          </div>

          {/* Status breakdown */}
          <div className="card">
            <div className="card-header">
              <span className="card-title">Email Status Breakdown</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {[
                { key: 'drafted', label: 'Drafted', icon: '📝' },
                { key: 'sent', label: 'Sent', icon: '📤' },
                { key: 'replied', label: 'Replied', icon: '💬' },
                { key: 'ignored', label: 'Ignored / No Reply', icon: '😶' },
                { key: 'follow_up_sent', label: 'Follow-up Sent', icon: '🔄' },
                { key: 'archived', label: 'Archived', icon: '🗄️' },
              ].map(({ key, label, icon }) => {
                const val = totals[key] ?? 0;
                const pct = totals.all > 0 ? (val / totals.all) * 100 : 0;
                return (
                  <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <span style={{ width: 20, textAlign: 'center' }}>{icon}</span>
                    <span style={{ width: 160, fontSize: '0.875rem', color: 'var(--text-secondary)' }}>{label}</span>
                    <div style={{ flex: 1, background: 'var(--border)', borderRadius: 99, height: 8, overflow: 'hidden' }}>
                      <div style={{
                        width: `${pct}%`, height: '100%', borderRadius: 99,
                        background: 'linear-gradient(90deg, var(--accent-1), var(--accent-2))',
                        minWidth: val > 0 ? 8 : 0, transition: 'width 0.5s ease'
                      }} />
                    </div>
                    <span style={{ fontSize: '0.875rem', fontWeight: 700, minWidth: 32, textAlign: 'right' }}>{val}</span>
                    <span className="text-xs text-muted" style={{ minWidth: 40 }}>{pct.toFixed(0)}%</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Due follow-ups list */}
          {dueFollowUps?.emails?.length > 0 && (
            <div className="card" style={{ marginTop: 20 }}>
              <div className="card-header">
                <span className="card-title">⏰ Overdue Follow-ups ({dueFollowUps.count})</span>
              </div>
              <div className="table-wrapper" style={{ marginTop: 0, border: 'none' }}>
                <table>
                  <thead>
                    <tr>
                      <th>Recipient</th>
                      <th>Company</th>
                      <th>Subject</th>
                      <th>Due Since</th>
                      <th>Follow-up #</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dueFollowUps.emails.map(e => (
                      <tr key={e.email_id}>
                        <td>{e.recipient_name || '—'}</td>
                        <td>{e.company_name || '—'}</td>
                        <td className="text-sm text-secondary">{e.subject?.slice(0, 50) || '—'}</td>
                        <td className="text-xs text-muted">{fmtRelative(e.follow_up_due_at)}</td>
                        <td><span className="badge badge-follow_up_sent">#{(e.follow_up_count ?? 0) + 1}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════════
//  Manual Reply Tracker (for individual emails)
// ════════════════════════════════════════════════════════════
export function ReplyTracker() {
  const toast = useToast();
  const [emailId, setEmailId] = useState('');
  const [snippet, setSnippet] = useState('');
  const [sentiment, setSentiment] = useState('neutral');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const { data: emails } = useApi(() => api.getEmails({ status: 'SENT', limit: 100 }));

  const mark = async (type) => {
    if (!emailId) { toast('Select an email first', 'error'); return; }
    setLoading(true);
    try {
      const r = type === 'replied'
        ? await api.markReplied(emailId, { reply_snippet: snippet, sentiment })
        : await api.markIgnored(emailId, true);
      setResult(r);
      toast(`Email marked as ${type}`, 'success');
    } catch (e) { toast(e.message, 'error'); }
    finally { setLoading(false); }
  };

  return (
    <div style={{ maxWidth: 600 }}>
      <div className="page-header">
        <div>
          <h1 className="page-title">✍️ Manual Reply Log</h1>
          <p className="page-subtitle">Manually log replies or no-replies for sent emails</p>
        </div>
      </div>

      <div className="card">
        <div className="form-group">
          <label className="form-label">Sent Email</label>
          <select className="form-select" value={emailId} onChange={e => setEmailId(e.target.value)}>
            <option value="">-- Select a sent email --</option>
            {emails?.map(e => (
              <option key={e.id} value={e.id}>{e.recipient_name} · {e.company_name} · {e.subject?.slice(0,40)}</option>
            ))}
          </select>
        </div>

        <div className="form-group">
          <label className="form-label">Reply Snippet (for "Replied")</label>
          <textarea className="form-textarea" style={{ minHeight: 80 }}
            placeholder="Paste first few lines of their reply…"
            value={snippet} onChange={e => setSnippet(e.target.value)} />
        </div>

        <div className="form-group">
          <label className="form-label">Sentiment</label>
          <select className="form-select" value={sentiment} onChange={e => setSentiment(e.target.value)}>
            <option value="positive">✅ Positive</option>
            <option value="neutral">😐 Neutral</option>
            <option value="negative">❌ Negative</option>
          </select>
        </div>

        <div className="flex gap-3">
          <button className="btn btn-primary" disabled={loading || !emailId} onClick={() => mark('replied')}>
            {loading ? <Spinner /> : '✅'} Mark as Replied
          </button>
          <button className="btn btn-secondary" disabled={loading || !emailId} onClick={() => mark('ignored')}>
            {loading ? <Spinner /> : '😶'} Mark as Ignored
          </button>
        </div>

        {result && (
          <div style={{ marginTop: 16, padding: '12px 16px', background: 'rgba(16,185,129,0.08)', borderRadius: 'var(--radius-sm)', border: '1px solid rgba(16,185,129,0.2)', fontSize: '0.875rem' }}>
            <div style={{ fontWeight: 600, color: 'var(--accent-1)', marginBottom: 4 }}>✅ Updated successfully</div>
            <div className="text-secondary">
              Status: <StatusBadge status={result.new_status} />
              {result.follow_up_due_at && (
                <span style={{ marginLeft: 12 }}>Follow-up due: {fmtDate(result.follow_up_due_at)}</span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
