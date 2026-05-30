import { useState, useEffect } from 'react';
import api from '../api';
import { useToast, StatusBadge, Spinner, EmptyState, Modal, ConfirmButton, useApi, fmtDate, fmtRelative } from '../components';
import { ScrollArea } from '@/components/ui/scroll-area';
import { BarChart3, PenLine } from 'lucide-react';

// ════════════════════════════════════════════════════════════
//  Tracking Page
// ════════════════════════════════════════════════════════════
export function Tracking() {
  const toast = useToast();
  const [campaignId, setCampaignId] = useState('');
  const [processingFollowUps, setProcessingFollowUps] = useState(false);
  const [showReplies, setShowReplies] = useState(false);
  const [expandedReply, setExpandedReply] = useState(null); // email id
  const [replyContents, setReplyContents] = useState({}); // email.id -> reply history
  const [loadingReply, setLoadingReply] = useState({});
  const [hasAutoPolled, setHasAutoPolled] = useState(false);

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
  
  useEffect(() => {
    if (gmailStatus?.authenticated && !hasAutoPolled) {
      setHasAutoPolled(true);
      pollGmail(true);
    }
  }, [gmailStatus?.authenticated, hasAutoPolled]);

  const { data: repliedEmails, loading: repliesLoading, reload: reloadReplies } = useApi(
    () => api.getEmails({ status: 'REPLIED', campaign_id: campaignId || undefined, limit: 100 }),
    [campaignId]
  );

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
      reloadReplies();
    } catch (e) { toast(e.message, 'error'); }
  };

  const totals = dashboard?.totals || {};
  const metrics = dashboard?.metrics || {};

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden">
      <div className="page-header shrink-0">
        <div>
          <h1 className="page-title"><BarChart3 className="inline-block w-6 h-6 mr-1" style={{ WebkitTextFillColor: 'initial', color: '#818cf8', verticalAlign: '-3px' }} /> Tracking</h1>
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

      <ScrollArea className="flex-1 w-full pr-4">
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

              {/* Clickable Replied card */}
              <div
                className="stat-card"
                onClick={() => setShowReplies(v => !v)}
                style={{
                  cursor: 'pointer',
                  border: showReplies ? '1.5px solid var(--accent-1)' : '1.5px solid transparent',
                  transition: 'border 0.2s, transform 0.15s, box-shadow 0.2s',
                  transform: showReplies ? 'scale(1.03)' : 'scale(1)',
                  boxShadow: showReplies ? '0 0 0 3px rgba(16,185,129,0.15)' : undefined,
                }}
                title="Click to view replied emails"
                onMouseOver={e => { if (!showReplies) e.currentTarget.style.borderColor = 'rgba(16,185,129,0.4)'; }}
                onMouseOut={e => { if (!showReplies) e.currentTarget.style.borderColor = 'transparent'; }}
              >
                <div className="stat-label" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  Replied
                  <span style={{
                    fontSize: '0.6rem', padding: '1px 6px', borderRadius: 99,
                    background: 'rgba(16,185,129,0.15)', color: 'var(--accent-1)', fontWeight: 700, letterSpacing: '0.03em'
                  }}>
                    {showReplies ? '▲ HIDE' : '▼ VIEW'}
                  </span>
                </div>
                <div className="stat-value" style={{ color: (totals.replied ?? 0) > 0 ? 'var(--accent-1)' : undefined }}>
                  {totals.replied ?? 0}
                </div>
                <div className="stat-sub">contacts responded · click to view</div>
              </div>

              <div className="stat-card">
                <div className="stat-label">Ignored</div>
                <div className="stat-value">{totals.ignored ?? 0}</div>
                <div className="stat-sub">no reply yet</div>
              </div>
            </div>

            {/* ── Replied Emails Panel ─────────────────────────────── */}
            {showReplies && (
              <div className="card" style={{ marginBottom: 24, borderColor: 'rgba(16,185,129,0.4)', animation: 'fadeIn 0.2s ease' }}>
                <div className="card-header" style={{ marginBottom: 12 }}>
                  <span className="card-title">💬 Replied Emails ({repliedEmails?.length ?? 0})</span>
                  <button className="btn btn-ghost btn-sm" onClick={() => setShowReplies(false)}>✕ Close</button>
                </div>
                {repliesLoading ? (
                  <div style={{ padding: 32, textAlign: 'center' }}><Spinner /></div>
                ) : !repliedEmails?.length ? (
                  <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
                    <div style={{ fontSize: '2rem', marginBottom: 8 }}>💬</div>
                    No replied emails yet. When someone replies to your outreach, they will appear here.
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    {repliedEmails.map(e => {
                      const camp = campaigns?.find(c => c.id === e.campaign_id);
                      const isExpanded = expandedReply === e.id;
                      const history = replyContents[e.id];
                      const isLoadingThis = loadingReply[e.id];

                      const toggleExpand = async () => {
                        if (isExpanded) { setExpandedReply(null); return; }
                        setExpandedReply(e.id);
                        if (!replyContents[e.id]) {
                          setLoadingReply(p => ({ ...p, [e.id]: true }));
                          try {
                            const r = await api.getReplyHistory(e.target_id);
                            setReplyContents(p => ({ ...p, [e.id]: r.history || [] }));
                          } catch {}
                          finally { setLoadingReply(p => ({ ...p, [e.id]: false })); }
                        }
                      };

                      return (
                        <div key={e.id} style={{
                          border: `1px solid ${isExpanded ? 'rgba(16,185,129,0.5)' : 'var(--border)'}`,
                          borderRadius: 'var(--radius)',
                          overflow: 'hidden',
                          transition: 'border-color 0.2s',
                        }}>
                          {/* Header row — always visible */}
                          <div
                            onClick={toggleExpand}
                            style={{
                              display: 'grid',
                              gridTemplateColumns: '1.5fr 1fr 2fr 1fr auto',
                              gap: 12,
                              padding: '12px 16px',
                              cursor: 'pointer',
                              alignItems: 'center',
                              background: isExpanded ? 'rgba(16,185,129,0.06)' : 'transparent',
                              transition: 'background 0.2s',
                            }}
                            onMouseOver={e2 => { if (!isExpanded) e2.currentTarget.style.background = 'rgba(255,255,255,0.03)'; }}
                            onMouseOut={e2 => { if (!isExpanded) e2.currentTarget.style.background = 'transparent'; }}
                          >
                            <div>
                              <div style={{ fontWeight: 600, fontSize: '0.875rem' }}>{e.recipient_name || '—'}</div>
                              <div className="text-xs text-muted font-mono">{e.recipient_email || ''}</div>
                            </div>
                            <div className="text-sm text-secondary">{e.company_name || '—'}</div>
                            <div className="text-sm" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text-secondary)' }}>
                              {e.subject || '—'}
                            </div>
                            <div className="text-xs text-muted">{fmtDate(e.sent_at)}</div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              <span className="badge badge-replied">✓ Replied</span>
                              <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>{isExpanded ? '▲' : '▼'}</span>
                            </div>
                          </div>

                          {/* Expanded reply content */}
                          {isExpanded && (
                            <div style={{ borderTop: '1px solid var(--border)', padding: '16px 20px', background: 'rgba(0,0,0,0.2)' }}>
                              {isLoadingThis ? (
                                <div style={{ textAlign: 'center', padding: 16 }}><Spinner /></div>
                              ) : (
                                <>
                                  {/* Original email */}
                                  <div style={{ marginBottom: 20 }}>
                                    <div style={{ fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.08em', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 8 }}>📤 Your Original Email</div>
                                    <div style={{
                                      background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border)',
                                      borderRadius: 'var(--radius-sm)', padding: '12px 14px',
                                      fontSize: '0.85rem', lineHeight: 1.7, color: 'var(--text-secondary)',
                                      whiteSpace: 'pre-wrap', maxHeight: 180, overflowY: 'auto',
                                    }}>
                                      {e.body || 'No email body stored.'}
                                    </div>
                                  </div>

                                  {/* Their reply */}
                                  <div style={{ fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.08em', color: 'var(--accent-1)', textTransform: 'uppercase', marginBottom: 8 }}>💬 Their Reply</div>
                                  {(!history || history.length === 0) ? (
                                    <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem', fontStyle: 'italic' }}>
                                      No reply content stored. This email was manually marked as replied — paste their reply using the "Log Reply" tool in the sidebar.
                                    </div>
                                  ) : (
                                    history.map((h, i) => (
                                      <div key={i} style={{
                                        background: 'rgba(16,185,129,0.06)', border: '1px solid rgba(16,185,129,0.25)',
                                        borderRadius: 'var(--radius-sm)', padding: '12px 14px', marginBottom: 10,
                                      }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                                          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Received: {fmtDate(h.reply_received_at)}</span>
                                          {h.sentiment && (
                                            <span style={{
                                              fontSize: '0.7rem', padding: '2px 8px', borderRadius: 99, fontWeight: 600,
                                              background: h.sentiment === 'positive' ? 'rgba(16,185,129,0.2)' : h.sentiment === 'negative' ? 'rgba(239,68,68,0.2)' : 'rgba(156,163,175,0.2)',
                                              color: h.sentiment === 'positive' ? 'var(--accent-1)' : h.sentiment === 'negative' ? '#ef4444' : 'var(--text-muted)',
                                            }}>
                                              {h.sentiment === 'positive' ? '✅ Positive' : h.sentiment === 'negative' ? '❌ Negative' : '😐 Neutral'}
                                            </span>
                                          )}
                                        </div>
                                        <div style={{ fontSize: '0.875rem', lineHeight: 1.7, color: 'var(--text)', whiteSpace: 'pre-wrap' }}>
                                          {h.reply_snippet || 'No reply text recorded.'}
                                        </div>
                                      </div>
                                    ))
                                  )}
                                </>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

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
                <div style={{ position: 'relative', zIndex: 10 }}>
                  {!gmailStatus?.authenticated ? (
                    <button className="btn btn-primary btn-sm" onClick={async () => {
                      try {
                        const r = await api.gmailAuthorize();
                        if (r.url) window.location.href = r.url;
                        else toast(r.message || 'Gmail not configured', 'error');
                      } catch (err) {
                        toast(err.message || 'Failed to connect Gmail', 'error');
                      }
                    }}>🔗 Connect Gmail</button>
                  ) : (
                    <>
                      <button className="btn btn-secondary btn-sm" onClick={pollGmail}>📥 Poll Inbox</button>
                      <button className="btn btn-ghost btn-sm" style={{ color: 'var(--status-ignored)' }} onClick={async () => {
                        try {
                          await api.gmailDisconnect();
                          toast('Gmail disconnected successfully.', 'success');
                          window.location.reload();
                        } catch (err) {
                          toast(err.message || 'Failed to disconnect Gmail', 'error');
                        }
                      }}>🔌 Sign Out</button>
                    </>
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
      </ScrollArea>
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
    <div className="flex-1 flex flex-col h-full overflow-hidden" style={{ maxWidth: 600 }}>
      <div className="page-header shrink-0">
        <div>
          <h1 className="page-title"><PenLine className="inline-block w-6 h-6 mr-1" style={{ WebkitTextFillColor: 'initial', color: '#818cf8', verticalAlign: '-3px' }} /> Manual Reply Log</h1>
          <p className="page-subtitle">Manually log replies or no-replies for sent emails</p>
        </div>
      </div>

      <ScrollArea className="flex-1 w-full pr-4">
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
      </ScrollArea>
    </div>
  );
}
